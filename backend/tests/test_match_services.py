from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from fastapi.testclient import TestClient

from app import app
from services.intent_parser import IntentParserService
from services.match_service import (
    EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED,
    MatchService,
)


class IntentParserServiceTests(unittest.TestCase):
    def test_parse_uses_llm_payload_when_available(self):
        service = IntentParserService(llm_enabled=True)
        with mock.patch.object(
            service,
            "_call_llm",
            return_value={
                "画面气质": "干净明亮、奶感柔和",
                "人设感觉": "母婴营养师、专业可信",
                "场景类型": "居家带娃、奶粉喂养",
                "服化道": "自然淡妆",
                "构图/镜头": "中近景",
                "文案感": "科普分享",
                "商业感": "低商业感",
            },
        ):
            result = service.parse("母婴、婴幼儿奶粉", brand_name="飞鹤")
        self.assertEqual(result["brand_name"], "飞鹤")
        self.assertFalse(result["metadata"]["fallback_used"])
        self.assertEqual(result["query_plan"]["formatted_query_json"]["画面气质"], "干净明亮、奶感柔和")
        self.assertIn("画面气质::干净明亮", [item["key"] for item in result["query_plan"]["formatted_tags"]])

    def test_parse_falls_back_to_heuristics_and_extracts_filters(self):
        service = IntentParserService(llm_enabled=False)
        result = service.parse("上海宝妈达人 10万到50万粉丝 居家带娃奶粉分享 不要营销号")
        self.assertTrue(result["metadata"]["fallback_used"])
        self.assertEqual(result["hard_filters"]["region"], ["上海"])
        self.assertEqual(result["hard_filters"]["gender"], "女")
        self.assertEqual(result["hard_filters"]["followers_min"], 100000)
        self.assertEqual(result["hard_filters"]["followers_max"], 500000)
        self.assertAlmostEqual(result["hard_filters"]["ad_ratio_max"], 0.35)


class MatchServiceTests(unittest.TestCase):
    def setUp(self):
        self.parser = mock.Mock()
        self.service = MatchService(parser=self.parser)
        self.query_plan = {
            "long_sentence_query": "明亮温馨，母婴专业，居家奶粉分享",
            "formatted_query_text": "画面气质:明亮温馨\n人设感觉:母婴专业\n场景类型:居家奶粉分享",
            "formatted_tags": [
                {"key": "画面气质::明亮温馨", "field": "画面气质", "tag": "明亮温馨", "default_weight": 1.0},
                {"key": "人设感觉::母婴专业", "field": "人设感觉", "tag": "母婴专业", "default_weight": 1.0},
                {"key": "场景类型::居家奶粉分享", "field": "场景类型", "tag": "居家奶粉分享", "default_weight": 1.0},
            ],
        }

    def test_build_query_context_weighted_mode(self):
        context = self.service.build_query_context(
            self.query_plan,
            experiment_mode=EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED,
            tag_weights={"画面气质::明亮温馨": 1.8, "人设感觉::母婴专业": 0.7, "场景类型::居家奶粉分享": 1.2},
        )
        vector = np.array(context["query_vector"], dtype=np.float32)
        self.assertEqual(context["experiment_mode"], EXPERIMENT_MODE_FIELD_TAGS_WEIGHTED)
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)
        self.assertIn("画面气质:明亮温馨(1.8)", context["embedding_input_preview"])
        self.assertEqual(context["tag_weights_used"]["场景类型::居家奶粉分享"], 1.2)

    @mock.patch("services.match_service.milvus_mgr")
    def test_retrieve_calls_milvus_and_enriches_results(self, mocked_milvus):
        self.parser.parse.return_value = {
            "query_plan": self.query_plan,
            "hard_filters": {"region": ["上海"]},
        }
        mocked_milvus.hybrid_search.return_value = [
            {"id": 1, "distance": 0.1, "score": 0.9, "followers": 120000, "region": "上海", "gender": "女", "ad_ratio": 0.2}
        ]
        with mock.patch.object(self.service, "_fetch_profiles_by_ids", return_value={1: {"nickname": "测试达人", "red_id": "xhs_001"}}):
            result = self.service.retrieve({"raw_text": "母婴奶粉", "top_k": 5, "use_cache": False})
        mocked_milvus.connect.assert_called_once()
        mocked_milvus.load_collection.assert_called_once()
        mocked_milvus.hybrid_search.assert_called_once()
        self.assertFalse(result["cached"])
        self.assertEqual(result["results"][0]["profile"]["nickname"], "测试达人")
        self.assertEqual(result["scalar_filters"]["region"], ["上海"])


class ApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @mock.patch("app.intent_parser_service.parse")
    def test_intent_parse_endpoint(self, mocked_parse):
        mocked_parse.return_value = {"raw_text": "母婴奶粉", "query_plan": {"long_sentence_query": "母婴奶粉"}}
        response = self.client.post("/api/v1/intent/parse", json={"raw_text": "母婴奶粉"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"]["raw_text"], "母婴奶粉")

    @mock.patch("app.match_service.submit_retrieve_task")
    def test_match_retrieve_endpoint(self, mocked_submit):
        mocked_submit.return_value = {
            "task_id": "task-demo",
            "status": "done",
            "result": {"result_count": 1, "results": [{"internal_id": 1}]},
        }
        response = self.client.post("/api/v1/match/retrieve", json={"raw_text": "母婴奶粉"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "task-demo")
        self.assertEqual(response.json()["result"]["result_count"], 1)


if __name__ == "__main__":
    unittest.main()
