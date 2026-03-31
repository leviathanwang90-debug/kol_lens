# Σ.Match 智能寻星工作站 — Sprint 详细任务清单

> 本文档是《全栈开发路线图》的执行层展开，将每个 Sprint 中的任务进一步拆解为可直接分配给工程师的**原子级子任务**。每条子任务均包含技术实现要点、上游依赖、预估工时和验收标准，确保团队成员拿到清单即可开工，无需二次解读。

---

## Sprint 1：基建层 — 数据地基与存储架构

**目标**：搭建 PostgreSQL + Milvus + Redis 三套存储服务，完成全部 Schema 定义，提供可运行的 Seed 脚本，使后续 Sprint 可以直接读写数据。

**负责人**：后端工程师 A（数据架构）
**工期**：2 周（第 1-2 周）
**里程碑验收**：三套存储服务全部就绪，通过集成测试脚本验证插入、查询、缓存读写均正常。

---

### 1.1 PostgreSQL 关系型数据库搭建

#### Task 1.1.1 — 设计并创建 `influencer_basics` 表

这是系统中最核心的关系表，存储每位达人的结构化基础信息。表结构需要支撑后续的资产库查询、入库打标和报价计算等多个业务场景。

**技术实现要点**：

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `internal_id` | SERIAL | PRIMARY KEY | 自增主键，映射 Milvus 的 id 字段 |
| `red_id` | VARCHAR(64) | UNIQUE, NOT NULL | 小红书号，建立唯一索引 |
| `nickname` | VARCHAR(128) | NOT NULL | 达人昵称 |
| `avatar_url` | TEXT | — | 头像 CDN 地址 |
| `gender` | VARCHAR(8) | — | 性别（男/女/未知） |
| `region` | VARCHAR(64) | INDEX | 所在地区，冗余至 Milvus 用于标量过滤 |
| `followers` | INTEGER | DEFAULT 0 | 粉丝数，冗余至 Milvus |
| `likes` | INTEGER | DEFAULT 0 | 获赞数 |
| `collections` | INTEGER | DEFAULT 0 | 收藏数 |
| `notes_count` | INTEGER | DEFAULT 0 | 笔记总数 |
| `ad_ratio_30d` | DECIMAL(5,4) | — | 近 30 天商单比例（0.0000-1.0000） |
| `latest_note_time` | TIMESTAMP | — | 最新笔记发布时间，触发特征更新 |
| `tags` | JSONB | DEFAULT '[]' | 达人标签数组（如 ["穿搭","高冷风"]） |
| `pricing` | JSONB | DEFAULT '{}' | 报价信息（图文CPM、视频CPM等） |
| `created_at` | TIMESTAMP | DEFAULT NOW() | 入库时间 |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | 最后更新时间 |

需要创建的索引包括：`red_id` 唯一索引、`region` B-Tree 索引（支持地区筛选）、`followers` B-Tree 索引（支持粉丝数范围查询）、`created_at` B-Tree 索引（支持时间排序）、`tags` GIN 索引（支持 JSONB 标签包含查询）。

**依赖**：无（Sprint 首任务）
**预估工时**：0.5 天
**验收标准**：可插入 10 条测试数据并通过 `red_id` 精确查询、`region` 范围查询、`tags` 包含查询均返回正确结果。

---

#### Task 1.1.2 — 设计并创建 `campaign_history` 表

该表记录每次寻星任务的完整上下文与决策结果，是 Rocchio 向量平移算法获取历史偏好数据的核心来源，也是资产库履约追踪的数据基础。

**技术实现要点**：

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `campaign_id` | SERIAL | PRIMARY KEY | 任务自增主键 |
| `brand_name` | VARCHAR(128) | NOT NULL, INDEX | 品牌名称 |
| `spu_name` | VARCHAR(256) | NOT NULL, INDEX | SPU 名称 |
| `operator_id` | INTEGER | — | 操作人 ID |
| `operator_role` | SMALLINT | NOT NULL | 角色类型（1:采购, 2:策划, 3:客户） |
| `selected_influencer_ids` | JSONB | DEFAULT '[]' | 选中达人 internal_id 数组 |
| `pending_influencer_ids` | JSONB | DEFAULT '[]' | 待定达人 internal_id 数组 |
| `rejected_influencer_ids` | JSONB | DEFAULT '[]' | 淘汰达人 internal_id 数组 |
| `intent_snapshot` | JSONB | — | 本次意图解析的完整 JSON 快照 |
| `query_vector_snapshot` | JSONB | — | 最终查询向量的序列化存储 |
| `status` | VARCHAR(16) | DEFAULT 'active' | 任务状态（active/committed/archived） |
| `created_at` | TIMESTAMP | DEFAULT NOW() | 创建时间 |
| `committed_at` | TIMESTAMP | — | 确认入库时间 |

需要创建复合索引 `(brand_name, spu_name)` 以支持品牌+SPU 联合查询，以及 `operator_role` 索引支持按角色筛选。

**依赖**：无
**预估工时**：0.5 天
**验收标准**：可插入包含 JSONB 数组的完整记录，通过品牌+SPU 联合查询返回正确结果，JSONB 字段可正确存取达人 ID 数组。

---

#### Task 1.1.3 — 设计并创建 `export_dictionary` 表

该表是智能导出引擎的知识库，存储用户手动确认的非标准表头到系统标准字段的映射关系。每次用户在导出流程中确认一个新的映射对，系统都会将其持久化到此表，使后续同类导出自动匹配。

**技术实现要点**：

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `mapping_id` | SERIAL | PRIMARY KEY | 自增主键 |
| `user_input_header` | VARCHAR(256) | NOT NULL | 用户输入的非标准表头名 |
| `mapped_standard_key` | VARCHAR(256) | NOT NULL | 映射到的系统标准字段名 |
| `confidence` | DECIMAL(3,2) | DEFAULT 1.00 | 匹配置信度（AI 推荐为 0.xx，用户确认为 1.00） |
| `source` | VARCHAR(16) | DEFAULT 'user' | 来源（user: 用户确认, ai: AI 推荐） |
| `usage_count` | INTEGER | DEFAULT 1 | 被使用次数（用于排序推荐优先级） |
| `created_at` | TIMESTAMP | DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | 最后使用时间 |

需要创建 `user_input_header` 的 UNIQUE 约束（或配合 `mapped_standard_key` 的联合唯一约束），以及 `usage_count DESC` 索引用于推荐排序。

**依赖**：无
**预估工时**：0.3 天
**验收标准**：可插入映射对，通过 `user_input_header` 模糊查询返回候选映射列表，按 `usage_count` 降序排列。

---

#### Task 1.1.4 — 设计并创建辅助业务表

除上述三张核心表外，还需要创建以下辅助表以支撑完整业务流程。

**`influencer_notes` 表**（达人笔记明细）：存储每篇笔记的结构化数据，支撑 34 维数据矩阵的计算。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `note_id` | VARCHAR(64), PK | 笔记唯一 ID |
| `influencer_id` | INTEGER, FK | 关联 influencer_basics |
| `note_type` | VARCHAR(16) | 笔记类型（图文/视频） |
| `is_ad` | BOOLEAN | 是否为商业合作笔记 |
| `impressions` | INTEGER | 曝光数 |
| `reads` | INTEGER | 阅读数 |
| `likes` | INTEGER | 点赞数 |
| `comments` | INTEGER | 评论数 |
| `collections` | INTEGER | 收藏数 |
| `shares` | INTEGER | 分享数 |
| `video_completion_rate` | DECIMAL(5,4) | 视频完播率（仅视频笔记） |
| `cover_image_url` | TEXT | 封面图 URL |
| `published_at` | TIMESTAMP | 发布时间 |

**`fulfillment_records` 表**（履约记录）：存储邀约、下单等履约操作的历史快照。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `record_id` | SERIAL, PK | 自增主键 |
| `campaign_id` | INTEGER, FK | 关联 campaign_history |
| `action_type` | VARCHAR(16) | 操作类型（invite/order/deliver/settle） |
| `influencer_ids` | JSONB | 涉及的达人 ID 列表 |
| `payload_snapshot` | JSONB | 操作时的表单/文案快照 |
| `operator_id` | INTEGER | 操作人 |
| `created_at` | TIMESTAMP | 操作时间 |

**依赖**：Task 1.1.1, Task 1.1.2
**预估工时**：0.5 天
**验收标准**：外键关联正确，可通过 `influencer_id` JOIN 查询达人的全部笔记数据。

---

#### Task 1.1.5 — 编写 Migration 脚本与 Seed 数据

使用 Alembic（Python）或 Flyway（Java）编写数据库迁移脚本，确保所有表结构变更可追踪、可回滚。同时编写 Seed 脚本，插入至少 50 条模拟达人数据（含笔记明细），用于后续开发和测试。

Seed 数据需要覆盖以下场景：不同地区（北京/上海/杭州/广州）、不同粉丝量级（1万-100万）、不同内容类型（图文为主/视频为主/混合）、不同商单比例（0%-50%）。

**依赖**：Task 1.1.1 - 1.1.4
**预估工时**：1 天
**验收标准**：执行 `python migrate.py upgrade` 一键创建全部表，执行 `python seed.py` 插入 50 条完整测试数据，执行 `python migrate.py downgrade` 可回滚。

---

### 1.2 Milvus 向量数据库搭建

#### Task 1.2.1 — 部署 Milvus 实例

使用 Docker Compose 部署 Milvus Standalone 实例（开发环境），包含 etcd、MinIO、Milvus 三个容器。编写 `docker-compose.milvus.yml` 配置文件，确保数据持久化到宿主机卷。

**技术实现要点**：Milvus 2.x 版本要求 etcd 作为元数据存储、MinIO 作为对象存储。开发环境建议使用 Standalone 模式（单节点），生产环境再切换为 Cluster 模式。需要配置的关键参数包括：`dataCoord.segment.maxSize`（段大小，影响索引构建时机）、`proxy.maxTaskNum`（最大并发任务数）。

**依赖**：无
**预估工时**：0.5 天
**验收标准**：`docker-compose up -d` 启动后，通过 `pymilvus` 连接成功，`utility.get_server_version()` 返回版本号。

---

#### Task 1.2.2 — 创建 Collection 并定义 Schema

创建 `influencer_multimodal_vectors` Collection，定义完整的 Schema。这是混合检索（Hybrid Search）的核心数据结构，标量字段从 PostgreSQL 冗余同步而来，向量字段由解剖层流水线写入。

**技术实现要点**：

```python
# Schema 定义伪代码
fields = [
    FieldSchema("id", DataType.INT64, is_primary=True),          # 映射 PG internal_id
    FieldSchema("followers", DataType.INT64),                      # 标量索引：粉丝数
    FieldSchema("region", DataType.VARCHAR, max_length=64),        # 标量索引：地区
    FieldSchema("gender", DataType.VARCHAR, max_length=8),         # 标量索引：性别
    FieldSchema("ad_ratio", DataType.FLOAT),                       # 标量索引：商单比例
    FieldSchema("v_face", DataType.FLOAT_VECTOR, dim=512),         # InsightFace 人脸向量
    FieldSchema("v_scene", DataType.FLOAT_VECTOR, dim=768),        # CLIP 场景向量
    FieldSchema("v_overall_style", DataType.FLOAT_VECTOR, dim=768) # 时序融合风格向量
]
```

向量索引初始使用 IVF_FLAT（开发阶段便于调试），Sprint 6 优化阶段切换为 HNSW。标量字段需要分别创建索引以支持过滤。

**依赖**：Task 1.2.1
**预估工时**：0.5 天
**验收标准**：Collection 创建成功，可插入一条包含全部字段的测试数据，`collection.num_entities` 返回 1。

---

#### Task 1.2.3 — 编写 Hybrid Search 基础查询封装

封装一个通用的混合检索函数 `hybrid_search()`，接收标量过滤条件和查询向量，返回 Top-K 结果。该函数是后续大脑层排序和调度层降级的基础调用单元。

**技术实现要点**：Milvus 的 Hybrid Search 通过 `expr` 参数实现标量过滤，与向量相似度检索在引擎内部联合执行。需要支持的过滤表达式包括：`region in ["上海", "杭州"]`、`followers >= 50000 and followers <= 500000`、`gender == "女"`、`ad_ratio < 0.3`。查询向量可指定使用 `v_overall_style`（默认）、`v_face` 或 `v_scene` 中的任意一个。

函数签名建议如下：

```python
def hybrid_search(
    vector_field: str,           # 使用哪个向量字段检索
    query_vector: List[float],   # 查询向量
    scalar_filters: dict,        # 标量过滤条件
    top_k: int = 100,            # 返回数量
    metric_type: str = "COSINE"  # 距离度量
) -> List[SearchResult]:
    ...
```

**依赖**：Task 1.2.2
**预估工时**：1 天
**验收标准**：插入 50 条测试向量数据后，给定标量条件 + 随机查询向量，返回 Top-10 结果且标量条件全部满足。

---

### 1.3 Redis 缓存层搭建

#### Task 1.3.1 — 部署 Redis 并定义键命名规范

使用 Docker 部署 Redis 实例（可复用 docker-compose 文件），配置持久化策略（AOF + RDB 混合）。定义统一的键命名规范，避免后续开发中键名冲突。

**键命名规范**：

| 键模式 | 用途 | TTL |
|--------|------|-----|
| `task:{task_id}:status` | 异步任务状态（pending/running/done/failed） | 1 小时 |
| `task:{task_id}:result` | 异步任务结果（JSON 序列化） | 1 小时 |
| `task:{task_id}:logs` | 降级日志列表（List 类型，RPUSH 追加） | 1 小时 |
| `influencer:{id}:basic` | 达人基础信息缓存 | 30 分钟 |
| `influencer:{id}:notes` | 达人笔记列表缓存 | 15 分钟 |
| `search:{hash}:result` | 相同查询条件的结果缓存 | 10 分钟 |
| `ws:{session_id}:channel` | WebSocket 会话通道 | 连接期间 |

**依赖**：无
**预估工时**：0.3 天
**验收标准**：Redis 连接正常，TTL 策略生效（设置后到期自动删除），List 类型 RPUSH/LRANGE 操作正常。

---

#### Task 1.3.2 — 封装任务状态读写工具函数

编写 Redis 操作的工具类 `TaskCache`，提供异步任务全生命周期的状态管理。这是调度层 Celery Worker 与前端轮询之间的桥梁。

**需要封装的核心方法**：

```python
class TaskCache:
    def create_task(task_id: str) -> None:
        """创建任务，状态设为 pending"""

    def update_status(task_id: str, status: str, progress: float = 0) -> None:
        """更新任务状态和进度百分比"""

    def append_log(task_id: str, log_line: str) -> None:
        """追加一条降级日志（RPUSH 到 List）"""

    def set_result(task_id: str, result: dict) -> None:
        """设置任务最终结果"""

    def get_task_info(task_id: str) -> dict:
        """获取任务完整信息（状态+进度+日志+结果）"""

    def get_logs_since(task_id: str, start_index: int) -> List[str]:
        """获取指定索引之后的增量日志（前端轮询用）"""
```

**依赖**：Task 1.3.1
**预估工时**：0.5 天
**验收标准**：单元测试覆盖全部方法，模拟完整的任务生命周期（create → update → append_log × N → set_result → get_task_info）。

---

#### Task 1.3.3 — 编写达人数据缓存封装

封装达人数据的缓存读写逻辑，采用 Cache-Aside 模式：先查 Redis，命中则直接返回；未命中则查 PostgreSQL，写入 Redis 后返回。

**依赖**：Task 1.3.1, Task 1.1.1
**预估工时**：0.5 天
**验收标准**：首次查询走 PostgreSQL（缓存未命中），第二次查询走 Redis（缓存命中），TTL 到期后再次走 PostgreSQL。

---

### Sprint 1 集成验证

#### Task 1.4.1 — 编写集成测试脚本

编写一个端到端的集成测试脚本 `test_infrastructure.py`，依次验证：PostgreSQL 全部表的 CRUD 操作、Milvus Collection 的插入与混合检索、Redis 的任务状态全生命周期、三套服务之间的数据一致性（PostgreSQL `internal_id` 与 Milvus `id` 的映射）。

**依赖**：全部 Sprint 1 任务
**预估工时**：1 天
**验收标准**：脚本一键执行，全部断言通过，输出 "Sprint 1 Infrastructure: ALL PASSED"。

---

## Sprint 2：解剖层 — 多模态特征提纯流水线

**目标**：构建完整的 DAG 流水线，实现从达人图片/文本到多维向量的自动化转换，并将结果写入 Milvus。

**负责人**：算法工程师 B（AI/ML）
**工期**：3 周（第 3-5 周）
**里程碑验收**：给定 100 个达人的小红书主页数据，流水线可批量处理并将全部向量写入 Milvus。

---

### 2.1 数据采集节点（Node 1: Data Ingest）

#### Task 2.1.1 — 图片下载器（支持并发、重试、超时）

编写异步图片下载模块，使用 `aiohttp` 或 `httpx` 实现并发下载。每个达人需要下载其近 20 篇笔记的封面图（从 `influencer_notes` 表获取 URL）。

**技术实现要点**：并发度控制在 10-20（避免触发反爬）；单张图片超时设为 10 秒；失败重试 3 次，间隔指数退避（1s → 2s → 4s）；所有失败记录写入 `download_failures.log`，不阻塞流水线继续处理下一张。需要设置合理的 User-Agent 和 Referer 头。

**依赖**：Sprint 1 Task 1.1.4（需要 influencer_notes 表中的图片 URL）
**预估工时**：1 天
**验收标准**：批量下载 100 张图片，成功率 > 95%，失败记录完整写入日志。

---

#### Task 2.1.2 — 图片预处理（Resize + 格式标准化）

对下载的原始图片进行标准化处理：统一 Resize 到 224×224 像素（CLIP 模型的标准输入尺寸），转换为 RGB 模式的 JPEG 格式，质量设为 95。处理过程中需要处理的边界情况包括：GIF 动图（取第一帧）、CMYK 色彩空间（转 RGB）、损坏图片（跳过并记录）。

**依赖**：Task 2.1.1
**预估工时**：0.5 天
**验收标准**：输入任意格式图片，输出统一 224×224 RGB JPEG，无异常中断。

---

#### Task 2.1.3 — OSS 存储封装（上传/读取/删除）

封装内部对象存储（MinIO 或阿里云 OSS）的操作接口。预处理后的图片上传到 OSS，返回可访问的 URL。后续的 YOLO、InsightFace、CLIP 模型均从 OSS 读取图片。

**技术实现要点**：使用 `boto3`（兼容 S3 协议）或 `minio-py` 客户端。Bucket 命名为 `sigma-match-images`，对象键格式为 `{influencer_id}/{note_id}_224.jpg`。需要封装 `upload_image()`、`get_image_url()`、`delete_image()` 三个方法。

**依赖**：Task 2.1.2
**预估工时**：0.5 天
**验收标准**：上传一张图片后通过 URL 可正常访问，删除后 URL 返回 404。

---

### 2.2 语义分割节点（Node 2: Semantic Split）

#### Task 2.2.1 — 部署 YOLO 分割模型（GPU 推理）

部署 YOLOv8-seg（实例分割版本）模型，用于将图片中的人物区域和背景区域分离。模型输出两张掩码图：`Mask_Person`（人物像素为白色，其余为黑色）和 `Mask_Background`（反转）。

**技术实现要点**：使用 `ultralytics` 库加载预训练模型 `yolov8m-seg.pt`。推理时设置 `conf=0.5`（置信度阈值）、`classes=[0]`（仅检测 person 类别）。如果图片中未检测到人物，`Mask_Person` 为全黑（后续 InsightFace 跳过该图），`Mask_Background` 为全白。需要处理多人场景：取面积最大的人物区域作为主体。

**依赖**：Task 2.1.3（从 OSS 读取图片）
**预估工时**：1.5 天
**验收标准**：输入包含人物的图片，输出正确的 Person/Background 二值掩码；输入无人物图片，Person 掩码为空。GPU 推理单张 < 100ms。

---

#### Task 2.2.2 — 部署 PaddleOCR 文字提取

部署 PaddleOCR 模型，提取图片中的文字内容。小红书笔记封面图通常包含标题文字、标签文字等，这些文字信息是理解笔记主题的重要补充。

**技术实现要点**：使用 `paddleocr` 库，设置 `use_angle_cls=True`（支持旋转文字）、`lang='ch'`（中文模型）。输出为文字区域列表，每个区域包含坐标框和识别文本。将所有识别文本拼接为一个字符串 `Text_Content`，用空格分隔。如果未识别到任何文字，`Text_Content` 设为空字符串。

**依赖**：Task 2.1.3
**预估工时**：1 天
**验收标准**：输入含中文文字的图片，正确识别文字内容（准确率 > 85%）；输入纯图片，返回空字符串。

---

#### Task 2.2.3 — 编写 Node 2 编排逻辑

将 YOLO 分割和 PaddleOCR 提取组合为一个编排函数 `semantic_split()`，对单张图片同时执行两个操作并返回结构化结果。

**函数签名**：

```python
def semantic_split(image_path: str) -> dict:
    """
    Returns:
    {
        "mask_person": np.ndarray | None,    # 人物掩码（224×224 二值图）
        "mask_background": np.ndarray | None, # 背景掩码
        "text_content": str,                  # OCR 提取的文字
        "has_person": bool                    # 是否检测到人物
    }
    """
```

YOLO 和 PaddleOCR 可以并行执行（两者无依赖关系），使用 `concurrent.futures.ThreadPoolExecutor` 并行调度。

**依赖**：Task 2.2.1, Task 2.2.2
**预估工时**：0.5 天
**验收标准**：单张图片同时产出掩码 + 文本，总耗时 < 300ms（GPU）。

---

### 2.3 并行嵌入节点（Node 3: Parallel Embedding）

#### Task 2.3.1 — InsightFace 模型部署与推理封装

部署 InsightFace 人脸识别模型，用于提取达人的面部特征向量。该向量用于"找相似脸型/气质的达人"场景。

**技术实现要点**：使用 `insightface` 库加载 `buffalo_l` 模型包。推理流程为：将 `Mask_Person` 覆盖到原图上（背景置黑），送入 InsightFace 的 `get()` 方法，提取 512 维 embedding。如果 `has_person == False`，跳过此步骤，`V_face` 设为 512 维零向量。如果检测到多张人脸，取面积最大的一张。

**依赖**：Task 2.2.3（需要 mask_person 输出）
**预估工时**：1.5 天
**验收标准**：输入含人脸的图片，输出 512 维非零向量；输入无人脸图片，输出零向量。两张相似人脸的余弦相似度 > 0.6。

---

#### Task 2.3.2 — CLIP Vision 模型部署与推理封装

部署 CLIP Vision 模型（ViT-L/14），用于提取图片的场景/风格特征向量。该向量捕捉图片的整体视觉风格（如"高冷风"、"日系清新"等）。

**技术实现要点**：使用 `transformers` 库加载 `openai/clip-vit-large-patch14` 模型。推理流程为：将 `Mask_Background` 覆盖到原图上（人物区域置黑，保留场景），经过 CLIP 预处理后送入 Vision Encoder，提取 768 维 embedding。如果需要同时考虑人物穿搭风格，可以将原图（不做掩码）也送入 CLIP，取两个向量的加权平均。

**依赖**：Task 2.2.3（需要 mask_background 输出）
**预估工时**：1.5 天
**验收标准**：输入场景图片，输出 768 维向量。两张风格相似的图片余弦相似度 > 0.7。

---

#### Task 2.3.3 — CLIP Text 模型部署与推理封装

部署 CLIP Text 模型，用于将 OCR 提取的文字内容和用户输入的自然语言查询转化为文本向量。该向量与 Vision 向量处于同一语义空间，支持跨模态检索。

**技术实现要点**：使用与 Task 2.3.2 相同的 CLIP 模型的 Text Encoder 部分。输入为 `Text_Content` 字符串，输出 768 维 embedding。如果 `Text_Content` 为空，输出零向量。需要注意 CLIP 的最大 token 长度为 77，超长文本需要截断或分段编码后取平均。

**依赖**：Task 2.2.3（需要 text_content 输出）
**预估工时**：0.5 天（复用 Task 2.3.2 的模型加载）
**验收标准**：输入中文文本，输出 768 维向量。语义相近的文本余弦相似度 > 0.7。

---

#### Task 2.3.4 — GPU 并行编排（ThreadPoolExecutor）

将 InsightFace、CLIP Vision、CLIP Text 三个推理任务编排为并行执行，最大化 GPU 利用率。

**技术实现要点**：三个模型加载到 GPU 后常驻内存（避免反复加载）。使用 `ThreadPoolExecutor(max_workers=3)` 并行提交三个推理任务。需要注意 CUDA 的线程安全问题：如果使用同一块 GPU，需要通过 `torch.cuda.Stream` 实现真正的并行；如果有多块 GPU，可以将三个模型分配到不同 GPU。

```python
def parallel_embedding(semantic_result: dict, original_image: np.ndarray) -> dict:
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_face = executor.submit(extract_face, semantic_result, original_image)
        future_scene = executor.submit(extract_scene, semantic_result, original_image)
        future_text = executor.submit(extract_text, semantic_result["text_content"])

    return {
        "v_face": future_face.result(),      # 512 维
        "v_scene": future_scene.result(),     # 768 维
        "v_text": future_text.result()        # 768 维
    }
```

**依赖**：Task 2.3.1, Task 2.3.2, Task 2.3.3
**预估工时**：1 天
**验收标准**：三线程并行执行，单张图片总处理时间 < 2 秒（含分割 + 嵌入），相比串行执行提速 > 40%。

---

### 2.4 时序融合节点（Node 4: Temporal Fusion）

#### Task 2.4.1 — 实现指数衰减权重函数

编写时间衰减函数，将笔记的发布时间转化为权重值。越新的笔记权重越高，30 天前的笔记权重趋近于零。

**技术实现要点**：衰减公式为 $w(t) = e^{-\lambda \cdot \Delta t}$，其中 $\Delta t$ 为笔记发布距今的天数，$\lambda$ 为衰减系数（建议初始值 0.1，即 30 天后权重约为 0.05）。$\lambda$ 应作为可配置参数，后续可根据业务需求调整。

**依赖**：无（纯数学函数）
**预估工时**：0.3 天
**验收标准**：今天发布的笔记权重为 1.0，7 天前约 0.50，15 天前约 0.22，30 天前约 0.05。

---

#### Task 2.4.2 — 实现滑动窗口融合逻辑

维护每个达人近 30 天笔记的向量滑动窗口，将多篇笔记的特征向量按时间衰减权重加权融合为单一的综合风格向量。

**技术实现要点**：对于一个达人的 N 篇笔记，每篇笔记产出 `(v_face_i, v_scene_i, v_text_i)` 三组向量。融合公式为：

$$V_{overall} = \sum_{i=1}^{N} w(t_i) \cdot (\alpha \cdot V_{scene\_i} + \beta \cdot V_{text\_i} + \gamma \cdot V_{face\_i}) \bigg/ \sum_{i=1}^{N} w(t_i)$$

其中 $\alpha, \beta, \gamma$ 为三种模态的权重系数（建议初始值 $\alpha=0.4, \beta=0.35, \gamma=0.25$），可配置。融合后的 `V_overall` 为 768 维向量（需要将 512 维的 `V_face` 通过线性投影层映射到 768 维，或在融合前进行零填充）。

**依赖**：Task 2.4.1, Task 2.3.4
**预估工时**：1 天
**验收标准**：给定一个达人的 10 篇笔记向量和发布时间，输出 768 维融合向量。最近发布的笔记对最终向量的影响明显大于早期笔记。

---

#### Task 2.4.3 — 将融合向量写回 Milvus

将计算完成的 `V_overall_style` 向量写入 Milvus 对应达人的记录中。如果达人已有向量记录则更新（upsert），如果是新达人则插入。同时将 `v_face` 和 `v_scene` 的最新值也一并写入。

**依赖**：Task 2.4.2, Sprint 1 Task 1.2.2
**预估工时**：0.5 天
**验收标准**：写入后通过 Milvus 查询该达人的 `v_overall_style` 字段，向量值与计算结果一致。

---

#### Task 2.4.4 — DAG 流水线端到端编排

将 Node 1 → Node 2 → Node 3 → Node 4 串联为完整的 DAG 流水线，编写主编排函数 `process_influencer(influencer_id)`，实现单个达人从图片下载到向量入库的全自动化处理。同时编写批量处理脚本 `batch_process.py`，支持并行处理多个达人。

**依赖**：Task 2.1.1 - 2.4.3（全部 Node）
**预估工时**：1 天
**验收标准**：执行 `python batch_process.py --ids 1,2,3,...,100`，100 个达人全部处理完成，Milvus 中新增 100 条向量记录。

---

## Sprint 3：大脑层 — 向量运算与推荐排序

**目标**：实现混合排序计分函数、Rocchio 向量平移算法和反向打标逻辑，使系统具备"理解偏好"和"进化推荐"的能力。

**负责人**：算法工程师 B（AI/ML）
**工期**：2 周（第 6-7 周）
**里程碑验收**：给定筛选条件和用户反馈，系统返回排序结果，"换一批"后结果有明显进化。

---

### 3.1 混合排序计分函数（Hybrid Ranking）

#### Task 3.1.1 — 实现余弦相似度计算模块

编写高效的余弦相似度计算函数，支持单向量对比和批量向量对比两种模式。

**技术实现要点**：使用 NumPy 向量化运算。单向量模式：`cos_sim(a, b) = dot(a, b) / (norm(a) * norm(b))`。批量模式：输入查询向量和 N 个候选向量矩阵，一次性输出 N 个相似度得分。需要处理零向量的边界情况（返回 0 而非 NaN）。

**依赖**：无（纯数学函数）
**预估工时**：0.3 天
**验收标准**：两个相同向量相似度为 1.0，两个正交向量相似度为 0.0，批量计算 100 个向量 < 1ms。

---

#### Task 3.1.2 — 实现 Min-Max 归一化模块

对达人的数值型指标（粉丝数、互动数、阅读数等）进行 Min-Max 归一化，映射到 [0, 1] 区间，使不同量级的指标可以直接比较和加权。

**技术实现要点**：归一化公式为 $x_{norm} = (x - x_{min}) / (x_{max} - x_{min})$。`x_min` 和 `x_max` 取当前批次（100 个候选人）的最小值和最大值，而非全局极值，以确保每批次内的相对排序有意义。需要处理 `x_min == x_max` 的边界情况（全部返回 0.5）。

需要归一化的字段包括：`followers`、`likes`、`collections`、`notes_count`、`ad_ratio_30d`，以及从 `influencer_notes` 聚合计算的中位数指标。

**依赖**：无
**预估工时**：0.3 天
**验收标准**：输入一组数值，输出全部在 [0, 1] 范围内，最小值映射为 0，最大值映射为 1。

---

#### Task 3.1.3 — 实现性价比计算函数

基于达人的报价信息和历史互动数据，计算商业性价比指数（ROI Proxy）。该指标帮助用户在预算有限时优先选择"性价比高"的达人。

**技术实现要点**：性价比函数定义为：

$$ROI_{proxy} = \frac{\text{互动中位数(日常)}}{\text{预估互动单价}} \times (1 - ad\_ratio_{30d})$$

其中分母为达人的报价（从 `pricing` JSONB 字段获取），分子为达人的日常互动表现。乘以 `(1 - ad_ratio)` 是为了惩罚商单比例过高的达人（商单多意味着粉丝可能对广告内容疲劳）。如果报价信息缺失，ROI_proxy 设为 0.5（中性值）。

**依赖**：Task 3.1.2（归一化后的数据）
**预估工时**：0.5 天
**验收标准**：互动高且报价低的达人 ROI > 0.7，互动低且报价高的达人 ROI < 0.3。

---

#### Task 3.1.4 — 组装 Hybrid Ranking 主函数

将余弦相似度、归一化得分、性价比指数和业务超参数组装为最终的混合排序函数。

**技术实现要点**：最终计分公式为：

$$Score = \alpha_1 \cdot Sim_{cosine} + \alpha_2 \cdot Data_{norm} + \alpha_3 \cdot ROI_{proxy}$$

其中 $\alpha_1, \alpha_2, \alpha_3$ 为业务超参数，由前端传入（通过 `<IntentDashboard>` 中的权重滑块控制）。默认值建议为 $\alpha_1=0.5, \alpha_2=0.3, \alpha_3=0.2$。函数接收 Milvus 召回的 100 个候选人，输出按 Score 降序排列的 Top-K 结果列表。

```python
def hybrid_rank(
    candidates: List[dict],       # Milvus 召回的候选人（含向量和标量数据）
    query_vector: List[float],    # 查询向量
    weights: dict,                # 业务超参数 {"similarity": 0.5, "data": 0.3, "roi": 0.2}
    top_k: int = 10               # 返回数量
) -> List[RankedResult]:
    ...
```

**依赖**：Task 3.1.1, Task 3.1.2, Task 3.1.3
**预估工时**：1 天
**验收标准**：输入 100 个候选人和不同的权重配置，输出排序结果。调整 `similarity` 权重为 1.0 时，排序完全按余弦相似度；调整 `roi` 权重为 1.0 时，排序完全按性价比。

---

### 3.2 Rocchio 向量平移（意图进化核心）

#### Task 3.2.1 — 实现向量平均计算

编写函数计算一组向量的算术平均值，分别用于计算"选中组平均向量"和"淘汰组平均向量"。

**技术实现要点**：从 Milvus 中批量取出指定 ID 列表的 `v_overall_style` 向量，计算均值。需要处理的边界情况：选中组为空（不执行正向拉近）、淘汰组为空（不执行负向推远）、两者都为空（返回原始查询向量不变）。

**依赖**：Sprint 1 Task 1.2.3（Milvus 查询封装）
**预估工时**：0.3 天
**验收标准**：输入 5 个 768 维向量，输出的均值向量维度正确，各维度值为输入向量对应维度的算术平均。

---

#### Task 3.2.2 — 实现 Rocchio 公式核心逻辑

实现经典的 Rocchio 相关反馈算法，根据用户的选中/淘汰反馈生成进化后的查询向量。

**技术实现要点**：Rocchio 公式为：

$$V_{next} = \alpha \cdot V_{original} + \beta \cdot \frac{1}{|S|}\sum_{s \in S} V_s - \gamma \cdot \frac{1}{|R|}\sum_{r \in R} V_r$$

其中 $\alpha=1.0$（保留原始意图）、$\beta=0.75$（正向拉近强度）、$\gamma=0.25$（负向推远强度）。$S$ 为选中组，$R$ 为淘汰组。"待定"组的处理方式为：`weight = +0.2`，即 $V_{pending}$ 以 0.2 的系数加入正向项。

生成 `V_next` 后需要进行 L2 归一化（单位向量化），确保与 Milvus 中存储的向量在同一尺度上。

```python
def rocchio_evolve(
    v_original: np.ndarray,       # 原始查询向量 (768,)
    selected_vectors: List[np.ndarray],  # 选中组向量
    rejected_vectors: List[np.ndarray],  # 淘汰组向量
    pending_vectors: List[np.ndarray],   # 待定组向量
    alpha: float = 1.0,
    beta: float = 0.75,
    gamma: float = 0.25,
    pending_weight: float = 0.2
) -> np.ndarray:
    ...
```

**依赖**：Task 3.2.1
**预估工时**：1 天
**验收标准**：选中一批"高冷风"达人并淘汰"甜美风"达人后，`V_next` 与"高冷风"达人的平均向量余弦相似度 > `V_original` 与其的相似度。

---

#### Task 3.2.3 — 集成到检索流程

将 Rocchio 算法集成到完整的检索-排序-进化流程中，形成闭环。

**完整流程**：前端发送反馈（selected_ids + rejected_ids + pending_ids）→ 后端从 Milvus 取出对应向量 → 执行 Rocchio 公式生成 `V_next` → 使用 `V_next` 重新执行 Hybrid Search → 执行 Hybrid Ranking → 返回新一批排序结果。

**依赖**：Task 3.2.2, Task 3.1.4, Sprint 1 Task 1.2.3
**预估工时**：1 天
**验收标准**：执行 3 轮"选中→换一批"循环，每轮返回的 Top-10 结果与选中组的平均相似度逐轮递增。

---

### 3.3 反向打标与权重沉淀

#### Task 3.3.1 — 实现角色权重映射逻辑

根据操作人角色（采购/策划/客户）分配不同的反馈权重，使客户的选择对品牌偏好向量的影响最大。

**技术实现要点**：权重映射表为：

| 角色 | `operator_role_id` | 反馈权重 | 说明 |
|------|-------------------|---------|------|
| 采购 | 1 | 0.3 | 基础权重，主要执行层 |
| 策划/前端 | 2 | 0.6 | 中等权重，理解品牌调性 |
| 客户 | 3 | 1.0 | 最高权重，定义品牌基准 |

当不同角色对同一 SPU 执行多次入库时，品牌偏好向量按加权移动平均更新：

$$V_{brand\_new} = \frac{w_{role} \cdot V_{selected\_avg} + n_{prev} \cdot V_{brand\_old}}{w_{role} + n_{prev}}$$

其中 $n_{prev}$ 为该 SPU 历史入库次数。

**依赖**：无
**预估工时**：0.5 天
**验收标准**：客户入库后品牌向量偏移幅度 > 策划 > 采购。

---

#### Task 3.3.2 — 实现品牌偏好向量沉淀

当用户点击"确认入库"时，将选中达人的特征向量加权融合后沉淀为该品牌+SPU 的偏好基准向量，存入 `campaign_history` 表的 `query_vector_snapshot` 字段。

**技术实现要点**：入库流程为：计算选中达人的加权平均向量 → 按角色权重与历史偏好向量融合 → 更新 `campaign_history` 表 → 同时将选中达人的 `internal_id` 写入 `selected_influencer_ids` JSONB 字段。下次同品牌+SPU 的寻星任务启动时，可以读取该偏好向量作为初始查询向量的补充（与 LLM 解析出的查询向量加权融合）。

**依赖**：Task 3.3.1, Sprint 1 Task 1.1.2
**预估工时**：1 天
**验收标准**：入库后 `campaign_history` 表新增一条记录，`query_vector_snapshot` 字段非空，`selected_influencer_ids` 包含正确的 ID 列表。再次查询同品牌+SPU 时，初始查询向量包含历史偏好成分。

---

### Sprint 3 集成验证

#### Task 3.4.1 — 推荐引擎端到端测试

编写测试脚本 `test_brain.py`，模拟完整的推荐流程：构造查询向量 → Milvus 召回 100 候选 → Hybrid Ranking 排序 → 模拟用户反馈 → Rocchio 进化 → 再次检索排序 → 验证结果质量提升。

**依赖**：全部 Sprint 3 任务
**预估工时**：1 天
**验收标准**：3 轮进化后，Top-10 结果的平均相似度提升 > 15%。入库后品牌偏好向量正确沉淀。


---

## Sprint 4：调度层 — 异步任务与弹性降级

**目标**：搭建 Celery 异步任务队列，实现弹性降级算法，完成全部后端 API 接口，使后端可以独立运行并通过 Postman 验证完整业务闭环。

**负责人**：后端工程师 A（数据架构）
**工期**：2 周（第 8-9 周）
**里程碑验收**：通过 Postman 调用全部 6 个 API，完成"自然语言输入 → 排序结果 → 反馈进化 → 确认入库"闭环。

---

### 4.1 Celery 异步任务队列

#### Task 4.1.1 — 部署 Celery + Redis Broker

搭建 Celery 异步任务框架，使用 Redis 作为消息代理（Broker）和结果后端（Result Backend）。定义 Worker 配置、任务路由和并发策略。

**技术实现要点**：在 `docker-compose.yml` 中新增 Celery Worker 容器，复用 Sprint 1 已部署的 Redis 实例作为 Broker。Celery 配置需要定义两个任务队列：`queue_search`（向量检索任务，优先级高）和 `queue_crawl`（小红书接口抓取任务，优先级低）。Worker 并发模式使用 `prefork`（CPU 密集型任务）或 `gevent`（IO 密集型任务），建议 `queue_search` 使用 prefork（4 进程），`queue_crawl` 使用 gevent（100 协程）。

```python
# celery_config.py
broker_url = "redis://redis:6379/0"
result_backend = "redis://redis:6379/1"
task_routes = {
    "tasks.search.*": {"queue": "queue_search"},
    "tasks.crawl.*": {"queue": "queue_crawl"},
}
task_serializer = "json"
result_serializer = "json"
task_track_started = True
task_time_limit = 60  # 单任务最大执行时间 60 秒
```

**依赖**：Sprint 1 Task 1.3.1（Redis 已部署）
**预估工时**：1 天
**验收标准**：`celery -A tasks worker --loglevel=info` 启动后，提交一个测试任务（`add.delay(2, 3)`），Worker 正确消费并返回结果 5。Flower 监控面板（可选）可查看任务状态。

---

#### Task 4.1.2 — 封装 Milvus 检索异步任务

将 Sprint 1 中封装的 `hybrid_search()` 函数包装为 Celery 异步任务，使前端请求不再阻塞等待向量检索结果。

**技术实现要点**：任务函数 `search_influencers.delay(parsed_intent, feedback)` 接收解析后的意图和反馈数据，内部执行以下流程：构建标量过滤表达式 → 生成/进化查询向量 → 调用 `hybrid_search()` 召回 Top-100 → 执行 `hybrid_rank()` 精排 → 将 Top-K 结果写入 Redis（`task:{task_id}:result`）→ 更新任务状态为 `done`。

任务执行过程中需要通过 Sprint 1 封装的 `TaskCache` 实时更新进度：接收任务（10%）→ 构建查询（20%）→ Milvus 检索中（50%）→ 精排中（80%）→ 结果写入（100%）。

**依赖**：Sprint 1 Task 1.2.3, Sprint 3 Task 3.1.4, Task 4.1.1
**预估工时**：1.5 天
**验收标准**：提交异步检索任务后，通过 `TaskCache.get_task_info(task_id)` 可实时查看进度百分比，任务完成后结果正确写入 Redis。

---

#### Task 4.1.3 — 封装小红书接口调用异步任务

将小红书数据抓取逻辑包装为 Celery 异步任务。当 Milvus 召回的达人在 PostgreSQL 中缺少最新数据时（`latest_note_time` 超过 7 天），触发异步抓取任务补充数据。

**技术实现要点**：任务函数 `crawl_influencer_data.delay(red_ids)` 接收需要更新的达人小红书号列表，内部执行：组装请求 Payload → 调用小红书开放接口（或爬虫接口）→ 解析返回数据 → 更新 PostgreSQL `influencer_basics` 和 `influencer_notes` 表 → 将最新数据写入 Redis 缓存。

需要实现的容错机制包括：单个达人抓取失败不影响批次中其他达人、请求频率控制（QPS 限制）、失败重试（最多 3 次）、超时保护（单个达人 10 秒）。抓取完成后，异步触发 Sprint 2 的 DAG 流水线对新数据进行特征提取。

**依赖**：Sprint 1 Task 1.1.1, Sprint 1 Task 1.3.2, Task 4.1.1
**预估工时**：2 天
**验收标准**：提交 10 个达人的抓取任务，成功率 > 80%，PostgreSQL 数据更新正确，Redis 缓存同步刷新。

---

#### Task 4.1.4 — 实现前端轮询与 WebSocket 推送机制

实现两种前端获取异步任务结果的方式：短轮询（Polling）作为基础方案，WebSocket 作为增强方案。

**短轮询方案**：前端每 500ms 调用 `GET /api/v1/task/{task_id}/status`，后端从 Redis 读取任务状态返回。响应体包含 `status`（pending/running/done/failed）、`progress`（0-100）、`logs`（增量日志数组，通过 `since_index` 参数实现增量拉取）、`result`（仅 status=done 时有值）。

**WebSocket 方案**：前端建立 WebSocket 连接后发送 `{"action": "subscribe", "task_id": "xxx"}`，后端在任务状态变更时主动推送。推送消息类型包括：`progress_update`（进度更新）、`log_append`（新增降级日志）、`result_ready`（结果就绪）。

```python
# WebSocket 消息格式
{"type": "progress_update", "task_id": "xxx", "progress": 65}
{"type": "log_append", "task_id": "xxx", "log": "[降级] 放宽粉丝数范围: 5万-50万 → 3.5万-65万"}
{"type": "result_ready", "task_id": "xxx", "data": {...}}
```

**依赖**：Sprint 1 Task 1.3.2, Task 4.1.2
**预估工时**：2 天
**验收标准**：短轮询方案：任务提交后 3 秒内前端收到首批进度更新。WebSocket 方案：连接建立后，后端状态变更在 100ms 内推送到前端。

---

### 4.2 弹性降级算法（Constraint Relaxation Tree）

#### Task 4.2.1 — 实现最小优先队列构建逻辑

根据 LLM 意图解析器输出的 `elastic_weights`（容忍度权重 1-5），构建一个最小优先队列（Min-Heap），权重越低的条件越先被降级（即用户对该条件的容忍度越高）。

**技术实现要点**：使用 Python `heapq` 模块构建最小堆。每个堆元素为 `(weight, condition_key, condition_value, condition_type)` 四元组。`condition_type` 区分数值型（如粉丝数范围）和枚举型（如地区列表）。

示例：用户输入"找上海的 5-50 万粉丝高冷风女博主"，LLM 解析后 `elastic_weights` 为 `{"location": 5, "gender": 5, "followers": 3, "soft_tags": 2}`。构建的优先队列为：`[(2, "soft_tags", ...), (3, "followers", ...), (5, "gender", ...), (5, "location", ...)]`。降级顺序为：先放宽 soft_tags → 再扩展 followers 范围 → 最后考虑 gender 和 location。

**依赖**：无（纯算法）
**预估工时**：0.5 天
**验收标准**：给定 `elastic_weights` 字典，输出正确排序的优先队列，弹出顺序与权重升序一致。

---

#### Task 4.2.2 — 实现条件剥离与数值平滑扩展

实现两种降级操作：枚举型条件的完全剥离（从过滤条件中移除）和数值型条件的平滑扩展（扩大范围但不完全移除）。

**技术实现要点**：

对于**枚举型条件**（如 `soft_tags`），降级操作为直接从 Milvus 的 `expr` 过滤表达式中移除该条件。例如，`soft_tags` 降级后，不再要求达人匹配"高冷风"标签，改为纯向量相似度匹配。

对于**数值型条件**（如 `followers`），执行平滑扩展函数：

$$C_{new} = [C_{min} \times 0.7, C_{max} \times 1.3]$$

即下界缩小 30%，上界扩大 30%。如果扩展后仍无结果，继续扩展（第二轮：`[C_min × 0.5, C_max × 1.5]`），最多扩展 3 轮。如果 3 轮后仍无结果，则完全移除该条件。

每次降级操作后，立即重新执行 Milvus 检索。如果返回结果数 >= `pagination.limit`，停止降级；否则继续弹出下一个条件。

**依赖**：Task 4.2.1
**预估工时**：1 天
**验收标准**：构造一个必然返回空结果的严苛查询，降级算法自动执行 2-3 轮放宽后返回非空结果。

---

#### Task 4.2.3 — 实现降级日志生成与推送

每次降级操作都需要生成一条人类可读的日志消息，实时推送给前端的 `<ElasticLoadingTerminal>` 组件渲染。日志风格模拟终端输出，增强用户的"系统正在努力为你寻找"的感知。

**技术实现要点**：日志格式定义如下：

```
[时间戳] [降级轮次] 操作描述
```

示例日志序列：

```
[10:23:01] [Round 1] 初始条件检索中... 命中 0 条结果
[10:23:01] [Round 1] 放宽条件: "高冷风" 标签要求 → 改为向量相似度匹配
[10:23:02] [Round 2] 重新检索中... 命中 3 条结果（不足 10 条）
[10:23:02] [Round 2] 扩展粉丝数范围: 5万-50万 → 3.5万-65万
[10:23:03] [Round 3] 重新检索中... 命中 15 条结果 ✓
[10:23:03] [完成] 经过 2 轮弹性调整，为您找到 15 位匹配达人
```

每条日志通过 `TaskCache.append_log(task_id, log_line)` 写入 Redis List，前端通过轮询或 WebSocket 增量获取。

**依赖**：Task 4.2.2, Sprint 1 Task 1.3.2
**预估工时**：0.5 天
**验收标准**：降级过程中每一步操作都生成对应日志，日志内容准确反映实际降级操作，前端可实时获取增量日志。

---

#### Task 4.2.4 — 集成到主检索流程

将弹性降级算法集成到 Task 4.1.2 的异步检索任务中，形成完整的"检索 → 判空 → 降级 → 重检索"闭环。

**完整流程**：接收解析后的意图 → 构建初始 Milvus 查询 → 执行检索 → 如果结果数 >= limit，直接进入精排 → 如果结果数 < limit，启动降级算法 → 循环（弹出最低权重条件 → 执行降级操作 → 生成日志 → 重新检索 → 判断结果数）→ 精排 → 返回结果。

需要设置降级的最大轮次上限（建议 5 轮），防止无限循环。如果达到上限仍无足够结果，返回当前已有的结果并附带提示信息"已尽力放宽条件，当前仅找到 N 位达人"。

**依赖**：Task 4.2.1, Task 4.2.2, Task 4.2.3, Task 4.1.2
**预估工时**：1 天
**验收标准**：构造 3 种场景测试：(1) 初始命中充足，不触发降级；(2) 初始命中不足，降级 1-2 轮后充足；(3) 极端严苛条件，降级达到上限后返回部分结果。三种场景均正确处理。

---

### 4.3 后端 API 层

#### Task 4.3.1 — 意图解析接口 `POST /api/v1/intent/parse`

实现意图解析 API，接收用户的自然语言输入，调用 LLM 解析后返回结构化的意图树。

**技术实现要点**：

请求体：
```json
{
  "raw_text": "找几个上海的高冷风女博主，粉丝5万到50万",
  "brand_context": {
    "brand_name": "某品牌",
    "spu_name": "某产品"
  }
}
```

响应体：
```json
{
  "code": 200,
  "data": {
    "task_id": "intent_abc123",
    "hard_filters": {
      "location": ["上海"],
      "gender": "女",
      "followers_min": 50000,
      "followers_max": 500000
    },
    "soft_tags": ["高冷风"],
    "elastic_weights": {
      "location": 5,
      "gender": 5,
      "followers": 3,
      "soft_tags": 2
    },
    "brand_preference_vector": [0.12, -0.34, ...] // 如有历史偏好，附带品牌基准向量
  }
}
```

如果 `brand_context` 中的品牌+SPU 在 `campaign_history` 表中有历史记录，需要从中读取 `query_vector_snapshot` 作为品牌偏好向量一并返回。接口响应时间目标 < 3 秒（LLM 调用耗时）。

**依赖**：Sprint 1 Task 1.1.2（campaign_history 表）
**预估工时**：1.5 天
**验收标准**：通过 Postman 发送 5 种不同的自然语言输入，全部返回格式正确的结构化意图树。

---

#### Task 4.3.2 — 弹性检索与反馈进化接口 `POST /api/v1/match/retrieve`

实现核心检索 API，支持首次检索和基于反馈的进化检索。

**技术实现要点**：

请求体：
```json
{
  "parsed_intent": {
    "hard_filters": {"location": ["上海"], "gender": "女", "followers_min": 50000, "followers_max": 500000},
    "soft_tags": ["高冷风"],
    "elastic_weights": {"location": 5, "gender": 5, "followers": 3, "soft_tags": 2},
    "brand_preference_vector": null
  },
  "feedback": {
    "selected_ids": [],
    "rejected_ids": [],
    "pending_ids": []
  },
  "ranking_weights": {"similarity": 0.5, "data": 0.3, "roi": 0.2},
  "pagination": {"limit": 10, "offset": 0}
}
```

响应体（异步模式）：
```json
{
  "code": 200,
  "data": {
    "task_id": "search_xyz789",
    "status": "pending",
    "poll_url": "/api/v1/task/search_xyz789/status"
  }
}
```

接口内部逻辑：接收请求 → 提交 Celery 异步任务 → 立即返回 `task_id` → 前端通过 `poll_url` 轮询结果。如果 `feedback` 非空，任务内部先执行 Rocchio 向量平移生成 `V_next`，再执行检索。

**依赖**：Task 4.1.2, Task 4.2.4, Sprint 3 Task 3.2.3
**预估工时**：1.5 天
**验收标准**：首次检索返回 Top-10 结果；提交 selected/rejected 反馈后再次调用，返回的结果与首次有明显差异。

---

#### Task 4.3.3 — 资产入库与打标接口 `POST /api/v1/assets/commit`

实现入库 API，将用户确认的达人写入资产库，同时触发品牌偏好向量沉淀。

**技术实现要点**：

请求体：
```json
{
  "project_context": {
    "brand_name": "某奶粉品牌",
    "spu_name": "高端系列 A 段",
    "operator_role_id": 2
  },
  "influencers": [
    {"id": 10023, "selected_reason_tags": ["互动率高", "高冷风"]},
    {"id": 10045, "selected_reason_tags": ["性价比高", "母婴达人"]}
  ],
  "campaign_id": "search_xyz789"
}
```

响应体：
```json
{
  "code": 200,
  "data": {
    "committed_count": 2,
    "campaign_id": "campaign_001",
    "brand_vector_updated": true
  }
}
```

接口内部逻辑：(1) 将达人 ID 写入 `campaign_history.selected_influencer_ids`；(2) 调用 Sprint 3 的反向打标逻辑，按角色权重更新品牌偏好向量；(3) 更新 `campaign_history.status` 为 `committed`；(4) 记录 `fulfillment_records` 操作日志。

**依赖**：Sprint 3 Task 3.3.2, Sprint 1 Task 1.1.2
**预估工时**：1 天
**验收标准**：入库后 `campaign_history` 表状态更新为 `committed`，`selected_influencer_ids` 包含正确 ID，品牌偏好向量已更新。

---

#### Task 4.3.4 — 智能表头匹配与字典沉淀接口 `POST /api/v1/export/confirm-mapping`

实现导出表头映射 API，接收用户确认的映射关系，持久化到 `export_dictionary` 表。

**技术实现要点**：

请求体：
```json
{
  "user_confirmed_mappings": [
    {"user_input_header": "视频均赞", "mapped_standard_key": "视频互动中位数(日常)"},
    {"user_input_header": "图文均藏", "mapped_standard_key": "图文收藏中位数(日常)"}
  ],
  "ignored_headers": ["备注说明", "内部评级"]
}
```

响应体：
```json
{
  "code": 200,
  "data": {
    "saved_mappings": 2,
    "ignored_count": 2,
    "dictionary_size": 156
  }
}
```

接口内部逻辑：(1) 对每个 `user_confirmed_mapping`，执行 UPSERT 到 `export_dictionary` 表（已存在则 `usage_count += 1`，`confidence = 1.00`）；(2) `ignored_headers` 不入库但记录日志（用于后续分析哪些字段用户经常忽略）；(3) 返回当前字典总条目数。

同时需要实现一个辅助接口 `GET /api/v1/export/suggest-mapping?header=视频均赞`，根据 `export_dictionary` 表中的历史映射，返回候选匹配列表（按 `usage_count` 降序、`confidence` 降序排列）。

**依赖**：Sprint 1 Task 1.1.3
**预估工时**：1 天
**验收标准**：确认映射后字典表正确更新，再次查询相同表头时 `usage_count` 递增。辅助接口返回正确的候选列表。

---

#### Task 4.3.5 — 达人资产库查询接口 `GET /api/v1/library/list`

实现资产库列表查询 API，支持多维度筛选、排序和分页。

**技术实现要点**：

查询参数：
```
GET /api/v1/library/list?
  brand_name=某品牌&
  region=上海&
  followers_min=10000&
  followers_max=500000&
  tags=高冷风,穿搭&
  sort_by=followers&
  sort_order=desc&
  page=1&
  page_size=20
```

响应体：
```json
{
  "code": 200,
  "data": {
    "total": 156,
    "page": 1,
    "page_size": 20,
    "items": [
      {
        "internal_id": 10023,
        "red_id": "red_10023",
        "nickname": "某达人",
        "avatar_url": "https://...",
        "followers": 120000,
        "region": "上海",
        "tags": ["高冷风", "穿搭"],
        "ad_ratio_30d": 0.15,
        "latest_note_time": "2026-03-28T10:00:00Z",
        "campaigns": [
          {"brand_name": "某品牌", "spu_name": "某产品", "committed_at": "2026-03-20"}
        ]
      }
    ]
  }
}
```

接口内部逻辑：从 PostgreSQL 查询 `influencer_basics` 表，LEFT JOIN `campaign_history` 表获取该达人参与的项目列表。支持的筛选维度包括：品牌名、地区、粉丝数范围、标签（JSONB 包含查询）、入库时间范围。优先从 Redis 缓存读取。

**依赖**：Sprint 1 Task 1.1.1, Sprint 1 Task 1.1.2, Sprint 1 Task 1.3.3
**预估工时**：1 天
**验收标准**：多种筛选条件组合查询返回正确结果，分页逻辑正确（total 与实际数据一致），排序生效。

---

#### Task 4.3.6 — 履约历史查询接口 `GET /api/v1/library/history`

实现单个达人的履约历史时间轴查询 API。

**技术实现要点**：

查询参数：
```
GET /api/v1/library/history?influencer_id=10023
```

响应体：
```json
{
  "code": 200,
  "data": {
    "influencer_id": 10023,
    "timeline": [
      {
        "campaign_id": 1,
        "brand_name": "品牌A",
        "spu_name": "产品X",
        "action_type": "selected",
        "operator_role": "策划",
        "reason_tags": ["互动率高", "高冷风"],
        "created_at": "2026-03-20T10:00:00Z"
      },
      {
        "campaign_id": 1,
        "brand_name": "品牌A",
        "spu_name": "产品X",
        "action_type": "invited",
        "operator_role": "采购",
        "created_at": "2026-03-21T14:00:00Z"
      }
    ]
  }
}
```

接口内部逻辑：查询 `campaign_history` 表中 `selected_influencer_ids` 包含该达人 ID 的所有记录，JOIN `fulfillment_records` 表获取后续操作（邀约、下单、交付、结算），按时间倒序排列组成时间轴。

**依赖**：Sprint 1 Task 1.1.2, Sprint 1 Task 1.1.4
**预估工时**：0.5 天
**验收标准**：查询已入库达人返回完整时间轴，按时间倒序排列，包含所有操作类型。

---

#### Task 4.3.7 — 任务状态查询接口 `GET /api/v1/task/{task_id}/status`

实现通用的异步任务状态查询接口，供前端轮询使用。

**技术实现要点**：

查询参数：
```
GET /api/v1/task/search_xyz789/status?logs_since=5
```

响应体：
```json
{
  "code": 200,
  "data": {
    "task_id": "search_xyz789",
    "status": "running",
    "progress": 65,
    "logs": [
      "[10:23:02] [Round 2] 扩展粉丝数范围: 5万-50万 → 3.5万-65万",
      "[10:23:03] [Round 3] 重新检索中... 命中 15 条结果 ✓"
    ],
    "logs_total": 7,
    "result": null
  }
}
```

`logs_since` 参数用于增量拉取日志（只返回索引 > `logs_since` 的新日志），避免重复传输。当 `status == "done"` 时，`result` 字段包含完整的检索结果。

**依赖**：Sprint 1 Task 1.3.2
**预估工时**：0.5 天
**验收标准**：任务执行过程中多次调用，每次返回最新的进度和增量日志，任务完成后返回完整结果。

---

### Sprint 4 集成验证

#### Task 4.4.1 — API 全链路 Postman 测试

编写 Postman Collection，按顺序调用全部 API 完成一次完整的业务闭环：

1. `POST /api/v1/intent/parse` — 输入自然语言，获取意图树
2. `POST /api/v1/match/retrieve` — 提交意图树，获取 task_id
3. `GET /api/v1/task/{task_id}/status` — 轮询直到 status=done
4. `POST /api/v1/match/retrieve` — 提交反馈（selected + rejected），获取进化结果
5. `POST /api/v1/assets/commit` — 确认入库
6. `GET /api/v1/library/list` — 查询资产库，验证入库成功
7. `GET /api/v1/library/history` — 查询履约历史
8. `POST /api/v1/export/confirm-mapping` — 确认导出映射

**依赖**：全部 Sprint 4 任务
**预估工时**：1 天
**验收标准**：Postman Collection 一键执行，全部请求返回 200，数据流转正确。

---

## Sprint 5：触点层 — 前端对接与 LLM 意图解析

**目标**：将 Σ.Match v1.0 前端 UI 的 Mock 数据全部替换为真实 API 调用，集成 LLM 意图解析，实现 WebSocket 实时通信，完成前后端联调。

**负责人**：前端工程师 C + 后端工程师 A（LLM 集成）
**工期**：3 周（第 10-12 周）
**里程碑验收**：用户可在浏览器中完成从自然语言输入到智能导出的完整业务闭环。

---

### 5.1 LLM 意图解析器集成（后端）

#### Task 5.1.1 — 编写 System Prompt 与 Few-shot 样本

设计 LLM 的 System Prompt，使用 Few-shot CoT（少样本思维链）方式引导模型输出强类型 JSON。Prompt 需要明确定义输出 Schema，并提供 5-8 个覆盖不同场景的示例。

**技术实现要点**：System Prompt 结构如下：

```
你是 Σ.Match 的意图解析引擎。用户会用自然语言描述他们想找的达人类型。
你的任务是将自然语言转化为结构化的检索条件。

## 输出格式（严格 JSON，不允许额外文字）
{
  "hard_filters": {
    "location": ["地区1", "地区2"] | null,
    "gender": "男" | "女" | null,
    "followers_min": number | null,
    "followers_max": number | null,
    "ad_ratio_max": number | null
  },
  "soft_tags": ["风格标签1", "风格标签2"],
  "elastic_weights": {
    "location": 1-5,
    "gender": 1-5,
    "followers": 1-5,
    "soft_tags": 1-5
  }
}

## elastic_weights 规则
- 5 = 绝对不能放宽（用户明确强调的条件）
- 3 = 可以适当放宽
- 1 = 可以完全忽略

## 示例
用户: "找几个上海的高冷风女博主"
思考: 用户明确指定了上海和女性，这两个是硬性条件(权重5)。"高冷风"是风格偏好，可以适当放宽(权重3)。没有指定粉丝数。
输出: {"hard_filters": {"location": ["上海"], "gender": "女", ...}, "soft_tags": ["高冷风"], "elastic_weights": {"location": 5, "gender": 5, "soft_tags": 3}}

[更多示例...]
```

Few-shot 样本需要覆盖的场景：纯地区查询、纯风格查询、粉丝数范围查询、多条件组合查询、模糊表述（如"便宜点的"→ 性价比权重高）、否定表述（如"不要太商业化的"→ ad_ratio_max 低）。

**依赖**：无
**预估工时**：2 天
**验收标准**：准备 10 条测试用例（含边界情况），LLM 输出格式 100% 合规，语义理解准确率 > 90%。

---

#### Task 5.1.2 — 实现 LLM 输出校验与容错

编写 JSON Schema 校验器和自动重试机制，确保 LLM 输出始终符合预期格式。

**技术实现要点**：使用 `jsonschema` 库定义严格的输出 Schema。校验流程为：调用 LLM → 尝试 JSON 解析 → Schema 校验 → 如果失败，将错误信息附加到 Prompt 中重试（最多 3 次）→ 如果 3 次仍失败，返回默认的空意图树并标记 `parse_failed: true`。

需要处理的常见 LLM 输出问题：JSON 前后有多余文字（正则提取 `{...}` 部分）、字段名拼写错误（模糊匹配纠正）、数值类型错误（字符串 "50000" → 数字 50000）。

**依赖**：Task 5.1.1
**预估工时**：1 天
**验收标准**：故意构造 LLM 输出格式错误的场景（Mock LLM 返回），校验器正确识别并触发重试，3 次内恢复正常输出。

---

#### Task 5.1.3 — 将 soft_tags 转化为 CLIP Text Embedding

将 LLM 解析出的 `soft_tags`（如 ["高冷风", "极简穿搭"]）转化为 CLIP Text Embedding 向量，作为 Milvus 向量检索的查询输入。

**技术实现要点**：将 `soft_tags` 数组拼接为自然语言描述（如 "高冷风格，极简穿搭风格的博主"），送入 Sprint 2 Task 2.3.3 封装的 CLIP Text Encoder，输出 768 维查询向量。如果同时存在品牌偏好向量（从 `campaign_history` 读取），需要将两个向量加权融合：

$$V_{query} = \alpha \cdot V_{soft\_tags} + (1 - \alpha) \cdot V_{brand\_preference}$$

其中 $\alpha$ 默认为 0.7（侧重当前意图），可配置。

**依赖**：Sprint 2 Task 2.3.3, Task 5.1.1
**预估工时**：0.5 天
**验收标准**：输入 soft_tags 数组，输出 768 维查询向量。"高冷风"和"冷淡风"生成的向量余弦相似度 > 0.8。

---

### 5.2 前端 API 对接（替换 Mock 数据）

#### Task 5.2.1 — 封装 API 客户端与类型定义

在前端项目中创建统一的 API 客户端层，定义所有接口的 TypeScript 类型和请求函数。

**技术实现要点**：在 `client/src/lib/api.ts` 中使用 `axios` 创建带有基础配置（baseURL、超时、错误拦截器）的实例。为每个 API 定义请求/响应的 TypeScript 接口。封装通用的轮询函数 `pollTaskResult(taskId, onProgress, onLog)`，内部实现 500ms 间隔轮询 + 进度回调 + 日志回调。

```typescript
// 类型定义示例
interface ParsedIntent {
  hard_filters: {
    location?: string[];
    gender?: string;
    followers_min?: number;
    followers_max?: number;
    ad_ratio_max?: number;
  };
  soft_tags: string[];
  elastic_weights: Record<string, number>;
  brand_preference_vector?: number[];
}

interface RetrieveRequest {
  parsed_intent: ParsedIntent;
  feedback: { selected_ids: number[]; rejected_ids: number[]; pending_ids: number[] };
  ranking_weights: { similarity: number; data: number; roi: number };
  pagination: { limit: number; offset: number };
}

// API 函数
export const api = {
  parseIntent: (rawText: string, brandContext?: BrandContext) => ...,
  retrieve: (req: RetrieveRequest) => ...,
  pollTask: (taskId: string, callbacks: PollCallbacks) => ...,
  commitAssets: (req: CommitRequest) => ...,
  getLibraryList: (params: LibraryQueryParams) => ...,
  getHistory: (influencerId: number) => ...,
  confirmMapping: (req: MappingRequest) => ...,
  suggestMapping: (header: string) => ...,
};
```

**依赖**：Sprint 4 全部 API 接口
**预估工时**：1.5 天
**验收标准**：所有 API 函数类型安全，TypeScript 编译无错误，可通过 `api.parseIntent("测试")` 成功调用后端。

---

#### Task 5.2.2 — 工作台：对话输入对接意图解析 API

将工作台页面的 `<ChatInterface>` 组件从 Mock 模式切换为真实 API 调用。用户输入自然语言后，调用 `api.parseIntent()` 获取结构化意图，渲染到 `<IntentDashboard>` 组件中。

**技术实现要点**：用户点击发送后，显示 loading 状态（对话气泡中显示"正在解析您的需求..."）→ 调用 `POST /api/v1/intent/parse` → 成功后将 `hard_filters`、`soft_tags`、`elastic_weights` 渲染到意图仪表盘 → 用户可在仪表盘中手动调整权重滑块和筛选条件 → 点击"确认并开始寻星"触发检索。

需要处理的错误场景：LLM 解析失败（`parse_failed: true`）时显示"未能理解您的需求，请尝试更具体的描述"；网络超时时显示重试按钮。

**依赖**：Task 5.2.1
**预估工时**：1.5 天
**验收标准**：输入"找上海的高冷风女博主"，意图仪表盘正确显示地区=上海、性别=女、风格=高冷风，权重滑块可拖动调整。

---

#### Task 5.2.3 — 工作台：意图确认对接弹性检索 API + 轮询

用户确认意图后，调用 `api.retrieve()` 提交检索请求，通过轮询机制实时展示降级过程和检索结果。

**技术实现要点**：点击"确认并开始寻星"→ 调用 `POST /api/v1/match/retrieve` 获取 `task_id` → 页面切换到 `<ElasticLoadingTerminal>` 视图 → 启动 `pollTaskResult()` 轮询 → 每次轮询回调更新进度条和终端日志 → 当 `status == "done"` 时，页面切换到 `<DataGridList>` 视图展示达人数据矩阵。

`<ElasticLoadingTerminal>` 组件需要实现打字机效果逐行渲染日志，配合扫描线动画增强科技感。进度条从 0% 平滑过渡到实际进度值。

**依赖**：Task 5.2.1, Sprint 4 Task 4.1.4
**预估工时**：2 天
**验收标准**：提交检索后，终端组件实时显示降级日志（如有），进度条平滑更新，结果就绪后自动切换到数据矩阵视图。

---

#### Task 5.2.4 — 工作台：评审反馈对接进化检索 API

在数据矩阵和沉浸式评审模式中，用户对达人执行"选中/待定/淘汰"操作后，点击"换一批"触发 Rocchio 进化检索。

**技术实现要点**：维护前端状态 `feedbackState: { selected_ids: number[], rejected_ids: number[], pending_ids: number[] }`。用户在 `<ReviewModal>` 中翻牌评审时，实时更新 `feedbackState`。点击"换一批"按钮时，将 `feedbackState` 连同 `parsed_intent` 一起提交到 `api.retrieve()`，触发新一轮检索。

`<FissionDock>` 底部操作栏需要实时显示当前选中/待定/淘汰的数量统计，以及"换一批"和"确认入库"两个主操作按钮。

**依赖**：Task 5.2.3
**预估工时**：1.5 天
**验收标准**：选中 3 个达人、淘汰 2 个达人后点击"换一批"，新结果与之前有明显差异（风格更接近选中组）。

---

#### Task 5.2.5 — 工作台：确认入库对接资产打标 API

用户在 `<FissionDock>` 中点击"确认入库"后，弹出入库确认对话框，填写品牌/SPU/角色信息，提交到 `api.commitAssets()`。

**技术实现要点**：入库确认对话框包含：品牌名称输入框（支持历史品牌自动补全）、SPU 名称输入框、操作角色选择（采购/策划/客户）、已选中达人列表预览（含原因标签）。提交成功后显示"已成功入库 N 位达人"的 Toast 通知，并提供"前往资产库查看"的跳转链接。

**依赖**：Task 5.2.4
**预估工时**：1 天
**验收标准**：填写完整信息后提交，后端返回成功，跳转到资产库可查看刚入库的达人。

---

#### Task 5.2.6 — 资产库：列表查询对接资产库 API

将资产库页面的 `<LibraryTable>` 和 `<FilterBar>` 组件从 Mock 数据切换为真实 API 调用。

**技术实现要点**：`<FilterBar>` 中的每个筛选条件变更都触发 `api.getLibraryList()` 重新查询。使用 `useMemo` 稳定查询参数引用，避免无限请求循环。分页使用 `page` + `page_size` 参数，表格底部显示分页控件。排序支持点击表头切换升序/降序。

需要实现的筛选维度：品牌名（下拉选择，选项从 API 动态获取）、地区（多选）、粉丝数范围（双滑块）、标签（多选标签云）、入库时间范围（日期选择器）。

**依赖**：Task 5.2.1
**预估工时**：1.5 天
**验收标准**：多种筛选条件组合查询返回正确结果，分页切换流畅，排序生效。

---

#### Task 5.2.7 — 资产库：履约历史对接历史查询 API

点击资产库中某个达人的"查看详情"时，展开 `<HistoryDrawer>` 抽屉组件，调用 `api.getHistory()` 获取该达人的履约时间轴。

**技术实现要点**：抽屉组件从右侧滑入，顶部显示达人基础信息卡片，下方显示时间轴。时间轴使用垂直布局，每个节点显示操作类型图标（选中/邀约/下单/交付/结算）、操作人角色、品牌+SPU 信息和时间戳。

**依赖**：Task 5.2.1
**预估工时**：1 天
**验收标准**：点击达人详情，抽屉滑入并显示完整的履约时间轴，按时间倒序排列。

---

#### Task 5.2.8 — 资产库：智能导出对接表头匹配 API

将智能导出四步流程（选择达人 → 上传模板 → AI 匹配表头 → 确认导出）对接真实 API。

**技术实现要点**：

**Step 1**（选择达人）：从资产库当前筛选结果中勾选要导出的达人，或选择"导出全部"。

**Step 2**（上传模板）：用户上传 Excel 模板文件，前端解析表头列表（使用 `xlsx` 库在浏览器端解析），将表头数组发送到后端。

**Step 3**（AI 匹配表头）：后端对每个用户表头调用 `GET /api/v1/export/suggest-mapping` 获取候选映射，前端渲染映射预览表格。用户可手动调整不正确的映射，标记需要忽略的列。

**Step 4**（确认导出）：用户确认映射后，调用 `POST /api/v1/export/confirm-mapping` 沉淀映射关系，同时前端根据最终映射生成 Excel 文件并触发下载。

**依赖**：Task 5.2.1
**预估工时**：2 天
**验收标准**：上传 Excel 模板后，AI 正确推荐大部分表头映射，用户确认后生成的 Excel 文件内容正确。

---

### 5.3 实时通信与状态同步

#### Task 5.3.1 — WebSocket 连接建立与心跳维护

在前端实现 WebSocket 客户端，与后端建立持久连接，用于接收实时推送消息。

**技术实现要点**：创建 `useWebSocket` 自定义 Hook，封装连接建立、心跳维护、断线重连和消息分发逻辑。心跳间隔 30 秒，发送 `{"type": "ping"}`，后端回复 `{"type": "pong"}`。断线后自动重连，重连间隔指数退避（1s → 2s → 4s → 8s → 最大 30s）。

```typescript
const useWebSocket = (url: string) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);

  const subscribe = (taskId: string) => { ... };
  const unsubscribe = (taskId: string) => { ... };

  return { isConnected, lastMessage, subscribe, unsubscribe };
};
```

**依赖**：Sprint 4 Task 4.1.4（后端 WebSocket 支持）
**预估工时**：1.5 天
**验收标准**：WebSocket 连接建立成功，心跳正常，手动断网后自动重连。

---

#### Task 5.3.2 — 降级日志实时推送到终端组件

将 `<ElasticLoadingTerminal>` 组件从轮询模式升级为 WebSocket 推送模式，实现更流畅的实时日志渲染。

**技术实现要点**：检索任务提交后，前端通过 WebSocket 发送 `{"action": "subscribe", "task_id": "xxx"}`。后端在降级算法每执行一步时，通过 WebSocket 推送 `{"type": "log_append", "log": "..."}` 消息。前端收到消息后，使用打字机动画效果逐字符渲染到终端组件中。

需要实现的降级策略：如果 WebSocket 连接不可用（断线或浏览器不支持），自动回退到轮询模式（Task 5.2.3 中已实现）。

**依赖**：Task 5.3.1, Task 5.2.3
**预估工时**：1 天
**验收标准**：降级过程中，终端组件在 100ms 内收到并渲染新日志行，视觉效果流畅无卡顿。

---

#### Task 5.3.3 — 检索进度百分比推送

通过 WebSocket 实时推送检索进度，驱动前端进度条的平滑更新。

**技术实现要点**：后端在检索任务的关键节点推送进度更新：`{"type": "progress_update", "progress": 65}`。前端收到后，使用 CSS transition 或 Framer Motion 实现进度条从当前值到目标值的平滑过渡动画（300ms ease-out）。

**依赖**：Task 5.3.1
**预估工时**：0.5 天
**验收标准**：进度条平滑过渡，无跳跃感，与实际后端进度同步。

---

### Sprint 5 集成验证

#### Task 5.4.1 — 前后端联调端到端测试

在浏览器中执行完整的业务流程测试，覆盖所有核心路径：

1. 在工作台输入"找上海的高冷风女博主，5-50 万粉丝"
2. 查看意图解析结果，调整权重滑块
3. 确认后观看弹性寻回过程（终端日志 + 进度条）
4. 在数据矩阵中浏览达人信息
5. 进入沉浸式评审，选中 3 个、淘汰 2 个
6. 点击"换一批"，验证结果进化
7. 确认入库，填写品牌/SPU 信息
8. 跳转到资产库，验证入库达人可查
9. 查看达人履约历史
10. 执行智能导出流程

**依赖**：全部 Sprint 5 任务
**预估工时**：2 天
**验收标准**：上述 10 步流程全部走通，无阻断错误，数据流转正确。

---

## Sprint 6：全链路联调、优化与上线

**目标**：端到端测试全部通过，性能指标达标，生产环境部署就绪。

**负责人**：全栈/DevOps D + 全团队
**工期**：2 周（第 13-14 周）
**里程碑验收**：系统正式上线，全链路可用。

---

### 6.1 端到端测试

#### Task 6.1.1 — 核心流程 E2E 自动化测试

使用 Playwright 或 Cypress 编写自动化 E2E 测试脚本，覆盖"寻星 → 评审 → 入库"核心流程。

**技术实现要点**：测试脚本模拟真实用户操作：打开工作台页面 → 在对话框输入自然语言 → 等待意图解析完成 → 点击确认 → 等待检索完成 → 在数据矩阵中选中/淘汰达人 → 点击确认入库 → 验证资产库中出现新入库达人。

需要编写的测试用例：正常流程（Happy Path）、空结果降级流程、多轮进化流程、网络异常恢复流程。

**依赖**：Sprint 5 全部完成
**预估工时**：2 天
**验收标准**：4 个测试用例全部通过，CI 环境可自动执行。

---

#### Task 6.1.2 — 弹性降级场景专项测试

构造极端查询条件（如"北极的粉丝超过1亿的男性美妆博主"），验证降级算法的鲁棒性。

**技术实现要点**：测试矩阵包括：(1) 单条件无结果 → 降级 1 轮即可；(2) 多条件全部无结果 → 逐轮降级直到有结果；(3) 降级达到上限仍无结果 → 返回部分结果 + 提示信息；(4) 降级过程中网络中断 → 恢复后继续。验证每种场景下前端终端日志的渲染是否正确。

**依赖**：Task 6.1.1
**预估工时**：1 天
**验收标准**：4 种极端场景全部正确处理，无崩溃或无限循环。

---

#### Task 6.1.3 — 意图进化质量评估测试

设计定量评估实验，验证 Rocchio 算法的进化效果。

**技术实现要点**：准备 5 组测试数据，每组包含一个初始查询和预定义的"理想达人"列表。执行 5 轮进化（每轮选中与理想列表最接近的达人，淘汰最远的），记录每轮 Top-10 结果与理想列表的 Precision@10 和 NDCG@10。

**依赖**：Sprint 3 Task 3.2.3
**预估工时**：1 天
**验收标准**：5 组测试中，第 3 轮的 Precision@10 平均比第 1 轮提升 > 20%。

---

#### Task 6.1.4 — 角色权重差异化验证测试

验证不同角色入库后对品牌偏好向量的影响差异。

**技术实现要点**：同一品牌+SPU，分别以采购（权重 0.3）、策划（权重 0.6）、客户（权重 1.0）角色入库相同的达人组合。比较三次入库后品牌偏好向量的偏移幅度，验证客户 > 策划 > 采购。

**依赖**：Sprint 3 Task 3.3.1
**预估工时**：0.5 天
**验收标准**：客户入库后向量偏移幅度约为采购的 3.3 倍（1.0/0.3），策划约为采购的 2 倍（0.6/0.3）。

---

### 6.2 性能优化

#### Task 6.2.1 — Milvus 索引调优（IVF_FLAT → HNSW）

将开发阶段使用的 IVF_FLAT 索引切换为 HNSW 索引，提升向量检索速度。

**技术实现要点**：HNSW 参数建议：`M=16`（每层连接数）、`efConstruction=256`（构建时搜索宽度）、`ef=128`（查询时搜索宽度）。切换步骤：释放旧索引 → 创建新索引 → 等待构建完成 → 执行基准测试对比。

需要对三个向量字段（`v_face`、`v_scene`、`v_overall_style`）分别创建 HNSW 索引。

**依赖**：Sprint 1 Task 1.2.2
**预估工时**：1 天
**验收标准**：10 万条数据量下，Top-100 召回延迟从 IVF_FLAT 的约 800ms 降低到 HNSW 的 < 500ms，召回率损失 < 2%。

---

#### Task 6.2.2 — Redis 缓存命中率优化

分析缓存命中率数据，优化缓存策略。

**技术实现要点**：添加缓存命中/未命中的监控计数器。分析热门查询模式，对高频查询条件组合实现预热缓存。调整 TTL 策略：热门达人数据 TTL 延长到 1 小时，冷门数据保持 15 分钟。实现缓存穿透保护（布隆过滤器或空值缓存）。

**依赖**：Sprint 1 Task 1.3.1
**预估工时**：1 天
**验收标准**：热门达人（Top 100 高频访问）缓存命中率 > 80%，整体缓存命中率 > 60%。

---

#### Task 6.2.3 — 前端首屏加载优化

通过代码分割、懒加载和资源优化降低首屏加载时间。

**技术实现要点**：使用 `React.lazy()` + `Suspense` 对工作台和资产库页面实现路由级代码分割。图片资源使用 WebP 格式 + 渐进式加载。字体文件使用 `font-display: swap` 避免 FOIT。Vite 构建配置中启用 `manualChunks` 将 vendor 库（React、Framer Motion、Recharts）拆分为独立 chunk。

**依赖**：Sprint 5 全部完成
**预估工时**：1 天
**验收标准**：Lighthouse Performance 评分 > 85，LCP < 2 秒，FCP < 1 秒。

---

#### Task 6.2.4 — DAG 流水线吞吐量压测

对 Sprint 2 的特征提取流水线进行压力测试，评估单 GPU 的处理能力上限。

**技术实现要点**：准备 500 张测试图片，使用 `batch_process.py` 批量处理，记录总耗时和各节点耗时。识别瓶颈节点（通常是 YOLO 或 InsightFace），针对性优化（如批量推理、半精度推理 FP16）。

**依赖**：Sprint 2 Task 2.4.4
**预估工时**：1 天
**验收标准**：单 GPU（如 A100）处理吞吐量 > 50 图/分钟，瓶颈节点已识别并记录优化建议。

---

### 6.3 部署与运维

#### Task 6.3.1 — Docker Compose 编排全部服务

编写生产环境的 `docker-compose.prod.yml`，编排全部服务容器。

**技术实现要点**：需要编排的服务包括：

| 服务 | 镜像 | 端口 | 依赖 |
|------|------|------|------|
| `web` | 自建前端镜像（Nginx + 静态文件） | 80/443 | — |
| `api` | 自建后端镜像（FastAPI/Flask） | 8000 | db, redis, milvus |
| `celery-search` | 同 api 镜像 | — | redis, milvus |
| `celery-crawl` | 同 api 镜像 | — | redis, db |
| `db` | postgres:15 | 5432 | — |
| `redis` | redis:7-alpine | 6379 | — |
| `milvus` | milvusdb/milvus:latest | 19530 | etcd, minio |
| `etcd` | quay.io/coreos/etcd | 2379 | — |
| `minio` | minio/minio | 9000 | — |

配置健康检查（healthcheck）、重启策略（restart: unless-stopped）、资源限制（deploy.resources）和日志驱动（logging）。

**依赖**：全部 Sprint 完成
**预估工时**：1.5 天
**验收标准**：`docker-compose -f docker-compose.prod.yml up -d` 一键启动全部容器，`docker-compose ps` 全部显示 healthy。

---

#### Task 6.3.2 — 环境变量与密钥管理

将所有硬编码的配置项提取为环境变量，敏感信息使用 Docker Secrets 或 `.env` 文件管理。

**技术实现要点**：需要外部化的配置项包括：数据库连接字符串、Redis 连接字符串、Milvus 连接地址、LLM API Key、小红书接口凭证、OSS 访问密钥、JWT Secret。编写 `.env.example` 文件列出所有必需的环境变量及说明。

**依赖**：Task 6.3.1
**预估工时**：0.5 天
**验收标准**：代码中无硬编码的密钥或连接字符串，`.env.example` 文档完整。

---

#### Task 6.3.3 — 日志收集与监控告警

搭建集中式日志收集和监控告警系统。

**技术实现要点**：使用 ELK Stack（Elasticsearch + Logstash + Kibana）或轻量级方案（Loki + Grafana）收集全部服务日志。定义告警规则：Celery 任务失败率 > 5% → 告警；API 响应时间 P99 > 5s → 告警；Milvus 连接异常 → 告警；GPU 利用率持续 < 10%（可能 Worker 挂了）→ 告警。告警通知渠道：企业微信/钉钉 Webhook。

**依赖**：Task 6.3.1
**预估工时**：1.5 天
**验收标准**：Grafana 仪表盘可查看全部服务日志和指标，手动触发异常后 5 分钟内收到告警通知。

---

#### Task 6.3.4 — 数据备份策略

实现 PostgreSQL 和 Milvus 的自动备份机制。

**技术实现要点**：PostgreSQL 使用 `pg_dump` 每日凌晨 3:00 执行全量备份，保留最近 7 天的备份文件，上传到 OSS。Milvus 使用内置的 `backup` 工具执行 Collection 级别备份。编写恢复脚本 `restore.sh`，支持指定日期恢复。

**依赖**：Task 6.3.1
**预估工时**：1 天
**验收标准**：执行备份 → 删除测试数据 → 执行恢复 → 数据完整恢复。

---

### Sprint 6 最终交付

#### Task 6.4.1 — 上线前检查清单

执行最终的上线前检查：

| 检查项 | 状态 |
|--------|------|
| 全部 E2E 测试通过 | ☐ |
| 性能指标全部达标 | ☐ |
| Docker Compose 一键启动成功 | ☐ |
| 环境变量文档完整 | ☐ |
| 日志收集和告警就绪 | ☐ |
| 数据备份策略已验证 | ☐ |
| API 文档（Swagger/OpenAPI）已生成 | ☐ |
| 前端构建产物已优化 | ☐ |
| 安全审计（SQL 注入、XSS、CSRF） | ☐ |
| 团队 Code Review 完成 | ☐ |

**依赖**：全部 Sprint 6 任务
**预估工时**：0.5 天
**验收标准**：检查清单全部打勾，系统正式上线。

---

## 附录：全量任务统计

| Sprint | 任务数 | 预估总工时 | 负责人 |
|--------|--------|-----------|--------|
| Sprint 1：基建层 | 12 | 6.6 天 | 后端工程师 A |
| Sprint 2：解剖层 | 13 | 10.5 天 | 算法工程师 B |
| Sprint 3：大脑层 | 10 | 6.4 天 | 算法工程师 B |
| Sprint 4：调度层 | 13 | 14.5 天 | 后端工程师 A |
| Sprint 5：触点层 | 14 | 19 天 | 前端工程师 C + 后端 A |
| Sprint 6：联调上线 | 12 | 13.5 天 | 全栈/DevOps D + 全团队 |
| **合计** | **74** | **约 70.5 人天** | |

---

*文档版本：v1.0 | 生成日期：2026-03-31 | 作者：Manus AI*
