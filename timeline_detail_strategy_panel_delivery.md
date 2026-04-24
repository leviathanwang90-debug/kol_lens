# 本轮交付说明：时间线节点下钻到履约/素材详情 + 前端可配置衰减策略面板

## 一、已完成内容

本轮继续沿着 `library/history` 与 `match/next-batch` 两条主链路向前推进，新增能力主要分为两部分。

第一部分，是把 **达人完整时间线中的节点继续下钻到具体履约记录**。现在在资产库与历史页中，无论是品牌批次时间线，还是达人完整历史时间线，用户都可以点击某个时间线节点进入对应的履约详情视图。该视图会展示当前记录的品牌与 SPU 上下文、品牌阶段、履约内容摘要、已选/淘汰/待定人数、关联达人列表、素材资产列表，以及基于现有达人笔记数据自动回退构建的内容笔记预览。这样下钻终点就不再停留在“某批次发生了什么”，而是可以继续看到“这次合作具体沉淀了什么内容与素材”。

第二部分，是把现有细粒度时间衰减从纯后端默认值控制，升级为 **前端可配置策略面板**。现在工作台顶部的设置下拉中，除了期望寻回数量，还可以直接配置统一半衰期天数、统一最小系数、品牌阶段匹配/不匹配系数、campaign 新鲜度衰减天数、新鲜度最小系数，以及采购/策划/客户三个角色的独立衰减覆盖参数。用户在面板中修改后，下一次 Fission 请求会直接把这些参数发送给后端，用于驱动下一批推荐的历史反馈衰减策略。

## 二、后端改动

| 文件 | 变更说明 |
| --- | --- |
| `backend/db/__init__.py` | 新增 `get_campaign_by_id` 与 `get_fulfillment_record`，为履约详情下钻提供单条记录与任务上下文查询能力；继续复用 `get_notes_by_influencer` 作为内容/素材预览的数据来源。 |
| `backend/services/asset_service.py` | 扩展资产提交快照，支持沉淀 `content_summary`、`collaboration_note`、`material_assets`、`delivery_links`；新增 `record_id` 模式的 `library/history` 查询；补充履约详情构建逻辑，统一输出内容详情、素材资产、达人卡片、笔记预览与品牌上下文。 |
| `backend/api/schemas.py` | 为 `assets/commit` 增加可选的内容摘要、合作备注、素材资产与履约链接字段。 |
| `backend/app.py` | 为 `/api/v1/library/history` 增加 `record_id` 查询参数，支持时间线节点直接下钻到具体履约记录。 |
| `backend/tests/test_asset_services.py` | 新增并补强回归测试，覆盖 `record_id` 履约详情模式与 API 路由。 |

## 三、前端改动

| 文件 | 变更说明 |
| --- | --- |
| `frontend/client/src/lib/api.ts` | 扩展 `LibraryHistoryResult`、`FulfillmentRecordDetail`、`DecayStrategyConfig` 等类型，支撑履约详情视图与策略面板配置。 |
| `frontend/client/src/pages/Library.tsx` | 新增履约详情抽屉；时间线卡片新增“查看履约 / 素材详情”动作；历史视图支持从时间线继续下钻到具体合作记录。 |
| `frontend/client/src/pages/Workspace.tsx` | 将顶部设置面板升级为可配置策略面板；下一批推荐请求现在会透传角色、品牌阶段与新鲜度相关衰减参数；确认入库时会一并提交内容摘要、合作备注和策略快照。 |

## 四、接口行为变化

### 1. `GET /api/v1/library/history`

现在除原有的 `brand_name + spu_name`、`campaign_id`、`influencer_id` 模式外，还支持：

- `record_id=<fulfillment_record_id>`：返回 `mode=fulfillment_detail`

返回结果中的 `record_detail` 结构包含：

| 字段 | 含义 |
| --- | --- |
| `campaign` | 任务上下文，包括品牌、SPU、操作角色和任务详情路径 |
| `brand_stage` | 当前履约记录对应的品牌阶段 |
| `history_explanation` | 当前记录沉淀的推荐进化摘要 |
| `content_detail` | 履约内容摘要、合作备注、selected/rejected/pending、tag 权重与数据要求 |
| `material_assets` | 素材资产或外部履约链接 |
| `note_previews` | 基于达人笔记表回退构建的内容素材预览 |
| `influencer_cards` | 可继续下钻达人完整时间线的关联达人卡片 |

### 2. `POST /api/v1/assets/commit`

可选新增提交字段：

- `content_summary`
- `collaboration_note`
- `material_assets`
- `delivery_links`

这些字段会被沉淀进 `payload_snapshot`，并在后续 `library/history?record_id=...` 中回放出来。

## 五、验证结果

本轮已完成两类验证。

| 验证项 | 结果 |
| --- | --- |
| `cd backend && pytest -q tests/test_asset_services.py` | 通过，`13 passed` |
| `cd frontend/client && pnpm build` | 通过，存在既有环境变量告警与 chunk 体积告警，但不影响构建成功 |

## 六、当前可直接继续推进的下一步

本轮已经把“时间线节点 -> 履约详情”的链路打通，后续最顺滑的下一步有两个方向。

其一，是继续把 `record_detail` 中的素材资产做成更完整的 **媒体预览与结构化内容卡片**，例如区分封面图、视频、笔记链接、结案截图、投放素材等资产类型，并在前端提供更强的预览与筛选能力。

其二，是把工作台中的策略面板再向前推进成 **可保存的品牌级策略模板**，让不同品牌阶段、不同客户角色能直接套用一套衰减参数，而不是每次手工输入。
