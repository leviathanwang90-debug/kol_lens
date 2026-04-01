# Σ.Match 后端基建层 — Sprint 1

> PostgreSQL 四表建模 + Milvus 三向量 Collection + Redis 三层缓存

## 目录结构

```
backend/
├── config/
│   └── __init__.py              # 全局配置 (PG/Redis/Milvus 连接参数)
├── db/
│   ├── __init__.py              # PostgreSQL 连接池 + CRUD 封装
│   ├── migrations/
│   │   └── init.sql             # DDL 初始化脚本 (5表 + 1视图)
│   └── seeds/
│       └── seed_data.py         # 50条模拟达人 + 笔记 + 任务 Seed 数据
├── milvus/
│   └── __init__.py              # Milvus Collection 管理 + Hybrid Search
├── redis/
│   └── __init__.py              # 三层缓存: TaskCache / InfluencerCache / SearchCache
├── tests/
│   └── test_infrastructure.py   # 端到端集成测试
├── docker-compose.yml           # 基础设施编排 (PG + Redis + Milvus + etcd + MinIO)
├── .env.example                 # 环境变量模板
├── requirements.txt             # Python 依赖
└── README.md                    # 本文件
```

## 快速开始

### 1. 启动基础设施

```bash
cd backend

# 复制环境变量
cp .env.example .env

# 启动全部服务 (PostgreSQL + Redis + Milvus + etcd + MinIO)
docker-compose up -d

# 查看服务状态
docker-compose ps
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化数据

PostgreSQL 表结构会在容器首次启动时自动创建（通过 `init.sql`）。

```bash
# 插入 Seed 测试数据 (50条达人 + 笔记 + 任务)
cd backend
python -m db.seeds.seed_data
```

### 4. 运行集成测试

```bash
cd backend
python -m tests.test_infrastructure
```

预期输出：`Sprint 1 Infrastructure: ALL PASSED`

## 数据库 Schema

### PostgreSQL (5 表 + 1 视图)

| 表名 | 说明 | 关键索引 |
|------|------|----------|
| `influencer_basics` | 达人基础信息 | `red_id` UNIQUE, `region` B-Tree, `tags` GIN |
| `campaign_history` | 寻星任务历史 | `(brand_name, spu_name)` 复合, `status` |
| `export_dictionary` | 导出映射字典 | `(user_input_header, mapped_standard_key)` UNIQUE |
| `influencer_notes` | 达人笔记明细 | `influencer_id` FK, `published_at` DESC |
| `fulfillment_records` | 履约记录 | `campaign_id` FK, `action_type` |
| `v_influencer_profile` | 达人画像视图 | — (JOIN 笔记统计) |

### Milvus Collection

**Collection**: `influencer_multimodal_vectors`

| 字段 | 类型 | 维度 | 说明 |
|------|------|------|------|
| `id` | INT64 (PK) | — | 映射 PG `internal_id` |
| `followers` | INT64 | — | 标量过滤: 粉丝数 |
| `region` | VARCHAR(64) | — | 标量过滤: 地区 |
| `gender` | VARCHAR(8) | — | 标量过滤: 性别 |
| `ad_ratio` | FLOAT | — | 标量过滤: 商单比例 |
| `v_face` | FLOAT_VECTOR | 512 | InsightFace 人脸向量 |
| `v_scene` | FLOAT_VECTOR | 768 | CLIP 场景向量 |
| `v_overall_style` | FLOAT_VECTOR | 768 | 时序融合风格向量 |

### Redis 键命名规范

| 键模式 | 用途 | TTL |
|--------|------|-----|
| `task:{task_id}:status` | 异步任务状态 | 1 小时 |
| `task:{task_id}:result` | 异步任务结果 | 1 小时 |
| `task:{task_id}:logs` | 降级日志列表 | 1 小时 |
| `influencer:{id}:basic` | 达人基础信息缓存 | 30 分钟 |
| `influencer:{id}:notes` | 达人笔记列表缓存 | 15 分钟 |
| `search:{hash}:result` | 检索结果缓存 | 10 分钟 |
| `ws:{session_id}:channel` | WebSocket 会话 | 24 小时 |

## 核心 API

### PostgreSQL CRUD (`db.Database`)

```python
from db import db

db.connect()

# 插入达人
internal_id = db.insert_influencer({...})

# 多维度筛选
results, total = db.search_influencers(region="上海", followers_min=50000)

# 创建寻星任务
campaign_id = db.create_campaign({...})

db.close()
```

### Milvus 混合检索 (`milvus.MilvusManager`)

```python
from milvus import milvus_mgr

milvus_mgr.connect()
milvus_mgr.create_collection()
milvus_mgr.load_collection()

# 混合检索: 标量过滤 + 向量相似度
results = milvus_mgr.hybrid_search(
    vector_field="v_overall_style",
    query_vector=[...],  # 768维
    scalar_filters={"region": ["上海"], "gender": "女"},
    top_k=100,
)

# 多向量加权检索
results = milvus_mgr.multi_vector_search(
    query_vectors={
        "v_overall_style": [...],
        "v_face": [...],
    },
    weights={"v_overall_style": 0.7, "v_face": 0.3},
)
```

### Redis 三层缓存

```python
from redis import task_cache, influencer_cache, search_cache

# Layer 1: 任务状态管理
task_cache.create_task("task_001")
task_cache.update_status("task_001", "running", 0.5)
task_cache.set_result("task_001", {"ids": [1, 2, 3]})

# Layer 2: 达人缓存 (Cache-Aside)
data = influencer_cache.get_basic(123, fallback=db.get_influencer_by_id)

# Layer 3: 检索结果缓存
search_cache.set({"region": ["上海"]}, results)
cached = search_cache.get({"region": ["上海"]})
```

## 服务端口

| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | 5432 | 关系型数据库 |
| Redis | 6379 | 缓存 + 消息代理 |
| Milvus | 19530 | 向量数据库 |
| MinIO API | 9000 | 对象存储 API |
| MinIO Console | 9001 | 对象存储管理界面 |
| Milvus Metrics | 9091 | 健康检查 + 指标 |

## 下一步 (Sprint 2)

Sprint 2 将在此基建层之上构建**多模态特征提取 DAG 流水线**：
- YOLO v8 人脸/场景检测
- InsightFace 512 维人脸向量提取
- CLIP ViT-L/14 768 维场景向量提取
- 时序融合风格向量计算
- DAG 编排引擎将处理结果写入 Milvus Collection
