# Σ.Match 新人上手指南

## 1) 先建立正确认知：这是一个“前端可运行 + 后端基建已落地 + 全链路待迭代”的项目

当前仓库不是“从零开始”，也不是“全量生产就绪”。更准确地说：

- **前端体验层（Landing / Workspace / Library）已完成一版高保真交互与视觉实现**。
- **后端 Sprint 1 的基建层（PostgreSQL / Milvus / Redis）已有代码与集成测试**。
- **Sprint 2~6 的多模态提取、算法进化、调度编排、API 全链路仍在路线图中**。

因此，新人入门最容易踩的坑是：误以为所有功能都已打通。实际上当前最稳妥的学习方式是“先理解架构，再识别实现边界”。

## 2) 代码库整体结构（按“价值流”理解）

### 根目录

- `README.md`：项目愿景、技术栈、页面定位、路线图总览。
- `docs/`：需求、PRD、路线图、后端逻辑摘要等“为什么这么做”的文档。
- `frontend/`：可直接运行的 React 前端（含静态服务入口）。
- `backend/`：Python 后端基础设施代码（数据库、向量库、缓存、集成测试）。
- `assets/`：品牌视觉素材。

### 前端（`frontend/`）

- `client/src/pages/`：三大页面：
  - `Home.tsx`：品牌与能力展示页。
  - `Workspace.tsx`：智能检索工作台（当前以 Mock 数据驱动交互流程）。
  - `Library.tsx`：达人资产库与履约中心（当前也以 Mock 数据驱动）。
- `client/src/components/`：
  - 业务组件（如 `Navbar`、`ParticleBackground`、`ErrorBoundary`）。
  - `ui/` 通用组件库（shadcn 风格封装）。
- `client/src/lib/constants.ts`：产品级常量（品牌信息、资源映射、维度分组等）。
- `server/index.ts`：生产态静态资源托管与 SPA 路由兜底。

### 后端（`backend/`）

- `config/`：PG/Redis/Milvus 的统一配置对象。
- `db/`：PostgreSQL 连接池 + 业务 CRUD 封装。
- `db/migrations/init.sql`：初始化 Schema（5 张表 + 1 个视图 + 索引/约束）。
- `db/seeds/seed_data.py`：基础种子数据。
- `milvus/`：Collection 管理、索引、混合检索、多向量检索。
- `redis/`：三层缓存封装（任务态、达人缓存、检索缓存）。
- `tests/test_infrastructure.py`：Sprint 1 端到端基建验证。
- `docker-compose.yml`：PostgreSQL + Redis + Milvus + etcd + MinIO 一键编排。

## 3) 新人必须掌握的“关键内容清单”

### A. 业务主线（先懂流程再看代码）

建议先背下主链路：

1. 用户在工作台输入自然语言需求。
2. 解析出硬筛选 + 软向量 + 容忍权重。
3. 先做混合召回（标量过滤 + 向量检索）。
4. 无结果时触发弹性降级（按权重放宽约束）。
5. 用户“选中/待定/淘汰”形成反馈。
6. 用 Rocchio 思想推动下一轮检索进化。
7. 最终入库沉淀到资产与履约体系。

当前前端主要演示这条链路的交互骨架；后端当前重点完成了存储与检索基础设施。

### B. 架构分层（文档高频术语）

项目在文档中反复使用五层模型：

- 触点层：前端交互 + 意图转译
- 调度层：异步队列 + 降级策略
- 解剖层：多模态特征提取 DAG
- 大脑层：混排与反馈进化算法
- 基建层：PG + Milvus + Redis

新人需要知道：**当前代码落地最完整的是触点层（前端展示）和基建层（后端 Sprint 1）**。

### C. 数据模型（后端最重要）

至少要读懂 `init.sql` 里的这几件事：

- `influencer_basics`：达人主表。
- `campaign_history`：任务与反馈沉淀。
- `influencer_notes`：内容明细。
- `fulfillment_records`：履约时间轴。
- `export_dictionary`：导出字段映射。
- `v_influencer_profile`：聚合视图（面向查询消费）。

### D. 检索与缓存（性能与体验关键）

- Milvus 里有 3 个核心向量字段（face / scene / style）+ 标量过滤字段。
- Redis 是三层缓存，不只是“存一下结果”：还承担异步任务状态桥接。

### E. 实现边界（避免误判）

- `Workspace.tsx`、`Library.tsx` 当前大量使用 Mock 数据与本地状态，适合理解交互，不代表 API 已完全接入。
- 后端 README 与路线图描述了未来目标能力，落地进度以具体代码与测试为准。

## 4) 建议的学习顺序（7 天上手版）

### Day 1：看文档，建立地图

- 先看根 `README.md`，再看：
  - `docs/SigmaMatch_Development_Roadmap.md`
  - `docs/backend_logic_summary.md`
  - `docs/SigmaMatch_Frontend_PRD.md`

目标：知道“最终要做成什么”。

### Day 2：跑前端，理解交互骨架

- `cd frontend && pnpm install && pnpm dev`
- 手动走三条路由：`/`、`/workspace`、`/library`
- 在 `Workspace.tsx` 里追踪：输入 → 意图卡片 → 数据表格 → 反馈状态

目标：知道“用户如何使用系统”。

### Day 3：读前端结构与组件边界

- 重点读 `App.tsx` 路由装配。
- 再读 `components/Navbar.tsx` 与 `lib/constants.ts`。
- 区分“页面状态逻辑”和“可复用 UI 组件”。

目标：知道“前端如何组织代码”。

### Day 4：跑后端基建（Docker）

- `cd backend`
- `cp .env.example .env`
- `docker-compose up -d`
- `pip install -r requirements.txt`
- `python -m db.seeds.seed_data`

目标：知道“基础设施能否在本地跑通”。

### Day 5：看数据库与 Python 模块

- 读 `db/migrations/init.sql`（表、索引、约束、视图）。
- 读 `db/__init__.py`（CRUD 封装与查询入口）。
- 读 `milvus/__init__.py`（Collection 与检索参数）。
- 读 `redis/__init__.py`（Task/Influencer/Search 三层缓存）。

目标：知道“数据怎么存、怎么取、怎么加速”。

### Day 6：跑集成测试

- `python -m tests.test_infrastructure`

目标：验证 Sprint 1 的真实可用性，建立“以测试判定进度”的习惯。

### Day 7：做一个最小闭环改造

推荐任务（任选其一）：

- 前端：把 `Workspace` 中一个 Mock 片段替换为真实 API stub（先接口契约后实现）。
- 后端：新增一个只读查询接口（例如按品牌查询 campaign 简版列表）。
- 数据：补一条 SQL 索引/查询优化并写明验证方式。

目标：从“读懂”进入“可交付”。

## 5) 给新人的实战建议

1. **先看边界再提方案**：先明确“现阶段实现到哪一步”，再讨论下一步，不要按终态文档直接假设已落地。
2. **以契约驱动前后端协作**：先写清请求/响应结构，再动实现。
3. **强制输出验证证据**：每次改动至少附一条可复现命令（如测试/脚本/SQL）。
4. **把“术语”翻译成“代码位置”**：例如“Rocchio”最终要落到某个函数，而不是停留在文档口号。
5. **优先维护可观察性**：日志、任务状态、缓存命中这些能力，会直接决定后续联调效率。

---

如果你是第一次接手这个仓库，建议把这份指南和根 README 一起读，再进入具体模块。这样可以避免在大量概念与组件中迷路。
