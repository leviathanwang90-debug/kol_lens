from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from config import milvus_config
from db import db
from milvus import FIELD_STYLE, milvus_mgr
from services.intent_parser import IntentParserService, intent_parser_service, value_to_text

try:  # Redis 基础设施未就绪时允许服务降级到内存缓存
    from redis import search_cache, task_cache
except Exception:  # pragma: no cover - 依赖外部环境时使用降级路径
    search_cache = None
    task_cache = None

logger = logging.getLogger(__name__)

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
ROCCHIO_ALPHA = 1.0
ROCCHIO_BETA = 0.2

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
    tokens = []
    for segment in segments or [normalized]:
        tokens.append(segment)
        if len(segment) <= 8:
            continue
        bigrams = [segment[index:index + 2] for index in range(0, len(segment) - 1)]
        tokens.extend(bigrams[:12])
    return list(dict.fromkeys(tokens))



def embed_text_to_style_vector(text: str, *, dim: int = DEFAULT_VECTOR_DIM) -> List[float]:
    tokens = _tokenize_text(text)
    if not tokens:
        raise ValueError("embedding 输入文本不能为空。")
    vector = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = np.random.default_rng(seed)
        vector += rng.standard_normal(dim).astype(np.float32)
    return _normalize_vector(vector)



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
    """封装自然语言检索向量构建与 Milvus 检索流程。"""

    def __init__(self, parser: Optional[IntentParserService] = None):
        self.parser = parser or intent_parser_service

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
        vector_field = value_to_text(payload.get("vector_field")) or FIELD_STYLE
        top_k = int(payload.get("top_k") or 20)
        scalar_filters = self._merge_scalar_filters(intent.get("hard_filters"), payload.get("scalar_filters"))
        cache_enabled = bool(payload.get("use_cache", True))
        cache_key = {
            "raw_text": raw_text,
            "query_plan": query_plan,
            "scalar_filters": scalar_filters,
            "top_k": top_k,
            "vector_field": vector_field,
            "experiment_mode": experiment_mode,
            "tag_weights": payload.get("tag_weights") or {},
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
                    "results": cached_results,
                    "result_count": len(cached_results),
                    "cached": True,
                }

        milvus_mgr.connect()
        milvus_mgr.load_collection()
        results = milvus_mgr.hybrid_search(
            vector_field=vector_field,
            query_vector=query_context["query_vector"],
            scalar_filters=scalar_filters,
            top_k=top_k,
        )
        enriched_results = self._enrich_results(results)

        if cache_enabled:
            self._set_cached_results(cache_key, enriched_results)

        return {
            "raw_text": raw_text,
            "intent": intent,
            "scalar_filters": scalar_filters,
            "vector_field": vector_field,
            "experiment_mode": experiment_mode,
            "embedding_input_preview": query_context["embedding_input_preview"],
            "tag_weights_used": query_context["tag_weights_used"],
            "results": enriched_results,
            "result_count": len(enriched_results),
            "cached": False,
        }

    def create_campaign(self, user_id: int, spu_id: int) -> int:
        """工作流 1: 新建项目，冷启动加载品牌 SPU 基因向量。"""
        db.connect()
        try:
            base_vector = db.get_brand_spu_base_vector(spu_id)
            if not base_vector:
                raise ValueError(f"SPU[{spu_id}] 缺少 base_vector，请先跑批生成。")
            return db.create_campaign_from_spu(user_id=user_id, spu_id=spu_id, initial_vector=base_vector)
        finally:
            db.close()

    def search_influencers(self, campaign_id: int, filters: Optional[Dict[str, Any]] = None, top_k: int = 100) -> List[Dict[str, Any]]:
        """工作流 2: Qdrant 查 ID + PostgreSQL 回表组装详情。"""
        db.connect()
        try:
            intent_vector = db.get_campaign_intent_vector(campaign_id)
            if not intent_vector:
                raise ValueError(f"campaign_id={campaign_id} 未找到 dynamic_intent_vector。")
            milvus_mgr.connect()
            milvus_mgr.load_collection()
            qdrant_results = milvus_mgr.hybrid_search(
                query_vector=intent_vector,
                scalar_filters=filters or {},
                top_k=top_k,
            )
            matched_ids = [int(hit["id"]) for hit in qdrant_results]
            profiles = db.get_influencer_profiles_by_ids(matched_ids)
            profiles_map = {int(item["internal_id"]): item for item in profiles}
            ranked = []
            for hit in qdrant_results:
                internal_id = int(hit["id"])
                ranked.append(
                    {
                        "internal_id": internal_id,
                        "score": float(hit["score"]),
                        "distance": float(hit["distance"]),
                        "profile": profiles_map.get(internal_id, {}),
                    }
                )
            return ranked
        finally:
            db.close()

    def update_campaign_preference(self, campaign_id: int, liked_id: int, *, alpha: float = ROCCHIO_ALPHA, beta: float = ROCCHIO_BETA) -> List[float]:
        """工作流 3: 用户反馈触发 Rocchio 向量平移。"""
        milvus_mgr.connect()
        records = milvus_mgr.retrieve_by_ids([liked_id], with_vectors=True)
        if not records:
            raise ValueError(f"未找到向量 ID: {liked_id}")
        target_vector = records[0].vector
        if isinstance(target_vector, dict):
            target_vector = target_vector.get("embedding") or target_vector.get(FIELD_STYLE)
        if target_vector is None:
            raise ValueError(f"向量 ID {liked_id} 缺少 embedding 数据")

        db.connect()
        try:
            current_vector = db.get_campaign_intent_vector(campaign_id)
            if not current_vector:
                raise ValueError(f"campaign_id={campaign_id} 未找到 dynamic_intent_vector")
            new_vector = self.calculate_rocchio(current_vector, target_vector, alpha=alpha, beta=beta)
            db.update_campaign_dynamic_vector(campaign_id, new_vector)
            return new_vector
        finally:
            db.close()

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
    def calculate_rocchio(current_vector: Sequence[float], target_vector: Sequence[float], *, alpha: float = ROCCHIO_ALPHA, beta: float = ROCCHIO_BETA) -> List[float]:
        current = np.array(current_vector, dtype=np.float32)
        target = np.array(target_vector, dtype=np.float32)
        if current.shape != target.shape:
            raise ValueError("Rocchio 计算时向量维度不一致")
        updated = alpha * current + beta * target
        return _normalize_vector(updated)

    @staticmethod
    def _merge_scalar_filters(base_filters: Optional[Dict[str, Any]], extra_filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(base_filters or {})
        for key, value in (extra_filters or {}).items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value
        return merged

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
        try:
            db.connect()
            for internal_id in ids:
                row = db.get_influencer_by_id(internal_id)
                if row:
                    profiles[internal_id] = dict(row)
        except Exception as exc:
            logger.warning("补充 PostgreSQL 达人信息失败，将仅返回向量检索结果: %s", exc)
        finally:
            try:
                db.close()
            except Exception:
                pass
        return profiles

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


match_service = MatchService()
