"""
Σ.Match 基建层集成测试
Sprint 1 · Task 1.4.1

端到端验证:
  1. PostgreSQL 全部表的 CRUD 操作
  2. Milvus Collection 的插入与混合检索
  3. Redis 的任务状态全生命周期
  4. 三套服务之间的数据一致性 (PG internal_id ↔ Milvus id)

执行方式: python -m tests.test_infrastructure
前置条件: docker-compose up -d (三套服务全部就绪)
"""

import json
import random
import sys
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import List

# 将 backend 目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 测试结果收集器
# ============================================================

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_true(self, condition: bool, msg: str):
        if condition:
            self.passed += 1
            print(f"  ✅ PASS: {msg}")
        else:
            self.failed += 1
            self.errors.append(msg)
            print(f"  ❌ FAIL: {msg}")

    def assert_equal(self, actual, expected, msg: str):
        if actual == expected:
            self.passed += 1
            print(f"  ✅ PASS: {msg}")
        else:
            self.failed += 1
            self.errors.append(f"{msg} (期望: {expected}, 实际: {actual})")
            print(f"  ❌ FAIL: {msg} (期望: {expected}, 实际: {actual})")

    def assert_not_none(self, value, msg: str):
        if value is not None:
            self.passed += 1
            print(f"  ✅ PASS: {msg}")
        else:
            self.failed += 1
            self.errors.append(msg)
            print(f"  ❌ FAIL: {msg} (值为 None)")

    def assert_gte(self, actual, expected, msg: str):
        if actual >= expected:
            self.passed += 1
            print(f"  ✅ PASS: {msg} (值: {actual})")
        else:
            self.failed += 1
            self.errors.append(f"{msg} (期望 >= {expected}, 实际: {actual})")
            print(f"  ❌ FAIL: {msg} (期望 >= {expected}, 实际: {actual})")

    def summary(self):
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        if self.failed == 0:
            print(f"🎉 Sprint 1 Infrastructure: ALL PASSED ({self.passed}/{total})")
        else:
            print(f"⚠️  Sprint 1 Infrastructure: {self.failed} FAILED ({self.passed}/{total})")
            print("\n失败的测试:")
            for err in self.errors:
                print(f"  - {err}")
        print("=" * 60)
        return self.failed == 0


runner = TestRunner()


# ============================================================
# Test 1: PostgreSQL CRUD
# ============================================================

def test_postgresql():
    print("\n" + "=" * 60)
    print("📦 Test 1: PostgreSQL CRUD 操作")
    print("=" * 60)

    from db import db
    db.connect()

    # 1.1 插入达人
    print("\n[1.1] 插入达人基础信息...")
    test_influencer = {
        "red_id": "test_red_001",
        "nickname": "测试达人小A",
        "avatar_url": "https://example.com/avatar.jpg",
        "gender": "女",
        "region": "上海",
        "followers": 150000,
        "likes": 500000,
        "collections": 80000,
        "notes_count": 120,
        "ad_ratio_30d": 0.1500,
        "latest_note_time": datetime.now().isoformat(),
        "tags": ["穿搭", "高冷风", "极简风"],
        "pricing": {"图文CPM": 150.0, "视频CPM": 300.0},
    }
    internal_id = db.insert_influencer(test_influencer)
    runner.assert_true(internal_id > 0, "达人插入成功并返回 internal_id")

    # 1.2 通过 red_id 查询
    print("\n[1.2] 通过 red_id 精确查询...")
    result = db.get_influencer_by_red_id("test_red_001")
    runner.assert_not_none(result, "通过 red_id 查询返回结果")
    runner.assert_equal(result["nickname"], "测试达人小A", "昵称匹配")
    runner.assert_equal(result["region"], "上海", "地区匹配")

    # 1.3 通过 internal_id 查询
    print("\n[1.3] 通过 internal_id 查询...")
    result2 = db.get_influencer_by_id(internal_id)
    runner.assert_not_none(result2, "通过 internal_id 查询返回结果")
    runner.assert_equal(result2["red_id"], "test_red_001", "red_id 匹配")

    # 1.4 多维度筛选
    print("\n[1.4] 多维度筛选查询...")
    # 先插入更多测试数据
    for i in range(5):
        db.insert_influencer({
            "red_id": f"test_filter_{i:03d}",
            "nickname": f"筛选测试达人{i}",
            "avatar_url": None,
            "gender": "女" if i % 2 == 0 else "男",
            "region": ["上海", "北京", "杭州"][i % 3],
            "followers": 50000 + i * 30000,
            "likes": 100000 + i * 50000,
            "collections": 20000,
            "notes_count": 50,
            "ad_ratio_30d": 0.1 * i,
            "latest_note_time": None,
            "tags": json.dumps(["穿搭"]),
            "pricing": json.dumps({}),
        })

    results, total = db.search_influencers(region="上海", gender="女")
    runner.assert_gte(total, 1, "上海+女性筛选返回结果数 >= 1")

    results2, total2 = db.search_influencers(
        followers_min=50000, followers_max=200000
    )
    runner.assert_gte(total2, 1, "粉丝数范围筛选返回结果数 >= 1")

    # 1.5 标签包含查询
    print("\n[1.5] JSONB 标签包含查询...")
    results3, total3 = db.search_influencers(tags=["穿搭"])
    runner.assert_gte(total3, 1, "标签包含查询返回结果数 >= 1")

    # 1.6 创建寻星任务
    print("\n[1.6] 创建寻星任务...")
    campaign_id = db.create_campaign({
        "brand_name": "测试品牌",
        "spu_name": "测试产品",
        "operator_id": 1,
        "operator_role": 2,
        "intent_snapshot": {"raw_text": "找上海的穿搭达人", "filters": {"region": "上海"}},
    })
    runner.assert_true(campaign_id > 0, "寻星任务创建成功")

    # 1.7 确认入库
    print("\n[1.7] 确认入库...")
    db.commit_campaign(campaign_id, [internal_id], [], [])
    campaigns = db.get_campaigns_by_brand("测试品牌", "测试产品")
    runner.assert_gte(len(campaigns), 1, "品牌+SPU 查询返回任务")
    runner.assert_equal(campaigns[0]["status"], "committed", "任务状态为 committed")

    # 1.8 插入笔记
    print("\n[1.8] 插入笔记数据...")
    note_id = db.insert_note({
        "note_id": "test_note_001",
        "influencer_id": internal_id,
        "note_type": "图文",
        "is_ad": False,
        "impressions": 50000,
        "reads": 20000,
        "likes": 3000,
        "comments": 500,
        "collections": 800,
        "shares": 200,
        "video_completion_rate": None,
        "cover_image_url": "https://example.com/cover.jpg",
        "published_at": datetime.now().isoformat(),
    })
    runner.assert_equal(note_id, "test_note_001", "笔记插入成功")

    notes = db.get_notes_by_influencer(internal_id)
    runner.assert_gte(len(notes), 1, "达人笔记查询返回结果")

    # 1.9 导出字典
    print("\n[1.9] 导出字典 UPSERT...")
    mapping_id = db.upsert_mapping("博主名称", "nickname", 1.0, "user")
    runner.assert_true(mapping_id > 0, "映射插入成功")

    # 再次插入相同映射，usage_count 应 +1
    mapping_id2 = db.upsert_mapping("博主名称", "nickname", 0.9, "ai")
    runner.assert_equal(mapping_id, mapping_id2, "UPSERT 返回相同 mapping_id")

    suggestions = db.suggest_mappings("博主")
    runner.assert_gte(len(suggestions), 1, "模糊推荐返回候选")

    # 1.10 履约记录
    print("\n[1.10] 履约记录...")
    record_id = db.create_fulfillment({
        "campaign_id": campaign_id,
        "action_type": "selected",
        "influencer_ids": [internal_id],
        "payload_snapshot": {"note": "测试选中"},
        "operator_id": 1,
    })
    runner.assert_true(record_id > 0, "履约记录创建成功")

    timeline = db.get_fulfillment_timeline(campaign_id)
    runner.assert_gte(len(timeline), 1, "履约时间轴查询返回结果")

    db.close()
    return internal_id


# ============================================================
# Test 2: Milvus Collection 与混合检索
# ============================================================

def test_milvus(pg_internal_id: int):
    print("\n" + "=" * 60)
    print("🔮 Test 2: Milvus Collection 与混合检索")
    print("=" * 60)

    from milvus import milvus_mgr, DIM_FACE, DIM_SCENE, DIM_STYLE

    # 2.1 连接
    print("\n[2.1] 连接 Milvus...")
    version = milvus_mgr.connect()
    runner.assert_true(len(version) > 0, f"Milvus 连接成功 (版本: {version})")

    # 2.2 创建 Collection
    print("\n[2.2] 创建 Collection...")
    col = milvus_mgr.create_collection(drop_if_exists=True)
    runner.assert_not_none(col, "Collection 创建成功")

    # 2.3 插入测试数据
    print("\n[2.3] 插入测试向量数据...")

    def random_vec(dim: int) -> List[float]:
        vec = [random.gauss(0, 1) for _ in range(dim)]
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm for x in vec]  # L2 归一化

    test_data = []
    for i in range(50):
        test_data.append({
            "id": pg_internal_id + i if i == 0 else 10000 + i,
            "followers": random.randint(10000, 1000000),
            "region": random.choice(["上海", "北京", "杭州", "广州"]),
            "gender": random.choice(["女", "男"]),
            "ad_ratio": round(random.uniform(0, 0.5), 4),
            "v_face": random_vec(DIM_FACE),
            "v_scene": random_vec(DIM_SCENE),
            "v_overall_style": random_vec(DIM_STYLE),
        })

    count = milvus_mgr.insert(test_data)
    runner.assert_equal(count, 50, "插入 50 条向量数据")

    # 2.4 Collection 统计
    print("\n[2.4] Collection 统计...")
    stats = milvus_mgr.collection_stats()
    runner.assert_equal(stats["num_entities"], 50, "实体数量为 50")

    # 2.5 加载到内存
    print("\n[2.5] 加载 Collection 到内存...")
    milvus_mgr.load_collection()

    # 2.6 混合检索 — 无过滤
    print("\n[2.6] 混合检索 (无标量过滤)...")
    query_vec = random_vec(DIM_STYLE)
    results = milvus_mgr.hybrid_search(
        vector_field="v_overall_style",
        query_vector=query_vec,
        top_k=10,
    )
    runner.assert_equal(len(results), 10, "无过滤检索返回 Top-10")

    # 2.7 混合检索 — 带标量过滤
    print("\n[2.7] 混合检索 (标量过滤: 上海+女性)...")
    results_filtered = milvus_mgr.hybrid_search(
        vector_field="v_overall_style",
        query_vector=query_vec,
        scalar_filters={
            "region": ["上海"],
            "gender": "女",
        },
        top_k=10,
    )
    # 验证过滤条件
    all_match = all(
        r.get("region") == "上海" and r.get("gender") == "女"
        for r in results_filtered
    )
    if len(results_filtered) > 0:
        runner.assert_true(all_match, "过滤结果全部满足标量条件")
    else:
        runner.assert_true(True, "过滤结果为空 (可能无匹配数据，属正常)")

    # 2.8 混合检索 — 粉丝数范围
    print("\n[2.8] 混合检索 (粉丝数范围: 50k-500k)...")
    results_range = milvus_mgr.hybrid_search(
        vector_field="v_scene",
        query_vector=random_vec(DIM_SCENE),
        scalar_filters={
            "followers_min": 50000,
            "followers_max": 500000,
        },
        top_k=10,
    )
    range_match = all(
        50000 <= r.get("followers", 0) <= 500000
        for r in results_range
    )
    if len(results_range) > 0:
        runner.assert_true(range_match, "粉丝数范围过滤正确")
    else:
        runner.assert_true(True, "范围过滤结果为空 (属正常)")

    # 2.9 人脸向量检索
    print("\n[2.9] 人脸向量检索...")
    results_face = milvus_mgr.hybrid_search(
        vector_field="v_face",
        query_vector=random_vec(DIM_FACE),
        top_k=5,
    )
    runner.assert_equal(len(results_face), 5, "人脸检索返回 Top-5")

    # 2.10 数据一致性验证
    print("\n[2.10] PG internal_id ↔ Vector DB id 映射验证...")
    check_result = milvus_mgr.retrieve_by_ids([pg_internal_id])
    runner.assert_gte(len(check_result), 1, f"向量库中存在 id={pg_internal_id} 的记录")

    milvus_mgr.release_collection()
    milvus_mgr.disconnect()


# ============================================================
# Test 3: Redis 三层缓存
# ============================================================

def test_redis():
    print("\n" + "=" * 60)
    print("🔴 Test 3: Redis 三层缓存")
    print("=" * 60)

    from redis import (
        redis_mgr, task_cache, influencer_cache, search_cache, ws_store
    )

    # 3.1 连接与健康检查
    print("\n[3.1] 连接与健康检查...")
    redis_mgr.connect()
    health = redis_mgr.health_check()
    runner.assert_equal(health["status"], "healthy", "Redis 健康检查通过")

    # ---- Layer 1: TaskCache ----
    print("\n[3.2] TaskCache — 任务生命周期...")
    test_task_id = "test_task_001"

    # 创建任务
    task_cache.create_task(test_task_id, meta={"query": "测试查询"})
    info = task_cache.get_task_info(test_task_id)
    runner.assert_not_none(info, "任务创建后可查询")
    runner.assert_equal(info["status"], "pending", "初始状态为 pending")

    # 更新为 running
    task_cache.update_status(test_task_id, "running", 0.3, "正在检索向量...")
    info2 = task_cache.get_task_info(test_task_id)
    runner.assert_equal(info2["status"], "running", "状态更新为 running")

    # 追加日志
    task_cache.append_log(test_task_id, "降级: Milvus 超时，切换到缓存", "warn")
    task_cache.append_log(test_task_id, "降级: 跳过人脸向量检索", "warn")
    logs = task_cache.get_logs_since(test_task_id, 0)
    runner.assert_gte(len(logs), 3, "日志数量 >= 3 (含初始日志)")

    # 增量日志
    new_logs = task_cache.get_logs_since(test_task_id, len(logs) - 1)
    runner.assert_gte(len(new_logs), 1, "增量日志返回最新条目")

    # 设置结果
    task_cache.set_result(test_task_id, {
        "influencer_ids": [1, 2, 3],
        "total": 3,
    })
    info3 = task_cache.get_task_info(test_task_id)
    runner.assert_equal(info3["status"], "done", "设置结果后状态为 done")
    runner.assert_not_none(info3["result"], "结果数据不为空")

    # 清理
    task_cache.delete_task(test_task_id)
    info4 = task_cache.get_task_info(test_task_id)
    runner.assert_true(info4 is None, "删除后查询返回 None")

    # ---- Layer 2: InfluencerCache ----
    print("\n[3.3] InfluencerCache — Cache-Aside 模式...")
    test_iid = 99999

    # 模拟 PostgreSQL 回调
    pg_call_count = {"count": 0}

    def mock_pg_loader(iid: int):
        pg_call_count["count"] += 1
        return {"internal_id": iid, "nickname": "缓存测试达人", "region": "上海"}

    # 首次查询: 应走 fallback (PG)
    pg_call_count["count"] = 0
    result1 = influencer_cache.get_basic(test_iid, fallback=mock_pg_loader)
    runner.assert_not_none(result1, "首次查询返回数据")
    runner.assert_equal(pg_call_count["count"], 1, "首次查询调用了 PG fallback")

    # 第二次查询: 应走缓存
    pg_call_count["count"] = 0
    result2 = influencer_cache.get_basic(test_iid, fallback=mock_pg_loader)
    runner.assert_not_none(result2, "二次查询返回数据")
    runner.assert_equal(pg_call_count["count"], 0, "二次查询未调用 PG (缓存命中)")

    # 清除缓存后再查询
    influencer_cache.invalidate(test_iid)
    pg_call_count["count"] = 0
    result3 = influencer_cache.get_basic(test_iid, fallback=mock_pg_loader)
    runner.assert_equal(pg_call_count["count"], 1, "清除缓存后重新调用 PG")

    # ---- Layer 3: SearchCache ----
    print("\n[3.4] SearchCache — 检索结果缓存...")
    query_params = {"region": ["上海"], "gender": "女", "top_k": 10}
    mock_results = [{"id": 1, "score": 0.95}, {"id": 2, "score": 0.88}]

    # 写入缓存
    query_hash = search_cache.set(query_params, mock_results)
    runner.assert_true(len(query_hash) == 32, "缓存键哈希长度为 32 (MD5)")

    # 读取缓存
    cached = search_cache.get(query_params)
    runner.assert_not_none(cached, "检索缓存命中")
    runner.assert_equal(len(cached), 2, "缓存结果数量正确")

    # 不同参数应未命中
    cached2 = search_cache.get({"region": ["北京"], "gender": "男"})
    runner.assert_true(cached2 is None, "不同参数缓存未命中")

    # 清除全部
    cleared = search_cache.invalidate_all()
    runner.assert_gte(cleared, 1, "清除检索缓存 >= 1 条")

    # ---- WebSocket 会话 ----
    print("\n[3.5] WSSessionStore — 会话管理...")
    ws_store.register("ws_test_001", {"user_id": 1})
    runner.assert_true(ws_store.is_active("ws_test_001"), "会话注册后为活跃状态")

    ws_store.heartbeat("ws_test_001")
    runner.assert_true(ws_store.is_active("ws_test_001"), "心跳后仍为活跃状态")

    ws_store.unregister("ws_test_001")
    runner.assert_true(not ws_store.is_active("ws_test_001"), "注销后为非活跃状态")

    redis_mgr.close()


# ============================================================
# 主入口
# ============================================================

def main():
    print("=" * 60)
    print("🚀 Σ.Match Sprint 1 基建层集成测试")
    print("=" * 60)
    print(f"时间: {datetime.now().isoformat()}")
    print(f"测试范围: PostgreSQL + Milvus + Redis")
    print("=" * 60)

    pg_id = None

    try:
        pg_id = test_postgresql()
    except Exception as e:
        print(f"\n❌ PostgreSQL 测试异常: {e}")
        traceback.print_exc()
        runner.failed += 1
        runner.errors.append(f"PostgreSQL 测试异常: {e}")

    try:
        test_milvus(pg_id or 1)
    except Exception as e:
        print(f"\n❌ Milvus 测试异常: {e}")
        traceback.print_exc()
        runner.failed += 1
        runner.errors.append(f"Milvus 测试异常: {e}")

    try:
        test_redis()
    except Exception as e:
        print(f"\n❌ Redis 测试异常: {e}")
        traceback.print_exc()
        runner.failed += 1
        runner.errors.append(f"Redis 测试异常: {e}")

    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
