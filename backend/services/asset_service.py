from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - 依赖外部数据库环境时允许导入降级
    from db import db
except Exception:  # pragma: no cover
    db = None

logger = logging.getLogger(__name__)

DEFAULT_STYLE_DIM = 768
DEFAULT_ROCCHIO_ALPHA = 1.0
DEFAULT_ROCCHIO_BETA = 0.65
DEFAULT_ROCCHIO_GAMMA = 0.30
DEFAULT_CURRENT_FEEDBACK_FACTOR = 1.0
DEFAULT_HISTORY_FEEDBACK_DECAY = 0.55
DEFAULT_SPU_HISTORY_DECAY = 0.85
DEFAULT_USER_HISTORY_DECAY = 1.0
DEFAULT_FEEDBACK_TAG_STEP = 0.32
DEFAULT_MAX_TAG_DELTA = 0.45
DEFAULT_HISTORY_LIMIT = 6
DEFAULT_ROLE_TIME_DECAY_DAYS = 21.0
DEFAULT_ROLE_TIME_DECAY_MIN_FACTOR = 0.35
DEFAULT_ROLE_DECAY_PROFILE = {
    1: {"decay_days": 18.0, "min_factor": 0.40},
    2: {"decay_days": 24.0, "min_factor": 0.35},
    3: {"decay_days": 32.0, "min_factor": 0.45},
}
DEFAULT_BRAND_STAGE_MATCH_FACTOR = 1.0
DEFAULT_BRAND_STAGE_MISMATCH_FACTOR = 0.72
DEFAULT_CAMPAIGN_FRESHNESS_DECAY_DAYS = 14.0
DEFAULT_CAMPAIGN_FRESHNESS_MIN_FACTOR = 0.60

ROLE_NAME_TO_CODE = {
    "采购": 1,
    "buyer": 1,
    "procurement": 1,
    "策划": 2,
    "planner": 2,
    "strategy": 2,
    "客户": 3,
    "client": 3,
    "customer": 3,
}

ROLE_CODE_TO_NAME = {
    1: "采购",
    2: "策划",
    3: "客户",
}

ROLE_FEEDBACK_WEIGHT = {
    1: 0.8,
    2: 1.0,
    3: 1.3,
}



def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))



def _normalize_vector(vector: Sequence[float], *, dim: int = DEFAULT_STYLE_DIM) -> List[float]:
    array = np.array(list(vector), dtype=np.float32)
    if array.size < dim:
        array = np.concatenate([array, np.zeros(dim - array.size, dtype=np.float32)])
    elif array.size > dim:
        array = array[:dim]
    norm = float(np.linalg.norm(array))
    if norm <= 0:
        return np.zeros(dim, dtype=np.float32).tolist()
    return (array / norm).astype(np.float32).tolist()



def _normalize_id_list(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    results: List[int] = []
    for item in value:
        normalized = _to_int(item)
        if normalized is None:
            continue
        if normalized not in results:
            results.append(normalized)
    return results



def _normalize_tags(value: Any) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(value, list):
        results: List[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text and text not in results:
                results.append(text)
        return results
    return []



def _normalize_role_code(value: Any) -> int:
    if isinstance(value, int) and value in ROLE_CODE_TO_NAME:
        return value
    text = str(value or "").strip().lower()
    return ROLE_NAME_TO_CODE.get(text, 2)



def _normalize_brand_stage(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None



def _safe_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}



def _safe_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []



def _tag_display_name(key: str) -> str:
    text = str(key or "").strip()
    if not text:
        return ""
    return text.split("::")[-1].strip() if "::" in text else text



def _round_dict(payload: Dict[str, float], digits: int = 3) -> Dict[str, float]:
    return {str(key): round(float(value), digits) for key, value in payload.items()}


class AssetService:
    """封装资产提交、SPU 记忆、用户偏好记忆、资产库列表与下一批推荐服务。"""

    def commit_assets(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()

        brand_name = str(payload.get("brand_name") or "").strip()
        spu_name = str(payload.get("spu_name") or "").strip()
        if not brand_name or not spu_name:
            raise ValueError("brand_name 与 spu_name 为必填字段。")

        operator_id = _to_int(payload.get("operator_id"))
        operator_role = _normalize_role_code(payload.get("operator_role"))
        selected_ids = _normalize_id_list(payload.get("selected_ids"))
        rejected_ids = _normalize_id_list(payload.get("rejected_ids"))
        pending_ids = _normalize_id_list(payload.get("pending_ids"))
        if not selected_ids and not rejected_ids and not pending_ids:
            raise ValueError("selected_ids、rejected_ids、pending_ids 至少需要提供一类反馈。")

        raw_text = str(payload.get("raw_text") or "").strip()
        intent_snapshot = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
        brand_stage = self._extract_brand_stage(payload, intent_snapshot)
        if raw_text and "raw_text" not in intent_snapshot:
            intent_snapshot = dict(intent_snapshot)
            intent_snapshot["raw_text"] = raw_text
        if brand_stage and not self._extract_brand_stage(intent_snapshot):
            intent_snapshot = dict(intent_snapshot)
            intent_snapshot["brand_stage"] = brand_stage

        campaign_id = _to_int(payload.get("campaign_id"))
        if campaign_id is None:
            campaign_id = database.create_campaign(
                {
                    "brand_name": brand_name,
                    "spu_name": spu_name,
                    "operator_id": operator_id,
                    "operator_role": operator_role,
                    "intent_snapshot": intent_snapshot,
                }
            )
            created_new_campaign = True
        else:
            created_new_campaign = False

        query_vector = payload.get("query_vector")
        if not isinstance(query_vector, list):
            query_vector = None
        elif query_vector:
            query_vector = _normalize_vector(query_vector)

        database.commit_campaign(
            campaign_id,
            selected_ids=selected_ids,
            rejected_ids=rejected_ids,
            pending_ids=pending_ids,
            query_vector=query_vector,
        )

        evolution_snapshot = payload.get("evolution_snapshot") if isinstance(payload.get("evolution_snapshot"), dict) else {}
        fulfillment_payload = {
            "campaign_id": campaign_id,
            "action_type": str(payload.get("action_type") or "commit"),
            "influencer_ids": selected_ids,
            "payload_snapshot": {
                "selected_ids": selected_ids,
                "rejected_ids": rejected_ids,
                "pending_ids": pending_ids,
                "tag_weights": payload.get("tag_weights") or {},
                "data_requirements": payload.get("data_requirements")
                or (intent_snapshot.get("data_requirements") if isinstance(intent_snapshot, dict) else {}),
                "brand_stage": brand_stage,
                "user_memory_enabled": bool(operator_id),
                "spu_memory_enabled": True,
                "evolution_snapshot": evolution_snapshot,
                "content_summary": str(payload.get("content_summary") or "").strip(),
                "collaboration_note": str(payload.get("collaboration_note") or "").strip(),
                "material_assets": payload.get("material_assets") if isinstance(payload.get("material_assets"), list) else [],
                "delivery_links": payload.get("delivery_links") if isinstance(payload.get("delivery_links"), list) else [],
            },
            "operator_id": operator_id,
        }
        record_id = database.create_fulfillment(fulfillment_payload)

        return {
            "campaign_id": campaign_id,
            "record_id": record_id,
            "record_detail_path": f"/api/v1/library/history?record_id={record_id}",
            "created_new_campaign": created_new_campaign,
            "operator_id": operator_id,
            "operator_role": operator_role,
            "operator_role_name": ROLE_CODE_TO_NAME.get(operator_role, "策划"),
            "selected_count": len(selected_ids),
            "rejected_count": len(rejected_ids),
            "pending_count": len(pending_ids),
            "selected_ids": selected_ids,
            "rejected_ids": rejected_ids,
            "pending_ids": pending_ids,
            "brand_name": brand_name,
            "spu_name": spu_name,
            "brand_stage": brand_stage,
            "next_batch_strategy": {
                "spu_memory_enabled": True,
                "user_memory_enabled": bool(operator_id),
                "campaign_id": campaign_id,
                "message": "已沉淀本次 SPU 与用户反馈，可用于后续换一批进化推荐。",
            },
            "history_snapshot_saved": bool(evolution_snapshot),
        }

    def get_spu_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()
        brand_name = str(payload.get("brand_name") or "").strip()
        spu_name = str(payload.get("spu_name") or "").strip()
        if not brand_name or not spu_name:
            raise ValueError("brand_name 与 spu_name 为必填字段。")

        campaigns = database.get_campaigns_by_brand(brand_name, spu_name=spu_name)
        memory = self._build_memory_profile(campaigns, source="spu_memory")
        return {
            "brand_name": brand_name,
            "spu_name": spu_name,
            **memory,
        }

    def get_user_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()
        operator_id = _to_int(payload.get("operator_id"))
        if operator_id is None:
            raise ValueError("operator_id 为必填字段。")
        brand_name = str(payload.get("brand_name") or "").strip() or None
        spu_name = str(payload.get("spu_name") or "").strip() or None

        campaigns = database.get_campaigns_by_operator(
            operator_id,
            brand_name=brand_name,
            spu_name=spu_name,
        )
        memory = self._build_memory_profile(campaigns, source="user_memory")
        return {
            "operator_id": operator_id,
            "brand_name": brand_name,
            "spu_name": spu_name,
            **memory,
        }

    def recommend_next_batch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        brand_name = str(payload.get("brand_name") or "").strip()
        spu_name = str(payload.get("spu_name") or "").strip()
        if not brand_name or not spu_name:
            raise ValueError("brand_name 与 spu_name 为必填字段。")

        operator_id = _to_int(payload.get("operator_id"))
        operator_role = _normalize_role_code(payload.get("operator_role"))
        spu_memory = self.get_spu_memory({"brand_name": brand_name, "spu_name": spu_name})
        user_memory = self.get_user_memory(
            {
                "operator_id": operator_id,
                "brand_name": brand_name,
                "spu_name": spu_name,
            }
        ) if operator_id is not None else {
            "memory_ready": False,
            "campaign_count": 0,
            "recommended_tag_weights": {},
            "preferred_tags": [],
            "history_ids": {},
            "latest_intent": {},
            "selected_rank": [],
            "rejected_rank": [],
            "selected_events": [],
            "rejected_events": [],
            "pending_events": [],
            "role_breakdown": {},
        }

        request_intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else None
        raw_text = str(payload.get("raw_text") or "").strip()
        intent = request_intent or spu_memory.get("latest_intent") or user_memory.get("latest_intent") or {}
        if not intent and raw_text:
            from services.intent_parser import intent_parser_service

            intent = intent_parser_service.parse(raw_text, brand_name=brand_name, spu_name=spu_name)
        if not intent:
            raise ValueError("当前 SPU 还没有可复用的意图快照，请先完成一轮检索并提交反馈，或在请求中显式传入 raw_text / intent。")

        from services.match_service import EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED, match_service

        experiment_mode = str(payload.get("experiment_mode") or EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED)
        manual_tag_weights = payload.get("tag_weights") if isinstance(payload.get("tag_weights"), dict) else {}
        base_merged_tag_weights = self._merge_tag_weights(
            spu_memory.get("recommended_tag_weights") or {},
            user_memory.get("recommended_tag_weights") or {},
            manual_tag_weights,
        )

        current_selected = _normalize_id_list(payload.get("selected_ids"))
        current_rejected = _normalize_id_list(payload.get("rejected_ids"))
        current_pending = _normalize_id_list(payload.get("pending_ids"))

        current_brand_stage = self._extract_brand_stage(payload, intent, spu_memory.get("latest_intent"), user_memory.get("latest_intent"))
        role_decay_overrides = payload.get("role_decay_overrides") if isinstance(payload.get("role_decay_overrides"), dict) else {}
        brand_stage_match_factor = _to_float(payload.get("brand_stage_match_factor"), DEFAULT_BRAND_STAGE_MATCH_FACTOR) or DEFAULT_BRAND_STAGE_MATCH_FACTOR
        brand_stage_mismatch_factor = _to_float(payload.get("brand_stage_mismatch_factor"), DEFAULT_BRAND_STAGE_MISMATCH_FACTOR)
        if brand_stage_mismatch_factor is None:
            brand_stage_mismatch_factor = DEFAULT_BRAND_STAGE_MISMATCH_FACTOR
        campaign_freshness_decay_days = _to_float(payload.get("campaign_freshness_decay_days"), DEFAULT_CAMPAIGN_FRESHNESS_DECAY_DAYS) or DEFAULT_CAMPAIGN_FRESHNESS_DECAY_DAYS
        campaign_freshness_min_factor = _to_float(payload.get("campaign_freshness_min_factor"), DEFAULT_CAMPAIGN_FRESHNESS_MIN_FACTOR)
        if campaign_freshness_min_factor is None:
            campaign_freshness_min_factor = DEFAULT_CAMPAIGN_FRESHNESS_MIN_FACTOR

        use_memory_feedback = bool(payload.get("use_memory_feedback", True))
        current_feedback_factor = _to_float(payload.get("current_feedback_factor"), DEFAULT_CURRENT_FEEDBACK_FACTOR) or DEFAULT_CURRENT_FEEDBACK_FACTOR
        history_feedback_decay = _to_float(payload.get("history_feedback_decay"), DEFAULT_HISTORY_FEEDBACK_DECAY) or DEFAULT_HISTORY_FEEDBACK_DECAY
        spu_history_decay = _to_float(payload.get("spu_history_decay"), DEFAULT_SPU_HISTORY_DECAY) or DEFAULT_SPU_HISTORY_DECAY
        user_history_decay = _to_float(payload.get("user_history_decay"), DEFAULT_USER_HISTORY_DECAY) or DEFAULT_USER_HISTORY_DECAY
        role_time_decay_days = _to_float(payload.get("role_time_decay_days"), DEFAULT_ROLE_TIME_DECAY_DAYS) or DEFAULT_ROLE_TIME_DECAY_DAYS
        role_time_decay_min_factor = _to_float(payload.get("role_time_decay_min_factor"), DEFAULT_ROLE_TIME_DECAY_MIN_FACTOR)
        if role_time_decay_min_factor is None:
            role_time_decay_min_factor = DEFAULT_ROLE_TIME_DECAY_MIN_FACTOR
        history_limit = max(_to_int(payload.get("history_feedback_limit"), DEFAULT_HISTORY_LIMIT) or DEFAULT_HISTORY_LIMIT, 1)

        feedback_candidates = self._build_feedback_candidates(
            current_selected=current_selected,
            current_rejected=current_rejected,
            operator_role=operator_role,
            spu_memory=spu_memory,
            user_memory=user_memory,
            use_memory_feedback=use_memory_feedback,
            current_feedback_factor=current_feedback_factor,
            history_feedback_decay=history_feedback_decay,
            spu_history_decay=spu_history_decay,
            user_history_decay=user_history_decay,
            role_time_decay_days=role_time_decay_days,
            role_time_decay_min_factor=role_time_decay_min_factor,
            role_decay_overrides=role_decay_overrides,
            current_brand_stage=current_brand_stage,
            brand_stage_match_factor=brand_stage_match_factor,
            brand_stage_mismatch_factor=brand_stage_mismatch_factor,
            campaign_freshness_decay_days=campaign_freshness_decay_days,
            campaign_freshness_min_factor=campaign_freshness_min_factor,
            history_limit=history_limit,
        )

        weight_changes = self._build_weight_change_explanation(
            base_tag_weights=base_merged_tag_weights,
            feedback_candidates=feedback_candidates,
            step=_to_float(payload.get("feedback_tag_step"), DEFAULT_FEEDBACK_TAG_STEP) or DEFAULT_FEEDBACK_TAG_STEP,
            max_delta=_to_float(payload.get("feedback_tag_max_delta"), DEFAULT_MAX_TAG_DELTA) or DEFAULT_MAX_TAG_DELTA,
        )
        evolved_tag_weights = weight_changes["after"]

        query_plan = _safe_json_dict(intent.get("query_plan"))
        query_context = match_service.build_query_context(
            query_plan,
            experiment_mode=experiment_mode,
            tag_weights=evolved_tag_weights,
        )

        rocchio_meta = self._build_rocchio_query(
            base_query_vector=query_context.get("query_vector") or [],
            vector_field=str(payload.get("vector_field") or "v_overall_style"),
            current_positive_candidates=feedback_candidates["current_positive"],
            current_negative_candidates=feedback_candidates["current_negative"],
            history_positive_candidates=feedback_candidates["history_positive"],
            history_negative_candidates=feedback_candidates["history_negative"],
            alpha=_to_float(payload.get("rocchio_alpha"), DEFAULT_ROCCHIO_ALPHA) or DEFAULT_ROCCHIO_ALPHA,
            beta=_to_float(payload.get("rocchio_beta"), DEFAULT_ROCCHIO_BETA) or DEFAULT_ROCCHIO_BETA,
            gamma=_to_float(payload.get("rocchio_gamma"), DEFAULT_ROCCHIO_GAMMA) or DEFAULT_ROCCHIO_GAMMA,
            operator_role=operator_role,
            strategy={
                "current_feedback_factor": current_feedback_factor,
                "history_feedback_decay": history_feedback_decay,
                "spu_history_decay": spu_history_decay,
                "user_history_decay": user_history_decay,
                "role_time_decay_days": role_time_decay_days,
                "role_time_decay_min_factor": role_time_decay_min_factor,
                "role_decay_overrides": role_decay_overrides,
                "current_brand_stage": current_brand_stage,
                "brand_stage_match_factor": brand_stage_match_factor,
                "brand_stage_mismatch_factor": brand_stage_mismatch_factor,
                "campaign_freshness_decay_days": campaign_freshness_decay_days,
                "campaign_freshness_min_factor": campaign_freshness_min_factor,
                "history_feedback_limit": history_limit,
            },
        )

        exclude_ids: List[int] = []
        if bool(payload.get("exclude_history", True)):
            exclude_ids.extend(spu_memory.get("history_ids", {}).get("considered_ids") or [])
            exclude_ids.extend(user_memory.get("history_ids", {}).get("considered_ids") or [])
        exclude_ids.extend(current_selected)
        exclude_ids.extend(current_rejected)
        exclude_ids.extend(current_pending)
        exclude_ids.extend(_normalize_id_list(payload.get("extra_exclude_ids")))
        exclude_ids = list(dict.fromkeys(exclude_ids))

        response = match_service.submit_retrieve_task(
            {
                "raw_text": raw_text or (intent.get("raw_text") if isinstance(intent, dict) else ""),
                "brand_name": brand_name,
                "spu_name": spu_name,
                "intent": intent,
                "top_k": _to_int(payload.get("top_k"), 10) or 10,
                "vector_field": str(payload.get("vector_field") or "v_overall_style"),
                "experiment_mode": experiment_mode,
                "tag_weights": evolved_tag_weights,
                "exclude_ids": exclude_ids,
                "use_cache": bool(payload.get("use_cache", True)),
                "enable_external_expansion": bool(payload.get("enable_external_expansion", True)),
                "enable_greedy_degrade": bool(payload.get("enable_greedy_degrade", True)),
                "external_page_size": _to_int(payload.get("external_page_size"), 20) or 20,
                "query_vector_override": rocchio_meta.get("query_vector") or query_context.get("query_vector") or [],
                "query_vector_meta": rocchio_meta,
            }
        )

        return {
            "brand_name": brand_name,
            "spu_name": spu_name,
            "memory_profile": {
                "spu_memory": {
                    "campaign_count": spu_memory.get("campaign_count", 0),
                    "recommended_tag_weights": spu_memory.get("recommended_tag_weights") or {},
                    "preferred_tags": spu_memory.get("preferred_tags") or [],
                    "history_ids": spu_memory.get("history_ids") or {},
                    "latest_campaign_id": spu_memory.get("latest_campaign_id"),
                    "role_breakdown": spu_memory.get("role_breakdown") or {},
                },
                "user_memory": {
                    "operator_id": operator_id,
                    "campaign_count": user_memory.get("campaign_count", 0),
                    "recommended_tag_weights": user_memory.get("recommended_tag_weights") or {},
                    "preferred_tags": user_memory.get("preferred_tags") or [],
                    "history_ids": user_memory.get("history_ids") or {},
                    "role_breakdown": user_memory.get("role_breakdown") or {},
                },
                "base_merged_tag_weights": base_merged_tag_weights,
                "merged_tag_weights": evolved_tag_weights,
            },
            "effective_request": {
                "top_k": _to_int(payload.get("top_k"), 10) or 10,
                "exclude_ids": exclude_ids,
                "tag_weights": evolved_tag_weights,
                "manual_tag_weights": _round_dict({str(key): float(value) for key, value in manual_tag_weights.items() if _to_float(value) is not None}),
                "exclude_history": bool(payload.get("exclude_history", True)),
                "current_feedback": {
                    "selected_ids": current_selected,
                    "rejected_ids": current_rejected,
                    "pending_ids": current_pending,
                    "operator_role": operator_role,
                    "operator_role_name": ROLE_CODE_TO_NAME.get(operator_role, "策划"),
                },
                "feedback_candidates": feedback_candidates,
                "weight_changes": weight_changes,
                "rocchio": rocchio_meta,
            },
            "recommendation_task": response,
        }

    def list_library(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()
        page = max(_to_int(payload.get("page"), 1) or 1, 1)
        page_size = min(max(_to_int(payload.get("page_size"), 20) or 20, 1), 100)
        offset = (page - 1) * page_size

        rows, total = database.search_influencers(
            region=str(payload.get("region") or "").strip() or None,
            followers_min=_to_int(payload.get("followers_min")),
            followers_max=_to_int(payload.get("followers_max")),
            tags=_normalize_tags(payload.get("tags")) or None,
            gender=str(payload.get("gender") or "").strip() or None,
            limit=page_size,
            offset=offset,
            sort_by=str(payload.get("sort_by") or "followers"),
            sort_order=str(payload.get("sort_order") or "DESC"),
        )

        items = []
        for row in rows:
            item = dict(row)
            item["history_hint"] = {
                "detail_path": f"/api/v1/library/history?influencer_id={item.get('internal_id')}",
            }
            items.append(item)

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if page_size else 0,
            },
            "filters": {
                "region": str(payload.get("region") or "").strip() or None,
                "followers_min": _to_int(payload.get("followers_min")),
                "followers_max": _to_int(payload.get("followers_max")),
                "gender": str(payload.get("gender") or "").strip() or None,
                "tags": _normalize_tags(payload.get("tags")),
                "sort_by": str(payload.get("sort_by") or "followers"),
                "sort_order": str(payload.get("sort_order") or "DESC").upper(),
            },
        }

    def get_history(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()
        influencer_id = _to_int(payload.get("influencer_id"))
        campaign_id = _to_int(payload.get("campaign_id"))
        record_id = _to_int(payload.get("record_id"))
        brand_name = str(payload.get("brand_name") or "").strip()
        spu_name = str(payload.get("spu_name") or "").strip() or None

        result: Dict[str, Any] = {
            "query": {
                "influencer_id": influencer_id,
                "campaign_id": campaign_id,
                "record_id": record_id,
                "brand_name": brand_name or None,
                "spu_name": spu_name,
            }
        }

        if record_id is not None:
            result["mode"] = "fulfillment_detail"
            result["record_detail"] = self._build_fulfillment_record_detail(record_id)
            return result

        if influencer_id is not None:
            result["mode"] = "influencer_history"
            result["influencer_profile"] = database.get_influencer_by_id(influencer_id) or {"internal_id": influencer_id}
            result["influencer_history"] = self._build_influencer_history_timeline(influencer_id)
            return result

        if campaign_id is not None:
            result["mode"] = "campaign_timeline"
            result["campaign_timeline"] = self._enrich_campaign_timeline(database.get_fulfillment_timeline(campaign_id))
            return result

        if brand_name:
            campaigns = database.get_campaigns_by_brand(brand_name, spu_name=spu_name)
            result["mode"] = "brand_campaigns"
            result["brand_campaigns"] = [self._build_campaign_history_card(item) for item in campaigns]
            return result

        raise ValueError("record_id、influencer_id、campaign_id、brand_name 至少提供一个。")

    def _to_iso_datetime(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        text = str(value).strip()
        if not text:
            return None
        return text.replace(" ", "T") if "T" not in text else text

    def _extract_brand_stage(self, *candidates: Any) -> Optional[str]:
        for candidate in candidates:
            if isinstance(candidate, dict):
                direct = _normalize_brand_stage(candidate.get("brand_stage"))
                if direct:
                    return direct
                nested_data = candidate.get("data_requirements")
                if isinstance(nested_data, dict):
                    nested = _normalize_brand_stage(nested_data.get("brand_stage"))
                    if nested:
                        return nested
                nested_intent = candidate.get("intent_snapshot")
                if isinstance(nested_intent, dict):
                    nested = self._extract_brand_stage(nested_intent)
                    if nested:
                        return nested
            else:
                normalized = _normalize_brand_stage(candidate)
                if normalized:
                    return normalized
        return None

    def _calculate_time_decay_factor(self, value: Any, *, decay_days: float, min_factor: float) -> float:
        if not value:
            return round(float(min_factor), 3)
        try:
            text = str(value).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = max((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0, 0.0)
            decay = 0.5 ** (age_days / max(float(decay_days), 1.0))
            return round(_clamp(float(decay), float(min_factor), 1.0), 3)
        except Exception:
            return round(float(min_factor), 3)

    def _resolve_role_decay_profile(
        self,
        role_code: int,
        *,
        default_days: float,
        default_min_factor: float,
        overrides: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, float]:
        profile = dict(DEFAULT_ROLE_DECAY_PROFILE.get(role_code, {}))
        profile.setdefault("decay_days", float(default_days))
        profile.setdefault("min_factor", float(default_min_factor))
        override_map = overrides or {}
        role_name = ROLE_CODE_TO_NAME.get(role_code, "策划")
        override = override_map.get(role_name) or override_map.get(str(role_code)) or {}
        if isinstance(override, dict):
            decay_days = _to_float(override.get("decay_days"), profile["decay_days"])
            min_factor = _to_float(override.get("min_factor"), profile["min_factor"])
            profile["decay_days"] = decay_days if decay_days is not None else profile["decay_days"]
            profile["min_factor"] = min_factor if min_factor is not None else profile["min_factor"]
        return {
            "decay_days": round(float(profile["decay_days"]), 3),
            "min_factor": round(float(profile["min_factor"]), 3),
        }

    def _calculate_campaign_freshness_factor(self, value: Any, *, decay_days: float, min_factor: float) -> float:
        return self._calculate_time_decay_factor(value, decay_days=decay_days, min_factor=min_factor)

    def _build_history_snapshot_summary(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        evolution_snapshot = _safe_json_dict(snapshot.get("evolution_snapshot"))
        weight_changes = _safe_json_dict(evolution_snapshot.get("weight_changes"))
        rocchio = _safe_json_dict(evolution_snapshot.get("rocchio"))
        promoted = weight_changes.get("promoted") if isinstance(weight_changes.get("promoted"), list) else []
        demoted = weight_changes.get("demoted") if isinstance(weight_changes.get("demoted"), list) else []
        return {
            "summary": str(weight_changes.get("summary") or rocchio.get("message") or "当前记录未附带推荐进化摘要。"),
            "promoted": promoted[:3],
            "demoted": demoted[:3],
            "rocchio": {
                "applied": bool(rocchio.get("applied")),
                "message": rocchio.get("message"),
                "current_role": rocchio.get("current_role") or {},
                "strategy": rocchio.get("strategy") or {},
                "breakdown": rocchio.get("breakdown") or {},
            },
            "weight_changes": {
                "before": weight_changes.get("before") or {},
                "after": weight_changes.get("after") or {},
                "summary": weight_changes.get("summary") or "",
                "promoted": promoted[:3],
                "demoted": demoted[:3],
            },
        }

    def _extract_material_assets(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_assets = snapshot.get("material_assets") if isinstance(snapshot.get("material_assets"), list) else []
        raw_links = snapshot.get("delivery_links") if isinstance(snapshot.get("delivery_links"), list) else []
        materials: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_assets):
            if isinstance(item, dict):
                materials.append(
                    {
                        "type": str(item.get("type") or item.get("asset_type") or "asset"),
                        "title": str(item.get("title") or item.get("name") or f"素材 {index + 1}"),
                        "url": str(item.get("url") or item.get("link") or "").strip() or None,
                        "preview_url": str(item.get("preview_url") or item.get("cover_image_url") or item.get("thumbnail") or "").strip() or None,
                        "source": str(item.get("source") or "payload_snapshot") or "payload_snapshot",
                    }
                )
            elif item:
                materials.append(
                    {
                        "type": "asset",
                        "title": f"素材 {index + 1}",
                        "url": str(item),
                        "preview_url": None,
                        "source": "payload_snapshot",
                    }
                )
        for index, item in enumerate(raw_links):
            if isinstance(item, dict):
                materials.append(
                    {
                        "type": str(item.get("type") or "delivery_link"),
                        "title": str(item.get("title") or item.get("name") or f"履约链接 {index + 1}"),
                        "url": str(item.get("url") or item.get("link") or "").strip() or None,
                        "preview_url": str(item.get("preview_url") or item.get("thumbnail") or "").strip() or None,
                        "source": str(item.get("source") or "payload_snapshot") or "payload_snapshot",
                    }
                )
            elif item:
                materials.append(
                    {
                        "type": "delivery_link",
                        "title": f"履约链接 {index + 1}",
                        "url": str(item),
                        "preview_url": None,
                        "source": "payload_snapshot",
                    }
                )
        return materials[:12]

    def _build_note_asset_previews(self, influencer_id: int) -> List[Dict[str, Any]]:
        database = self._require_db()
        try:
            notes = database.get_notes_by_influencer(influencer_id)
        except Exception:
            return []
        items: List[Dict[str, Any]] = []
        for row in notes[:3]:
            item = dict(row)
            items.append(
                {
                    "note_id": item.get("note_id"),
                    "note_type": item.get("note_type"),
                    "is_ad": bool(item.get("is_ad")),
                    "published_at": self._to_iso_datetime(item.get("published_at")),
                    "cover_image_url": item.get("cover_image_url"),
                    "reads": item.get("reads"),
                    "likes": item.get("likes"),
                    "comments": item.get("comments"),
                    "collections": item.get("collections"),
                    "shares": item.get("shares"),
                }
            )
        return items

    def _build_fulfillment_record_detail(self, record_id: int) -> Dict[str, Any]:
        database = self._require_db()
        record = database.get_fulfillment_record(record_id)
        if not record:
            raise ValueError("record_id 对应的履约记录不存在。")
        item = dict(record)
        snapshot = _safe_json_dict(item.get("payload_snapshot"))
        campaign_id = _to_int(item.get("campaign_id"), 0) or 0
        campaign = database.get_campaign_by_id(campaign_id) or {"campaign_id": campaign_id}
        related_ids = list(
            dict.fromkeys(
                _normalize_id_list(snapshot.get("selected_ids"))
                + _normalize_id_list(snapshot.get("rejected_ids"))
                + _normalize_id_list(snapshot.get("pending_ids"))
            )
        )
        influencer_cards: List[Dict[str, Any]] = []
        note_previews: List[Dict[str, Any]] = []
        for influencer_id in related_ids[:8]:
            profile = database.get_influencer_by_id(influencer_id) or {"internal_id": influencer_id}
            influencer_cards.append(
                {
                    "internal_id": influencer_id,
                    "display_name": profile.get("nickname") or profile.get("name") or f"达人 {influencer_id}",
                    "platform": profile.get("platform"),
                    "tags": _normalize_tags(profile.get("tags")),
                    "detail_path": f"/api/v1/library/history?influencer_id={influencer_id}",
                }
            )
            for note in self._build_note_asset_previews(influencer_id):
                note_previews.append({**note, "influencer_id": influencer_id, "influencer_name": influencer_cards[-1]["display_name"]})
        return {
            **item,
            "created_at": self._to_iso_datetime(item.get("created_at")),
            "campaign": {
                "campaign_id": campaign_id,
                "brand_name": campaign.get("brand_name"),
                "spu_name": campaign.get("spu_name"),
                "operator_role": campaign.get("operator_role"),
                "operator_id": campaign.get("operator_id"),
                "detail_path": f"/api/v1/library/history?campaign_id={campaign_id}",
            },
            "brand_stage": self._extract_brand_stage(snapshot, campaign),
            "history_explanation": self._build_history_snapshot_summary(snapshot),
            "influencer_cards": influencer_cards,
            "content_detail": {
                "content_summary": str(snapshot.get("content_summary") or "").strip() or None,
                "collaboration_note": str(snapshot.get("collaboration_note") or "").strip() or None,
                "selected_ids": _normalize_id_list(snapshot.get("selected_ids")),
                "rejected_ids": _normalize_id_list(snapshot.get("rejected_ids")),
                "pending_ids": _normalize_id_list(snapshot.get("pending_ids")),
                "tag_weights": _safe_json_dict(snapshot.get("tag_weights")),
                "data_requirements": _safe_json_dict(snapshot.get("data_requirements")),
            },
            "material_assets": self._extract_material_assets(snapshot),
            "note_previews": note_previews[:12],
        }

    def _build_timeline_influencer_cards(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        database = self._require_db()
        influencer_ids = _normalize_id_list(snapshot.get("selected_ids")) + _normalize_id_list(snapshot.get("rejected_ids")) + _normalize_id_list(snapshot.get("pending_ids"))
        cards: List[Dict[str, Any]] = []
        for influencer_id in list(dict.fromkeys(influencer_ids))[:8]:
            profile = database.get_influencer_by_id(influencer_id) or {"internal_id": influencer_id}
            cards.append(
                {
                    "internal_id": influencer_id,
                    "display_name": profile.get("nickname") or profile.get("name") or f"达人 {influencer_id}",
                    "platform": profile.get("platform"),
                    "tags": _normalize_tags(profile.get("tags")),
                    "detail_path": f"/api/v1/library/history?influencer_id={influencer_id}",
                }
            )
        return cards

    def _enrich_campaign_timeline(self, timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for row in timeline:
            item = dict(row)
            snapshot = _safe_json_dict(item.get("payload_snapshot"))
            item["history_explanation"] = self._build_history_snapshot_summary(snapshot)
            item["created_at"] = self._to_iso_datetime(item.get("created_at"))
            item["brand_stage"] = self._extract_brand_stage(snapshot)
            item["influencer_cards"] = self._build_timeline_influencer_cards(snapshot)
            item["record_detail_path"] = f"/api/v1/library/history?record_id={_to_int(item.get('record_id'), 0) or 0}"
            item["campaign_detail_path"] = f"/api/v1/library/history?campaign_id={_to_int(item.get('campaign_id'), 0) or 0}"
            item["detail_path"] = item["record_detail_path"]
            item["content_summary"] = str(snapshot.get("content_summary") or "").strip() or None
            item["material_assets"] = self._extract_material_assets(snapshot)
            items.append(item)
        return items

    def _build_campaign_history_card(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        database = self._require_db()
        item = dict(campaign)
        timeline = self._enrich_campaign_timeline(database.get_fulfillment_timeline(_to_int(item.get("campaign_id"), 0) or 0))
        latest_timeline = timeline[-1] if timeline else {}
        latest_explanation = latest_timeline.get("history_explanation") if isinstance(latest_timeline, dict) else {}
        return {
            **item,
            "created_at": self._to_iso_datetime(item.get("created_at")),
            "brand_stage": self._extract_brand_stage(item),
            "history_summary": latest_explanation or {"summary": "当前任务尚未沉淀推荐进化摘要。"},
            "timeline_count": len(timeline),
            "timeline_preview": timeline[-3:],
            "detail_path": f"/api/v1/library/history?campaign_id={_to_int(item.get('campaign_id'), 0) or 0}",
        }

    def _build_influencer_history_timeline(self, influencer_id: int) -> List[Dict[str, Any]]:
        database = self._require_db()
        raw_history = database.get_influencer_history(influencer_id)
        items: List[Dict[str, Any]] = []
        for row in raw_history:
            item = dict(row)
            campaign_id = _to_int(item.get("campaign_id"), 0) or 0
            timeline = self._enrich_campaign_timeline(database.get_fulfillment_timeline(campaign_id))
            related_steps: List[Dict[str, Any]] = []
            for step in timeline:
                snapshot = _safe_json_dict(step.get("payload_snapshot"))
                related_ids = _normalize_id_list(snapshot.get("selected_ids")) + _normalize_id_list(snapshot.get("rejected_ids")) + _normalize_id_list(snapshot.get("pending_ids"))
                if influencer_id in related_ids:
                    related_steps.append(step)
            latest_step = related_steps[-1] if related_steps else (timeline[-1] if timeline else {})
            latest_explanation = latest_step.get("history_explanation") if isinstance(latest_step, dict) else {}
            items.append(
                {
                    **item,
                    "created_at": self._to_iso_datetime(item.get("created_at")),
                    "operator_role_name": ROLE_CODE_TO_NAME.get(_normalize_role_code(item.get("operator_role")), "策划"),
                    "detail_path": f"/api/v1/library/history?campaign_id={campaign_id}",
                    "history_explanation": latest_explanation or {"summary": "当前记录暂无推荐偏移摘要。"},
                    "timeline_preview": related_steps[-3:] if related_steps else timeline[-3:],
                }
            )
        return items

    def _build_memory_profile(self, campaigns: List[Dict[str, Any]], *, source: str) -> Dict[str, Any]:
        database = self._require_db()
        latest_campaign = dict(campaigns[0]) if campaigns else None
        latest_intent = _safe_json_dict(latest_campaign.get("intent_snapshot")) if latest_campaign else {}
        latest_query_vector = _safe_json_list(latest_campaign.get("query_vector_snapshot")) if latest_campaign else []

        tag_weight_totals: Dict[str, float] = defaultdict(float)
        tag_weight_weight_sum: Dict[str, float] = defaultdict(float)
        selected_scores: Dict[int, float] = defaultdict(float)
        rejected_scores: Dict[int, float] = defaultdict(float)
        pending_scores: Dict[int, float] = defaultdict(float)
        selected_events: List[Dict[str, Any]] = []
        rejected_events: List[Dict[str, Any]] = []
        pending_events: List[Dict[str, Any]] = []
        considered_ids: List[int] = []
        latest_data_requirements: Dict[str, Any] = {}
        role_breakdown: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "role_code": 2,
            "campaign_count": 0,
            "selected_count": 0,
            "rejected_count": 0,
            "pending_count": 0,
            "role_weight": 1.0,
        })

        for campaign in campaigns:
            intent_snapshot = _safe_json_dict(campaign.get("intent_snapshot"))
            campaign_brand_stage = self._extract_brand_stage(campaign, intent_snapshot)
            role_code = _normalize_role_code(campaign.get("operator_role"))
            role_name = ROLE_CODE_TO_NAME.get(role_code, "策划")
            role_weight = ROLE_FEEDBACK_WEIGHT.get(role_code, 1.0)
            role_breakdown[role_name]["role_code"] = role_code
            role_breakdown[role_name]["role_weight"] = role_weight
            role_breakdown[role_name]["campaign_count"] += 1
            selected_ids = _normalize_id_list(campaign.get("selected_influencer_ids"))
            rejected_ids = _normalize_id_list(campaign.get("rejected_influencer_ids"))
            pending_ids = _normalize_id_list(campaign.get("pending_influencer_ids"))
            campaign_id = _to_int(campaign.get("campaign_id"))
            created_at = self._to_iso_datetime(campaign.get("created_at"))
            role_breakdown[role_name]["selected_count"] += len(selected_ids)
            role_breakdown[role_name]["rejected_count"] += len(rejected_ids)
            role_breakdown[role_name]["pending_count"] += len(pending_ids)

            for influencer_id in selected_ids:
                selected_scores[influencer_id] += role_weight
                selected_events.append(
                    {
                        "internal_id": influencer_id,
                        "score": round(role_weight, 3),
                        "role_code": role_code,
                        "role_name": role_name,
                        "role_weight": round(role_weight, 3),
                        "created_at": created_at,
                        "campaign_id": campaign_id,
                        "brand_stage": campaign_brand_stage,
                    }
                )
            for influencer_id in rejected_ids:
                rejected_scores[influencer_id] += role_weight
                rejected_events.append(
                    {
                        "internal_id": influencer_id,
                        "score": round(role_weight, 3),
                        "role_code": role_code,
                        "role_name": role_name,
                        "role_weight": round(role_weight, 3),
                        "created_at": created_at,
                        "campaign_id": campaign_id,
                        "brand_stage": campaign_brand_stage,
                    }
                )
            for influencer_id in pending_ids:
                pending_scores[influencer_id] += role_weight
                pending_events.append(
                    {
                        "internal_id": influencer_id,
                        "score": round(role_weight, 3),
                        "role_code": role_code,
                        "role_name": role_name,
                        "role_weight": round(role_weight, 3),
                        "created_at": created_at,
                        "campaign_id": campaign_id,
                        "brand_stage": campaign_brand_stage,
                    }
                )
            considered_ids.extend(selected_ids + rejected_ids + pending_ids)

            timeline = database.get_fulfillment_timeline(_to_int(campaign.get("campaign_id"), 0) or 0)
            payload_snapshots = [_safe_json_dict(item.get("payload_snapshot")) for item in timeline]

            derived_tag_weights: Dict[str, float] = {}
            for snapshot in payload_snapshots:
                if snapshot.get("data_requirements"):
                    latest_data_requirements = _safe_json_dict(snapshot.get("data_requirements"))
                for key, value in (_safe_json_dict(snapshot.get("tag_weights")) or {}).items():
                    numeric = _to_float(value)
                    if numeric is None:
                        continue
                    derived_tag_weights[str(key)] = numeric

            if not latest_data_requirements and intent_snapshot.get("data_requirements"):
                latest_data_requirements = _safe_json_dict(intent_snapshot.get("data_requirements"))

            if not derived_tag_weights:
                query_plan = _safe_json_dict(intent_snapshot.get("query_plan"))
                for item in query_plan.get("formatted_tags", query_plan.get("tags", [])):
                    if not isinstance(item, dict):
                        continue
                    tag = str(item.get("tag") or "").strip()
                    key = str(item.get("key") or item.get("tag") or "").strip()
                    if not tag or not key:
                        continue
                    derived_tag_weights[key] = _to_float(item.get("default_weight"), 1.0) or 1.0

            for key, value in derived_tag_weights.items():
                numeric = _clamp(float(value), 0.0, 2.0)
                tag_weight_totals[key] += numeric * role_weight
                tag_weight_weight_sum[key] += role_weight

        recommended_tag_weights: Dict[str, float] = {}
        for key, total in tag_weight_totals.items():
            base = total / max(tag_weight_weight_sum.get(key, 1.0), 1e-6)
            recommended_tag_weights[key] = round(_clamp(base, 0.2, 2.0), 3)

        preferred_tags = [
            {"key": key, "weight": weight, "source": source, "display_name": _tag_display_name(key)}
            for key, weight in sorted(recommended_tag_weights.items(), key=lambda item: item[1], reverse=True)
        ]

        selected_rank = [
            {"internal_id": internal_id, "score": round(score, 3)}
            for internal_id, score in sorted(selected_scores.items(), key=lambda item: item[1], reverse=True)
        ]
        rejected_rank = [
            {"internal_id": internal_id, "score": round(score, 3)}
            for internal_id, score in sorted(rejected_scores.items(), key=lambda item: item[1], reverse=True)
        ]
        pending_rank = [
            {"internal_id": internal_id, "score": round(score, 3)}
            for internal_id, score in sorted(pending_scores.items(), key=lambda item: item[1], reverse=True)
        ]

        return {
            "memory_ready": bool(campaigns),
            "campaign_count": len(campaigns),
            "latest_campaign_id": _to_int(latest_campaign.get("campaign_id")) if latest_campaign else None,
            "latest_intent": latest_intent,
            "latest_query_vector": latest_query_vector,
            "data_requirements_reference": latest_data_requirements,
            "recommended_tag_weights": recommended_tag_weights,
            "preferred_tags": preferred_tags,
            "selected_rank": selected_rank,
            "rejected_rank": rejected_rank,
            "pending_rank": pending_rank,
            "selected_events": selected_events,
            "rejected_events": rejected_events,
            "pending_events": pending_events,
            "role_breakdown": dict(role_breakdown),
            "history_ids": {
                "selected_ids": [item["internal_id"] for item in selected_rank],
                "rejected_ids": [item["internal_id"] for item in rejected_rank],
                "pending_ids": [item["internal_id"] for item in pending_rank],
                "considered_ids": list(dict.fromkeys(_normalize_id_list(considered_ids))),
            },
        }

    def _merge_tag_weights(
        self,
        spu_weights: Dict[str, Any],
        user_weights: Dict[str, Any],
        manual_weights: Dict[str, Any],
    ) -> Dict[str, float]:
        merged: Dict[str, float] = {}
        for source_weights, source_factor in ((spu_weights, 1.0), (user_weights, 0.85)):
            for key, value in (source_weights or {}).items():
                numeric = _to_float(value)
                if numeric is None or numeric <= 0:
                    continue
                if key not in merged:
                    merged[str(key)] = 0.0
                merged[str(key)] += float(numeric) * source_factor
        for key, value in list(merged.items()):
            merged[key] = round(_clamp(value, 0.2, 2.0), 3)
        for key, value in (manual_weights or {}).items():
            numeric = _to_float(value)
            if numeric is None:
                continue
            merged[str(key)] = round(_clamp(float(numeric), 0.0, 2.0), 3)
        return merged

    def _build_feedback_candidates(
        self,
        *,
        current_selected: Sequence[int],
        current_rejected: Sequence[int],
        operator_role: int,
        spu_memory: Dict[str, Any],
        user_memory: Dict[str, Any],
        use_memory_feedback: bool,
        current_feedback_factor: float,
        history_feedback_decay: float,
        spu_history_decay: float,
        user_history_decay: float,
        role_time_decay_days: float,
        role_time_decay_min_factor: float,
        role_decay_overrides: Dict[str, Dict[str, float]],
        current_brand_stage: Optional[str],
        brand_stage_match_factor: float,
        brand_stage_mismatch_factor: float,
        campaign_freshness_decay_days: float,
        campaign_freshness_min_factor: float,
        history_limit: int,
    ) -> Dict[str, Any]:
        role_weight = ROLE_FEEDBACK_WEIGHT.get(operator_role, 1.0)
        current_weight = round(role_weight * float(current_feedback_factor), 3)

        current_positive = self._make_current_feedback_items(
            current_selected,
            weight=current_weight,
            role_code=operator_role,
            direction="positive",
        )
        current_negative = self._make_current_feedback_items(
            current_rejected,
            weight=current_weight,
            role_code=operator_role,
            direction="negative",
        )

        history_positive: List[Dict[str, Any]] = []
        history_negative: List[Dict[str, Any]] = []
        if use_memory_feedback:
            history_positive.extend(
                self._make_history_feedback_items(
                    spu_memory.get("selected_events") or spu_memory.get("selected_rank") or [],
                    source="spu_memory",
                    source_decay=spu_history_decay,
                    history_feedback_decay=history_feedback_decay,
                    role_time_decay_days=role_time_decay_days,
                    role_time_decay_min_factor=role_time_decay_min_factor,
                    role_decay_overrides=role_decay_overrides,
                    current_brand_stage=current_brand_stage,
                    brand_stage_match_factor=brand_stage_match_factor,
                    brand_stage_mismatch_factor=brand_stage_mismatch_factor,
                    campaign_freshness_decay_days=campaign_freshness_decay_days,
                    campaign_freshness_min_factor=campaign_freshness_min_factor,
                    limit=history_limit,
                    direction="positive",
                )
            )
            history_positive.extend(
                self._make_history_feedback_items(
                    user_memory.get("selected_events") or user_memory.get("selected_rank") or [],
                    source="user_memory",
                    source_decay=user_history_decay,
                    history_feedback_decay=history_feedback_decay,
                    role_time_decay_days=role_time_decay_days,
                    role_time_decay_min_factor=role_time_decay_min_factor,
                    role_decay_overrides=role_decay_overrides,
                    current_brand_stage=current_brand_stage,
                    brand_stage_match_factor=brand_stage_match_factor,
                    brand_stage_mismatch_factor=brand_stage_mismatch_factor,
                    campaign_freshness_decay_days=campaign_freshness_decay_days,
                    campaign_freshness_min_factor=campaign_freshness_min_factor,
                    limit=history_limit,
                    direction="positive",
                )
            )
            history_negative.extend(
                self._make_history_feedback_items(
                    spu_memory.get("rejected_events") or spu_memory.get("rejected_rank") or [],
                    source="spu_memory",
                    source_decay=spu_history_decay,
                    history_feedback_decay=history_feedback_decay,
                    role_time_decay_days=role_time_decay_days,
                    role_time_decay_min_factor=role_time_decay_min_factor,
                    role_decay_overrides=role_decay_overrides,
                    current_brand_stage=current_brand_stage,
                    brand_stage_match_factor=brand_stage_match_factor,
                    brand_stage_mismatch_factor=brand_stage_mismatch_factor,
                    campaign_freshness_decay_days=campaign_freshness_decay_days,
                    campaign_freshness_min_factor=campaign_freshness_min_factor,
                    limit=history_limit,
                    direction="negative",
                )
            )
            history_negative.extend(
                self._make_history_feedback_items(
                    user_memory.get("rejected_events") or user_memory.get("rejected_rank") or [],
                    source="user_memory",
                    source_decay=user_history_decay,
                    history_feedback_decay=history_feedback_decay,
                    role_time_decay_days=role_time_decay_days,
                    role_time_decay_min_factor=role_time_decay_min_factor,
                    role_decay_overrides=role_decay_overrides,
                    current_brand_stage=current_brand_stage,
                    brand_stage_match_factor=brand_stage_match_factor,
                    brand_stage_mismatch_factor=brand_stage_mismatch_factor,
                    campaign_freshness_decay_days=campaign_freshness_decay_days,
                    campaign_freshness_min_factor=campaign_freshness_min_factor,
                    limit=history_limit,
                    direction="negative",
                )
            )

        history_positive = self._deduplicate_feedback_items(history_positive)
        history_negative = self._deduplicate_feedback_items(history_negative)

        return {
            "current_positive": current_positive,
            "current_negative": current_negative,
            "history_positive": history_positive,
            "history_negative": history_negative,
            "strategy": {
                "current_feedback_factor": round(float(current_feedback_factor), 3),
                "history_feedback_decay": round(float(history_feedback_decay), 3),
                "spu_history_decay": round(float(spu_history_decay), 3),
                "user_history_decay": round(float(user_history_decay), 3),
                "role_time_decay_days": round(float(role_time_decay_days), 3),
                "role_time_decay_min_factor": round(float(role_time_decay_min_factor), 3),
                "role_decay_overrides": role_decay_overrides,
                "current_brand_stage": current_brand_stage,
                "brand_stage_match_factor": round(float(brand_stage_match_factor), 3),
                "brand_stage_mismatch_factor": round(float(brand_stage_mismatch_factor), 3),
                "campaign_freshness_decay_days": round(float(campaign_freshness_decay_days), 3),
                "campaign_freshness_min_factor": round(float(campaign_freshness_min_factor), 3),
                "current_role": {
                    "role_code": operator_role,
                    "role_name": ROLE_CODE_TO_NAME.get(operator_role, "策划"),
                    "role_weight": round(role_weight, 3),
                },
                "role_weights": _round_dict({str(key): float(value) for key, value in ROLE_FEEDBACK_WEIGHT.items()}),
            },
        }

    def _make_current_feedback_items(
        self,
        ids: Sequence[int],
        *,
        weight: float,
        role_code: int,
        direction: str,
    ) -> List[Dict[str, Any]]:
        role_name = ROLE_CODE_TO_NAME.get(role_code, "策划")
        return [
            {
                "internal_id": internal_id,
                "weight": round(float(weight), 3),
                "source": "current_session",
                "source_label": "本轮反馈",
                "source_bucket": "current",
                "history_source": None,
                "role_code": role_code,
                "role_name": role_name,
                "role_weight": round(float(ROLE_FEEDBACK_WEIGHT.get(role_code, 1.0)), 3),
                "time_decay_factor": 1.0,
                "memory_score": round(float(weight), 3),
                "direction": direction,
            }
            for internal_id in list(dict.fromkeys(_normalize_id_list(list(ids))))
        ]

    def _make_history_feedback_items(
        self,
        rank_items: Sequence[Dict[str, Any]],
        *,
        source: str,
        source_decay: float,
        history_feedback_decay: float,
        role_time_decay_days: float,
        role_time_decay_min_factor: float,
        role_decay_overrides: Dict[str, Dict[str, float]],
        current_brand_stage: Optional[str],
        brand_stage_match_factor: float,
        brand_stage_mismatch_factor: float,
        campaign_freshness_decay_days: float,
        campaign_freshness_min_factor: float,
        limit: int,
        direction: str,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        source_label = "SPU 历史" if source == "spu_memory" else "用户历史"
        for item in list(rank_items)[:limit]:
            internal_id = _to_int(item.get("internal_id"))
            score = _to_float(item.get("score"), 0.0) or 0.0
            if internal_id is None or score <= 0:
                continue
            role_code = _normalize_role_code(item.get("role_code"))
            role_profile = self._resolve_role_decay_profile(
                role_code,
                default_days=role_time_decay_days,
                default_min_factor=role_time_decay_min_factor,
                overrides=role_decay_overrides,
            )
            time_decay = self._calculate_time_decay_factor(
                item.get("created_at"),
                decay_days=role_profile["decay_days"],
                min_factor=role_profile["min_factor"],
            )
            freshness_decay = self._calculate_campaign_freshness_factor(
                item.get("created_at"),
                decay_days=campaign_freshness_decay_days,
                min_factor=campaign_freshness_min_factor,
            )
            history_brand_stage = self._extract_brand_stage(item)
            stage_factor = 1.0
            if current_brand_stage and history_brand_stage:
                stage_factor = brand_stage_match_factor if current_brand_stage == history_brand_stage else brand_stage_mismatch_factor
            role_weight = _to_float(item.get("role_weight"), ROLE_FEEDBACK_WEIGHT.get(role_code, 1.0)) or 1.0
            weight = round(score * float(history_feedback_decay) * float(source_decay) * float(time_decay) * float(freshness_decay) * float(stage_factor), 3)
            items.append(
                {
                    "internal_id": internal_id,
                    "weight": weight,
                    "source": source,
                    "source_label": source_label,
                    "source_bucket": "history",
                    "history_source": source,
                    "role_code": role_code,
                    "role_name": item.get("role_name") or ROLE_CODE_TO_NAME.get(role_code, "策划"),
                    "role_weight": round(float(role_weight), 3),
                    "time_decay_factor": round(float(time_decay), 3),
                    "campaign_freshness_factor": round(float(freshness_decay), 3),
                    "brand_stage": history_brand_stage,
                    "brand_stage_factor": round(float(stage_factor), 3),
                    "memory_score": round(score, 3),
                    "created_at": self._to_iso_datetime(item.get("created_at")),
                    "campaign_id": _to_int(item.get("campaign_id")),
                    "role_decay_profile": role_profile,
                    "direction": direction,
                }
            )
        return items

    def _deduplicate_feedback_items(self, items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[int, Dict[str, Any]] = {}
        for item in items:
            internal_id = _to_int(item.get("internal_id"))
            if internal_id is None:
                continue
            if internal_id not in merged:
                merged[internal_id] = dict(item)
                merged[internal_id]["source_chain"] = [str(item.get("source_label") or item.get("source") or "未知")]
                merged[internal_id]["source_breakdown"] = [
                    {
                        "source": item.get("source"),
                        "source_label": item.get("source_label"),
                        "weight": item.get("weight"),
                        "time_decay_factor": item.get("time_decay_factor"),
                        "campaign_freshness_factor": item.get("campaign_freshness_factor"),
                        "brand_stage": item.get("brand_stage"),
                        "brand_stage_factor": item.get("brand_stage_factor"),
                        "created_at": item.get("created_at"),
                        "campaign_id": item.get("campaign_id"),
                    }
                ]
                continue
            merged[internal_id]["weight"] = round(float(merged[internal_id].get("weight") or 0.0) + float(item.get("weight") or 0.0), 3)
            merged[internal_id]["memory_score"] = round(float(merged[internal_id].get("memory_score") or 0.0) + float(item.get("memory_score") or 0.0), 3)
            merged[internal_id].setdefault("source_breakdown", []).append(
                {
                    "source": item.get("source"),
                    "source_label": item.get("source_label"),
                    "weight": item.get("weight"),
                    "time_decay_factor": item.get("time_decay_factor"),
                    "campaign_freshness_factor": item.get("campaign_freshness_factor"),
                    "brand_stage": item.get("brand_stage"),
                    "brand_stage_factor": item.get("brand_stage_factor"),
                    "created_at": item.get("created_at"),
                    "campaign_id": item.get("campaign_id"),
                }
            )
            label = str(item.get("source_label") or item.get("source") or "未知")
            if label not in merged[internal_id]["source_chain"]:
                merged[internal_id]["source_chain"].append(label)
        return list(merged.values())

    def _build_weight_change_explanation(
        self,
        *,
        base_tag_weights: Dict[str, float],
        feedback_candidates: Dict[str, Any],
        step: float,
        max_delta: float,
    ) -> Dict[str, Any]:
        positive_sources = [
            ("current_positive", feedback_candidates.get("current_positive") or []),
            ("history_positive", feedback_candidates.get("history_positive") or []),
        ]
        negative_sources = [
            ("current_negative", feedback_candidates.get("current_negative") or []),
            ("history_negative", feedback_candidates.get("history_negative") or []),
        ]

        feedback_signals = self._collect_feedback_tag_signals(positive_sources, negative_sources)
        after = dict(base_tag_weights)
        deltas: List[Dict[str, Any]] = []
        keys = set(base_tag_weights.keys()) | set(feedback_signals.keys())
        for key in sorted(keys):
            signal = feedback_signals.get(key) or {
                "positive": 0.0,
                "negative": 0.0,
                "positive_examples": [],
                "negative_examples": [],
                "positive_source_weights": {},
                "negative_source_weights": {},
            }
            before_value = float(base_tag_weights.get(key, 1.0 if signal["positive"] > signal["negative"] else 0.8))
            net_signal = float(signal["positive"] or 0.0) - float(signal["negative"] or 0.0)
            delta = float(np.tanh(net_signal / 2.0) * float(step))
            delta = _clamp(delta, -float(max_delta), float(max_delta))
            after_value = round(_clamp(before_value + delta, 0.0, 2.0), 3)
            if abs(after_value - before_value) < 0.03:
                after_value = round(before_value, 3)
                delta = 0.0
            after[key] = after_value
            if abs(delta) < 1e-6:
                continue
            direction = "up" if delta > 0 else "down"
            deltas.append(
                {
                    "key": key,
                    "display_name": _tag_display_name(key),
                    "before": round(before_value, 3),
                    "after": after_value,
                    "delta": round(after_value - before_value, 3),
                    "direction": direction,
                    "positive_score": round(float(signal["positive"] or 0.0), 3),
                    "negative_score": round(float(signal["negative"] or 0.0), 3),
                    "positive_source_weights": _round_dict(signal["positive_source_weights"]),
                    "negative_source_weights": _round_dict(signal["negative_source_weights"]),
                    "positive_examples": signal["positive_examples"][:4],
                    "negative_examples": signal["negative_examples"][:4],
                    "reason": self._build_weight_reason(direction, signal),
                }
            )

        promoted = [item for item in deltas if item["direction"] == "up"]
        demoted = [item for item in deltas if item["direction"] == "down"]
        promoted.sort(key=lambda item: abs(float(item["delta"])), reverse=True)
        demoted.sort(key=lambda item: abs(float(item["delta"])), reverse=True)
        deltas.sort(key=lambda item: abs(float(item["delta"])), reverse=True)
        summary_parts: List[str] = []
        if promoted:
            top = promoted[0]
            summary_parts.append(
                f"{top['display_name']} 从 {top['before']:.1f} 上调到 {top['after']:.1f}。"
            )
        if demoted:
            top = demoted[0]
            summary_parts.append(
                f"{top['display_name']} 从 {top['before']:.1f} 下调到 {top['after']:.1f}。"
            )
        if not summary_parts:
            summary_parts.append("当前反馈对 tag 权重未形成显著改动，继续沿用上一轮配置。")

        return {
            "before": _round_dict(base_tag_weights),
            "after": _round_dict(after),
            "deltas": deltas,
            "promoted": promoted,
            "demoted": demoted,
            "summary": " ".join(summary_parts),
        }

    def _build_weight_reason(self, direction: str, signal: Dict[str, Any]) -> str:
        positive_labels = ", ".join(signal["positive_source_weights"].keys()) or "正反馈"
        negative_labels = ", ".join(signal["negative_source_weights"].keys()) or "负反馈"
        if direction == "up":
            return f"该 tag 在 {positive_labels} 中获得更强支持，因此被系统自动升权。"
        return f"该 tag 在 {negative_labels} 中负反馈更强，因此被系统自动降权。"

    def _collect_feedback_tag_signals(
        self,
        positive_sources: Sequence[Tuple[str, Sequence[Dict[str, Any]]]],
        negative_sources: Sequence[Tuple[str, Sequence[Dict[str, Any]]]],
    ) -> Dict[str, Dict[str, Any]]:
        signals: Dict[str, Dict[str, Any]] = {}
        all_ids: List[int] = []
        for _, items in list(positive_sources) + list(negative_sources):
            all_ids.extend([item.get("internal_id") for item in items])
        tag_map = self._fetch_influencer_tags_by_ids(_normalize_id_list(all_ids))
        key_aliases: Dict[str, str] = {}
        for tags in tag_map.values():
            for tag in tags:
                alias = tag.lower()
                key_aliases.setdefault(alias, tag)

        profile_map = self._fetch_influencer_profiles_by_ids(_normalize_id_list(all_ids))

        def ensure_slot(tag_key: str) -> Dict[str, Any]:
            slot = signals.setdefault(
                tag_key,
                {
                    "positive": 0.0,
                    "negative": 0.0,
                    "positive_examples": [],
                    "negative_examples": [],
                    "positive_source_weights": defaultdict(float),
                    "negative_source_weights": defaultdict(float),
                },
            )
            return slot

        def resolve_key(raw_tag: str) -> str:
            text = raw_tag.strip()
            if not text:
                return ""
            return key_aliases.get(text.lower(), text)

        for source_name, items in positive_sources:
            for item in items:
                internal_id = _to_int(item.get("internal_id"))
                if internal_id is None:
                    continue
                for tag in tag_map.get(internal_id, []):
                    tag_key = resolve_key(tag)
                    if not tag_key:
                        continue
                    slot = ensure_slot(tag_key)
                    weight = float(item.get("weight") or 0.0)
                    slot["positive"] += weight
                    source_label = str(item.get("source_label") or source_name)
                    slot["positive_source_weights"][source_label] += weight
                    if len(slot["positive_examples"]) < 4:
                        profile = profile_map.get(internal_id) or {}
                        slot["positive_examples"].append(
                            {
                                "internal_id": internal_id,
                                "display_name": profile.get("nickname") or profile.get("name") or f"达人 {internal_id}",
                                "tags": tag_map.get(internal_id, []),
                                "source": source_label,
                                "source_bucket": item.get("source_bucket") or ("current" if str(item.get("source")) == "current_session" else "history"),
                                "history_source": item.get("history_source"),
                                "role_name": item.get("role_name"),
                                "time_decay_factor": round(float(item.get("time_decay_factor") or 1.0), 3),
                                "weight": round(weight, 3),
                            }
                        )

        for source_name, items in negative_sources:
            for item in items:
                internal_id = _to_int(item.get("internal_id"))
                if internal_id is None:
                    continue
                for tag in tag_map.get(internal_id, []):
                    tag_key = resolve_key(tag)
                    if not tag_key:
                        continue
                    slot = ensure_slot(tag_key)
                    weight = float(item.get("weight") or 0.0)
                    slot["negative"] += weight
                    source_label = str(item.get("source_label") or source_name)
                    slot["negative_source_weights"][source_label] += weight
                    if len(slot["negative_examples"]) < 4:
                        profile = profile_map.get(internal_id) or {}
                        slot["negative_examples"].append(
                            {
                                "internal_id": internal_id,
                                "display_name": profile.get("nickname") or profile.get("name") or f"达人 {internal_id}",
                                "tags": tag_map.get(internal_id, []),
                                "source": source_label,
                                "source_bucket": item.get("source_bucket") or ("current" if str(item.get("source")) == "current_session" else "history"),
                                "history_source": item.get("history_source"),
                                "role_name": item.get("role_name"),
                                "time_decay_factor": round(float(item.get("time_decay_factor") or 1.0), 3),
                                "weight": round(weight, 3),
                            }
                        )

        normalized: Dict[str, Dict[str, Any]] = {}
        for key, value in signals.items():
            normalized[key] = {
                "positive": round(float(value["positive"]), 3),
                "negative": round(float(value["negative"]), 3),
                "positive_examples": value["positive_examples"],
                "negative_examples": value["negative_examples"],
                "positive_source_weights": dict(value["positive_source_weights"]),
                "negative_source_weights": dict(value["negative_source_weights"]),
            }
        return normalized

    def _fetch_influencer_profiles_by_ids(self, ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
        database = self._require_db()
        normalized_ids = list(dict.fromkeys(_normalize_id_list(list(ids))))
        output: Dict[int, Dict[str, Any]] = {}
        for internal_id in normalized_ids:
            try:
                profile = database.get_influencer_by_id(internal_id)
            except Exception:
                profile = None
            if isinstance(profile, dict):
                output[internal_id] = profile
        return output

    def _fetch_influencer_tags_by_ids(self, ids: Sequence[int]) -> Dict[int, List[str]]:
        profile_map = self._fetch_influencer_profiles_by_ids(ids)
        output: Dict[int, List[str]] = {}
        for internal_id, profile in profile_map.items():
            tags = self._extract_tags_from_profile(profile)
            if tags:
                output[internal_id] = tags
        return output

    def _extract_tags_from_profile(self, profile: Any) -> List[str]:
        if not isinstance(profile, dict):
            return []
        raw_tags = profile.get("tags")
        if isinstance(raw_tags, str):
            parsed_list = _safe_json_list(raw_tags)
            if parsed_list:
                return _normalize_tags(parsed_list)
            parsed_dict = _safe_json_dict(raw_tags)
            if parsed_dict:
                flattened: List[str] = []
                for value in parsed_dict.values():
                    flattened.extend(_normalize_tags(value))
                return flattened
            return _normalize_tags([item.strip() for item in raw_tags.replace("，", ",").split(",") if item.strip()])
        if isinstance(raw_tags, list):
            return _normalize_tags(raw_tags)
        if isinstance(raw_tags, dict):
            flattened: List[str] = []
            for value in raw_tags.values():
                flattened.extend(_normalize_tags(value))
            return flattened
        return []

    def _fetch_vectors_by_ids(self, ids: Sequence[int], vector_field: str) -> Dict[int, List[float]]:
        normalized_ids = list(dict.fromkeys(_normalize_id_list(list(ids))))
        if not normalized_ids:
            return {}
        try:
            from milvus import milvus_mgr

            manager = milvus_mgr
            manager.connect()
            manager.load_collection()
            rows = manager.get_entities_by_ids(normalized_ids, output_fields=["id", vector_field])
            output: Dict[int, List[float]] = {}
            for row in rows:
                internal_id = _to_int(row.get("id"))
                vector = row.get(vector_field)
                if internal_id is None or not isinstance(vector, list) or not vector:
                    continue
                output[internal_id] = _normalize_vector(vector)
            return output
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("读取 Milvus 向量失败，将跳过 Rocchio 进化: %s", exc)
            return {}

    def _build_rocchio_query(
        self,
        *,
        base_query_vector: Sequence[float],
        vector_field: str,
        current_positive_candidates: Sequence[Dict[str, Any]],
        current_negative_candidates: Sequence[Dict[str, Any]],
        history_positive_candidates: Sequence[Dict[str, Any]],
        history_negative_candidates: Sequence[Dict[str, Any]],
        alpha: float,
        beta: float,
        gamma: float,
        operator_role: int,
        strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        base_vector = np.array(_normalize_vector(base_query_vector), dtype=np.float32)
        all_ids: List[int] = []
        for group in (
            current_positive_candidates,
            current_negative_candidates,
            history_positive_candidates,
            history_negative_candidates,
        ):
            all_ids.extend([item.get("internal_id") for item in group])
        vector_map = self._fetch_vectors_by_ids(_normalize_id_list(all_ids), vector_field)

        current_positive_meta = self._build_weighted_vector_group(current_positive_candidates, vector_map)
        current_negative_meta = self._build_weighted_vector_group(current_negative_candidates, vector_map)
        history_positive_meta = self._build_weighted_vector_group(history_positive_candidates, vector_map)
        history_negative_meta = self._build_weighted_vector_group(history_negative_candidates, vector_map)

        if not any(
            meta["applied"]
            for meta in (
                current_positive_meta,
                current_negative_meta,
                history_positive_meta,
                history_negative_meta,
            )
        ):
            return {
                "applied": False,
                "method": "rocchio",
                "alpha": float(alpha),
                "beta": float(beta),
                "gamma": float(gamma),
                "current_role": {
                    "role_code": operator_role,
                    "role_name": ROLE_CODE_TO_NAME.get(operator_role, "策划"),
                    "role_weight": ROLE_FEEDBACK_WEIGHT.get(operator_role, 1.0),
                },
                "strategy": {
                    **strategy,
                    "role_weights": _round_dict({str(key): float(value) for key, value in ROLE_FEEDBACK_WEIGHT.items()}),
                },
                "breakdown": {
                    "current_positive": current_positive_meta,
                    "current_negative": current_negative_meta,
                    "history_positive": history_positive_meta,
                    "history_negative": history_negative_meta,
                },
                "message": "缺少可用于进化的 selected/rejected 向量，已回退到基础查询向量。",
                "query_vector": base_vector.tolist(),
            }

        evolved = base_vector * float(alpha)
        if current_positive_meta["applied"]:
            evolved += np.array(current_positive_meta["centroid"], dtype=np.float32) * float(beta) * float(current_positive_meta["effective_weight"])
        if history_positive_meta["applied"]:
            evolved += np.array(history_positive_meta["centroid"], dtype=np.float32) * float(beta) * float(history_positive_meta["effective_weight"])
        if current_negative_meta["applied"]:
            evolved -= np.array(current_negative_meta["centroid"], dtype=np.float32) * float(gamma) * float(current_negative_meta["effective_weight"])
        if history_negative_meta["applied"]:
            evolved -= np.array(history_negative_meta["centroid"], dtype=np.float32) * float(gamma) * float(history_negative_meta["effective_weight"])
        normalized = _normalize_vector(evolved.tolist())
        return {
            "applied": True,
            "method": "rocchio",
            "alpha": float(alpha),
            "beta": float(beta),
            "gamma": float(gamma),
            "current_role": {
                "role_code": operator_role,
                "role_name": ROLE_CODE_TO_NAME.get(operator_role, "策划"),
                "role_weight": ROLE_FEEDBACK_WEIGHT.get(operator_role, 1.0),
            },
            "strategy": {
                **strategy,
                "role_weights": _round_dict({str(key): float(value) for key, value in ROLE_FEEDBACK_WEIGHT.items()}),
            },
            "breakdown": {
                "current_positive": current_positive_meta,
                "current_negative": current_negative_meta,
                "history_positive": history_positive_meta,
                "history_negative": history_negative_meta,
            },
            "message": "已区分本轮反馈与历史反馈执行 Rocchio 进化，并叠加角色权重衰减策略。",
            "query_vector": normalized,
        }

    def _build_weighted_vector_group(
        self,
        items: Sequence[Dict[str, Any]],
        vector_map: Dict[int, List[float]],
    ) -> Dict[str, Any]:
        vectors: List[np.ndarray] = []
        weights: List[float] = []
        used_ids: List[int] = []
        by_source: Dict[str, float] = defaultdict(float)
        for item in items:
            internal_id = _to_int(item.get("internal_id"))
            if internal_id is None or internal_id not in vector_map:
                continue
            weight = _to_float(item.get("weight"), 0.0) or 0.0
            if weight <= 0:
                continue
            vectors.append(np.array(vector_map[internal_id], dtype=np.float32))
            weights.append(weight)
            used_ids.append(internal_id)
            source_label = str(item.get("source_label") or item.get("source") or "未知")
            by_source[source_label] += weight

        if not vectors:
            return {
                "applied": False,
                "requested_ids": _normalize_id_list([item.get("internal_id") for item in items]),
                "used_ids": [],
                "count": 0,
                "effective_weight": 0.0,
                "by_source": {},
                "centroid": [],
            }

        stacked = np.stack(vectors, axis=0)
        centroid = np.average(stacked, axis=0, weights=np.array(weights, dtype=np.float32))
        normalized_centroid = _normalize_vector(centroid.tolist())
        effective_weight = round(float(sum(weights)) / max(len(weights), 1), 3)
        return {
            "applied": True,
            "requested_ids": _normalize_id_list([item.get("internal_id") for item in items]),
            "used_ids": used_ids,
            "count": len(used_ids),
            "effective_weight": effective_weight,
            "by_source": _round_dict(dict(by_source)),
            "centroid": normalized_centroid,
        }

    def _require_db(self):
        if db is None:
            raise RuntimeError("数据库服务不可用，请先完成 PostgreSQL 环境配置。")
        return db


asset_service = AssetService()
