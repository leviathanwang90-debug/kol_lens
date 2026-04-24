# 本轮交付说明：`library/history` 达人下钻与细粒度时间衰减升级

## 一、交付概述

本轮继续沿着 `library/history` 的可解释复盘链路推进，完成了两项核心升级。第一项是把历史视图中的达人证据做成了**可点击下钻**，现在无论是时间线中的关键证据，还是批次时间线中的关联达人卡片，都可以继续下钻查看该达人在系统中的**完整历史时间线**。第二项是把原先较粗的统一半衰期方案，升级为按**角色**、**品牌阶段**与 **campaign 新鲜度**共同作用的细粒度衰减逻辑，使下一批推荐对历史反馈的使用更贴近真实业务演化。

## 二、本轮落地内容

| 模块 | 本轮升级内容 | 结果 |
| --- | --- | --- |
| 后端历史接口 | `library/history` 在 `influencer_id` 模式下返回达人档案与完整时间线 | 已完成 |
| 后端时间线富化 | campaign timeline 中补充 `influencer_cards`、`detail_path`、`brand_stage` | 已完成 |
| 后端反馈衰减 | 历史反馈项新增角色衰减覆盖、品牌阶段匹配因子、campaign 新鲜度因子 | 已完成 |
| 后端快照沉淀 | `assets/commit` 现在会把 `brand_stage` 一并写入历史快照 | 已完成 |
| 前端资产库页面 | `Library` 页支持点击证据达人并查看达人完整时间线 | 已完成 |
| 前端解释层 | 历史证据卡片直接回显时间衰减、新鲜度与阶段信息 | 已完成 |
| 回归测试 | 补充达人下钻与细粒度衰减断言 | 已完成 |

## 三、关键代码变更

| 文件 | 变更说明 |
| --- | --- |
| `backend/services/asset_service.py` | 扩展历史查询、达人时间线组装、timeline 达人卡片、品牌阶段提取、角色/阶段/新鲜度衰减逻辑 |
| `backend/api/schemas.py` | 为下一批推荐与资产提交补充 `brand_stage`、角色衰减覆盖和新鲜度衰减参数 |
| `backend/tests/test_asset_services.py` | 新增并更新达人下钻、品牌阶段沉淀和细粒度衰减回归测试 |
| `frontend/client/src/lib/api.ts` | 扩展历史结果、达人证据与衰减字段的前端类型定义 |
| `frontend/client/src/pages/Library.tsx` | 重写资产库历史页，接入达人证据点击下钻与达人完整时间线抽屉 |

## 四、接口与行为变化

### 1. `GET /api/v1/library/history?influencer_id=...`

现在该接口不再只返回简单历史记录，而是返回两层信息：一层是 `influencer_profile`，用于前端顶部展示达人档案；另一层是 `influencer_history`，其中每个时间线节点都包含当前批次的推荐偏移摘要、时间线预览以及可继续关联查看的上下文。

### 2. `GET /api/v1/library/history?campaign_id=...`

campaign 时间线现在会带回更丰富的可解释字段，包括：

| 字段 | 含义 |
| --- | --- |
| `brand_stage` | 当前时间线节点对应的品牌/项目阶段 |
| `influencer_cards` | 本节点涉及的达人卡片，可直接下钻 |
| `detail_path` | 当前 campaign 的历史详情路径 |
| `history_explanation` | 本节点的推荐偏移摘要与升降权信息 |

### 3. `POST /api/v1/match/next-batch`

该接口本轮新增并真正启用了更细粒度的反馈衰减参数。

| 参数 | 作用 |
| --- | --- |
| `brand_stage` | 当前品牌/项目阶段 |
| `role_decay_overrides` | 覆盖默认角色半衰期与最低保留系数 |
| `brand_stage_match_factor` | 历史反馈阶段与当前一致时的附加系数 |
| `brand_stage_mismatch_factor` | 阶段不一致时的附加系数 |
| `campaign_freshness_decay_days` | campaign 新鲜度衰减窗口 |
| `campaign_freshness_min_factor` | campaign 新鲜度最低保留系数 |

同时，接口返回的 `feedback_candidates.history_positive/history_negative` 中，也新增了如下解释字段：

| 字段 | 含义 |
| --- | --- |
| `campaign_freshness_factor` | 该历史反馈在 campaign 新鲜度维度上的保留系数 |
| `brand_stage` | 该历史反馈所属的品牌阶段 |
| `brand_stage_factor` | 该历史反馈与当前阶段匹配后的修正系数 |
| `role_decay_profile` | 该反馈实际使用的角色衰减配置 |
| `source_breakdown` | 去重合并后保留的来源拆分明细 |

## 五、前端体验变化

本轮前端的主要变化集中在 `Library` 页面。

首先，品牌/SPU 历史抽屉中的**关键证据达人**不再只是静态文案，而是变成了可点击按钮。用户点击后，会再次请求 `library/history?influencer_id=...`，并打开第二层抽屉展示该达人的完整历史时间线。其次，campaign timeline 中新增了**关联达人卡片**，用户也可以从这里继续向下追踪。

此外，历史证据标签的说明文本中，已经开始直接回显时间衰减、新鲜度因子和品牌阶段，让用户能够更容易理解为什么一条历史反馈在本轮推荐里权重更高，或者为什么它被明显削弱。

## 六、验证结果

| 验证项 | 结果 | 说明 |
| --- | --- | --- |
| `pytest -q tests/test_asset_services.py` | 通过 | `12 passed` |
| `pnpm build` | 通过 | 前端构建成功 |
| `pytest -q` 全量后端测试 | 部分失败 | 失败集中在现有基础设施测试，需要本地 PostgreSQL / Redis / Milvus 环境，不属于本轮改动回归失败 |

## 七、当前状态与下一步建议

本轮完成后，`library/history` 已经从“可看摘要”升级为“可沿证据链继续下钻”。这意味着复盘不再停留在“某个 tag 为什么被升降权”，而是可以继续追问“到底是哪几个达人、来自哪几批任务、在什么角色与阶段语境下推动了这个变化”。

下一步如果继续推进，最自然的方向有两个。第一，是把达人完整时间线中的每个节点再接上**履约内容详情**或**素材资产详情**，让下钻终点从时间线继续延伸到具体合作记录。第二，是进一步把当前已经接入的细粒度衰减做成**前端可配置策略面板**，让运营、策划和客户能够按品牌实际阶段调整衰减规则，而不仅仅由后端默认值控制。
