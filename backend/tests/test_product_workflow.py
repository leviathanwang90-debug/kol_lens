from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from app import app
match_service_module = importlib.import_module("services.match_service")
from services.intent_parser import IntentParserService
from services.match_service import MatchService
from services.pgy_service import PgyPayloadService


client = TestClient(app)


def test_intent_parser_extracts_data_and_content_requirements():
    parser = IntentParserService(llm_enabled=False)
    result = parser.parse(
        "找5位上海宝妈达人，粉丝8万到15万，图文报价1万以内，视频报价2万以内，画面温柔有奶感，居家带娃场景，低商业感。",
        brand_name="A2",
        spu_name="奶粉",
    )

    assert result["data_requirements"]["fansNumRange"] == [80000, 150000]
    assert result["data_requirements"]["picturePriceRange"][1] == 10000
    assert result["data_requirements"]["videoPriceRange"][1] == 20000
    assert result["data_requirements"]["requiredCount"] == 5
    assert result["hard_filters"]["region"] == ["上海"]
    assert result["hard_filters"]["gender"] == "女"
    assert "奶感" in result["content_requirements"]
    assert result["query_plan"]["long_sentence_query"]


def test_pgy_payload_service_builds_variants_for_two_price_modes(monkeypatch):
    service = PgyPayloadService(llm_enabled=False)

    def fake_parse(_text: str, *, base_payload=None):
        payload = dict(base_payload or {})
        payload["contentTag"] = ["母婴"]
        return {
            "natural_language_query": _text,
            "selected_content_tags": ["母婴"],
            "reasoning": "ok",
            "payload": payload,
        }

    monkeypatch.setattr(service, "parse_natural_language_to_payload", fake_parse)
    bundle = service.build_payload_variants(
        {
            "fansNumRange": [50000, 120000],
            "coopPriceRange": [5000, 15000],
            "cpmRange": [0, 200],
            "requireBothPriceModes": False,
            "requireBothCpmModes": False,
        },
        {"long_sentence_query": "母婴 宝妈 居家"},
        page_size=30,
    )

    assert bundle["content_payload"]["contentTag"] == ["母婴"]
    assert len(bundle["payload_variants"]) == 2
    assert bundle["payload_variants"][0]["fansNumberLower"] == 50000
    assert bundle["payload_variants"][0]["fansNumberUpper"] == 120000


def test_match_service_runs_expansion_then_degrade(monkeypatch):
    service = MatchService(parser=IntentParserService(llm_enabled=False))
    retrieve_rounds = [
        [{"internal_id": 1, "score": 0.9, "distance": 0.1, "profile": {"pricing": {"picture_price": 9000, "video_price": 18000}}}],
        [{"internal_id": 1, "score": 0.9, "distance": 0.1, "profile": {"pricing": {"picture_price": 9000, "video_price": 18000}}}],
        [
            {"internal_id": 1, "score": 0.9, "distance": 0.1, "profile": {"pricing": {"picture_price": 9000, "video_price": 18000}}},
            {"internal_id": 2, "score": 0.88, "distance": 0.12, "profile": {"pricing": {"picture_price": 10000, "video_price": 19000}}},
            {"internal_id": 3, "score": 0.85, "distance": 0.15, "profile": {"pricing": {"picture_price": 11000, "video_price": 20000}}},
        ],
    ]

    def fake_retrieve_local(**_kwargs):
        return retrieve_rounds.pop(0)

    monkeypatch.setattr(service, "_retrieve_local", fake_retrieve_local)
    monkeypatch.setattr(
        match_service_module.pgy_expansion_service,
        "expand_library",
        lambda **_kwargs: {"attempted": True, "message": "扩库完成。", "imported_internal_ids": [2]},
    )
    monkeypatch.setattr(
        service,
        "_greedy_relax_and_retrieve",
        lambda **_kwargs: {
            "attempted": True,
            "logs": ["放宽粉丝区间。", "降级后结果数 3（之前 1）。"],
            "results": [
                {"internal_id": 1, "score": 0.9, "distance": 0.1, "profile": {"pricing": {"picture_price": 9000, "video_price": 18000}}},
                {"internal_id": 2, "score": 0.88, "distance": 0.12, "profile": {"pricing": {"picture_price": 10000, "video_price": 19000}}},
                {"internal_id": 3, "score": 0.85, "distance": 0.15, "profile": {"pricing": {"picture_price": 11000, "video_price": 20000}}},
            ],
        },
    )

    result = service.retrieve(
        {
            "raw_text": "找3位上海宝妈达人，粉丝8万到15万，图文报价1万以内，视频报价2万以内，画面温柔，居家带娃。",
            "top_k": 3,
            "use_cache": False,
            "enable_external_expansion": True,
            "enable_greedy_degrade": True,
        }
    )

    assert result["result_count"] == 3
    assert result["expansion"]["attempted"] is True
    assert result["degradation"]["attempted"] is True
    assert any("扩库" in line for line in result["logs"])
    assert any("降级" in line for line in result["logs"])


def test_api_routes(monkeypatch):
    monkeypatch.setattr(
        "app.intent_parser_service.parse",
        lambda raw_text, brand_name="", spu_name="": {"raw_text": raw_text, "brand_name": brand_name, "spu_name": spu_name},
    )
    monkeypatch.setattr(
        "app.pgy_expansion_service.generate_payload",
        lambda payload: {"payload_variants": [{"contentTag": ["母婴"]}], "variant_count": 1, "content_payload": {"contentTag": ["母婴"]}},
    )
    monkeypatch.setattr(
        "app.match_service.submit_retrieve_task",
        lambda payload: {"task_id": "task-1", "status": "done", "result": {"result_count": 1, "raw_text": payload["raw_text"]}},
    )

    parse_response = client.post(
        "/api/v1/intent/parse",
        json={"raw_text": "宝妈达人", "brand_name": "A2", "spu_name": "奶粉"},
    )
    assert parse_response.status_code == 200
    assert parse_response.json()["intent"]["brand_name"] == "A2"

    payload_response = client.post(
        "/api/v1/pgy/payload/generate",
        json={"data_requirements": {}, "query_plan": {"long_sentence_query": "母婴"}, "page_size": 20},
    )
    assert payload_response.status_code == 200
    assert payload_response.json()["payload_bundle"]["variant_count"] == 1

    retrieve_response = client.post(
        "/api/v1/match/retrieve",
        json={"raw_text": "宝妈达人", "top_k": 5},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["task_id"] == "task-1"
