from __future__ import annotations

import copy
import json
import logging
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from config import milvus_config
from services.intent_parser import IntentParserService, intent_parser_service, value_to_text
from services.pgy_service import _embed_text_to_style_vector, pgy_expansion_service

try:  # Redis 基础设施未就绪时允许服务降级到内存缓存
    from redis import search_cache, task_cache
except Exception:  # pragma: no cover - 依赖外部环境时使用降级路径
    search_cache = None
    task_cache = None

logger = logging.getLogger(__name__)

milvus_mgr = None

EXPERIMENT_MODE_LONG_SENTENCE = "long_sentence"
EXPERIMENT_MODE_FIELD_TAGS = "field_tags"
EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED = "field_tags_weighted"
EXPERIMENT_MODE_FIELD_TAGS_EXPLICIT_WEIGHT_TEXT = "field_tags_explicit_weight_text"
EXPERIMENT_MODE_CHOICES = {
    EXPERIMENT_MODE_LONG_SENTENCE,
    EXPERIMENT_MODE_FIELD_TAGS,
    EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED,
    EXPERIMENT_MODE_FIELD_TAGS_EXPLICIT_WEIGHT_TEXT,
}
DEFAULT_VECTOR_DIM = milvus_config.embedding_dim

_LOCAL_TASK_STORE: Dict[str, Dict[str, Any]] = {}
_LOCAL_SEARCH_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _normalize_vector(vector: Sequence[float]) -> List[float]:
    array = np.array(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        raise ValueError("query 向量不能为空或零向量。")
    return (array / norm).astype(np.float32).tolist()



def _tokenize_text(text: str) -> List[str]:
    normalized = value_to_text(text)
    if not normalized:
        return []
    segments = [segment.strip() for segment in re.split(r"[，,；;。\n]+", normalized) if segment and segment.strip()]
    tokens: List[str] = []
    for segment in segments or [normalized]:
        tokens.append(segment)
        if len(segment) <= 8:
            continue
        tokens.extend(segment[index:index + 2] for index in range(0, len(segment) - 1))
    return list(dict.fromkeys(tokens))



def embed_text_to_style_vector(text: str, *, dim: int = DEFAULT_VECTOR_DIM) -> List[float]:
    vector = _embed_text_to_style_vector(text, dim=dim)
    if len(vector) == dim:
        return vector
    if len(vector) > dim:
        return _normalize_vector(vector[:dim])
    return _normalize_vector(list(vector) + [0.0] * (dim - len(vector)))



def _normalize_experiment_mode(mode: str) -> str:
    normalized = value_to_text(mode) or EXPERIMENT_MODE_LONG_SENTENCE
    if normalized not in EXPERIMENT_MODE_CHOICES:
        raise ValueError(f"不支持的 experiment_mode: {normalized}")
    return normalized



def _extract_formatted_tags(query_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in query_plan.get("formatted_tags", query_plan.get("tags", [])):
        tag = value_to_text(item.get("tag"))
        field_name = value_to_text(item.get("field"))
        key = value_to_text(item.get("key")) or (f"{field_name}::{tag}" if field_name else tag)
        if not tag:
            continue
        try:
            default_weight = float(item.get("default_weight", 1.0))
        except (TypeError, ValueError):
            default_weight = 1.0
        results.append(
            {
                "key": key,
                "field": field_name,
                "tag": tag,
                "default_weight": default_weight,
            }
        )
    return results



def _build_explicit_weight_text(tag_entries: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for item in tag_entries:
        prefix = f"{item['field']}:" if item.get("field") else ""
        parts.append(f"{prefix}{item['tag']}({item['weight']})")
    return "，".join(parts)



def _build_preview_lines(tag_entries: Sequence[Dict[str, Any]], *, include_weight: bool) -> str:
    lines = []
    for item in tag_entries:
        prefix = f"{item['field']}:" if item.get("field") else ""
        if include_weight:
            lines.append(f"{prefix}{item['tag']}({item['weight']})")
        else:
            lines.append(f"{prefix}{item['tag']}")
    return "\n".join(lines)


class MatchService:
    """封装自然语言检索、外部扩库与贪心降级流程。"""

    def __init__(self, parser: Optional[IntentParserService] = None):
        self.parser = parser or intent_parser_service

    def create_campaign(self, user_id: int, spu_id: int) -> int:
        db_client = _safe_get_db_client()
        if db_client is None:
            raise RuntimeError("db client unavailable")
        db_client.connect()
        try:
            spu_record = db_client.get_brand_spu_record(spu_id)
            if not spu_record:
                raise ValueError(f"spu_id not found: {spu_id}")
            initial_vector = spu_record.get("base_vector") or [0.0] * DEFAULT_VECTOR_DIM
            return db_client.create_campaign_from_spu(user_id, spu_id, initial_vector)
        finally:
            db_client.close()

    def search_influencers(self, campaign_id: int, filters: Dict[str, Any], top_k: int = 100) -> List[Dict[str, Any]]:
        db_client = _safe_get_db_client()
        manager = milvus_mgr or _safe_get_milvus_manager()
        if db_client is None or manager is None:
            return []
        db_client.connect()
        try:
            vector = db_client.get_campaign_intent_vector(campaign_id) or [0.0] * DEFAULT_VECTOR_DIM
            manager.connect()
            manager.load_collection()
            results = manager.hybrid_search(
                vector_field="embedding",
                query_vector=vector,
                scalar_filters=filters or {},
                top_k=top_k,
            )
            ids = [int(item["id"]) for item in results]
            profile_rows = db_client.get_influencer_profiles_by_ids(ids)
            profile_map = {int(row["internal_id"]): row for row in profile_rows}
            ordered = []
            for item in results:
                internal_id = int(item["id"])
                ordered.append(
                    {
                        "internal_id": internal_id,
                        "score": float(item.get("score", 0.0)),
                        "distance": float(item.get("distance", 0.0)),
                        "profile": profile_map.get(internal_id, {}),
                    }
                )
            return ordered
        finally:
            db_client.close()

    def update_campaign_preference(self, campaign_id: int, liked_id: int, alpha: float = 1.0, beta: float = 0.2) -> List[float]:
        db_client = _safe_get_db_client()
        manager = milvus_mgr or _safe_get_milvus_manager()
        if db_client is None or manager is None:
            raise RuntimeError("required dependency unavailable")
        db_client.connect()
        try:
            current = db_client.get_campaign_intent_vector(campaign_id) or [0.0] * DEFAULT_VECTOR_DIM
            manager.connect()
            vectors = manager.retrieve_by_ids([liked_id])
            if not vectors:
                raise ValueError(f"liked influencer not found: {liked_id}")
            target = vectors[0].get("embedding") or []
            if len(current) != len(target):
                max_dim = max(len(current), len(target), DEFAULT_VECTOR_DIM)
                current = list(current) + [0.0] * (max_dim - len(current))
                target = list(target) + [0.0] * (max_dim - len(target))
            shifted = (alpha * np.array(current, dtype=np.float32) + beta * np.array(target, dtype=np.float32)).tolist()
            try:
                new_vector = _normalize_vector(shifted)
            except ValueError:
                new_vector = _normalize_vector(target)
            db_client.update_campaign_dynamic_vector(campaign_id, new_vector)
            return new_vector
        finally:
            db_client.close()

    def build_query_context(
        self,
        query_plan: Dict[str, Any],
        *,
        experiment_mode: str,
        tag_weights: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        mode = _normalize_experiment_mode(experiment_mode)
        long_sentence_query = value_to_text(query_plan.get("long_sentence_query"))
        formatted_query_text = value_to_text(query_plan.get("formatted_query_text"))
        formatted_tags = _extract_formatted_tags(query_plan)
        normalized_weights = self._normalize_tag_weights(tag_weights)

        if mode == EXPERIMENT_MODE_LONG_SENTENCE:
            return {
                "experiment_mode": mode,
                "query_vector": embed_text_to_style_vector(long_sentence_query),
                "embedding_input_preview": long_sentence_query,
                "formatted_tags_used": [],
                "tag_weights_used": {},
                "long_sentence_query": long_sentence_query,
                "formatted_query_text": formatted_query_text,
            }

        if mode == EXPERIMENT_MODE_FIELD_TAGS_EXPLICIT_WEIGHT_TEXT:
            weighted_tags = self._resolve_weighted_tags(formatted_tags, normalized_weights)
            if not weighted_tags:
                return {
                    "experiment_mode": mode,
                    "query_vector": embed_text_to_style_vector(long_sentence_query),
                    "embedding_input_preview": long_sentence_query,
                    "formatted_tags_used": [],
                    "tag_weights_used": {},
                    "long_sentence_query": long_sentence_query,
                    "formatted_query_text": formatted_query_text,
                }
            explicit_weight_text = _build_explicit_weight_text(weighted_tags)
            return {
                "experiment_mode": mode,
                "query_vector": embed_text_to_style_vector(explicit_weight_text),
                "embedding_input_preview": explicit_weight_text,
                "formatted_tags_used": weighted_tags,
                "tag_weights_used": {item["key"]: item["weight"] for item in weighted_tags},
                "long_sentence_query": long_sentence_query,
                "formatted_query_text": formatted_query_text,
            }

        weighted_vectors = []
        weighted_tags = []
        for item in formatted_tags:
            weight = 1.0
            if mode == EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED:
                weight = normalized_weights.get(item["key"], normalized_weights.get(item["tag"], item["default_weight"]))
            if weight <= 0:
                continue
            tag_vector = np.array(embed_text_to_style_vector(item["tag"]), dtype=np.float32)
            weighted_vectors.append(tag_vector * float(weight))
            weighted_tags.append(
                {
                    "key": item["key"],
                    "field": item["field"],
                    "tag": item["tag"],
                    "weight": float(weight),
                }
            )

        if not weighted_vectors:
            return {
                "experiment_mode": mode,
                "query_vector": embed_text_to_style_vector(long_sentence_query),
                "embedding_input_preview": long_sentence_query,
                "formatted_tags_used": [],
                "tag_weights_used": {},
                "long_sentence_query": long_sentence_query,
                "formatted_query_text": formatted_query_text,
            }

        combined_vector = np.sum(np.array(weighted_vectors, dtype=np.float32), axis=0)
        return {
            "experiment_mode": mode,
            "query_vector": _normalize_vector(combined_vector),
            "embedding_input_preview": _build_preview_lines(
                weighted_tags,
                include_weight=mode == EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED,
            ),
            "formatted_tags_used": weighted_tags,
            "tag_weights_used": {item["key"]: item["weight"] for item in weighted_tags},
            "long_sentence_query": long_sentence_query,
            "formatted_query_text": formatted_query_text,
        }

    def retrieve(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_text = value_to_text(payload.get("raw_text") or payload.get("query"))
        intent = payload.get("intent")
        if not isinstance(intent, dict):
            intent = self.parser.parse(
                raw_text,
                brand_name=value_to_text(payload.get("brand_name")),
                spu_name=value_to_text(payload.get("spu_name")),
            )
        query_plan = intent.get("query_plan", {})
        experiment_mode = _normalize_experiment_mode(value_to_text(payload.get("experiment_mode")))
        query_context = self.build_query_context(
            query_plan,
            experiment_mode=experiment_mode,
            tag_weights=payload.get("tag_weights"),
        )
        campaign_id = payload.get("campaign_id")
        fusion_alpha = float(payload.get("fusion_alpha", 0.7) or 0.7)
        fusion_beta = float(payload.get("fusion_beta", 0.3) or 0.3)
        fusion_applied = False
        if campaign_id is not None:
            query_context["query_vector"], fusion_applied = self._fuse_campaign_and_text_vector(
                campaign_id=int(campaign_id),
                text_vector=query_context["query_vector"],
                alpha=fusion_alpha,
                beta=fusion_beta,
            )
        override_vector = payload.get("query_vector_override")
        override_meta = payload.get("query_vector_meta") if isinstance(payload.get("query_vector_meta"), dict) else {}
        if isinstance(override_vector, list) and override_vector:
            query_context = dict(query_context)
            query_context["query_vector"] = _normalize_vector(override_vector)
            query_context["query_vector_meta"] = override_meta
            query_context["embedding_input_preview"] = override_meta.get("message") or query_context["embedding_input_preview"]
        vector_field = value_to_text(payload.get("vector_field")) or "v_overall_style"
        requested_count = int(
            payload.get("top_k")
            or (intent.get("data_requirements") or {}).get("requiredCount")
            or 20
        )
        scalar_filters = self._merge_scalar_filters(intent.get("hard_filters"), payload.get("scalar_filters"))
        data_requirements = dict(intent.get("data_requirements") or {})
        cache_enabled = bool(payload.get("use_cache", True))
        enable_external_expansion = bool(payload.get("enable_external_expansion", False))
        enable_greedy_degrade = bool(payload.get("enable_greedy_degrade", False))
        cache_key = {
            "raw_text": raw_text,
            "query_plan": query_plan,
            "scalar_filters": scalar_filters,
            "data_requirements": data_requirements,
            "top_k": requested_count,
            "vector_field": vector_field,
            "experiment_mode": experiment_mode,
            "tag_weights": payload.get("tag_weights") or {},
            "query_vector_override": query_context.get("query_vector_meta") or {},
            "enable_external_expansion": enable_external_expansion,
            "enable_greedy_degrade": enable_greedy_degrade,
        }

        if cache_enabled:
            cached_results = self._get_cached_results(cache_key)
            if cached_results is not None:
                return {
                    "raw_text": raw_text,
                    "intent": intent,
                    "scalar_filters": scalar_filters,
                    "vector_field": vector_field,
                    "experiment_mode": experiment_mode,
                    "embedding_input_preview": query_context["embedding_input_preview"],
                    "tag_weights_used": query_context["tag_weights_used"],
                    "query_vector_meta": query_context.get("query_vector_meta") or {},
                    "campaign_fusion": {
                        "campaign_id": campaign_id,
                        "applied": fusion_applied,
                        "alpha": fusion_alpha,
                        "beta": fusion_beta,
                    },
                    "results": cached_results,
                    "result_count": len(cached_results),
                    "desired_count": requested_count,
                    "cached": True,
                    "expansion": {"attempted": False, "message": "命中缓存，跳过扩库。"},
                    "degradation": {"attempted": False, "logs": []},
                }

        logs: List[str] = []
        self._append_log(logs, f"开始库内检索，目标返回 {requested_count} 位达人。")
        initial_results = self._retrieve_local(
            query_vector=query_context["query_vector"],
            vector_field=vector_field,
            scalar_filters=scalar_filters,
            data_requirements=data_requirements,
            requested_count=requested_count,
            exclude_ids=payload.get("exclude_ids") or [],
        )
        self._append_log(logs, f"库内检索返回 {len(initial_results)} 位达人。")
        final_results = list(initial_results)
        expansion_result: Dict[str, Any] = {"attempted": False, "message": "未触发扩库。"}
        degradation_result: Dict[str, Any] = {"attempted": False, "logs": []}

        if len(final_results) < requested_count and enable_external_expansion:
            needed_count = requested_count - len(final_results)
            self._append_log(logs, f"库内结果不足，触发蒲公英扩库，缺口 {needed_count} 位。")
            expansion_result = pgy_expansion_service.expand_library(
                data_requirements=data_requirements,
                query_plan=query_plan,
                needed_count=needed_count,
                brand_name=value_to_text(intent.get("brand_name") or payload.get("brand_name")),
                page_size=int(payload.get("external_page_size") or max(needed_count, 20)),
            )
            self._append_log(logs, expansion_result.get("message") or "扩库流程执行完成。")
            if expansion_result.get("attempted"):
                final_results = self._retrieve_local(
                    query_vector=query_context["query_vector"],
                    vector_field=vector_field,
                    scalar_filters=scalar_filters,
                    data_requirements=data_requirements,
                    requested_count=requested_count,
                    exclude_ids=payload.get("exclude_ids") or [],
                )
                self._append_log(logs, f"扩库后二次库内检索返回 {len(final_results)} 位达人。")

        if len(final_results) < requested_count and enable_greedy_degrade:
            self._append_log(logs, "结果仍不足，开始执行贪心降级。")
            degradation_result = self._greedy_relax_and_retrieve(
                query_vector=query_context["query_vector"],
                vector_field=vector_field,
                scalar_filters=scalar_filters,
                data_requirements=data_requirements,
                elastic_weights=dict(intent.get("elastic_weights") or {}),
                requested_count=requested_count,
                exclude_ids=payload.get("exclude_ids") or [],
            )
            final_results = degradation_result.get("results") or final_results
            for line in degradation_result.get("logs") or []:
                self._append_log(logs, line)

        if cache_enabled:
            self._set_cached_results(cache_key, final_results)

        return {
            "raw_text": raw_text,
            "intent": intent,
            "scalar_filters": scalar_filters,
            "vector_field": vector_field,
            "experiment_mode": experiment_mode,
            "embedding_input_preview": query_context["embedding_input_preview"],
            "tag_weights_used": query_context["tag_weights_used"],
            "query_vector_meta": query_context.get("query_vector_meta") or {},
            "campaign_fusion": {
                "campaign_id": campaign_id,
                "applied": fusion_applied,
                "alpha": fusion_alpha,
                "beta": fusion_beta,
            },
            "results": final_results,
            "result_count": len(final_results),
            "desired_count": requested_count,
            "cached": False,
            "expansion": expansion_result,
            "degradation": {
                "attempted": bool(degradation_result.get("attempted")),
                "logs": degradation_result.get("logs") or [],
            },
            "logs": logs,
        }

    def submit_retrieve_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = value_to_text(payload.get("task_id")) or uuid.uuid4().hex
        meta = {
            "raw_text": value_to_text(payload.get("raw_text") or payload.get("query")),
            "experiment_mode": value_to_text(payload.get("experiment_mode")) or EXPERIMENT_MODE_LONG_SENTENCE,
        }
        self._create_task(task_id, meta)
        self._update_task_status(task_id, "running", 0.2, "开始解析意图并执行检索")
        try:
            result = self.retrieve(payload)
            self._set_task_result(task_id, result)
            return {
                "task_id": task_id,
                "status": "done",
                "result": result,
            }
        except Exception as exc:
            self._set_task_error(task_id, str(exc))
            raise

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        local_info = _LOCAL_TASK_STORE.get(task_id)
        if task_cache is None:
            return local_info
        try:
            cached = task_cache.get_task_info(task_id)
            return cached or local_info
        except Exception:
            return local_info

    @staticmethod
    def _normalize_tag_weights(tag_weights: Optional[Dict[str, Any]]) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for key, value in (tag_weights or {}).items():
            try:
                weight = float(value)
            except (TypeError, ValueError):
                continue
            if weight <= 0:
                continue
            normalized[value_to_text(key)] = weight
        return normalized

    def _resolve_weighted_tags(
        self,
        formatted_tags: Sequence[Dict[str, Any]],
        normalized_weights: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for item in formatted_tags:
            weight = normalized_weights.get(item["key"], normalized_weights.get(item["tag"], item["default_weight"]))
            if weight <= 0:
                continue
            results.append(
                {
                    "key": item["key"],
                    "field": item["field"],
                    "tag": item["tag"],
                    "weight": float(weight),
                }
            )
        return results

    @staticmethod
    def _merge_scalar_filters(base_filters: Optional[Dict[str, Any]], extra_filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(base_filters or {})
        for key, value in (extra_filters or {}).items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value
        return merged

    def _retrieve_local(
        self,
        *,
        query_vector: Sequence[float],
        vector_field: str,
        scalar_filters: Dict[str, Any],
        data_requirements: Dict[str, Any],
        requested_count: int,
        exclude_ids: Sequence[int],
    ) -> List[Dict[str, Any]]:
        working_filters = dict(scalar_filters or {})
        if exclude_ids:
            working_filters["id_not_in"] = list(dict.fromkeys(int(item) for item in exclude_ids))
        candidate_top_k = max(int(requested_count) * 5, int(requested_count), 20)
        results = self._retrieve_from_milvus(
            query_vector=list(query_vector),
            vector_field=vector_field,
            scalar_filters=working_filters,
            top_k=candidate_top_k,
        )
        if not results:
            results = self._retrieve_from_db_only(
                scalar_filters=working_filters,
                query_vector=list(query_vector),
                requested_count=candidate_top_k,
            )
        filtered = self._apply_business_filters(results, data_requirements)
        return filtered[:requested_count]

    def _fuse_campaign_and_text_vector(
        self,
        *,
        campaign_id: int,
        text_vector: Sequence[float],
        alpha: float,
        beta: float,
    ) -> Tuple[List[float], bool]:
        db_client = _safe_get_db_client()
        if db_client is None:
            return list(text_vector), False
        try:
            db_client.connect()
            campaign_vector = db_client.get_campaign_intent_vector(campaign_id)
        except Exception:
            return list(text_vector), False
        finally:
            try:
                db_client.close()
            except Exception:
                pass
        if not campaign_vector:
            return list(text_vector), False
        max_dim = max(len(campaign_vector), len(text_vector), DEFAULT_VECTOR_DIM)
        v_campaign = np.array(list(campaign_vector) + [0.0] * (max_dim - len(campaign_vector)), dtype=np.float32)
        v_text = np.array(list(text_vector) + [0.0] * (max_dim - len(text_vector)), dtype=np.float32)
        fused = (alpha * v_campaign) + (beta * v_text)
        return _normalize_vector(fused.tolist()), True

    def _retrieve_from_milvus(
        self,
        *,
        query_vector: List[float],
        vector_field: str,
        scalar_filters: Dict[str, Any],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        manager = milvus_mgr or _safe_get_milvus_manager()
        if manager is None:
            return []
        try:
            manager.connect()
            manager.load_collection()
            results = manager.hybrid_search(
                vector_field=vector_field,
                query_vector=query_vector,
                scalar_filters=scalar_filters,
                top_k=top_k,
            )
            return self._enrich_results(results)
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("Milvus 检索失败，回退到 PostgreSQL 方案: %s", exc)
            return []

    def _retrieve_from_db_only(
        self,
        *,
        scalar_filters: Dict[str, Any],
        query_vector: List[float],
        requested_count: int,
    ) -> List[Dict[str, Any]]:
        db_client = _safe_get_db_client()
        if db_client is None:
            return []
        try:
            db_client.connect()
            region_filters = scalar_filters.get("region") or []
            rows, _ = db_client.search_influencers(
                region=region_filters[0] if isinstance(region_filters, list) and len(region_filters) == 1 else None,
                followers_min=scalar_filters.get("followers_min"),
                followers_max=scalar_filters.get("followers_max"),
                gender=scalar_filters.get("gender"),
                limit=requested_count,
            )
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("PostgreSQL 搜索回退失败: %s", exc)
            return []
        finally:
            try:
                db_client.close()
            except Exception:
                pass

        scored: List[Tuple[float, Dict[str, Any]]] = []
        query_arr = np.array(query_vector, dtype=np.float32)
        for row in rows:
            profile = dict(row)
            text = self._profile_to_text(profile)
            profile_vector = np.array(embed_text_to_style_vector(text), dtype=np.float32)
            score = float(np.dot(query_arr, profile_vector))
            scored.append(
                (
                    score,
                    {
                        "internal_id": int(profile["internal_id"]),
                        "score": score,
                        "distance": 1.0 - score,
                        "region": profile.get("region"),
                        "gender": profile.get("gender"),
                        "followers": profile.get("followers"),
                        "ad_ratio": profile.get("ad_ratio_30d") or 0.0,
                        "profile": profile,
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]

    def _apply_business_filters(self, results: Sequence[Dict[str, Any]], data_requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not data_requirements:
            return list(results)
        filtered: List[Dict[str, Any]] = []
        for item in results:
            if self._matches_data_requirements(item, data_requirements):
                filtered.append(item)
        return filtered

    def _matches_data_requirements(self, item: Dict[str, Any], data_requirements: Dict[str, Any]) -> bool:
        profile = dict(item.get("profile") or {})
        pricing = dict(profile.get("pricing") or {})
        fans_range = data_requirements.get("fansNumRange")
        if fans_range and not self._value_in_range(item.get("followers") or profile.get("followers"), fans_range):
            return False
        if data_requirements.get("picturePriceRange") and not self._value_in_range(
            pricing.get("picture_price") or pricing.get("note_price") or pricing.get("notePrice"),
            data_requirements.get("picturePriceRange"),
        ):
            return False
        if data_requirements.get("videoPriceRange") and not self._value_in_range(
            pricing.get("video_price") or pricing.get("videoPrice"),
            data_requirements.get("videoPriceRange"),
        ):
            return False
        if data_requirements.get("coopPriceRange"):
            picture_match = self._value_in_range(
                pricing.get("picture_price") or pricing.get("note_price") or pricing.get("notePrice"),
                data_requirements.get("coopPriceRange"),
            )
            video_match = self._value_in_range(
                pricing.get("video_price") or pricing.get("videoPrice"),
                data_requirements.get("coopPriceRange"),
            )
            if data_requirements.get("requireBothPriceModes"):
                if not picture_match or not video_match:
                    return False
            elif not picture_match and not video_match:
                return False
        if data_requirements.get("estimatePictureCpmRange") and not self._value_in_range(
            pricing.get("estimate_picture_cpm") or pricing.get("estimatePictureCpm"),
            data_requirements.get("estimatePictureCpmRange"),
        ):
            return False
        if data_requirements.get("estimateVideoCpmRange") and not self._value_in_range(
            pricing.get("estimate_video_cpm") or pricing.get("estimateVideoCpm"),
            data_requirements.get("estimateVideoCpmRange"),
        ):
            return False
        if data_requirements.get("cpmRange"):
            picture_match = self._value_in_range(
                pricing.get("estimate_picture_cpm") or pricing.get("estimatePictureCpm"),
                data_requirements.get("cpmRange"),
            )
            video_match = self._value_in_range(
                pricing.get("estimate_video_cpm") or pricing.get("estimateVideoCpm"),
                data_requirements.get("cpmRange"),
            )
            if data_requirements.get("requireBothCpmModes"):
                if not picture_match or not video_match:
                    return False
            elif not picture_match and not video_match:
                return False
        return True

    @staticmethod
    def _value_in_range(value: Any, value_range: Optional[Sequence[Optional[int]]]) -> bool:
        if not value_range:
            return True
        if value in (None, ""):
            return False
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        lower = value_range[0] if len(value_range) >= 1 else None
        upper = value_range[1] if len(value_range) >= 2 else None
        if lower is not None and numeric < float(lower):
            return False
        if upper is not None and numeric > float(upper):
            return False
        return True

    def _greedy_relax_and_retrieve(
        self,
        *,
        query_vector: Sequence[float],
        vector_field: str,
        scalar_filters: Dict[str, Any],
        data_requirements: Dict[str, Any],
        elastic_weights: Dict[str, Any],
        requested_count: int,
        exclude_ids: Sequence[int],
    ) -> Dict[str, Any]:
        logs: List[str] = []
        current_filters = copy.deepcopy(scalar_filters)
        current_data_requirements = copy.deepcopy(data_requirements)
        current_results = self._retrieve_local(
            query_vector=query_vector,
            vector_field=vector_field,
            scalar_filters=current_filters,
            data_requirements=current_data_requirements,
            requested_count=requested_count,
            exclude_ids=exclude_ids,
        )
        ranked_actions = self._build_degradation_actions(current_filters, current_data_requirements, elastic_weights)
        for action in ranked_actions:
            action_key = action["key"]
            before_count = len(current_results)
            current_filters, current_data_requirements, action_description = self._relax_constraints(
                current_filters,
                current_data_requirements,
                action_key,
            )
            logs.append(action_description)
            current_results = self._retrieve_local(
                query_vector=query_vector,
                vector_field=vector_field,
                scalar_filters=current_filters,
                data_requirements=current_data_requirements,
                requested_count=requested_count,
                exclude_ids=exclude_ids,
            )
            logs.append(f"降级后结果数 {len(current_results)}（之前 {before_count}）。")
            if len(current_results) >= requested_count:
                logs.append("已达到目标数量，停止降级。")
                break
        return {
            "attempted": bool(ranked_actions),
            "logs": logs,
            "results": current_results,
            "effective_scalar_filters": current_filters,
            "effective_data_requirements": current_data_requirements,
        }

    @staticmethod
    def _build_degradation_actions(
        scalar_filters: Dict[str, Any],
        data_requirements: Dict[str, Any],
        elastic_weights: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidate_keys: List[str] = []
        for key in [*scalar_filters.keys(), *data_requirements.keys()]:
            if key in {"requiredCount", "requireBothPriceModes", "requireBothCpmModes"}:
                continue
            value = scalar_filters.get(key) if key in scalar_filters else data_requirements.get(key)
            if value in (None, False, [], {}):
                continue
            candidate_keys.append(key)
        deduped = list(dict.fromkeys(candidate_keys))
        ranked = sorted(
            deduped,
            key=lambda key: (
                int(elastic_weights.get(key, 99)),
                key,
            ),
        )
        return [{"key": key, "weight": int(elastic_weights.get(key, 99))} for key in ranked]

    def _relax_constraints(
        self,
        scalar_filters: Dict[str, Any],
        data_requirements: Dict[str, Any],
        action_key: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        new_filters = copy.deepcopy(scalar_filters)
        new_requirements = copy.deepcopy(data_requirements)
        if action_key == "region":
            new_filters.pop("region", None)
            return new_filters, new_requirements, "放宽地区限制。"
        if action_key == "gender":
            new_filters.pop("gender", None)
            return new_filters, new_requirements, "放宽性别限制。"
        if action_key == "followers_min":
            if new_filters.get("followers_min") is not None:
                new_filters["followers_min"] = int(math.floor(float(new_filters["followers_min"]) * 0.7))
            if new_requirements.get("fansNumRange") and new_requirements["fansNumRange"][0] is not None:
                new_requirements["fansNumRange"][0] = int(math.floor(float(new_requirements["fansNumRange"][0]) * 0.7))
            return new_filters, new_requirements, "下调粉丝下限到 70%。"
        if action_key == "followers_max":
            if new_filters.get("followers_max") is not None:
                new_filters["followers_max"] = int(math.ceil(float(new_filters["followers_max"]) * 1.3))
            if new_requirements.get("fansNumRange") and new_requirements["fansNumRange"][1] is not None:
                new_requirements["fansNumRange"][1] = int(math.ceil(float(new_requirements["fansNumRange"][1]) * 1.3))
            return new_filters, new_requirements, "上调粉丝上限到 130%。"
        if action_key == "ad_ratio_max":
            current = float(new_filters.get("ad_ratio_max") or 0.0)
            new_filters["ad_ratio_max"] = min(round(current * 1.3, 4), 1.0)
            return new_filters, new_requirements, "放宽商业比例上限。"
        if action_key in new_requirements:
            original = new_requirements.get(action_key)
            relaxed = self._expand_range(original)
            new_requirements[action_key] = relaxed
            if action_key == "picturePriceRange":
                return new_filters, new_requirements, "放宽图文报价范围。"
            if action_key == "videoPriceRange":
                return new_filters, new_requirements, "放宽视频报价范围。"
            if action_key == "coopPriceRange":
                return new_filters, new_requirements, "放宽合作报价范围。"
            if action_key == "estimatePictureCpmRange":
                return new_filters, new_requirements, "放宽图文 CPM 范围。"
            if action_key == "estimateVideoCpmRange":
                return new_filters, new_requirements, "放宽视频 CPM 范围。"
            if action_key == "cpmRange":
                return new_filters, new_requirements, "放宽统一 CPM 范围。"
        return new_filters, new_requirements, f"跳过未知降级键 {action_key}。"

    @staticmethod
    def _expand_range(value_range: Optional[Sequence[Optional[int]]]) -> Optional[List[Optional[int]]]:
        if not value_range:
            return value_range if value_range is None else list(value_range)
        lower = value_range[0] if len(value_range) >= 1 else None
        upper = value_range[1] if len(value_range) >= 2 else None
        if lower is not None:
            lower = int(math.floor(float(lower) * 0.7))
        if upper is not None:
            upper = int(math.ceil(float(upper) * 1.3))
        return [lower, upper]

    def _enrich_results(self, milvus_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        profiles = self._fetch_profiles_by_ids([int(item["id"]) for item in milvus_results])
        output = []
        for item in milvus_results:
            internal_id = int(item["id"])
            profile = profiles.get(internal_id, {})
            output.append(
                {
                    "internal_id": internal_id,
                    "score": float(item.get("score", 0.0)),
                    "distance": float(item.get("distance", 0.0)),
                    "region": item.get("region"),
                    "gender": item.get("gender"),
                    "followers": item.get("followers"),
                    "ad_ratio": item.get("ad_ratio"),
                    "profile": profile,
                }
            )
        return output

    @staticmethod
    def _fetch_profiles_by_ids(ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
        profiles: Dict[int, Dict[str, Any]] = {}
        if not ids:
            return profiles
        db_client = _safe_get_db_client()
        if db_client is None:
            return profiles
        try:
            db_client.connect()
            for internal_id in ids:
                row = db_client.get_influencer_by_id(internal_id)
                if row:
                    profiles[internal_id] = dict(row)
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("补充 PostgreSQL 达人信息失败，将仅返回向量检索结果: %s", exc)
        finally:
            try:
                db_client.close()
            except Exception:
                pass
        return profiles

    @staticmethod
    def _profile_to_text(profile: Dict[str, Any]) -> str:
        tags = profile.get("tags") or []
        pricing = profile.get("pricing") or {}
        parts = [
            value_to_text(profile.get("nickname")),
            value_to_text(profile.get("region")),
            value_to_text(profile.get("gender")),
            "、".join([value_to_text(item) for item in tags if value_to_text(item)]),
            f"图文报价:{pricing.get('picture_price') or pricing.get('notePrice') or ''}",
            f"视频报价:{pricing.get('video_price') or pricing.get('videoPrice') or ''}",
        ]
        return "，".join([part for part in parts if value_to_text(part)])

    def _get_cached_results(self, cache_key: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        local_key = json.dumps(cache_key, ensure_ascii=False, sort_keys=True)
        if local_key in _LOCAL_SEARCH_CACHE:
            return _LOCAL_SEARCH_CACHE[local_key]
        if search_cache is None:
            return None
        try:
            return search_cache.get(cache_key)
        except Exception:
            return None

    def _set_cached_results(self, cache_key: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
        local_key = json.dumps(cache_key, ensure_ascii=False, sort_keys=True)
        _LOCAL_SEARCH_CACHE[local_key] = results
        if search_cache is None:
            return
        try:
            search_cache.set(cache_key, results)
        except Exception:
            pass

    def _create_task(self, task_id: str, meta: Dict[str, Any]) -> None:
        _LOCAL_TASK_STORE[task_id] = {
            "status": "pending",
            "progress": 0.0,
            "meta": meta,
            "logs": [],
            "result": None,
        }
        if task_cache is None:
            return
        try:
            task_cache.create_task(task_id, meta)
        except Exception:
            pass

    def _update_task_status(self, task_id: str, status: str, progress: float, message: str) -> None:
        _LOCAL_TASK_STORE.setdefault(task_id, {"logs": [], "meta": {}, "result": None}).update(
            {
                "status": status,
                "progress": progress,
                "message": message,
            }
        )
        if task_cache is None:
            return
        try:
            task_cache.update_status(task_id, status, progress, message)
        except Exception:
            pass

    def _set_task_result(self, task_id: str, result: Dict[str, Any]) -> None:
        _LOCAL_TASK_STORE.setdefault(task_id, {"logs": [], "meta": {}}).update(
            {
                "status": "done",
                "progress": 1.0,
                "result": result,
            }
        )
        if task_cache is None:
            return
        try:
            task_cache.set_result(task_id, result)
        except Exception:
            pass

    def _set_task_error(self, task_id: str, error_message: str) -> None:
        _LOCAL_TASK_STORE.setdefault(task_id, {"logs": [], "meta": {}, "result": None}).update(
            {
                "status": "failed",
                "progress": 1.0,
                "message": error_message,
            }
        )
        if task_cache is None:
            return
        try:
            task_cache.set_error(task_id, error_message)
        except Exception:
            pass

    @staticmethod
    def _append_log(logs: List[str], message: str) -> None:
        if value_to_text(message):
            logs.append(value_to_text(message))



def _safe_get_db_client():
    try:
        from db import db

        return db
    except Exception:
        return None



def _safe_get_milvus_manager():
    try:
        from milvus import milvus_mgr

        return milvus_mgr
    except Exception:
        return None


if milvus_mgr is None:
    milvus_mgr = _safe_get_milvus_manager()

match_service = MatchService()
