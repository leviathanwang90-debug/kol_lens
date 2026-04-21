# kol_lens SPU 偏好记忆与下一批推荐接口交付说明

## 本轮完成内容

本轮是在上一轮 `assets/commit`、`library/list`、`library/history` 的基础上继续往前推进，目标是把你提出的“是否应该存在一个针对当前 SPU 的推荐层”真正落到后端接口上。

这次我没有把它实现成一套新的独立达人库，而是按更符合最终产品结构的方式，落成了两类能力：第一类是 **SPU 偏好记忆读取**，第二类是 **基于历史反馈的下一批推荐接口雏形**。这样设计的原因是，当前产品真正需要沉淀的是“这个 SPU 的偏好与反馈记忆”，而不是再复制一份资产库。

## 新增与更新的文件

| 文件 | 作用 |
|---|---|
| `backend/services/asset_service.py` | 扩展资产服务，新增 SPU 偏好记忆聚合与下一批推荐编排 |
| `backend/api/schemas.py` | 新增 SPU 记忆与下一批推荐接口契约 |
| `backend/app.py` | 暴露新的 API 路由 |
| `backend/tests/test_asset_services.py` | 新增聚合逻辑、推荐编排和 API 路由测试 |

## 新增接口

### 1. `GET /api/v1/spu/memory`

这个接口用于读取某个 `brand_name + spu_name` 维度下已经沉淀的偏好记忆。当前它会聚合以下信息：

| 聚合项 | 说明 |
|---|---|
| `campaign_count` | 当前 SPU 历史任务数 |
| `latest_campaign_id` | 最近一次任务 ID |
| `latest_intent` | 最近一次可复用的意图快照 |
| `latest_query_vector` | 最近一次查询向量快照 |
| `data_requirements_reference` | 最近一次较完整的数据需求参考 |
| `recommended_tag_weights` | 根据历史提交与角色权重聚合出的推荐 tag 权重 |
| `preferred_tags` | 供前端展示的 SPU 推荐特征列表 |
| `history_ids` | 已选中 / 已淘汰 / 已待定 / 已看过达人集合 |

这里的 `recommended_tag_weights` 已经可以直接给前端 `<IntentDashboard>` 的“SPU 推荐特征”区块使用，前端可以把它和本轮意图解析得到的标签一起展示给用户，再允许用户继续调节。

### 2. `POST /api/v1/match/next-batch`

这个接口是“获取更多 / Fission”的第一版后端雏形。它当前做的事情是：

首先读取当前 SPU 的历史记忆；然后拿最近一次意图快照作为基底，叠加 SPU 聚合得到的推荐 tag 权重；再结合当前前端刚刚产生的 `selected_ids / rejected_ids / pending_ids` 做排重；最后继续复用现有 `match_service.submit_retrieve_task()` 发起一轮新的检索。

这个版本还不是最终形态的 Rocchio 进化推荐，但已经具备了**真正可调用的第一版“下一批推荐”接口**。它至少解决了两个现实问题：第一，不会再把这个 SPU 历史上已经看过或刚刚决策过的达人反复推回来；第二，可以把历史偏好以权重形式真实作用到下一轮检索中。

## 当前推荐逻辑的实现方式

当前的“下一批推荐”逻辑遵循下面这个思路。

| 步骤 | 当前实现 |
|---|---|
| 读取 SPU 历史 | 读取同一 `brand + spu` 的历史 campaign |
| 聚合反馈 | 聚合 `selected / rejected / pending` 以及提交时保留的 `tag_weights` |
| 角色加权 | 客户 > 策划 > 采购，按不同权重沉淀偏好 |
| 生成推荐权重 | 形成 `recommended_tag_weights` |
| 排重 | 默认排除该 SPU 历史已决策达人，以及本轮新增已决策达人 |
| 发起新检索 | 复用现有检索服务继续召回下一批 |

这意味着你前面提到的交互设计，现在在后端上已经开始具备真实承接能力了。

## 它如何对应前端交互

你前面提到，前端在用户输入自然语言并完成第一轮语义格式化后，应该弹出一个面板，展示风格化标签、数据指标，并允许用户对每个标签调节权重、对数据范围做改写。这个方向是正确的，而且这次新增的接口就是在为那套 UI 提供后端支撑。

现在建议前端这样接：

| 前端区块 | 对应后端数据来源 |
|---|---|
| 基础筛选项 | `intent.data_requirements` |
| 视觉/标签项 | `intent.query_plan.formatted_tags` |
| SPU 推荐特征 | `GET /api/v1/spu/memory` 返回的 `preferred_tags` 与 `recommended_tag_weights` |
| 获取更多 | `POST /api/v1/match/next-batch` |
| 确认入库 | `POST /api/v1/assets/commit` |

也就是说，当前设计下，前端无需等待未来的多模态特征流水线全部完成，就已经可以先把这套“用户确认意图—评审—再来一批—确认入库”的核心链路跑起来。

## 我对你产品问题的进一步判断

关于“用户选中未选中这里是否应该有一个针对当前所选 SPU 的库，用于推荐下一批博主”，现在我会把答案进一步明确成下面这句话：

> **应该有，但它不是一套新的物理达人库，而是一个 SPU 级偏好记忆层。**

这层记忆现在已经开始落地，核心载体是 `campaign_history + fulfillment_records + query_vector_snapshot + tag_weights + feedback ids` 的组合。后续你如果要做更强的“换一批”，就不需要从零设计新库，而是在这层记忆上继续升级算法即可。

## 当前版本的边界

这次已经把接口做成了真实可调用的版本，但仍然是“下一批推荐雏形”，不是最终完整进化系统。当前边界主要有三点。

| 当前边界 | 说明 |
|---|---|
| 还未做 Rocchio 向量平移 | 目前主要是基于历史权重与排重，不是严格的正负样本向量进化 |
| 还未直接读取达人真实多模态向量做 selected/rejected 对比学习 | 当前仍先复用现有检索主链路 |
| 角色权重已沉淀但仍是规则版 | 后面可进一步做更细的用户级/品牌级/角色级分层记忆 |

换句话说，这次做的是一个**工程上真实可用、且能平滑升级到最终形态**的过渡版本，而不是为了演示而硬写一套临时逻辑。

## 测试结果

本轮代码已经与现有核心链路一起完成回归验证。

| 测试命令 | 结果 |
|---|---|
| `pytest -q tests/test_asset_services.py tests/test_match_services.py tests/test_product_workflow.py` | 20 项通过 |

## 我建议你下一步继续做什么

如果按产品价值和联调顺序继续推进，我建议下一步优先做下面两件事。

| 优先级 | 建议 | 原因 |
|---|---|
| P0 | 前端接入 `spu/memory`，把“SPU 推荐特征”区块展示出来 | 用户能立刻感知到系统在“记住这个 SPU” |
| P0 | 前端把 Fission 动作改接 `match/next-batch` | 这样“获取更多”就不再只是重复首轮检索 |
| P1 | 在下一批推荐中接入 Rocchio 或更明确的 selected/rejected 向量进化 | 这是后续推荐质量提升的关键 |
| P1 | 引入用户私有偏好记忆 | 对应 PRD 里的“用户私有标签” |

如果你要我继续，我建议下一步就直接做两件事中的其中一个：要么继续写 **Rocchio 初版**，要么继续把 **导出映射接口 `export/confirm-mapping`** 补齐。
