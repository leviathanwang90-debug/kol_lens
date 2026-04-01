"""
Σ.Match Seed 数据生成器
Sprint 1 · Task 1.1.5

生成 50 条模拟达人数据（含笔记明细），覆盖以下场景:
- 不同地区: 北京/上海/杭州/广州/成都/深圳
- 不同粉丝量级: 1万 ~ 100万
- 不同内容类型: 图文为主/视频为主/混合
- 不同商单比例: 0% ~ 50%

执行方式: python -m db.seeds.seed_data
"""

import json
import random
import sys
import os
from datetime import datetime, timedelta

# 将 backend 目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db import db


# ============================================================
# 常量定义
# ============================================================

REGIONS = ["北京", "上海", "杭州", "广州", "成都", "深圳", "南京", "武汉"]
GENDERS = ["女", "女", "女", "男", "女"]  # 偏向女性（符合小红书用户画像）

STYLE_TAGS = [
    "高冷风", "甜美风", "极简风", "复古风", "街头风", "学院风",
    "日系风", "韩系风", "法式风", "运动风", "文艺风", "性感风",
]

CONTENT_TAGS = [
    "穿搭", "美妆", "护肤", "美食", "旅行", "家居", "母婴",
    "健身", "数码", "摄影", "读书", "职场", "宠物", "探店",
]

NICKNAMES_PREFIX = [
    "小", "大", "阿", "萌", "甜", "酷", "暖", "清",
    "星", "月", "花", "云", "雪", "风", "雨", "晴",
]

NICKNAMES_SUFFIX = [
    "酱", "子", "儿", "宝", "妹", "姐", "哥", "弟",
    "er", "ya", "xi", "mi", "lu", "qi", "an", "yi",
]

NOTE_TITLES = [
    "今日穿搭分享", "新入手的好物推荐", "周末探店记录",
    "旅行vlog", "日常妆容教程", "家居好物合集",
    "健身打卡第N天", "读书笔记分享", "美食制作教程",
    "开箱测评", "年度爱用品", "平价替代推荐",
]


def random_nickname() -> str:
    """生成随机昵称"""
    prefix = random.choice(NICKNAMES_PREFIX)
    suffix = random.choice(NICKNAMES_SUFFIX)
    return f"{prefix}{suffix}{random.randint(1, 99)}"


def random_tags(n: int = 3) -> list:
    """生成随机标签组合"""
    style = random.sample(STYLE_TAGS, min(random.randint(1, 2), len(STYLE_TAGS)))
    content = random.sample(CONTENT_TAGS, min(random.randint(1, 3), len(CONTENT_TAGS)))
    combined = style + content
    return combined[:n]


def random_pricing(followers: int) -> dict:
    """根据粉丝数生成合理的报价"""
    base = followers / 100  # 基础CPM
    return {
        "图文CPM": round(base * random.uniform(0.8, 1.5), 2),
        "视频CPM": round(base * random.uniform(1.2, 2.5), 2),
        "图文单价": round(base * random.uniform(5, 15), 0),
        "视频单价": round(base * random.uniform(10, 30), 0),
    }


def generate_influencer(index: int) -> dict:
    """生成一条达人数据"""
    followers = random.choice([
        random.randint(10000, 50000),       # 小博主
        random.randint(50000, 200000),      # 中腰部
        random.randint(200000, 500000),     # 头部
        random.randint(500000, 1000000),    # 大V
    ])

    return {
        "red_id": f"red_{10000 + index:05d}",
        "nickname": random_nickname(),
        "avatar_url": f"https://picsum.photos/seed/{index}/200/200",
        "gender": random.choice(GENDERS),
        "region": random.choice(REGIONS),
        "followers": followers,
        "likes": int(followers * random.uniform(2, 10)),
        "collections": int(followers * random.uniform(0.5, 3)),
        "notes_count": random.randint(20, 500),
        "ad_ratio_30d": round(random.uniform(0.0, 0.5), 4),
        "latest_note_time": (
            datetime.now() - timedelta(days=random.randint(0, 30))
        ).isoformat(),
        "tags": json.dumps(random_tags(), ensure_ascii=False),
        "pricing": json.dumps(random_pricing(followers), ensure_ascii=False),
    }


def generate_notes(influencer_id: int, count: int = 10) -> list:
    """为一个达人生成笔记数据"""
    notes = []
    content_types = random.choice([
        ["图文"] * 8 + ["视频"] * 2,   # 图文为主
        ["图文"] * 3 + ["视频"] * 7,   # 视频为主
        ["图文"] * 5 + ["视频"] * 5,   # 混合
    ])

    for i in range(count):
        note_type = random.choice(content_types)
        is_ad = random.random() < 0.2  # 20% 概率是商单

        base_engagement = random.randint(100, 10000)
        notes.append({
            "note_id": f"note_{influencer_id}_{i:03d}",
            "influencer_id": influencer_id,
            "note_type": note_type,
            "is_ad": is_ad,
            "impressions": int(base_engagement * random.uniform(5, 20)),
            "reads": int(base_engagement * random.uniform(2, 8)),
            "likes": int(base_engagement * random.uniform(0.5, 3)),
            "comments": int(base_engagement * random.uniform(0.05, 0.5)),
            "collections": int(base_engagement * random.uniform(0.1, 1)),
            "shares": int(base_engagement * random.uniform(0.02, 0.2)),
            "video_completion_rate": (
                round(random.uniform(0.1, 0.9), 4) if note_type == "视频" else None
            ),
            "cover_image_url": f"https://picsum.photos/seed/{influencer_id}_{i}/400/300",
            "published_at": (
                datetime.now() - timedelta(days=random.randint(0, 90))
            ).isoformat(),
        })

    return notes


def seed():
    """执行 Seed 数据插入"""
    print("=" * 60)
    print("Σ.Match Seed 数据生成器")
    print("=" * 60)

    db.connect()

    # 1. 插入 50 条达人数据
    print("\n[1/4] 插入达人基础信息...")
    influencer_ids = []
    for i in range(50):
        data = generate_influencer(i)
        internal_id = db.insert_influencer(data)
        influencer_ids.append(internal_id)
        if (i + 1) % 10 == 0:
            print(f"  ✓ 已插入 {i + 1}/50 条达人数据")

    # 2. 为每个达人生成 5-15 条笔记
    print("\n[2/4] 插入达人笔记明细...")
    total_notes = 0
    for idx, iid in enumerate(influencer_ids):
        notes = generate_notes(iid, count=random.randint(5, 15))
        for note in notes:
            db.insert_note(note)
            total_notes += 1
        if (idx + 1) % 10 == 0:
            print(f"  ✓ 已处理 {idx + 1}/50 位达人的笔记")
    print(f"  ✓ 共插入 {total_notes} 条笔记数据")

    # 3. 创建 5 条模拟寻星任务
    print("\n[3/4] 插入模拟寻星任务...")
    campaigns = [
        {"brand_name": "完美日记", "spu_name": "小细跟口红", "operator_id": 1, "operator_role": 2,
         "intent_snapshot": {"raw_text": "找上海的高冷风女博主", "hard_filters": {"location": ["上海"], "gender": "女"}}},
        {"brand_name": "花西子", "spu_name": "蜜粉饼", "operator_id": 2, "operator_role": 3,
         "intent_snapshot": {"raw_text": "找杭州的甜美风美妆达人", "hard_filters": {"location": ["杭州"]}}},
        {"brand_name": "元气森林", "spu_name": "气泡水", "operator_id": 1, "operator_role": 1,
         "intent_snapshot": {"raw_text": "找健身类达人推广气泡水", "hard_filters": {}}},
        {"brand_name": "泡泡玛特", "spu_name": "MOLLY系列", "operator_id": 3, "operator_role": 2,
         "intent_snapshot": {"raw_text": "找潮玩收藏类博主", "hard_filters": {}}},
        {"brand_name": "完美日记", "spu_name": "眼影盘", "operator_id": 2, "operator_role": 3,
         "intent_snapshot": {"raw_text": "找北京的美妆达人", "hard_filters": {"location": ["北京"]}}},
    ]

    campaign_ids = []
    for c in campaigns:
        cid = db.create_campaign(c)
        campaign_ids.append(cid)
        print(f"  ✓ 创建任务: {c['brand_name']} - {c['spu_name']} (ID: {cid})")

    # 4. 为部分任务创建履约记录
    print("\n[4/4] 插入模拟履约记录...")
    # 第一个任务: 完整流程
    selected = random.sample(influencer_ids[:20], 5)
    db.commit_campaign(campaign_ids[0], selected, [], [])
    for action in ["selected", "invited", "ordered"]:
        db.create_fulfillment({
            "campaign_id": campaign_ids[0],
            "action_type": action,
            "influencer_ids": selected[:3] if action != "selected" else selected,
            "payload_snapshot": {"note": f"模拟{action}操作"},
            "operator_id": 1,
        })
    print(f"  ✓ 任务 {campaign_ids[0]} 创建了 3 条履约记录")

    # 第二个任务: 部分流程
    selected2 = random.sample(influencer_ids[20:40], 3)
    db.commit_campaign(campaign_ids[1], selected2, [], [])
    db.create_fulfillment({
        "campaign_id": campaign_ids[1],
        "action_type": "selected",
        "influencer_ids": selected2,
        "payload_snapshot": {"note": "模拟选中操作"},
        "operator_id": 2,
    })
    print(f"  ✓ 任务 {campaign_ids[1]} 创建了 1 条履约记录")

    print("\n" + "=" * 60)
    print("✅ Seed 数据生成完成!")
    print(f"   - 达人: {len(influencer_ids)} 条")
    print(f"   - 笔记: {total_notes} 条")
    print(f"   - 任务: {len(campaign_ids)} 条")
    print(f"   - 履约: 4 条")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    seed()
