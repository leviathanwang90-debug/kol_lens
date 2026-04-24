from __future__ import annotations

import csv
import json
import logging
import os
import random
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

from services.openai_compat import build_openai_client, first_env_value
from services.pgy_cookie_source import load_pgy_cookie_pool

try:  # pragma: no cover - 依赖运行环境时允许降级
    from db import db
except Exception:  # pragma: no cover
    db = None

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = DATA_DIR / "exports"
TEMPLATE_STORE_PATH = DATA_DIR / "export_templates.json"

for _path in (DATA_DIR, EXPORT_DIR):
    _path.mkdir(parents=True, exist_ok=True)

EMPTY_RESPONSE_TEXT = '{"msg":"","result":0,"success":true}'
REQUEST_TIMEOUT_SECONDS = 20

SOURCE_ENDPOINTS = {
    "basic": "https://pgy.xiaohongshu.com/api/solar/cooperator/user/blogger/{uid}",
    "unit_price": "https://pgy.xiaohongshu.com/api/solar/kol/dataV2/costEffective?userId={uid}",
    "recent_notes": "https://pgy.xiaohongshu.com/api/solar/kol/dataV2/notesDetail?advertiseSwitch=1&orderType=1&pageNumber=1&pageSize=8&userId={uid}&noteType=3&withComponent=false",
    "fans_summary": "https://pgy.xiaohongshu.com/api/solar/kol/dataV3/fansSummary?userId={uid}",
    "fans_trend": "https://pgy.xiaohongshu.com/api/solar/kol/data/{uid}/fans_overall_new_history?dateType=1&increaseType=1",
    "fans_profile": "https://pgy.xiaohongshu.com/api/solar/kol/data/{uid}/fans_profile",
    "performance": "https://pgy.xiaohongshu.com/api/pgy/kol/data/core_data",
}

PERFORMANCE_VARIANTS = {
    "performance_daily_30": {"business": "0", "dateType": 1, "noteType": 3, "advertiseSwitch": 1},
    "performance_collab_30": {"business": "1", "dateType": 1, "noteType": 3, "advertiseSwitch": 1},
    "performance_daily_90": {"business": "0", "dateType": 2, "noteType": 3, "advertiseSwitch": 1},
    "performance_collab_90": {"business": "1", "dateType": 2, "noteType": 3, "advertiseSwitch": 1},
}

FIELD_CATALOG: List[Dict[str, Any]] = [
    {"key": "nickname", "label": "达人昵称", "group": "基础信息", "source": "basic", "default": True},
    {"key": "redbook_id", "label": "小红书号", "group": "基础信息", "source": "basic", "default": True},
    {"key": "region", "label": "地区", "group": "基础信息", "source": "basic", "default": True},
    {"key": "institution_name", "label": "所属机构", "group": "基础信息", "source": "basic", "default": False},
    {"key": "content_tags", "label": "内容标签", "group": "基础信息", "source": "basic", "default": True},
    {"key": "personal_tags", "label": "人设标签", "group": "基础信息", "source": "basic", "default": False},
    {"key": "feature_tags", "label": "特征标签", "group": "基础信息", "source": "basic", "default": False},
    {"key": "fans_count", "label": "粉丝量", "group": "基础信息", "source": "basic", "default": True},
    {"key": "likes_collect_count", "label": "赞藏总量", "group": "基础信息", "source": "basic", "default": False},
    {"key": "picture_price", "label": "图文报价", "group": "基础信息", "source": "basic", "default": True},
    {"key": "video_price", "label": "视频报价", "group": "基础信息", "source": "basic", "default": True},
    {"key": "excellent_level", "label": "蒲公英等级", "group": "基础信息", "source": "basic", "default": False},
    {"key": "read_picture_unit_price", "label": "预估阅读单价（图文）", "group": "报价表现", "source": "unit_price", "default": True},
    {"key": "read_video_unit_price", "label": "预估阅读单价（视频）", "group": "报价表现", "source": "unit_price", "default": True},
    {"key": "recent_cooperative_brand", "label": "合作品牌", "group": "合作笔记", "source": "recent_notes", "default": True},
    {"key": "recent_note_image_urls", "label": "近8篇合作笔记图片", "group": "合作笔记", "source": "recent_notes", "default": False},
    {"key": "baby_age", "label": "出镜宝宝年龄", "group": "合作笔记", "source": "recent_notes", "default": False},
    {"key": "fans_trend", "label": "粉丝增量", "group": "粉丝画像", "source": "fans_summary", "default": True},
    {"key": "active_percent", "label": "活跃粉丝占比", "group": "粉丝画像", "source": "fans_summary", "default": True},
    {"key": "read_fans_rate", "label": "阅读粉丝占比", "group": "粉丝画像", "source": "fans_summary", "default": False},
    {"key": "engage_fans_rate", "label": "互动粉丝占比", "group": "粉丝画像", "source": "fans_summary", "default": False},
    {"key": "age_0_18_percent", "label": "粉丝年龄<18", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "age_18_25_percent", "label": "粉丝年龄18-24", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "age_25_35_percent", "label": "粉丝年龄25-34", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "age_35_45_percent", "label": "粉丝年龄35-44", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "age_45_100_percent", "label": "粉丝年龄>44", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "city_data", "label": "城市分布", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "province_data", "label": "省份分布", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "male_percent", "label": "男性占比", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "female_percent", "label": "女性占比", "group": "粉丝画像", "source": "fans_profile", "default": False},
    {"key": "fans_growth_trend", "label": "粉丝增长趋势图", "group": "粉丝画像", "source": "fans_trend", "default": False},
    {"key": "notenumber", "label": "笔记数", "group": "内容表现", "source": "performance_collab_30", "default": True},
    {"key": "videonotenumber", "label": "视频数", "group": "内容表现", "source": "performance_collab_30", "default": True},
    {"key": "daily_all_full_read_median_30", "label": "30天日常笔记阅读中位数", "group": "内容表现", "source": "performance_daily_30", "default": True},
    {"key": "daily_all_full_like_median_30", "label": "30天日常笔记点赞中位数", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_all_full_comment_median_30", "label": "30天日常笔记评论中位数", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_all_full_collect_median_30", "label": "30天日常笔记收藏中位数", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_all_full_interact_median_30", "label": "30天日常笔记互动中位数", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_all_full_imp_median_30", "label": "30天日常笔记曝光中位数", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_all_full_interaction_rate_30", "label": "30天日常笔记互动率", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "daily_video_completion_rate_30", "label": "30天日常笔记完播率", "group": "内容表现", "source": "performance_daily_30", "default": False},
    {"key": "cooperate_all_full_read_median_30", "label": "30天合作笔记阅读中位数", "group": "内容表现", "source": "performance_collab_30", "default": True},
    {"key": "cooperate_all_full_like_median_30", "label": "30天合作笔记点赞中位数", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_all_full_comment_median_30", "label": "30天合作笔记评论中位数", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_all_full_collect_median_30", "label": "30天合作笔记收藏中位数", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_all_full_interact_median_30", "label": "30天合作笔记互动中位数", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_all_full_imp_median_30", "label": "30天合作笔记曝光中位数", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_all_full_interaction_rate_30", "label": "30天合作笔记互动率", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "cooperate_video_completion_rate_30", "label": "30天合作笔记完播率", "group": "内容表现", "source": "performance_collab_30", "default": False},
    {"key": "daily_all_full_read_median_90", "label": "90天日常笔记阅读中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_like_median_90", "label": "90天日常笔记点赞中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_comment_median_90", "label": "90天日常笔记评论中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_collect_median_90", "label": "90天日常笔记收藏中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_interact_median_90", "label": "90天日常笔记互动中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_imp_median_90", "label": "90天日常笔记曝光中位数", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_all_full_interaction_rate_90", "label": "90天日常笔记互动率", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "daily_video_completion_rate_90", "label": "90天日常笔记完播率", "group": "内容表现", "source": "performance_daily_90", "default": False},
    {"key": "cooperate_all_full_read_median_90", "label": "90天合作笔记阅读中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_like_median_90", "label": "90天合作笔记点赞中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_comment_median_90", "label": "90天合作笔记评论中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_collect_median_90", "label": "90天合作笔记收藏中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_interact_median_90", "label": "90天合作笔记互动中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_imp_median_90", "label": "90天合作笔记曝光中位数", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_all_full_interaction_rate_90", "label": "90天合作笔记互动率", "group": "内容表现", "source": "performance_collab_90", "default": False},
    {"key": "cooperate_video_completion_rate_90", "label": "90天合作笔记完播率", "group": "内容表现", "source": "performance_collab_90", "default": False},
]

FIELD_INDEX = {item["key"]: item for item in FIELD_CATALOG}
DEFAULT_FIELD_KEYS = [item["key"] for item in FIELD_CATALOG if item.get("default")]


def _safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _extract_by_regex(text: str, pattern: str) -> str:
    if not text:
        return ""
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else ""


def _json_loads(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except Exception:
        return None


def _flatten_mapping(mapping: Dict[str, Any]) -> str:
    if not mapping:
        return ""
    ordered = sorted(mapping.items(), key=lambda item: item[1], reverse=True)
    return "；".join(f"{key}:{round(float(value) * 100, 2)}%" for key, value in ordered)


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _format_export_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        normalized = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(json.dumps(item, ensure_ascii=False))
            else:
                normalized.append(str(item))
        return " | ".join(normalized)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _guess_uid(creator: Dict[str, Any]) -> str:
    candidates = [
        creator.get("creator_uid"),
        creator.get("external_uid"),
        creator.get("uid"),
        creator.get("user_id"),
        creator.get("userId"),
        creator.get("redbook_id"),
        creator.get("red_id"),
    ]
    raw = creator.get("raw") if isinstance(creator.get("raw"), dict) else {}
    candidates.extend([
        raw.get("creator_uid"),
        raw.get("external_uid"),
        raw.get("uid"),
        raw.get("user_id"),
        raw.get("userId"),
        raw.get("redbook_id"),
        raw.get("red_id"),
    ])
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return ""


class ExportTemplateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def _load(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def list(self, *, operator_id: Optional[int] = None, brand_name: str = "", spu_name: str = "") -> List[Dict[str, Any]]:
        records = self._load()
        result: List[Dict[str, Any]] = []
        for record in records:
            if operator_id and record.get("operator_id") not in (None, operator_id):
                continue
            if brand_name and record.get("brand_name") not in ("", brand_name):
                continue
            if spu_name and record.get("spu_name") not in ("", spu_name):
                continue
            result.append(record)
        return sorted(result, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)

    def get(self, template_id: str) -> Optional[Dict[str, Any]]:
        for record in self._load():
            if record.get("template_id") == template_id:
                return record
        return None

    def save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = int(time.time())
        with self.lock:
            records = self._load()
            template_id = str(payload.get("template_id") or uuid.uuid4().hex)
            normalized = {
                "template_id": template_id,
                "template_name": str(payload.get("template_name") or "未命名模板").strip() or "未命名模板",
                "field_keys": [key for key in payload.get("field_keys") or [] if key in FIELD_INDEX],
                "brand_name": str(payload.get("brand_name") or "").strip(),
                "spu_name": str(payload.get("spu_name") or "").strip(),
                "operator_id": payload.get("operator_id"),
                "description": str(payload.get("description") or "").strip(),
                "updated_at": now,
            }
            for idx, record in enumerate(records):
                if record.get("template_id") == template_id:
                    normalized["created_at"] = record.get("created_at", now)
                    records[idx] = {**record, **normalized}
                    break
            else:
                normalized["created_at"] = now
                records.append(normalized)
            self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return normalized


class CreatorFullDataProvider:
    def __init__(self) -> None:
        self.session = requests.Session()

    def _load_cookie_pool(self) -> List[str]:
        return load_pgy_cookie_pool()

    def _pick_cookie(self, cookies: Sequence[str]) -> str:
        if not cookies:
            return ""
        return random.choice(list(cookies))

    def _request_text(self, method: str, url: str, *, payload: Optional[Dict[str, Any]] = None) -> str:
        cookies = self._load_cookie_pool()
        if not cookies:
            raise ValueError("未找到可用的 PGY Cookie。请直接写入 PGY_COOKIE / PGY_COOKIE_HEADER，或提供 backend/data/token.txt，或配置 OSS token 下载参数。")
        last_error: Optional[Exception] = None
        for attempt in range(3):
            cookie_header = self._pick_cookie(cookies)
            headers = {
                "Cookie": cookie_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            try:
                if method.upper() == "POST":
                    resp = self.session.post(url, headers=headers, json=payload or {}, timeout=REQUEST_TIMEOUT_SECONDS)
                else:
                    resp = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
                text = resp.text
                if resp.ok and text.strip() != EMPTY_RESPONSE_TEXT:
                    return text
                last_error = ValueError(f"status={resp.status_code}, body={text[:200]}")
            except Exception as exc:  # pragma: no cover - 依赖外部网络环境
                last_error = exc
            time.sleep(0.6 * (attempt + 1))
        raise ValueError(f"达人补充数据接口请求失败: {last_error}")

    def fetch_bundle(self, creator_uid: str, field_keys: Sequence[str]) -> Dict[str, Any]:
        required_sources = {FIELD_INDEX[key]["source"] for key in field_keys if key in FIELD_INDEX}
        required_sources.add("basic")
        raw: Dict[str, str] = {}
        for source in required_sources:
            if source.startswith("performance"):
                url = SOURCE_ENDPOINTS["performance"]
                payload = {"userId": creator_uid, **PERFORMANCE_VARIANTS[source]}
                raw[source] = self._request_text("POST", url, payload=payload)
            else:
                url = SOURCE_ENDPOINTS[source].format(uid=creator_uid)
                raw[source] = self._request_text("GET", url)
        return raw

    def parse_bundle(self, raw_bundle: Dict[str, str], field_keys: Sequence[str]) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        parsed.update(self._parse_basic(raw_bundle.get("basic", "")))
        parsed.update(self._parse_unit_price(raw_bundle.get("unit_price", "")))
        parsed.update(self._parse_recent_notes(raw_bundle.get("recent_notes", ""), field_keys))
        parsed.update(self._parse_fans_summary(raw_bundle.get("fans_summary", "")))
        parsed.update(self._parse_fans_profile(raw_bundle.get("fans_profile", "")))
        parsed.update(self._parse_fans_trend(raw_bundle.get("fans_trend", "")))
        parsed.update(self._parse_performance(raw_bundle.get("performance_daily_30", ""), prefix="daily_all_full", suffix="30", is_collab=False))
        parsed.update(self._parse_performance(raw_bundle.get("performance_collab_30", ""), prefix="cooperate_all_full", suffix="30", is_collab=True))
        parsed.update(self._parse_performance(raw_bundle.get("performance_daily_90", ""), prefix="daily_all_full", suffix="90", is_collab=False))
        parsed.update(self._parse_performance(raw_bundle.get("performance_collab_90", ""), prefix="cooperate_all_full", suffix="90", is_collab=False))
        return {key: parsed.get(key) for key in field_keys if key in parsed}

    def _parse_basic(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        content_tags: List[str] = []
        for segment in re.findall(r'"taxonomy2Tags":\[(.*?)\]', text):
            content_tags.extend(re.findall(r'"(.*?)"', segment))
        personal_tags = re.findall(r'"personalTags":\[(.*?)\]', text)
        feature_tags = re.findall(r'"featureTags":\[(.*?)\]', text)
        return {
            "nickname": _extract_by_regex(text, r'"name":"(.*?)"'),
            "redbook_id": _extract_by_regex(text, r'"redId":"(.*?)"'),
            "region": _extract_by_regex(text, r'"location":"(.*?)"'),
            "content_tags": content_tags,
            "personal_tags": re.findall(r'"(.*?)"', personal_tags[0]) if personal_tags else [],
            "feature_tags": re.findall(r'"(.*?)"', feature_tags[0]) if feature_tags else [],
            "fans_count": _safe_int(_extract_by_regex(text, r'"fansCount":(.*?),')),
            "likes_collect_count": _safe_int(_extract_by_regex(text, r'"likeCollectCountInfo":(.*?),')),
            "picture_price": _safe_float(_extract_by_regex(text, r'"picturePrice":(.*?),')),
            "video_price": _safe_float(_extract_by_regex(text, r'"videoPrice":(.*?),')),
            "excellent_level": _safe_int(_extract_by_regex(text, r'"currentLevel":(.*?),')),
            "institution_name": _extract_by_regex(text, r'"noteSign":\{"userId":".*?","name":"(.*?)"\}'),
        }

    def _parse_unit_price(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        return {
            "read_picture_unit_price": _safe_float(_extract_by_regex(text, r'"pictureReadCost":(.*?),')),
            "read_video_unit_price": _safe_float(_extract_by_regex(text, r'"videoReadCost":"(.*?)"')),
        }

    def _parse_recent_notes(self, text: str, field_keys: Sequence[str]) -> Dict[str, Any]:
        if not text:
            return {}
        brands: List[str] = []
        likes: List[int] = []
        collects: List[int] = []
        images: List[str] = []
        data = _json_loads(text) or {}
        note_list = (((data.get("data") or {}).get("list")) if isinstance(data, dict) else None) or []
        if not note_list:
            images = re.findall(r'"imgUrl":"(.*?)"', text)[:8]
            brands = sorted(set(re.findall(r'"brandName":"(.*?)"', text)))
            likes = [_safe_int(item) for item in re.findall(r'"likeNum":(\d+)', text)]
            collects = [_safe_int(item) for item in re.findall(r'"collectNum":(\d+)', text)]
        else:
            for note in note_list:
                if not isinstance(note, dict):
                    continue
                brand_name = str(note.get("brandName") or "").strip()
                if brand_name:
                    brands.append(brand_name)
                if note.get("imgUrl"):
                    images.append(str(note.get("imgUrl")))
                likes.append(_safe_int(note.get("likeNum")))
                collects.append(_safe_int(note.get("collectNum")))
        result: Dict[str, Any] = {
            "recent_cooperative_brand": sorted(set(brands)),
            "recent_note_image_urls": images[:8],
        }
        if likes:
            result["cooperate_all_full_like_median_30"] = int(sorted(likes)[len(likes) // 2])
            result["cooperate_all_full_like_median_90"] = result["cooperate_all_full_like_median_30"]
        if collects:
            result["cooperate_all_full_collect_median_30"] = int(sorted(collects)[len(collects) // 2])
            result["cooperate_all_full_collect_median_90"] = result["cooperate_all_full_collect_median_30"]
        enable_baby_age = os.getenv("CREATOR_DATA_ENABLE_BABY_AGE", "0") == "1"
        if "baby_age" in field_keys and enable_baby_age:
            result["baby_age"] = self._infer_baby_age(images[:5])
        return result

    def _parse_fans_summary(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        return {
            "fans_trend": _safe_int(_extract_by_regex(text, r'"fansIncreaseNum":(.*?),')),
            "active_percent": _safe_float(_extract_by_regex(text, r'"activeFansRate":"(.*?)"')) / 100.0,
            "read_fans_rate": _safe_float(_extract_by_regex(text, r'"readFansRate":(.*?),')) / 100.0,
            "engage_fans_rate": _safe_float(_extract_by_regex(text, r'"engageFansRate":(.*?),')) / 100.0,
        }

    def _parse_fans_profile(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        result: Dict[str, Any] = {}
        age_map = {
            "<18": "age_0_18_percent",
            "18-24": "age_18_25_percent",
            "25-34": "age_25_35_percent",
            "35-44": "age_35_45_percent",
            ">44": "age_45_100_percent",
        }
        for group, pct in re.findall(r'"group":"(.*?)","percent":(.*?)}', text):
            key = age_map.get(group, f"age_{group}_percent")
            result[key] = _safe_float(pct)
        city_data: Dict[str, float] = {}
        city_match = re.search(r'"cities":\[(.*?)\]', text, re.DOTALL)
        if city_match:
            for city, pct in re.findall(r'"name":"(.*?)","percent":(.*?)}', city_match.group(1))[:8]:
                city_data[city] = _safe_float(pct)
        if city_data:
            result["city_data"] = city_data
        province_data: Dict[str, float] = {}
        province_match = re.search(r'"provinces":\[(.*?)\]', text, re.DOTALL)
        if province_match:
            for province, pct in re.findall(r'"name":"(.*?)","percent":(.*?)}', province_match.group(1))[:8]:
                province_data[province] = _safe_float(pct)
        if province_data:
            result["province_data"] = province_data
        gender_match = re.search(r'"gender":\{"male":(.*?),"female":(.*?)\}', text)
        if gender_match:
            result["male_percent"] = _safe_float(gender_match.group(1))
            result["female_percent"] = _safe_float(gender_match.group(2))
        return result

    def _parse_fans_trend(self, text: str) -> Dict[str, Any]:
        data = _json_loads(text) or {}
        rows = (((data.get("data") or {}).get("list")) if isinstance(data, dict) else None) or []
        points = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            points.append({"date": item.get("dateKey"), "value": _safe_int(item.get("num"))})
        return {"fans_growth_trend": points}

    def _parse_performance(self, text: str, *, prefix: str, suffix: str, is_collab: bool) -> Dict[str, Any]:
        if not text:
            return {}
        perf = {
            f"{prefix}_read_median_{suffix}": _safe_int(_extract_by_regex(text, r'"readMedian":(.*?),')),
            f"{prefix}_like_median_{suffix}": _safe_int(_extract_by_regex(text, r'"likeMedian":(.*?),')),
            f"{prefix}_comment_median_{suffix}": _safe_int(_extract_by_regex(text, r'"commentMedian":(.*?),')),
            f"{prefix}_collect_median_{suffix}": _safe_int(_extract_by_regex(text, r'"collectMedian":(.*?),')),
            f"{prefix}_interact_median_{suffix}": _safe_int(_extract_by_regex(text, r'"mEngagementNum":(\d+)')),
            f"{prefix}_imp_median_{suffix}": _safe_int(_extract_by_regex(text, r'"impMedian":(.*?),')),
            f"{prefix}_interaction_rate_{suffix}": _safe_float(_extract_by_regex(text, r'"interactionRate":(.*?),')) / 100.0,
        }
        if prefix == "daily_all_full":
            perf[f"daily_video_completion_rate_{suffix}"] = _safe_float(_extract_by_regex(text, r'"videoFullViewRate":(.*?),')) / 100.0
        else:
            perf[f"cooperate_video_completion_rate_{suffix}"] = _safe_float(_extract_by_regex(text, r'"videoFullViewRate":(.*?),')) / 100.0
        if is_collab:
            perf["notenumber"] = _safe_int(_extract_by_regex(text, r'"noteNumber":(.*?),'))
            perf["videonotenumber"] = _safe_int(_extract_by_regex(text, r'"videoNoteNumber":(.*?)(?:,|\})'))
        return perf

    def _infer_baby_age(self, img_urls: Sequence[str]) -> str:
        if not img_urls:
            return ""
        api_key = first_env_value("CREATOR_DATA_VL_API_KEY", "OPENAI_API_KEY")
        if not api_key:
            return ""
        try:
            from openai import OpenAI

            client = build_openai_client(
                api_key_envs=("CREATOR_DATA_VL_API_KEY",),
                base_url_envs=("CREATOR_DATA_VL_BASE_URL",),
            )
            content: List[Dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        "你会收到最多五张图片。请综合判断图片中出镜小孩或婴儿的年龄，"
                        "只输出最终年龄结果，不要解释。若所有图片都没有小孩或婴儿，"
                        "固定输出：没有识别到小孩或婴儿。"
                    ),
                }
            ]
            for url in img_urls[:5]:
                if url:
                    content.append({"type": "image_url", "image_url": {"url": url}})
            response = client.chat.completions.create(
                model=os.getenv("CREATOR_DATA_VL_MODEL", "qwen-vl-max-2025-01-25"),
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的图片识别助手。必须只输出年龄结果，不要解释，不要输出推理过程。",
                    },
                    {"role": "user", "content": content},
                ],
                temperature=0,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # pragma: no cover - 依赖外部模型服务
            logger.warning("宝宝年龄识别失败，已忽略: %s", exc)
            return ""


class CreatorDataService:
    def __init__(self, provider: Optional[CreatorFullDataProvider] = None, template_store: Optional[ExportTemplateStore] = None) -> None:
        self.provider = provider or CreatorFullDataProvider()
        self.template_store = template_store or ExportTemplateStore(TEMPLATE_STORE_PATH)

    def get_catalog(self) -> Dict[str, Any]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in FIELD_CATALOG:
            grouped.setdefault(item["group"], []).append(item)
        return {
            "fields": FIELD_CATALOG,
            "groups": grouped,
            "default_field_keys": DEFAULT_FIELD_KEYS,
        }

    def list_templates(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        templates = self.template_store.list(
            operator_id=_safe_int(payload.get("operator_id")) or None,
            brand_name=str(payload.get("brand_name") or "").strip(),
            spu_name=str(payload.get("spu_name") or "").strip(),
        )
        return {"templates": templates}

    def save_template(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        field_keys = self._resolve_field_keys(payload)
        if not field_keys:
            raise ValueError("field_keys 不能为空。")
        saved = self.template_store.save({**payload, "field_keys": field_keys})
        return {"template": saved}

    def enrich_creators(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        creators = self._resolve_creators(payload)
        field_keys = self._resolve_field_keys(payload)
        rows: List[Dict[str, Any]] = []
        provider_enabled = True
        for creator in creators:
            row = self._build_base_row(creator)
            creator_uid = _guess_uid(creator)
            row["creator_uid"] = creator_uid
            enriched_fields: Dict[str, Any] = {}
            error_message = ""
            if creator_uid:
                try:
                    raw_bundle = self.provider.fetch_bundle(creator_uid, field_keys)
                    enriched_fields = self.provider.parse_bundle(raw_bundle, field_keys)
                except Exception as exc:
                    provider_enabled = False
                    error_message = str(exc)
                    logger.warning("达人补充数据拉取失败 uid=%s: %s", creator_uid, exc)
            row["fields"] = {key: enriched_fields.get(key, row["fields"].get(key)) for key in field_keys}
            row["display_fields"] = {FIELD_INDEX[key]["label"]: _format_export_value(row["fields"].get(key)) for key in field_keys if key in FIELD_INDEX}
            row["provider_status"] = "ok" if enriched_fields else ("degraded" if creator_uid else "missing_uid")
            row["provider_error"] = error_message
            rows.append(row)
        selected_template = None
        template_id = str(payload.get("template_id") or "").strip()
        if template_id:
            selected_template = self.template_store.get(template_id)
        return {
            "rows": rows,
            "field_keys": field_keys,
            "fields": [FIELD_INDEX[key] for key in field_keys if key in FIELD_INDEX],
            "catalog": self.get_catalog(),
            "provider_enabled": provider_enabled,
            "selected_template": selected_template,
        }

    def export_creator_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        field_keys = self._resolve_field_keys(payload)
        rows = payload.get("rows") or []
        normalized_rows: List[Dict[str, Any]] = []
        if rows:
            for row in rows:
                fields = row.get("fields") if isinstance(row, dict) else {}
                normalized_rows.append({
                    "creator_id": row.get("creator_id"),
                    "creator_uid": row.get("creator_uid"),
                    "fields": {key: fields.get(key) for key in field_keys},
                })
        else:
            normalized_rows = self.enrich_creators(payload).get("rows", [])
        if not normalized_rows:
            raise ValueError("没有可导出的达人补充数据。")
        file_name = self._build_export_filename(payload)
        file_path = EXPORT_DIR / file_name
        headers = [FIELD_INDEX[key]["label"] for key in field_keys if key in FIELD_INDEX]
        with file_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writeheader()
            for row in normalized_rows:
                fields = row.get("fields") or {}
                writer.writerow({FIELD_INDEX[key]["label"]: _format_export_value(fields.get(key)) for key in field_keys if key in FIELD_INDEX})
        return {
            "file_name": file_name,
            "download_url": f"/api/v1/export/download/{file_name}",
            "row_count": len(normalized_rows),
            "field_keys": field_keys,
            "headers": headers,
            "template_id": payload.get("template_id"),
        }

    def get_export_file_path(self, file_name: str) -> Path:
        safe_name = Path(file_name).name
        file_path = EXPORT_DIR / safe_name
        if not file_path.exists():
            raise ValueError("导出文件不存在。")
        return file_path

    def _build_export_filename(self, payload: Dict[str, Any]) -> str:
        brand = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_-]+", "_", str(payload.get("brand_name") or "brand").strip())
        spu = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_-]+", "_", str(payload.get("spu_name") or "spu").strip())
        suffix = time.strftime("%Y%m%d_%H%M%S")
        return f"creator_export_{brand}_{spu}_{suffix}.csv"

    def _resolve_field_keys(self, payload: Dict[str, Any]) -> List[str]:
        template_id = str(payload.get("template_id") or "").strip()
        if template_id:
            template = self.template_store.get(template_id)
            if template and template.get("field_keys"):
                return [key for key in template["field_keys"] if key in FIELD_INDEX]
        keys = payload.get("field_keys") or payload.get("selected_field_keys") or []
        if not keys:
            return list(DEFAULT_FIELD_KEYS)
        return [key for key in keys if key in FIELD_INDEX]

    def _resolve_creators(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        creators = payload.get("creators") or []
        if creators:
            return [item for item in creators if isinstance(item, dict)]
        influencer_ids = payload.get("influencer_ids") or payload.get("selected_ids") or []
        if not influencer_ids:
            raise ValueError("creators 或 influencer_ids 至少提供一项。")
        if db is None:
            raise ValueError("当前环境未配置数据库，无法仅通过 influencer_ids 查询达人。")
        rows: List[Dict[str, Any]] = []
        for influencer_id in influencer_ids:
            record = db.get_influencer_by_id(_safe_int(influencer_id))
            if record:
                rows.append(dict(record))
        if not rows:
            raise ValueError("未找到可补充数据的达人。")
        return rows

    def _build_base_row(self, creator: Dict[str, Any]) -> Dict[str, Any]:
        raw = creator.get("raw") if isinstance(creator.get("raw"), dict) else {}
        combined = {**raw, **creator}
        base_fields: Dict[str, Any] = {
            "nickname": combined.get("nickname") or combined.get("name") or "",
            "redbook_id": combined.get("redbook_id") or combined.get("red_id") or "",
            "region": combined.get("region") or "",
            "fans_count": combined.get("followers") or combined.get("fans_count") or 0,
            "picture_price": combined.get("picture_price") or "",
            "video_price": combined.get("video_price") or "",
            "content_tags": combined.get("tags") or combined.get("content_tags") or [],
        }
        return {
            "creator_id": creator.get("internal_id") or creator.get("id"),
            "creator_uid": _guess_uid(creator),
            "fields": base_fields,
            "raw": combined,
        }


creator_data_service = CreatorDataService()
