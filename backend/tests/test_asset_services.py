from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import app
from services.asset_service import AssetService
from services.creator_data_service import CreatorDataService, ExportTemplateStore


class AssetServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = AssetService()

    @mock.patch("services.asset_service.db")
    def test_commit_assets_creates_campaign_and_fulfillment(self, mocked_db):
        mocked_db.create_campaign.return_value = 101
        mocked_db.create_fulfillment.return_value = 9001

        result = self.service.commit_assets(
            {
                "brand_name": "A2",
                "spu_name": "奶粉",
                "raw_text": "找3位宝妈达人",
                "intent": {"query_plan": {"long_sentence_query": "宝妈 奶粉"}},
                "selected_ids": [1, 2],
                "rejected_ids": [5],
                "pending_ids": [7],
                "operator_id": 12,
                "operator_role": "客户",
                "brand_stage": "冷启",
                "query_vector": [0.1, 0.2, 0.3],
            }
        )

        mocked_db.create_campaign.assert_called_once()
        mocked_db.commit_campaign.assert_called_once()
        mocked_db.create_fulfillment.assert_called_once()
        self.assertEqual(result["campaign_id"], 101)
        self.assertEqual(result["record_id"], 9001)
        self.assertEqual(result["operator_role"], 3)
        self.assertEqual(result["brand_stage"], "冷启")
        self.assertTrue(result["next_batch_strategy"]["spu_memory_enabled"])
        self.assertTrue(result["next_batch_strategy"]["user_memory_enabled"])

    @mock.patch("services.asset_service.db")
    def test_get_spu_memory_aggregates_history_and_tag_weights(self, mocked_db):
        mocked_db.get_campaigns_by_brand.return_value = [
            {
                "campaign_id": 11,
                "operator_role": 3,
                "intent_snapshot": {
                    "query_plan": {
                        "formatted_tags": [
                            {"key": "style::高冷", "tag": "高冷", "default_weight": 1.2}
                        ]
                    },
                    "data_requirements": {"followers_min": 50000, "brand_stage": "冷启"},
                },
                "query_vector_snapshot": [0.1, 0.2],
                "selected_influencer_ids": [101, 102],
                "rejected_influencer_ids": [201],
                "pending_influencer_ids": [301],
            }
        ]
        mocked_db.get_fulfillment_timeline.return_value = [
            {
                "payload_snapshot": {
                    "tag_weights": {"style::高冷": 1.8, "scene::极简": 1.2},
                    "data_requirements": {"followers_min": 80000, "followers_max": 300000},
                }
            }
        ]

        result = self.service.get_spu_memory({"brand_name": "A2", "spu_name": "奶粉"})

        self.assertTrue(result["memory_ready"])
        self.assertEqual(result["campaign_count"], 1)
        self.assertEqual(result["latest_campaign_id"], 11)
        self.assertEqual(result["history_ids"]["selected_ids"], [101, 102])
        self.assertIn("style::高冷", result["recommended_tag_weights"])
        self.assertEqual(result["data_requirements_reference"]["followers_min"], 80000)

    @mock.patch("services.asset_service.db")
    def test_get_user_memory_uses_operator_dimension(self, mocked_db):
        mocked_db.get_campaigns_by_operator.return_value = [
            {
                "campaign_id": 22,
                "operator_role": 2,
                "intent_snapshot": {
                    "query_plan": {
                        "formatted_tags": [
                            {"key": "scene::极简", "tag": "极简", "default_weight": 1.1}
                        ]
                    }
                },
                "selected_influencer_ids": [8, 9],
                "rejected_influencer_ids": [10],
                "pending_influencer_ids": [],
                "query_vector_snapshot": [0.2, 0.3],
            }
        ]
        mocked_db.get_fulfillment_timeline.return_value = [
            {"payload_snapshot": {"tag_weights": {"scene::极简": 1.4}}}
        ]

        result = self.service.get_user_memory({"operator_id": 99, "brand_name": "A2", "spu_name": "奶粉"})

        mocked_db.get_campaigns_by_operator.assert_called_once_with(99, brand_name="A2", spu_name="奶粉")
        self.assertEqual(result["operator_id"], 99)
        self.assertEqual(result["campaign_count"], 1)
        self.assertEqual(result["history_ids"]["selected_ids"], [8, 9])
        self.assertIn("scene::极简", result["recommended_tag_weights"])

    @mock.patch.object(AssetService, "_fetch_vectors_by_ids")
    @mock.patch("services.match_service.match_service.submit_retrieve_task")
    @mock.patch("services.match_service.match_service.build_query_context")
    @mock.patch("services.asset_service.db")
    def test_recommend_next_batch_uses_spu_user_memory_and_rocchio(
        self,
        mocked_db,
        mocked_build_query_context,
        mocked_submit,
        mocked_fetch_vectors,
    ):
        mocked_db.get_campaigns_by_brand.return_value = [
            {
                "campaign_id": 11,
                "operator_role": 2,
                "intent_snapshot": {
                    "raw_text": "找高冷极简风宝妈",
                    "query_plan": {
                        "long_sentence_query": "高冷 极简 宝妈",
                        "formatted_tags": [
                            {"key": "style::高冷", "tag": "高冷", "default_weight": 1.0},
                            {"key": "scene::极简", "tag": "极简", "default_weight": 1.0},
                        ],
                    },
                    "data_requirements": {"followers_min": 100000},
                },
                "query_vector_snapshot": [0.3, 0.4],
                "selected_influencer_ids": [1, 2],
                "rejected_influencer_ids": [3],
                "pending_influencer_ids": [4],
            }
        ]
        mocked_db.get_campaigns_by_operator.return_value = [
            {
                "campaign_id": 21,
                "operator_role": 3,
                "intent_snapshot": {
                    "query_plan": {
                        "formatted_tags": [
                            {"key": "style::质感", "tag": "质感", "default_weight": 1.2}
                        ]
                    }
                },
                "query_vector_snapshot": [0.5, 0.6],
                "selected_influencer_ids": [7],
                "rejected_influencer_ids": [8],
                "pending_influencer_ids": [],
            }
        ]
        mocked_db.get_fulfillment_timeline.side_effect = [
            [{"payload_snapshot": {"tag_weights": {"style::高冷": 1.5, "scene::极简": 1.1}}}],
            [{"payload_snapshot": {"tag_weights": {"style::质感": 1.6}}}],
        ]
        mocked_db.get_influencer_by_id.side_effect = lambda internal_id: {
            1: {"internal_id": 1, "tags": ["高冷", "极简"]},
            2: {"internal_id": 2, "tags": ["高冷"]},
            3: {"internal_id": 3, "tags": ["甜美"]},
            7: {"internal_id": 7, "tags": ["质感"]},
            8: {"internal_id": 8, "tags": ["甜美"]},
            9: {"internal_id": 9, "tags": ["高冷", "质感"]},
            10: {"internal_id": 10, "tags": ["甜美"]},
        }.get(internal_id, {"internal_id": internal_id, "tags": []})
        mocked_build_query_context.return_value = {
            "query_vector": [0.11, 0.22, 0.33],
            "embedding_input_preview": "高冷 极简 宝妈",
            "tag_weights_used": {"style::高冷": 1.5},
        }
        mocked_fetch_vectors.return_value = {
            1: [1.0, 0.0, 0.0],
            2: [0.8, 0.1, 0.0],
            3: [0.0, 1.0, 0.0],
            7: [0.7, 0.1, 0.2],
            8: [0.0, 0.8, 0.2],
            9: [1.0, 0.0, 0.0],
            10: [0.0, 1.0, 0.0],
        }
        mocked_submit.return_value = {
            "task_id": "task-001",
            "status": "done",
            "result": {"results": [{"internal_id": 88}]},
        }

        result = self.service.recommend_next_batch(
            {
                "brand_name": "A2",
                "spu_name": "奶粉",
                "brand_stage": "冷启",
                "operator_id": 66,
                "top_k": 6,
                "selected_ids": [9],
                "rejected_ids": [10],
                "extra_exclude_ids": [12],
                "tag_weights": {"style::高冷": 2.0},
                "role_decay_overrides": {"客户": {"decay_days": 40, "min_factor": 0.5}},
            }
        )

        mocked_submit.assert_called_once()
        called_payload = mocked_submit.call_args.args[0]
        self.assertEqual(called_payload["brand_name"], "A2")
        self.assertEqual(called_payload["spu_name"], "奶粉")
        self.assertEqual(called_payload["top_k"], 6)
        self.assertIn(1, called_payload["exclude_ids"])
        self.assertIn(7, called_payload["exclude_ids"])
        self.assertIn(9, called_payload["exclude_ids"])
        self.assertIn(12, called_payload["exclude_ids"])
        self.assertGreaterEqual(called_payload["tag_weights"]["高冷"], 1.0)
        self.assertTrue(result["effective_request"]["rocchio"]["applied"])
        self.assertGreater(result["effective_request"]["rocchio"]["breakdown"]["current_positive"]["count"], 0)
        self.assertGreater(result["effective_request"]["rocchio"]["breakdown"]["history_positive"]["count"], 0)
        self.assertEqual(result["effective_request"]["feedback_candidates"]["strategy"]["current_brand_stage"], "冷启")
        self.assertIn("客户", result["effective_request"]["feedback_candidates"]["strategy"]["role_decay_overrides"])
        history_positive = result["effective_request"]["feedback_candidates"]["history_positive"]
        self.assertTrue(any("campaign_freshness_factor" in item for item in history_positive))
        self.assertTrue(any("brand_stage_factor" in item for item in history_positive))
        self.assertTrue(result["effective_request"]["weight_changes"]["summary"])
        self.assertTrue(result["effective_request"]["weight_changes"]["promoted"])
        self.assertEqual(result["recommendation_task"]["task_id"], "task-001")

    @mock.patch("services.asset_service.db")
    def test_list_library_returns_pagination(self, mocked_db):
        mocked_db.search_influencers.return_value = (
            [
                {
                    "internal_id": 1,
                    "nickname": "测试达人",
                    "region": "上海",
                    "followers": 120000,
                }
            ],
            1,
        )

        result = self.service.list_library(
            {
                "page": 1,
                "page_size": 20,
                "region": "上海",
                "sort_by": "followers",
                "sort_order": "DESC",
            }
        )

        mocked_db.search_influencers.assert_called_once()
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["items"][0]["nickname"], "测试达人")
        self.assertIn("history_hint", result["items"][0])

    @mock.patch("services.asset_service.db")
    def test_get_history_supports_multiple_modes(self, mocked_db):
        mocked_db.get_influencer_by_id.side_effect = lambda internal_id: {"internal_id": internal_id, "nickname": "测试达人", "tags": ["高冷"]}
        mocked_db.get_influencer_history.return_value = [{"campaign_id": 1, "brand_name": "A2", "operator_role": 3}]
        mocked_db.get_fulfillment_timeline.return_value = [{"record_id": 9, "campaign_id": 1, "action_type": "commit", "payload_snapshot": {"selected_ids": [1], "brand_stage": "冷启", "content_summary": "首轮合作摘要"}}]
        mocked_db.get_campaigns_by_brand.return_value = [{"campaign_id": 11, "spu_name": "奶粉"}]
        mocked_db.get_fulfillment_record.return_value = {
            "record_id": 9,
            "campaign_id": 1,
            "action_type": "commit",
            "payload_snapshot": {"selected_ids": [1], "material_assets": [{"title": "封面图", "url": "https://example.com/cover.png"}], "content_summary": "首轮合作摘要", "brand_stage": "冷启"},
        }
        mocked_db.get_campaign_by_id.return_value = {"campaign_id": 1, "brand_name": "A2", "spu_name": "奶粉", "operator_role": 3, "operator_id": 12}
        mocked_db.get_notes_by_influencer.return_value = [{"note_id": "n1", "note_type": "图文", "cover_image_url": "https://example.com/n1.png", "published_at": None, "reads": 1000, "likes": 120, "comments": 8, "collections": 16, "shares": 4}]

        influencer_result = self.service.get_history({"influencer_id": 1})
        campaign_result = self.service.get_history({"campaign_id": 11})
        brand_result = self.service.get_history({"brand_name": "A2", "spu_name": "奶粉"})
        record_result = self.service.get_history({"record_id": 9})

        self.assertEqual(influencer_result["mode"], "influencer_history")
        self.assertEqual(influencer_result["influencer_profile"]["nickname"], "测试达人")
        self.assertTrue(influencer_result["influencer_history"])
        self.assertEqual(campaign_result["mode"], "campaign_timeline")
        self.assertEqual(campaign_result["campaign_timeline"][0]["brand_stage"], "冷启")
        self.assertEqual(brand_result["mode"], "brand_campaigns")
        self.assertEqual(record_result["mode"], "fulfillment_detail")
        self.assertEqual(record_result["record_detail"]["campaign"]["brand_name"], "A2")
        self.assertTrue(record_result["record_detail"]["material_assets"])
        self.assertTrue(record_result["record_detail"]["note_previews"])


class CreatorDataServiceTests(unittest.TestCase):
    def test_enrich_creators_returns_selected_fields(self):
        provider = mock.Mock()
        provider.fetch_bundle.return_value = {"basic": "{}"}
        provider.parse_bundle.return_value = {
            "nickname": "测试达人",
            "fans_count": 88000,
            "read_picture_unit_price": 12.6,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            service = CreatorDataService(provider=provider, template_store=ExportTemplateStore(Path(tmpdir) / "templates.json"))
            result = service.enrich_creators(
                {
                    "creators": [
                        {
                            "creator_id": 7,
                            "creator_uid": "abc123",
                            "nickname": "测试达人",
                            "raw": {"uid": "abc123"},
                        }
                    ],
                    "field_keys": ["nickname", "fans_count", "read_picture_unit_price"],
                }
            )

        self.assertEqual(result["rows"][0]["creator_uid"], "abc123")
        self.assertEqual(result["rows"][0]["fields"]["fans_count"], 88000)
        self.assertEqual(result["rows"][0]["display_fields"]["预估阅读单价（图文）"], "12.6")

    def test_template_save_and_export(self):
        provider = mock.Mock()
        with tempfile.TemporaryDirectory() as tmpdir:
            service = CreatorDataService(provider=provider, template_store=ExportTemplateStore(Path(tmpdir) / "templates.json"))
            template_result = service.save_template(
                {
                    "template_name": "高优先字段",
                    "field_keys": ["nickname", "fans_count", "read_picture_unit_price"],
                    "brand_name": "A2",
                    "spu_name": "奶粉",
                    "operator_id": 3,
                }
            )
            template_id = template_result["template"]["template_id"]
            rows = [
                {
                    "creator_id": 1,
                    "creator_uid": "uid-1",
                    "fields": {
                        "nickname": "达人A",
                        "fans_count": 120000,
                        "read_picture_unit_price": 9.8,
                    },
                }
            ]
            export_result = service.export_creator_data(
                {
                    "brand_name": "A2",
                    "spu_name": "奶粉",
                    "template_id": template_id,
                    "rows": rows,
                }
            )
            file_path = service.get_export_file_path(export_result["file_name"])

        self.assertTrue(file_path.name.endswith(".csv"))
        self.assertIn("/api/v1/export/download/", export_result["download_url"])


class AssetApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @mock.patch("app.asset_service.commit_assets")
    def test_assets_commit_endpoint(self, mocked_commit):
        mocked_commit.return_value = {"campaign_id": 101, "record_id": 9}
        response = self.client.post(
            "/api/v1/assets/commit",
            json={
                "brand_name": "A2",
                "spu_name": "奶粉",
                "selected_ids": [1],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["campaign_id"], 101)

    @mock.patch("app.asset_service.get_spu_memory")
    def test_spu_memory_endpoint(self, mocked_memory):
        mocked_memory.return_value = {"campaign_count": 2, "recommended_tag_weights": {"style::高冷": 1.4}}
        response = self.client.get("/api/v1/spu/memory?brand_name=A2&spu_name=%E5%A5%B6%E7%B2%89")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["campaign_count"], 2)

    @mock.patch("app.asset_service.get_user_memory")
    def test_user_memory_endpoint(self, mocked_memory):
        mocked_memory.return_value = {"operator_id": 12, "campaign_count": 3}
        response = self.client.get("/api/v1/user/memory?operator_id=12&brand_name=A2&spu_name=%E5%A5%B6%E7%B2%89")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["operator_id"], 12)

    @mock.patch("app.asset_service.recommend_next_batch")
    def test_next_batch_endpoint(self, mocked_next_batch):
        mocked_next_batch.return_value = {
            "memory_profile": {"spu_memory": {"campaign_count": 2}},
            "recommendation_task": {"task_id": "task-002", "status": "done", "result": {"results": []}},
        }
        response = self.client.post(
            "/api/v1/match/next-batch",
            json={
                "brand_name": "A2",
                "spu_name": "奶粉",
                "operator_id": 66,
                "top_k": 8,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["recommendation_task"]["task_id"], "task-002")

    @mock.patch("app.asset_service.list_library")
    def test_library_list_endpoint(self, mocked_list):
        mocked_list.return_value = {"items": [], "pagination": {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}}
        response = self.client.get("/api/v1/library/list?page=1&page_size=20&region=%E4%B8%8A%E6%B5%B7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["pagination"]["page"], 1)

    @mock.patch("app.asset_service.get_history")
    def test_library_history_endpoint(self, mocked_history):
        mocked_history.return_value = {"mode": "brand_campaigns", "brand_campaigns": []}
        response = self.client.get("/api/v1/library/history?brand_name=A2&spu_name=%E5%A5%B6%E7%B2%89")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["mode"], "brand_campaigns")

    @mock.patch("app.asset_service.get_history")
    def test_library_history_record_detail_endpoint(self, mocked_history):
        mocked_history.return_value = {"mode": "fulfillment_detail", "record_detail": {"record_id": 9}}
        response = self.client.get("/api/v1/library/history?record_id=9")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["mode"], "fulfillment_detail")
        self.assertEqual(response.json()["result"]["record_detail"]["record_id"], 9)

    @mock.patch("app.creator_data_service.get_catalog")
    def test_creator_data_catalog_endpoint(self, mocked_catalog):
        mocked_catalog.return_value = {"fields": [{"key": "nickname", "label": "达人昵称"}], "default_field_keys": ["nickname"]}
        response = self.client.get("/api/v1/creator-data/catalog")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["default_field_keys"], ["nickname"])

    @mock.patch("app.creator_data_service.enrich_creators")
    def test_creator_data_enrich_endpoint(self, mocked_enrich):
        mocked_enrich.return_value = {"rows": [{"creator_id": 1, "fields": {"nickname": "达人A"}}], "field_keys": ["nickname"]}
        response = self.client.post(
            "/api/v1/creator-data/enrich",
            json={
                "creators": [{"creator_id": 1, "creator_uid": "uid-1", "nickname": "达人A"}],
                "field_keys": ["nickname"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["rows"][0]["fields"]["nickname"], "达人A")

    @mock.patch("app.creator_data_service.list_templates")
    def test_export_template_list_endpoint(self, mocked_list):
        mocked_list.return_value = {"templates": [{"template_id": "tpl-1", "template_name": "默认模板", "field_keys": ["nickname"]}]}
        response = self.client.get("/api/v1/export/templates?operator_id=12&brand_name=A2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["templates"][0]["template_id"], "tpl-1")

    @mock.patch("app.creator_data_service.save_template")
    def test_export_template_save_endpoint(self, mocked_save):
        mocked_save.return_value = {"template": {"template_id": "tpl-2", "template_name": "高优先字段", "field_keys": ["nickname"]}}
        response = self.client.post(
            "/api/v1/export/templates",
            json={"template_name": "高优先字段", "field_keys": ["nickname"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["template"]["template_id"], "tpl-2")

    @mock.patch("app.creator_data_service.export_creator_data")
    def test_export_creators_endpoint(self, mocked_export):
        mocked_export.return_value = {"file_name": "creator_export.csv", "download_url": "/api/v1/export/download/creator_export.csv"}
        response = self.client.post(
            "/api/v1/export/creators",
            json={
                "creators": [{"creator_id": 1, "creator_uid": "uid-1", "nickname": "达人A"}],
                "field_keys": ["nickname"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/v1/export/download/", response.json()["result"]["download_url"])

    @mock.patch("app.creator_data_service.get_export_file_path")
    def test_export_download_endpoint(self, mocked_get_path):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write("达人昵称\n达人A\n".encode("utf-8"))
            tmp_path = Path(tmp.name)
        mocked_get_path.return_value = tmp_path
        try:
            response = self.client.get(f"/api/v1/export/download/{tmp_path.name}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/csv", response.headers.get("content-type", ""))
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
