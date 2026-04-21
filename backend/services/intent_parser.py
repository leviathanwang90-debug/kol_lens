from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.openai_compat import build_openai_client

logger = logging.getLogger(__name__)

VISUAL_SUMMARY_FIELDS: Tuple[str, ...] = (
    "画面气质",
    "人设感觉",
    "场景类型",
    "服化道",
    "构图/镜头",
    "文案感",
    "商业感",
)

FIELD_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "画面气质": (
        "明亮", "奶感", "柔和", "清爽", "清新", "自然光", "氛围", "色调", "通透", "干净", "暖调", "冷调", "质感", "治愈", "温馨",
    ),
    "人设感觉": (
        "宝妈", "妈妈", "奶爸", "达人", "博主", "营养师", "专业", "可信", "亲和", "白领", "女孩", "女生", "男生", "潮人", "运动员", "老师",
    ),
    "场景类型": (
        "居家", "户外", "街头", "露营", "亲子", "带娃", "喂养", "通勤", "跑步", "登山", "旅行", "厨房", "办公室", "健身", "商圈", "探店",
    ),
    "服化道": (
        "穿搭", "妆容", "发型", "服装", "配饰", "道具", "奶瓶", "童车", "跑鞋", "装备", "包袋", "帽子", "淡妆", "发量",
    ),
    "构图/镜头": (
        "近景", "特写", "半身", "全身", "平视", "俯拍", "仰拍", "构图", "镜头", "自拍", "抓拍", "空镜", "远景",
    ),
    "文案感": (
        "口播", "干货", "科普", "测评", "分享", "vlog", "标题", "文案", "教程", "讲解", "普通话", "表达", "知识",
    ),
    "商业感": (
        "种草", "广告", "软广", "商业", "营销", "植入", "转化", "带货", "品牌露出", "低商业感", "低营销感", "无硬广",
    ),
}

REGION_KEYWORDS: Tuple[str, ...] = (
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "西安", "长沙", "青岛", "厦门", "天津",
)

LOW_COMMERCIAL_HINTS: Tuple[str, ...] = (
    "低商业感", "低营销感", "不要营销", "不要营销号", "不营销", "软植入", "自然植入", "无硬广", "少广告", "弱广告",
)

BOTH_PRICE_HINTS: Tuple[str, ...] = (
    "图文和视频都", "图文视频都", "图文和视频同时", "图文与视频都", "同时满足图文和视频", "图文和视频笔记都",
)

BOTH_CPM_HINTS: Tuple[str, ...] = (
    "图文和视频cpm都", "图文和视频 CPM 都", "图文与视频cpm都", "图文与视频 CPM 都", "同时满足图文和视频cpm", "图文和视频都小于",
)


LLM_SPLIT_PROMPT = """
你是 Σ.Match 的达人需求解析器。请把用户 query 拆成结构化 JSON，只输出 JSON。

输出格式：
{
  "data_requirements": {
    "fansNumRange": [50000, 150000] 或 null,
    "picturePriceRange": null 或 [min, max],
    "videoPriceRange": null 或 [min, max],
    "coopPriceRange": null 或 [min, max],
    "cpmRange": null 或 [min, max],
    "estimatePictureCpmRange": null 或 [min, max],
    "estimateVideoCpmRange": null 或 [min, max],
    "requiredCount": null 或 整数,
    "requireBothPriceModes": false,
    "requireBothCpmModes": false
  },
  "content_requirements": "用于风格匹配的纯内容描述",
  "reasoning": "简短中文说明"
}

规则：
1. 如果用户没有区分图文和视频，只能把报价写入 coopPriceRange，把 CPM 写入 cpmRange。
2. 只有用户明确表达图文和视频都要满足时，才把 requireBothPriceModes 或 requireBothCpmModes 置为 true。
3. 内容需求必须去掉所有数值、价格、粉丝量、数量类约束，只保留视觉风格、人设、场景、内容方向。
4. 只输出 JSON，不要输出 markdown。
""".strip()

LLM_VISUAL_PROMPT = (
    "你是 Σ.Match 的视觉 query 规划器。"
    "请把输入内容改写成仅包含 7 个字段的 JSON：画面气质、人设感觉、场景类型、服化道、构图/镜头、文案感、商业感。"
    "每个字段输出短语级标签串，字段内使用顿号分隔，最多 3 个 tag，没有就输出空字符串。"
    "优先保留可感知、可检索、判别力强的约束，禁止输出额外字段。"
)


def value_to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()



def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        normalized = value_to_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output



def _split_tags(text: str) -> List[str]:
    normalized = value_to_text(text)
    for separator in ("，", ",", "；", ";", "\n", "|", "/"):
        normalized = normalized.replace(separator, "、")
    return [segment.strip() for segment in normalized.split("、") if segment.strip()]



def _normalize_field_text(text: str, max_tags: int = 3) -> str:
    return "、".join(_dedupe_preserve_order(_split_tags(text))[:max_tags])



def _empty_visual_summary() -> Dict[str, str]:
    return {field_name: "" for field_name in VISUAL_SUMMARY_FIELDS}



def _empty_data_requirements() -> Dict[str, Any]:
    return {
        "fansNumRange": None,
        "picturePriceRange": None,
        "videoPriceRange": None,
        "coopPriceRange": None,
        "cpmRange": None,
        "estimatePictureCpmRange": None,
        "estimateVideoCpmRange": None,
        "requiredCount": None,
        "requireBothPriceModes": False,
        "requireBothCpmModes": False,
    }



def _extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = value_to_text(text).replace("```json", "").replace("```", "").strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("模型输出不是 JSON object")
    return payload



def _parse_numeric_value(number_text: str, unit_text: str = "") -> int:
    number = float(number_text)
    unit = value_to_text(unit_text).lower()
    if unit in {"w", "万"}:
        number *= 10000
    elif unit == "k":
        number *= 1000
    return int(round(number))



def _range_from_match(match: re.Match[str], lower_index: int = 1, lower_unit_index: int = 2, upper_index: int = 3, upper_unit_index: int = 4) -> List[Optional[int]]:
    lower = _parse_numeric_value(match.group(lower_index), match.group(lower_unit_index) or "")
    upper = _parse_numeric_value(match.group(upper_index), match.group(upper_unit_index) or "")
    return [lower, upper]



def _parse_about_range(number_text: str, unit_text: str = "") -> List[int]:
    center = _parse_numeric_value(number_text, unit_text)
    return [int(round(center * 0.8)), int(round(center * 1.2))]



def _extract_context_window(raw_text: str, keyword_pattern: str) -> str:
    matched = re.search(keyword_pattern, raw_text, flags=re.IGNORECASE)
    if not matched:
        return ""
    start = max(0, matched.start() - 24)
    end = min(len(raw_text), matched.end() + 32)
    return raw_text[start:end]



def _extract_count(raw_text: str) -> Optional[int]:
    patterns = [
        r"(\d+)\s*(?:位|个|人)\s*(?:达人|博主|创作者)",
        r"需要\s*(\d+)\s*(?:位|个|人)",
        r"返回\s*(\d+)\s*(?:位|个|人)",
        r"找\s*(\d+)\s*(?:位|个|人)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw_text)
        if matched:
            return int(matched.group(1))
    return None



def _extract_simple_range(
    raw_text: str,
    keywords: Sequence[str],
    *,
    default_lower_zero: bool = False,
    allow_reverse_match: bool = True,
) -> Optional[List[Optional[int]]]:
    keyword_pattern = "(?:" + "|".join(re.escape(item) for item in keywords) + ")"
    window = _extract_context_window(raw_text, keyword_pattern) or raw_text

    range_patterns = [
        rf"{keyword_pattern}.{{0,16}}?(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:到|至|-|~)\\s*(\\d+(?:\\.\\d+)?)([wW万kK]?)",
    ]
    if allow_reverse_match:
        range_patterns.append(
            rf"(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:到|至|-|~)\\s*(\\d+(?:\\.\\d+)?)([wW万kK]?).{{0,16}}?{keyword_pattern}"
        )

    for pattern in range_patterns:
        matched = re.search(pattern, window, flags=re.IGNORECASE)
        if matched:
            return _range_from_match(matched)

    about_patterns = [
        rf"{keyword_pattern}.{{0,16}}?(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:左右|上下|附近)",
    ]
    if allow_reverse_match:
        about_patterns.append(
            rf"(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:左右|上下|附近).{{0,16}}?{keyword_pattern}"
        )

    for pattern in about_patterns:
        matched = re.search(pattern, window, flags=re.IGNORECASE)
        if matched:
            return _parse_about_range(matched.group(1), matched.group(2) or "")

    min_patterns = [
        rf"{keyword_pattern}.{{0,16}}?(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:以上|起|及以上)",
    ]
    if allow_reverse_match:
        min_patterns.append(
            rf"(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:以上|起|及以上).{{0,16}}?{keyword_pattern}"
        )

    for pattern in min_patterns:
        matched = re.search(pattern, window, flags=re.IGNORECASE)
        if matched:
            return [_parse_numeric_value(matched.group(1), matched.group(2) or ""), None]

    max_patterns = [
        rf"{keyword_pattern}.{{0,16}}?(?:小于|低于|不高于|不超过|最多|控制在)\\s*(\\d+(?:\\.\\d+)?)([wW万kK]?)",
        rf"{keyword_pattern}.{{0,16}}?(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:以下|以内|内)",
    ]
    if allow_reverse_match:
        max_patterns.append(
            rf"(\\d+(?:\\.\\d+)?)([wW万kK]?)\\s*(?:以下|以内|内).{{0,16}}?{keyword_pattern}"
        )

    for pattern in max_patterns:
        matched = re.search(pattern, window, flags=re.IGNORECASE)
        if matched:
            lower = 0 if default_lower_zero else None
            return [lower, _parse_numeric_value(matched.group(1), matched.group(2) or "")]

    return None



def _extract_followers_range(raw_text: str) -> Optional[List[Optional[int]]]:
    patterns = [
        r"粉丝\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:到|至|-|~)\s*(\d+(?:\.\d+)?)([wW万kK]?)",
        r"(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:到|至|-|~)\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*粉丝",
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if matched:
            return _range_from_match(matched)

    min_patterns = [
        r"粉丝\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以上|起|及以上)",
        r"(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以上|起|及以上)\s*粉丝",
    ]
    for pattern in min_patterns:
        matched = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if matched:
            return [_parse_numeric_value(matched.group(1), matched.group(2) or ""), None]

    max_patterns = [
        r"粉丝\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以下|以内|内)",
        r"(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以下|以内|内)\s*粉丝",
    ]
    for pattern in max_patterns:
        matched = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if matched:
            return [None, _parse_numeric_value(matched.group(1), matched.group(2) or "")]

    return _extract_simple_range(raw_text, ["粉丝", "粉量", "粉丝量"])



def _extract_keyword_only_range(
    raw_text: str,
    keywords: Sequence[str],
    *,
    default_lower_zero: bool = False,
) -> Optional[List[Optional[int]]]:
    keyword_pattern = "(?:" + "|".join(re.escape(item) for item in keywords) + ")"
    patterns = [
        rf"{keyword_pattern}\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:到|至|-|~)\s*(\d+(?:\.\d+)?)([wW万kK]?)",
        rf"{keyword_pattern}\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:左右|上下|附近)",
        rf"{keyword_pattern}\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以上|起|及以上)",
        rf"{keyword_pattern}\s*(?:小于|低于|不高于|不超过|最多|控制在)?\s*(\d+(?:\.\d+)?)([wW万kK]?)\s*(?:以下|以内|内)?",
    ]
    matched = re.search(patterns[0], raw_text, flags=re.IGNORECASE)
    if matched:
        return _range_from_match(matched)
    matched = re.search(patterns[1], raw_text, flags=re.IGNORECASE)
    if matched:
        return _parse_about_range(matched.group(1), matched.group(2) or "")
    matched = re.search(patterns[2], raw_text, flags=re.IGNORECASE)
    if matched:
        return [_parse_numeric_value(matched.group(1), matched.group(2) or ""), None]
    matched = re.search(patterns[3], raw_text, flags=re.IGNORECASE)
    if matched:
        lower = 0 if default_lower_zero else None
        return [lower, _parse_numeric_value(matched.group(1), matched.group(2) or "")]
    return None



def _remove_numeric_constraints(raw_text: str) -> str:
    text = raw_text
    patterns = [
        r"粉丝[^，,；;。\n]{0,24}(?:万|w|k|以上|以下|以内|左右|到|至|-|~)",
        r"(?:图文|视频|合作|商单|报价|预算|CPM|cpm)[^，,；;。\n]{0,24}(?:万|w|k|以上|以下|以内|左右|到|至|-|~|\d+)",
        r"(?:需要|找|返回)\s*\d+\s*(?:位|个|人)(?:达人|博主|创作者)?",
        r"\d+\s*(?:位|个|人)\s*(?:达人|博主|创作者)",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"[，,；;]\s*[，,；;]+", "，", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,；;。\n")
    return text.strip() or raw_text.strip()


class IntentParserService:
    """将自然语言需求解析为结构化产品意图。"""

    def __init__(self, llm_enabled: Optional[bool] = None):
        if llm_enabled is None:
            llm_enabled = os.getenv("KOL_LENS_DISABLE_LLM", "0") != "1"
        self._llm_enabled = bool(llm_enabled)
        self._model_name = os.getenv("KOL_LENS_INTENT_MODEL", "gpt-4.1-mini")

    def parse(self, raw_text: str, brand_name: str = "", spu_name: str = "") -> Dict[str, Any]:
        normalized_text = value_to_text(raw_text)
        if not normalized_text:
            raise ValueError("raw_text 不能为空。")

        split_result, split_backend, split_fallback_used = self._split_query(normalized_text)
        data_requirements = self._normalize_data_requirements(split_result.get("data_requirements"))
        content_requirements = value_to_text(split_result.get("content_requirements")) or _remove_numeric_constraints(normalized_text)
        reasoning = value_to_text(split_result.get("reasoning"))

        formatted_query_json, rewrite_backend, rewrite_fallback_used = self._rewrite_query_fields(content_requirements)
        hard_filters = self._extract_hard_filters(normalized_text, data_requirements)
        elastic_weights = self._build_elastic_weights(hard_filters, data_requirements)
        query_plan = self._build_query_plan(formatted_query_json, content_requirements)

        return {
            "raw_text": normalized_text,
            "brand_name": value_to_text(brand_name),
            "spu_name": value_to_text(spu_name),
            "data_requirements": data_requirements,
            "content_requirements": content_requirements,
            "split_reasoning": reasoning,
            "hard_filters": hard_filters,
            "soft_vectors": {
                "v_overall_style": query_plan["long_sentence_query"],
                "query_visual_text": query_plan["formatted_query_text"],
                "formatted_tags": query_plan["formatted_tags"],
            },
            "elastic_weights": elastic_weights,
            "query_plan": query_plan,
            "metadata": {
                "split_backend": split_backend,
                "rewrite_backend": rewrite_backend,
                "fallback_used": split_fallback_used or rewrite_fallback_used,
                "visual_field_count": sum(1 for value in formatted_query_json.values() if value),
            },
        }

    def _split_query(self, raw_text: str) -> Tuple[Dict[str, Any], str, bool]:
        if self._llm_enabled:
            try:
                payload = self._call_llm_json(LLM_SPLIT_PROMPT, raw_text)
                return payload, "openai_compatible", False
            except Exception as exc:  # pragma: no cover - 运行时回退
                logger.warning("LLM 数据需求拆解失败，回退到规则解析: %s", exc)
        return self._heuristic_split_query(raw_text), "heuristic", True

    def _rewrite_query_fields(self, content_text: str) -> Tuple[Dict[str, str], str, bool]:
        if self._llm_enabled:
            try:
                payload = self._call_llm(content_text)
                return self._normalize_formatted_query_json(payload), "openai_compatible", False
            except Exception as exc:  # pragma: no cover - 运行时回退
                logger.warning("LLM 风格字段改写失败，回退到规则解析: %s", exc)
        return self._heuristic_fields(content_text), "heuristic", True

    def _call_llm(self, raw_text: str) -> Dict[str, Any]:
        return self._call_llm_json(LLM_VISUAL_PROMPT, raw_text)

    def _call_llm_json(self, system_prompt: str, user_text: str) -> Dict[str, Any]:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - 依赖缺失时走规则回退
            raise RuntimeError("openai 依赖不可用") from exc

        client = build_openai_client(
            api_key_envs=("KOL_LENS_INTENT_API_KEY",),
            base_url_envs=("KOL_LENS_INTENT_BASE_URL",),
        )
        completion = client.chat.completions.create(
            model=self._model_name,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        return _extract_json_object(value_to_text(completion.choices[0].message.content))

    def _heuristic_split_query(self, raw_text: str) -> Dict[str, Any]:
        data_requirements = _empty_data_requirements()
        data_requirements["fansNumRange"] = _extract_followers_range(raw_text)
        data_requirements["picturePriceRange"] = _extract_keyword_only_range(raw_text, ["图文报价", "图文价格", "图文合作价", "笔记报价", "图文商单"])
        data_requirements["videoPriceRange"] = _extract_keyword_only_range(raw_text, ["视频报价", "视频价格", "视频合作价", "视频商单"])
        data_requirements["coopPriceRange"] = _extract_keyword_only_range(raw_text, ["合作报价", "合作价", "报价", "预算", "商单报价", "合作预算"])
        data_requirements["estimatePictureCpmRange"] = _extract_keyword_only_range(raw_text, ["图文cpm", "图文 CPM", "图文千次曝光成本"], default_lower_zero=True)
        data_requirements["estimateVideoCpmRange"] = _extract_keyword_only_range(raw_text, ["视频cpm", "视频 CPM", "视频千次曝光成本"], default_lower_zero=True)
        data_requirements["cpmRange"] = _extract_keyword_only_range(raw_text, ["cpm", "CPM", "千次曝光成本"], default_lower_zero=True)
        data_requirements["requiredCount"] = _extract_count(raw_text)
        data_requirements["requireBothPriceModes"] = any(hint in raw_text for hint in BOTH_PRICE_HINTS)
        data_requirements["requireBothCpmModes"] = any(hint in raw_text for hint in BOTH_CPM_HINTS)
        return {
            "data_requirements": data_requirements,
            "content_requirements": _remove_numeric_constraints(raw_text),
            "reasoning": "基于规则抽取粉丝、报价、CPM 与数量需求，并保留视觉和内容描述。",
        }

    def _normalize_data_requirements(self, payload: Any) -> Dict[str, Any]:
        normalized = _empty_data_requirements()
        incoming = payload if isinstance(payload, dict) else {}
        for key in normalized:
            if key not in incoming:
                continue
            if key.startswith("requireBoth"):
                normalized[key] = bool(incoming.get(key))
            elif key == "requiredCount":
                try:
                    normalized[key] = int(incoming.get(key)) if incoming.get(key) not in (None, "") else None
                except (TypeError, ValueError):
                    normalized[key] = None
            else:
                value = incoming.get(key)
                if value in (None, "", []):
                    normalized[key] = None
                    continue
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    lower = None if value[0] in (None, "") else int(value[0])
                    upper = None if value[1] in (None, "") else int(value[1])
                    normalized[key] = [lower, upper]
        return normalized

    def _heuristic_fields(self, raw_text: str) -> Dict[str, str]:
        summary = _empty_visual_summary()
        segments = _dedupe_preserve_order(
            [
                segment.strip()
                for segment in re.split(r"[，,；;。\n]+", raw_text)
                if segment and segment.strip()
            ]
        )

        residual_segments: List[str] = []
        for segment in segments:
            assigned = False
            for field_name in VISUAL_SUMMARY_FIELDS:
                if any(keyword in segment for keyword in FIELD_KEYWORDS[field_name]):
                    existing_tags = _split_tags(summary[field_name])
                    summary[field_name] = _normalize_field_text("、".join(existing_tags + [segment]))
                    assigned = True
                    break
            if not assigned:
                residual_segments.append(segment)

        if residual_segments:
            existing_scene_tags = _split_tags(summary["场景类型"])
            summary["场景类型"] = _normalize_field_text("、".join(existing_scene_tags + residual_segments))

        if not any(summary.values()):
            summary["画面气质"] = _normalize_field_text(raw_text)

        return summary

    def _normalize_formatted_query_json(self, payload: Dict[str, Any]) -> Dict[str, str]:
        normalized = _empty_visual_summary()
        for field_name in VISUAL_SUMMARY_FIELDS:
            normalized[field_name] = _normalize_field_text(value_to_text(payload.get(field_name)))
        if not any(normalized.values()):
            normalized["画面气质"] = _normalize_field_text(value_to_text(payload))
        return normalized

    def _extract_hard_filters(self, raw_text: str, data_requirements: Dict[str, Any]) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}

        regions = [region for region in REGION_KEYWORDS if region in raw_text]
        if regions:
            filters["region"] = regions

        if any(token in raw_text for token in ("女性", "女生", "女孩", "宝妈", "妈妈", "女达人")):
            filters["gender"] = "女"
        elif any(token in raw_text for token in ("男性", "男生", "男孩", "奶爸", "爸爸", "男达人")):
            filters["gender"] = "男"

        fans_range = data_requirements.get("fansNumRange")
        if fans_range:
            if fans_range[0] is not None:
                filters["followers_min"] = int(fans_range[0])
            if fans_range[1] is not None:
                filters["followers_max"] = int(fans_range[1])

        if any(token in raw_text for token in LOW_COMMERCIAL_HINTS):
            filters["ad_ratio_max"] = 0.35

        return filters

    def _build_elastic_weights(self, hard_filters: Dict[str, Any], data_requirements: Dict[str, Any]) -> Dict[str, int]:
        weights: Dict[str, int] = {}
        for key in hard_filters:
            if key in {"region", "gender"}:
                weights[key] = 2
            elif key in {"followers_min", "followers_max"}:
                weights[key] = 4
            elif key == "ad_ratio_max":
                weights[key] = 5
        for key, value in (data_requirements or {}).items():
            if value in (None, False, {}, []):
                continue
            if key in {"picturePriceRange", "videoPriceRange", "coopPriceRange"}:
                weights[key] = 4
            elif key in {"estimatePictureCpmRange", "estimateVideoCpmRange", "cpmRange"}:
                weights[key] = 5
        return weights

    def _build_query_plan(self, formatted_query_json: Dict[str, str], content_text: str) -> Dict[str, Any]:
        formatted_query_text = "\n".join(
            f"{field_name}:{formatted_query_json[field_name]}"
            for field_name in VISUAL_SUMMARY_FIELDS
            if formatted_query_json[field_name]
        )
        formatted_tags: List[Dict[str, Any]] = []
        for field_name in VISUAL_SUMMARY_FIELDS:
            for tag in _split_tags(formatted_query_json[field_name]):
                formatted_tags.append(
                    {
                        "key": f"{field_name}::{tag}",
                        "field": field_name,
                        "tag": tag,
                        "default_weight": 1.0,
                    }
                )
        long_sentence_query = "，".join(
            formatted_query_json[field_name]
            for field_name in VISUAL_SUMMARY_FIELDS
            if formatted_query_json[field_name]
        ) or content_text
        return {
            "long_sentence_query": long_sentence_query,
            "formatted_query_json": formatted_query_json,
            "formatted_query_text": formatted_query_text,
            "formatted_tags": formatted_tags,
            "retrieval_query_text": long_sentence_query,
            "query_visual_text": formatted_query_text or long_sentence_query,
            "tags": formatted_tags,
        }


intent_parser_service = IntentParserService()
