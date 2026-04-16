from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
        "明亮", "奶感", "柔和", "清爽", "清新", "自然光", "氛围", "色调", "通透", "干净", "暖调", "冷调", "高级", "质感",
    ),
    "人设感觉": (
        "宝妈", "妈妈", "奶爸", "达人", "博主", "营养师", "专业", "可信", "亲和", "白领", "女孩", "女生", "男生", "潮人", "运动员",
    ),
    "场景类型": (
        "居家", "户外", "街头", "露营", "亲子", "带娃", "喂养", "通勤", "跑步", "登山", "旅行", "厨房", "办公室", "健身", "商圈",
    ),
    "服化道": (
        "穿搭", "妆容", "发型", "服装", "配饰", "道具", "奶瓶", "童车", "跑鞋", "装备", "包袋", "帽子",
    ),
    "构图/镜头": (
        "近景", "特写", "半身", "全身", "平视", "俯拍", "仰拍", "构图", "镜头", "自拍", "抓拍",
    ),
    "文案感": (
        "口播", "干货", "科普", "测评", "分享", "vlog", "标题", "文案", "教程", "讲解",
    ),
    "商业感": (
        "种草", "广告", "软广", "商业", "营销", "植入", "转化", "带货", "品牌露出",
    ),
}

REGION_KEYWORDS: Tuple[str, ...] = (
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "西安", "长沙", "青岛", "厦门", "天津",
)

LOW_COMMERCIAL_HINTS: Tuple[str, ...] = (
    "低商业感", "低营销感", "不要营销", "不要营销号", "不营销", "软植入", "自然植入", "无硬广", "少广告", "弱广告",
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


class IntentParserService:
    """将自然语言需求转为结构化意图和检索 query plan。"""

    def __init__(self, llm_enabled: Optional[bool] = None):
        if llm_enabled is None:
            llm_enabled = os.getenv("KOL_LENS_DISABLE_LLM", "0") != "1"
        self._llm_enabled = bool(llm_enabled)
        self._model_name = os.getenv("KOL_LENS_INTENT_MODEL", "gpt-4.1-mini")

    def parse(self, raw_text: str, brand_name: str = "", spu_name: str = "") -> Dict[str, Any]:
        normalized_text = value_to_text(raw_text)
        if not normalized_text:
            raise ValueError("raw_text 不能为空。")

        formatted_query_json, parser_backend, fallback_used = self._rewrite_query_fields(normalized_text)
        hard_filters = self._extract_hard_filters(normalized_text)
        elastic_weights = self._build_elastic_weights(hard_filters)
        query_plan = self._build_query_plan(formatted_query_json, normalized_text)

        return {
            "raw_text": normalized_text,
            "brand_name": value_to_text(brand_name),
            "spu_name": value_to_text(spu_name),
            "hard_filters": hard_filters,
            "soft_vectors": {
                "v_overall_style": query_plan["long_sentence_query"],
                "query_visual_text": query_plan["formatted_query_text"],
                "formatted_tags": query_plan["formatted_tags"],
            },
            "elastic_weights": elastic_weights,
            "query_plan": query_plan,
            "metadata": {
                "parser_backend": parser_backend,
                "fallback_used": fallback_used,
                "visual_field_count": sum(1 for value in formatted_query_json.values() if value),
            },
        }

    def _rewrite_query_fields(self, raw_text: str) -> Tuple[Dict[str, str], str, bool]:
        if self._llm_enabled:
            try:
                llm_payload = self._call_llm(raw_text)
                return self._normalize_formatted_query_json(llm_payload), "openai_compatible", False
            except Exception as exc:  # pragma: no cover - 回退路径主要依赖运行环境
                logger.warning("LLM 意图解析失败，回退到规则解析: %s", exc)
        return self._heuristic_fields(raw_text), "heuristic", True

    def _call_llm(self, raw_text: str) -> Dict[str, Any]:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - 依赖缺失时会回退到规则解析
            raise RuntimeError("openai 依赖不可用") from exc

        client = OpenAI()
        completion = client.chat.completions.create(
            model=self._model_name,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 Σ.Match 的意图解析器。"
                        "请把用户的达人需求改写成仅包含 7 个字段的 JSON："
                        "画面气质、人设感觉、场景类型、服化道、构图/镜头、文案感、商业感。"
                        "每个字段输出短语级标签串，字段内用顿号分隔多个标签。"
                        "每个字段最多 3 个 tag，没有就输出空字符串。"
                        "不要解释，不要输出额外字段。"
                    ),
                },
                {"role": "user", "content": raw_text},
            ],
        )
        content = value_to_text(completion.choices[0].message.content)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:  # pragma: no cover - 依赖真实模型输出
            raise RuntimeError(f"LLM 输出不是合法 JSON: {content}") from exc

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

    def _extract_hard_filters(self, raw_text: str) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}

        regions = [region for region in REGION_KEYWORDS if region in raw_text]
        if regions:
            filters["region"] = regions

        if any(token in raw_text for token in ("女性", "女生", "女孩", "宝妈", "妈妈", "女达人")):
            filters["gender"] = "女"
        elif any(token in raw_text for token in ("男性", "男生", "男孩", "奶爸", "爸爸", "男达人")):
            filters["gender"] = "男"

        followers_min, followers_max = self._parse_followers_range(raw_text)
        if followers_min is not None:
            filters["followers_min"] = followers_min
        if followers_max is not None:
            filters["followers_max"] = followers_max

        if any(token in raw_text for token in LOW_COMMERCIAL_HINTS):
            filters["ad_ratio_max"] = 0.35

        return filters

    def _parse_followers_range(self, raw_text: str) -> Tuple[Optional[int], Optional[int]]:
        patterns = [
            r"(\d+)\s*[wW万]\s*(?:到|至|-|~)\s*(\d+)\s*[wW万]",
            r"(\d+)\s*(?:到|至|-|~)\s*(\d+)\s*[wW万]",
        ]
        for pattern in patterns:
            matched = re.search(pattern, raw_text)
            if matched:
                return self._unit_to_int(matched.group(1)), self._unit_to_int(matched.group(2))

        min_match = re.search(r"(\d+)\s*[wW万]\s*(?:以上|起|及以上)", raw_text)
        if min_match:
            return self._unit_to_int(min_match.group(1)), None

        max_match = re.search(r"(\d+)\s*[wW万]\s*(?:以下|以内|内)", raw_text)
        if max_match:
            return None, self._unit_to_int(max_match.group(1))

        return None, None

    @staticmethod
    def _unit_to_int(number_text: str) -> int:
        return int(float(number_text) * 10000)

    def _build_elastic_weights(self, hard_filters: Dict[str, Any]) -> Dict[str, int]:
        weights: Dict[str, int] = {
            "region": 2,
            "gender": 2,
            "followers_min": 4,
            "followers_max": 4,
            "ad_ratio_max": 5,
        }
        return {key: value for key, value in weights.items() if key in hard_filters}

    def _build_query_plan(self, formatted_query_json: Dict[str, str], raw_text: str) -> Dict[str, Any]:
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
        ) or raw_text
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
