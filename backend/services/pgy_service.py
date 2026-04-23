from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests

from services.intent_parser import value_to_text
from services.openai_compat import build_openai_client
from services.pgy_cookie_source import has_pgy_cookie_source, pick_pgy_cookie_header

logger = logging.getLogger(__name__)

PGY_BLOGGER_SEARCH_URL = os.getenv(
    "PGY_BLOGGER_SEARCH_URL",
    "https://pgy.xiaohongshu.com/api/solar/cooperator/blogger/v2",
)
DEFAULT_BRAND_USER_ID = os.getenv("PGY_BRAND_USER_ID", "6438f862000000000e01e59a")
CATEGORY_TREE_PATH = Path(__file__).resolve().parents[1] / "data" / "pgy_category_tree.json"
DEFAULT_STYLE_DIM = 768

REQUIRED_BASE_PAYLOAD: Dict[str, Any] = {
    "searchType": 0,
    "column": "comprehensiverank",
    "sort": "desc",
    "pageNum": 1,
    "pageSize": 20,
    "brandUserId": DEFAULT_BRAND_USER_ID,
}

OPTIONAL_DEFAULTS: Dict[str, Any] = {
    "marketTarget": None,
    "audienceGroup": [],
    "contentTag": [],
    "personalTags": [],
    "gender": None,
    "location": None,
    "signed": -1,
    "featureTags": [],
    "fansNumberLower": None,
    "fansNumberUpper": None,
    "notePriceLower": -1,
    "notePriceUpper": -1,
    "videoPriceLower": -1,
    "videoPriceUpper": -1,
    "tradeType": "不限",
    "estimatePictureCpm": [],
    "estimateVideoCpm": [],
    "filterList": [],
    "inStar": 0,
    "newHighQuality": 0,
    "flagList": [
        {"flagType": "HAS_BRAND_COOP_BUYER_AUTH", "flagValue": "0"},
        {"flagType": "IS_HIGH_QUALITY", "flagValue": "0"},
    ],
    "filterIntention": False,
    "firstIndustry": "",
    "secondIndustry": "",
    "activityCodes": [],
    "excludeLowActive": False,
}


class PgyClientService:
    def __init__(
        self,
        *,
        url: str = PGY_BLOGGER_SEARCH_URL,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv("PGY_AUTHORIZATION") or has_pgy_cookie_source())

    @staticmethod
    def build_headers(overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://pgy.xiaohongshu.com",
            "Referer": "https://pgy.xiaohongshu.com/solar/pre-trade/note/kol",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            ),
        }
        authorization = value_to_text(os.getenv("PGY_AUTHORIZATION"))
        cookie = value_to_text(os.getenv("PGY_COOKIE")) or pick_pgy_cookie_header()
        trace_id = value_to_text(os.getenv("PGY_TRACE_ID")) or uuid.uuid4().hex[:16]
        if authorization:
            headers["Authorization"] = authorization
        if cookie:
            headers["Cookie"] = cookie
        headers["X-B3-Traceid"] = trace_id
        if overrides:
            headers.update({key: value for key, value in overrides.items() if value is not None})
        return headers

    @staticmethod
    def apply_request_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(payload)
        normalized.setdefault("brandUserId", DEFAULT_BRAND_USER_ID)
        normalized.setdefault("trackId", "kolSearch_" + uuid.uuid4().hex)
        return normalized

    def fetch_page(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized_payload = self.apply_request_context(payload)
        response = self.session.post(
            self.url,
            headers=self.build_headers(),
            json=normalized_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        response_json = response.json()
        data = response_json.get("data") or {}
        kols = data.get("kols") or []
        total = data.get("total") if isinstance(data.get("total"), int) else len(kols)
        return {
            "payload": normalized_payload,
            "trackId": data.get("trackId") or normalized_payload.get("trackId"),
            "total": total,
            "kols": kols,
            "raw": response_json,
        }


class PgyPayloadService:
    def __init__(self, llm_enabled: Optional[bool] = None) -> None:
        if llm_enabled is None:
            llm_enabled = os.getenv("KOL_LENS_DISABLE_LLM", "0") != "1"
        self._llm_enabled = bool(llm_enabled)
        self._model_name = os.getenv("KOL_LENS_INTENT_MODEL", "qwen3.6-plus-2026-04-02")
        self._category_tree_cache: Optional[Dict[str, Any]] = None

    def build_default_payload(self, *, include_optional_defaults: bool = True) -> Dict[str, Any]:
        payload = dict(REQUIRED_BASE_PAYLOAD)
        if include_optional_defaults:
            for key, value in OPTIONAL_DEFAULTS.items():
                payload[key] = copy.deepcopy(value)
        return PgyClientService.apply_request_context(payload)

    def load_category_tree(self) -> Dict[str, Any]:
        if self._category_tree_cache is None:
            if CATEGORY_TREE_PATH.exists():
                self._category_tree_cache = json.loads(CATEGORY_TREE_PATH.read_text(encoding="utf-8"))
            else:
                self._category_tree_cache = {"primary_to_secondary": {}, "secondary_to_primary": {}}
        return self._category_tree_cache

    def get_primary_to_secondary(self) -> Dict[str, List[str]]:
        tree = self.load_category_tree()
        return {str(key): list(value) for key, value in (tree.get("primary_to_secondary") or {}).items()}

    def get_secondary_to_primary(self) -> Dict[str, str]:
        tree = self.load_category_tree()
        return {str(key): str(value) for key, value in (tree.get("secondary_to_primary") or {}).items()}

    def get_all_secondary_tags(self) -> List[str]:
        primary_to_secondary = self.get_primary_to_secondary()
        ordered: List[str] = []
        seen = set()
        for items in primary_to_secondary.values():
            for item in items:
                if item in seen:
                    continue
                seen.add(item)
                ordered.append(item)
        return ordered

    def normalize_payload(self, payload: Dict[str, Any], *, include_optional_defaults: bool = True) -> Dict[str, Any]:
        normalized = self.build_default_payload(include_optional_defaults=include_optional_defaults)
        for key, value in (payload or {}).items():
            normalized[key] = copy.deepcopy(value)
        return PgyClientService.apply_request_context(normalized)

    def parse_natural_language_to_payload(self, natural_language_query: str, *, base_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = self.normalize_payload(base_payload or {}, include_optional_defaults=True)
        query_text = value_to_text(natural_language_query)
        if not query_text:
            return {
                "natural_language_query": "",
                "selected_content_tags": [],
                "reasoning": "未提供内容描述，跳过 contentTag 生成。",
                "payload": payload,
            }
        primary_to_secondary = self.get_primary_to_secondary()
        all_secondary_tags = self.get_all_secondary_tags()
        selected = self._select_content_tags(query_text, primary_to_secondary, all_secondary_tags)
        payload["contentTag"] = selected
        return {
            "natural_language_query": query_text,
            "selected_content_tags": selected,
            "reasoning": "根据自然语言描述映射类目标签。" if selected else "未匹配到明确类目标签，保留空 contentTag。",
            "payload": payload,
        }

    def _select_content_tags(
        self,
        query_text: str,
        primary_to_secondary: Dict[str, List[str]],
        all_secondary_tags: Sequence[str],
    ) -> List[str]:
        if self._llm_enabled and all_secondary_tags:
            try:
                return self._select_tags_via_llm(query_text, primary_to_secondary, all_secondary_tags)
            except Exception as exc:  # pragma: no cover - 运行时回退
                logger.warning("LLM contentTag 选择失败，回退到规则匹配: %s", exc)
        matched: List[str] = []
        lower_query = query_text.lower()
        for tag in all_secondary_tags:
            if tag.lower() in lower_query and tag not in matched:
                matched.append(tag)
        if matched:
            return matched[:5]
        for primary, secondary_list in primary_to_secondary.items():
            if primary.lower() in lower_query:
                matched.extend(secondary_list[:2])
        return list(dict.fromkeys(matched))[:5]

    def _select_tags_via_llm(
        self,
        query_text: str,
        primary_to_secondary: Dict[str, List[str]],
        all_secondary_tags: Sequence[str],
    ) -> List[str]:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("openai 依赖不可用") from exc
        available_tags_text = "\n".join(
            f"{primary}: {', '.join(tags)}" for primary, tags in primary_to_secondary.items()
        )
        client = build_openai_client(
            api_key_envs=("KOL_LENS_INTENT_API_KEY",),
            base_url_envs=("KOL_LENS_INTENT_BASE_URL",),
        )
        completion = client.chat.completions.create(
            model=self._model_name,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是蒲公英找博主 payload 生成助手。"
                        "请只从给定类目树里选择最匹配的 contentTag，优先选择二级条目。"
                        "输出 JSON，格式为 {\"contentTag\": [\"条目1\", \"条目2\"]}。"
                        "最多返回 5 个，不要生成不存在的条目。\n\n类目树：\n"
                        + available_tags_text
                    ),
                },
                {"role": "user", "content": query_text},
            ],
        )
        content = value_to_text(completion.choices[0].message.content).replace("```json", "").replace("```", "").strip()
        payload = json.loads(content)
        tags = payload.get("contentTag") if isinstance(payload, dict) else []
        valid_tags = [str(tag) for tag in tags if str(tag) in all_secondary_tags or str(tag) in primary_to_secondary]
        return valid_tags[:5]

    def build_payload_variants(
        self,
        data_requirements: Dict[str, Any],
        query_plan: Dict[str, Any],
        *,
        page_size: int = 20,
        explicit_content_query: str = "",
    ) -> Dict[str, Any]:
        base_payload = self.build_default_payload(include_optional_defaults=True)
        base_payload["pageSize"] = max(1, min(int(page_size or 20), 50))
        self._set_lower_upper(base_payload, "fansNumberLower", "fansNumberUpper", data_requirements.get("fansNumRange"))

        content_text = value_to_text(explicit_content_query) or value_to_text((query_plan or {}).get("long_sentence_query"))
        content_payload: Dict[str, Any] = {}
        if content_text:
            parsed = self.parse_natural_language_to_payload(content_text, base_payload=base_payload)
            base_payload = parsed["payload"]
            content_payload = dict(parsed["payload"])

        picture_price_range = data_requirements.get("picturePriceRange")
        video_price_range = data_requirements.get("videoPriceRange")
        coop_price_range = data_requirements.get("coopPriceRange")
        picture_cpm_range = data_requirements.get("estimatePictureCpmRange")
        video_cpm_range = data_requirements.get("estimateVideoCpmRange")
        cpm_range = data_requirements.get("cpmRange")
        require_both_price_modes = bool(data_requirements.get("requireBothPriceModes"))
        require_both_cpm_modes = bool(data_requirements.get("requireBothCpmModes"))

        variants: List[Dict[str, Any]] = []
        if require_both_price_modes or require_both_cpm_modes:
            both_payload = copy.deepcopy(base_payload)
            self._set_lower_upper(both_payload, "notePriceLower", "notePriceUpper", picture_price_range or coop_price_range)
            self._set_lower_upper(both_payload, "videoPriceLower", "videoPriceUpper", video_price_range or coop_price_range)
            self._set_list_range(both_payload, "estimatePictureCpm", picture_cpm_range or cpm_range)
            self._set_list_range(both_payload, "estimateVideoCpm", video_cpm_range or cpm_range)
            variants.append(PgyClientService.apply_request_context(both_payload))
        else:
            if picture_price_range or picture_cpm_range or coop_price_range or cpm_range:
                picture_payload = copy.deepcopy(base_payload)
                picture_payload.pop("videoPriceLower", None)
                picture_payload.pop("videoPriceUpper", None)
                self._set_lower_upper(picture_payload, "notePriceLower", "notePriceUpper", picture_price_range or coop_price_range)
                self._set_list_range(picture_payload, "estimatePictureCpm", picture_cpm_range or cpm_range)
                variants.append(PgyClientService.apply_request_context(picture_payload))
            if video_price_range or video_cpm_range or coop_price_range or cpm_range:
                video_payload = copy.deepcopy(base_payload)
                video_payload.pop("notePriceLower", None)
                video_payload.pop("notePriceUpper", None)
                self._set_lower_upper(video_payload, "videoPriceLower", "videoPriceUpper", video_price_range or coop_price_range)
                self._set_list_range(video_payload, "estimateVideoCpm", video_cpm_range or cpm_range)
                variants.append(PgyClientService.apply_request_context(video_payload))
        if not variants:
            variants.append(PgyClientService.apply_request_context(base_payload))
        return {
            "content_payload": content_payload,
            "payload_variants": variants,
        }

    @staticmethod
    def _set_lower_upper(payload: Dict[str, Any], lower_key: str, upper_key: str, value_range: Optional[Sequence[Optional[int]]]) -> None:
        if not value_range:
            return
        lower, upper = value_range
        if lower is not None:
            payload[lower_key] = int(lower)
        if upper is not None:
            payload[upper_key] = int(upper)

    @staticmethod
    def _set_list_range(payload: Dict[str, Any], key: str, value_range: Optional[Sequence[Optional[int]]]) -> None:
        if not value_range:
            return
        lower, upper = value_range
        if lower == 0 and key in {"estimatePictureCpm", "estimateVideoCpm"}:
            lower = -1
        payload[key] = [lower, upper]


class PgyExpansionService:
    def __init__(
        self,
        *,
        payload_service: Optional[PgyPayloadService] = None,
        client: Optional[PgyClientService] = None,
    ) -> None:
        self.payload_service = payload_service or PgyPayloadService()
        self.client = client or PgyClientService()

    def generate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data_requirements = dict(payload.get("data_requirements") or {})
        query_plan = dict(payload.get("query_plan") or {})
        content_query = value_to_text(payload.get("content_query"))
        page_size = int(payload.get("page_size") or 20)
        bundle = self.payload_service.build_payload_variants(
            data_requirements,
            query_plan,
            page_size=page_size,
            explicit_content_query=content_query,
        )
        return {
            "content_query": content_query or value_to_text(query_plan.get("long_sentence_query")),
            "content_payload": bundle.get("content_payload") or {},
            "payload_variants": bundle.get("payload_variants") or [],
            "variant_count": len(bundle.get("payload_variants") or []),
        }

    def expand_library(
        self,
        *,
        data_requirements: Dict[str, Any],
        query_plan: Dict[str, Any],
        needed_count: int,
        brand_name: str = "",
        page_size: int = 20,
    ) -> Dict[str, Any]:
        bundle = self.payload_service.build_payload_variants(
            data_requirements,
            query_plan,
            page_size=page_size,
        )
        payload_variants = list(bundle.get("payload_variants") or [])
        content_payload = dict(bundle.get("content_payload") or {})
        if needed_count <= 0:
            return self._empty_expansion_result(content_payload, payload_variants)
        if not self.client.is_configured():
            return {
                **self._empty_expansion_result(content_payload, payload_variants),
                "attempted": False,
                "message": "未检测到蒲公英鉴权环境变量，已跳过外部扩库。",
            }

        existing_red_ids = self._collect_existing_red_ids()
        imported_internal_ids: List[int] = []
        imported_red_ids: List[str] = []
        variant_reports: List[Dict[str, Any]] = []
        pages_fetched = 0
        returned_red_ids: List[str] = []

        for index, payload in enumerate(payload_variants, start=1):
            remaining = max(needed_count - len(imported_red_ids), 0)
            if remaining <= 0:
                break
            variant_payload = copy.deepcopy(payload)
            variant_payload["pageSize"] = max(1, min(max(page_size, remaining), 50))
            first_page = self.client.fetch_page(variant_payload)
            pages_fetched += 1
            total = int(first_page.get("total") or 0)
            kols = list(first_page.get("kols") or [])
            max_pages = max(1, math.ceil(min(total, remaining) / max(int(variant_payload.get("pageSize") or 20), 1)))
            collected_rows = list(kols)
            for page_num in range(2, max_pages + 1):
                if len(collected_rows) >= remaining:
                    break
                next_payload = copy.deepcopy(variant_payload)
                next_payload["pageNum"] = page_num
                page_result = self.client.fetch_page(next_payload)
                pages_fetched += 1
                collected_rows.extend(page_result.get("kols") or [])
            collected_rows = collected_rows[:remaining]
            returned_ids_for_variant = [self._row_red_id(row) for row in collected_rows if self._row_red_id(row)]
            returned_red_ids.extend(returned_ids_for_variant)
            ingest_result = self._upsert_external_creators(collected_rows, brand_name=brand_name)
            imported_internal_ids.extend(ingest_result["internal_ids"])
            imported_red_ids.extend(ingest_result["red_ids"])
            variant_reports.append(
                {
                    "variant_index": index,
                    "track_id": first_page.get("trackId"),
                    "requested_count": remaining,
                    "returned_count": len(returned_ids_for_variant),
                    "imported_count": len(ingest_result["red_ids"]),
                    "existing_count": len([rid for rid in returned_ids_for_variant if rid in existing_red_ids]),
                    "payload": variant_payload,
                }
            )

        deduped_returned = list(dict.fromkeys([item for item in returned_red_ids if item]))
        deduped_imported = list(dict.fromkeys([item for item in imported_red_ids if item]))
        new_red_ids = [item for item in deduped_imported if item not in existing_red_ids]
        existing_hits = [item for item in deduped_returned if item in existing_red_ids]
        return {
            "attempted": True,
            "requested_count": int(needed_count),
            "variant_count": len(payload_variants),
            "content_payload": content_payload,
            "payload_variants": payload_variants,
            "variant_reports": variant_reports,
            "pages_fetched": pages_fetched,
            "returned_uid_count": len(deduped_returned),
            "new_uid_count": len(new_red_ids),
            "existing_uid_count": len(existing_hits),
            "returned_uids": deduped_returned,
            "new_uids": new_red_ids,
            "existing_uids": existing_hits,
            "imported_internal_ids": list(dict.fromkeys(imported_internal_ids)),
            "message": "扩库完成。",
        }

    @staticmethod
    def _empty_expansion_result(content_payload: Dict[str, Any], payload_variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "attempted": False,
            "requested_count": 0,
            "variant_count": len(payload_variants),
            "content_payload": content_payload,
            "payload_variants": payload_variants,
            "variant_reports": [],
            "pages_fetched": 0,
            "returned_uid_count": 0,
            "new_uid_count": 0,
            "existing_uid_count": 0,
            "returned_uids": [],
            "new_uids": [],
            "existing_uids": [],
            "imported_internal_ids": [],
        }

    def _collect_existing_red_ids(self) -> set[str]:
        db_client = _safe_get_db_client()
        if db_client is None:
            return set()
        try:
            db_client.connect()
            with db_client.get_cursor() as cur:
                cur.execute("SELECT red_id FROM influencer_basics")
                return {value_to_text(row["red_id"]) for row in cur.fetchall() if value_to_text(row["red_id"])}
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("读取现有达人 red_id 失败，将按空库处理: %s", exc)
            return set()
        finally:
            try:
                db_client.close()
            except Exception:
                pass

    def _upsert_external_creators(self, kol_rows: Sequence[Dict[str, Any]], *, brand_name: str = "") -> Dict[str, Any]:
        internal_ids: List[int] = []
        red_ids: List[str] = []
        db_client = _safe_get_db_client()
        if db_client is None:
            return {"internal_ids": internal_ids, "red_ids": red_ids}

        milvus_rows: List[Dict[str, Any]] = []
        try:
            db_client.connect()
            for kol_row in kol_rows:
                influencer_payload = self._map_kol_to_influencer_record(kol_row, brand_name=brand_name)
                red_id = value_to_text(influencer_payload.get("red_id"))
                if not red_id:
                    continue
                internal_id = int(db_client.insert_influencer(influencer_payload))
                internal_ids.append(internal_id)
                red_ids.append(red_id)
                for note in self._iter_note_records(kol_row, internal_id):
                    try:
                        db_client.insert_note(note)
                    except Exception as exc:  # pragma: no cover - 单条笔记写入失败不阻塞主流程
                        logger.warning("写入达人笔记失败 red_id=%s note_id=%s: %s", red_id, note.get("note_id"), exc)
                milvus_rows.append(self._build_milvus_row(internal_id, influencer_payload, kol_row))
        except Exception as exc:  # pragma: no cover - 依赖运行环境
            logger.warning("外部达人入库失败，已回退为仅返回外部数据: %s", exc)
        finally:
            try:
                db_client.close()
            except Exception:
                pass

        _safe_upsert_milvus_rows(milvus_rows)
        return {"internal_ids": internal_ids, "red_ids": red_ids}

    def _map_kol_to_influencer_record(self, kol_row: Dict[str, Any], *, brand_name: str = "") -> Dict[str, Any]:
        content_tags = self._extract_content_tags(kol_row)
        feature_tags = [value_to_text(item) for item in (kol_row.get("featureTags") or []) if value_to_text(item)]
        personal_tags = [value_to_text(item) for item in (kol_row.get("personalTags") or []) if value_to_text(item)]
        merged_tags = list(dict.fromkeys([*content_tags, *feature_tags, *personal_tags]))
        if brand_name and brand_name not in merged_tags:
            merged_tags.append(brand_name)
        pricing = {
            "picture_price": _safe_int(kol_row.get("picturePrice")),
            "video_price": _safe_int(kol_row.get("videoPrice")),
            "lower_price": _safe_int(kol_row.get("lowerPrice")),
            "estimate_picture_cpm": _safe_int(kol_row.get("estimatePictureCpm")),
            "estimate_video_cpm": _safe_int(kol_row.get("estimateVideoCpm")),
        }
        note_list = list(kol_row.get("noteList") or [])
        return {
            "red_id": self._row_red_id(kol_row),
            "nickname": value_to_text(kol_row.get("name")) or self._row_red_id(kol_row),
            "avatar_url": value_to_text(kol_row.get("headPhoto")),
            "gender": value_to_text(kol_row.get("gender")) or "未知",
            "region": value_to_text(kol_row.get("location")),
            "followers": _safe_int(kol_row.get("fansNum")),
            "likes": _safe_int(kol_row.get("likes")),
            "collections": _safe_int(kol_row.get("collections")),
            "notes_count": len(note_list),
            "ad_ratio_30d": _safe_ad_ratio(kol_row),
            "latest_note_time": None,
            "tags": merged_tags,
            "pricing": pricing,
        }

    def _iter_note_records(self, kol_row: Dict[str, Any], influencer_id: int) -> Iterable[Dict[str, Any]]:
        for index, note in enumerate(kol_row.get("noteList") or [], start=1):
            if not isinstance(note, dict):
                continue
            note_id = value_to_text(note.get("noteId") or note.get("id") or note.get("note_id"))
            if not note_id:
                note_id = f"{self._row_red_id(kol_row)}:{index}"
            note_type = value_to_text(note.get("noteType") or note.get("type")) or ("视频" if note.get("videoUrl") else "图文")
            yield {
                "note_id": note_id,
                "influencer_id": influencer_id,
                "note_type": note_type,
                "is_ad": bool(note.get("isAd") or note.get("is_ad")),
                "impressions": _safe_int(note.get("impressions") or note.get("exposure")),
                "reads": _safe_int(note.get("reads") or note.get("readCount")),
                "likes": _safe_int(note.get("likes") or note.get("likeCount")),
                "comments": _safe_int(note.get("comments") or note.get("commentCount")),
                "collections": _safe_int(note.get("collections") or note.get("collectCount")),
                "shares": _safe_int(note.get("shares") or note.get("shareCount")),
                "video_completion_rate": _safe_float(note.get("videoCompletionRate")),
                "cover_image_url": value_to_text(note.get("imageUrl") or note.get("imgUrl") or note.get("coverUrl")),
                "published_at": None,
            }

    def _build_milvus_row(
        self,
        internal_id: int,
        influencer_payload: Dict[str, Any],
        kol_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        avatar_url = value_to_text(kol_row.get("headPhoto") or influencer_payload.get("avatar_url"))
        note_list = list(kol_row.get("noteList") or [])
        cover_urls: List[str] = []
        for note in note_list:
            if not isinstance(note, dict):
                continue
            url = value_to_text(note.get("imageUrl") or note.get("imgUrl") or note.get("coverUrl"))
            if url:
                cover_urls.append(url)
            if len(cover_urls) >= 2:
                break
        style_vector = _embed_multimodal_profile_vector(
            avatar_url=avatar_url,
            cover_urls=cover_urls,
            dim=DEFAULT_STYLE_DIM,
        )
        if not style_vector:
            query_text = self._build_style_text(influencer_payload)
            style_vector = _embed_text_to_style_vector(query_text)
        return {
            "id": int(internal_id),
            "followers": _safe_int(influencer_payload.get("followers")),
            "region": value_to_text(influencer_payload.get("region")),
            "gender": value_to_text(influencer_payload.get("gender")) or "未知",
            "ad_ratio": float(influencer_payload.get("ad_ratio_30d") or 0.0),
            "v_face": [0.0] * 512,
            "v_scene": style_vector,
            "v_overall_style": style_vector,
        }

    @staticmethod
    def _build_style_text(influencer_payload: Dict[str, Any]) -> str:
        tags = influencer_payload.get("tags") or []
        pricing = influencer_payload.get("pricing") or {}
        parts = [
            value_to_text(influencer_payload.get("nickname")),
            value_to_text(influencer_payload.get("region")),
            "、".join([value_to_text(item) for item in tags if value_to_text(item)]),
            f"图文报价:{pricing.get('picture_price') or ''}",
            f"视频报价:{pricing.get('video_price') or ''}",
            f"图文CPM:{pricing.get('estimate_picture_cpm') or ''}",
            f"视频CPM:{pricing.get('estimate_video_cpm') or ''}",
        ]
        return "，".join([part for part in parts if value_to_text(part)]) or "default_style_seed"

    @staticmethod
    def _extract_content_tags(kol_row: Dict[str, Any]) -> List[str]:
        tags: List[str] = []
        for item in kol_row.get("contentTags") or []:
            if not isinstance(item, dict):
                continue
            taxonomy1 = value_to_text(item.get("taxonomy1Tag"))
            if taxonomy1:
                tags.append(taxonomy1)
            for taxonomy2 in item.get("taxonomy2Tags") or []:
                text = value_to_text(taxonomy2)
                if text:
                    tags.append(text)
        return list(dict.fromkeys(tags))

    @staticmethod
    def _row_red_id(kol_row: Dict[str, Any]) -> str:
        return value_to_text(kol_row.get("redId") or kol_row.get("userId"))



def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0



def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None



def _safe_ad_ratio(kol_row: Dict[str, Any]) -> float:
    ratio = _safe_float(kol_row.get("adRatio30d") or kol_row.get("adRatio"))
    return float(ratio or 0.0)



def _normalize_vector(vector: Sequence[float]) -> List[float]:
    array = np.array(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        array = np.ones(len(array), dtype=np.float32)
        norm = float(np.linalg.norm(array))
    return (array / norm).astype(np.float32).tolist()



def _tokenize_text(text: str) -> List[str]:
    normalized = value_to_text(text)
    if not normalized:
        return []
    segments = [segment.strip() for segment in re.split(r"[，,；;。\n]+", normalized) if segment and segment.strip()]
    tokens: List[str] = []
    for segment in segments or [normalized]:
        tokens.append(segment)
        if len(segment) > 2:
            tokens.extend(segment[index:index + 2] for index in range(0, len(segment) - 1))
    return list(dict.fromkeys(tokens))



def _embed_text_to_style_vector(text: str, *, dim: int = DEFAULT_STYLE_DIM) -> List[float]:
    normalized = value_to_text(text)
    if not normalized:
        normalized = "default_style_seed"
    try:
        from openai import OpenAI

        model_name = os.getenv("KOL_LENS_EMBEDDING_MODEL", "qwen3-vl-embedding")
        client = build_openai_client(
            api_key_envs=("KOL_LENS_EMBEDDING_API_KEY",),
            base_url_envs=("KOL_LENS_EMBEDDING_BASE_URL",),
        )
        embedding = client.embeddings.create(model=model_name, input=normalized)
        vector = embedding.data[0].embedding
        if vector:
            if len(vector) >= dim:
                return _normalize_vector(vector[:dim])
            return _normalize_vector(list(vector) + [0.0] * (dim - len(vector)))
    except Exception:
        pass

    vector = np.zeros(dim, dtype=np.float32)
    for token in _tokenize_text(normalized):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = np.random.default_rng(seed)
        vector += rng.standard_normal(dim).astype(np.float32)
    return _normalize_vector(vector)


def _embed_multimodal_profile_vector(
    *,
    avatar_url: str,
    cover_urls: Sequence[str],
    dim: int = DEFAULT_STYLE_DIM,
) -> List[float]:
    urls = [value_to_text(avatar_url)] + [value_to_text(url) for url in list(cover_urls)[:2]]
    urls = [url for url in urls if url]
    if not urls:
        return []
    try:
        model_name = os.getenv("KOL_LENS_EMBEDDING_MODEL", "qwen3-vl-embedding")
        client = build_openai_client(
            api_key_envs=("KOL_LENS_EMBEDDING_API_KEY",),
            base_url_envs=("KOL_LENS_EMBEDDING_BASE_URL",),
        )
        weighted_hint = (
            "为达人生成多模态检索向量：头像权重0.2，第一张笔记封面权重0.4，第二张笔记封面权重0.4。"
            "只需用于 embedding，不输出文本。"
        )
        input_payload: List[Dict[str, Any]] = [{"type": "text", "text": weighted_hint}]
        for url in urls:
            input_payload.append({"type": "image_url", "image_url": {"url": url}})
        embedding = client.embeddings.create(model=model_name, input=input_payload)
        vector = embedding.data[0].embedding
        if vector:
            if len(vector) >= dim:
                return _normalize_vector(vector[:dim])
            return _normalize_vector(list(vector) + [0.0] * (dim - len(vector)))
    except Exception:
        return []
    return []



def _safe_get_db_client():
    try:
        from db import db

        return db
    except Exception:
        return None



def _safe_upsert_milvus_rows(rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    try:
        from milvus import milvus_mgr

        milvus_mgr.connect()
        milvus_mgr.create_collection(drop_if_exists=False)
        milvus_mgr.load_collection()
        milvus_mgr.upsert(list(rows))
    except Exception as exc:  # pragma: no cover - 依赖运行环境
        logger.warning("Milvus 冷启动向量写入失败，已跳过: %s", exc)


pgy_payload_service = PgyPayloadService()
pgy_expansion_service = PgyExpansionService(payload_service=pgy_payload_service)
