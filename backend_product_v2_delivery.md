# kol_lens 新版达人匹配链路后端化交付说明

## 交付概览

本次改造以你上传的 `creator_multimodal_v2.zip` 为参考，将其中已经扩展到完整产品链路的脚本能力，重构为 `kol_lens` 仓库内可直接对接产品的后端接口与服务。改造后的后端不再停留在测试脚本层，而是按照仓库现有的 `FastAPI + PostgreSQL + Milvus + Redis` 分层方式，补齐了**需求理解、库内匹配、外部扩库、入库与冷启动向量化、贪心降级**的真实服务链路。

这次实现同时对原压缩包脚本做了若干工程化优化。最重要的变化在于：原测试逻辑里较多能力混杂在脚本主流程中，配置和请求生成也更偏实验性质；现在已经被拆分为**意图解析服务、匹配编排服务、蒲公英 payload 与扩库服务**三个稳定模块，接口边界更清晰，测试覆盖也更容易做。

## 新增与改造文件

| 文件 | 作用 | 说明 |
|---|---|---|
| `backend/services/intent_parser.py` | 自然语言需求理解 | 新增数据要求与风格要求双通道解析，输出 `data_requirements`、`content_requirements`、`query_plan`、`elastic_weights` |
| `backend/services/match_service.py` | 检索编排主服务 | 打通库内 Milvus/DB 检索、结果不足时外部扩库、冷启动回查、贪心降级 |
| `backend/services/pgy_service.py` | 蒲公英服务层 | 封装 contentTag 映射、payload 生成、外部请求、PG 入库、Milvus 冷启动向量化 |
| `backend/api/schemas.py` | API 契约 | 扩展请求响应模型，支持 payload 生成与显式扩库接口 |
| `backend/app.py` | FastAPI 入口 | 新增 `/api/v1/pgy/payload/generate`、`/api/v1/library/expand`，并保留现有解析与检索接口 |
| `backend/data/pgy_category_tree.json` | 蒲公英类目树 | 从压缩包迁移入仓库，作为 contentTag 约束源 |
| `backend/.gitignore` | 忽略规则 | 放开 `pgy_category_tree.json` 的版本管理 |
| `backend/tests/test_product_workflow.py` | 新链路测试 | 覆盖需求解析、payload 生成、扩库编排与 API 路由 |
| `backend/requirements.txt` | 依赖清单 | 增补 `pytest` 测试依赖 |

## 真实接口能力

### 1. `POST /api/v1/intent/parse`

这个接口现在已经能把自然语言拆成两部分：一部分是**数据要求**，例如粉丝区间、图文报价、视频报价、CPM、目标数量；另一部分是**风格要求**，例如画面气质、人设、场景、文案感、商业感。解析结果会同时产出适合检索的 `query_plan`，以及用于后续降级的 `elastic_weights`。

### 2. `POST /api/v1/pgy/payload/generate`

这个接口用于把已解析的内容需求生成蒲公英可用 payload。它会先根据自然语言内容描述映射 `contentTag`，再结合粉丝、价格、CPM 条件生成一个或多个 payload 变体。这样前端或中台如果只想看“将请求发成什么样”，可以单独调用，不必强耦合检索流程。

### 3. `POST /api/v1/library/expand`

这个接口用于显式触发外部扩库。它会根据 `data_requirements + query_plan` 生成 payload 变体，请求蒲公英接口，在拿到博主数据后写入 `influencer_basics` 与 `influencer_notes`，同时基于文本冷启动方式把达人向量写入 Milvus，保证这些新达人能立刻回流到库内检索链路中。

### 4. `POST /api/v1/match/retrieve`

这个接口是完整产品链路入口。它会先做库内检索；如果结果不足并且显式开启 `enable_external_expansion`，则自动走外部扩库；如果回查后仍不足，并且显式开启 `enable_greedy_degrade`，则按 `elastic_weights` 做贪心降级。返回体里会包含结果、扩库信息、降级日志和最终编排日志，方便前端展示“弹性寻回过程”。

## 对压缩包脚本的优化点

| 原脚本问题 | 本次优化方式 | 落地效果 |
|---|---|---|
| 自然语言理解与检索编排耦合较紧 | 拆成 `intent_parser` 与 `match_service` | 更容易单测、复用和替换模型 |
| 蒲公英 payload 生成偏脚本化 | 抽成 `pgy_service` 中的独立 payload 生成服务 | 可单独暴露接口，也便于前端调试 |
| 外部数据抓取后与产品库结构衔接较弱 | 对齐仓库现有 `influencer_basics / influencer_notes / Milvus` | 扩库结果可立即进入产品内的真实检索链路 |
| 新入库达人缺少即时可检索能力 | 增加基于文本特征的冷启动向量化 | 不必等待完整多模态流水线跑完即可参与召回 |
| 降级逻辑主要存在于脚本实验流程 | 重构为可编排的贪心降级服务逻辑 | 便于前端展示与后续接 WebSocket |
| 静态类目树依赖留在压缩包 | 迁入仓库并纳入版本管理 | payload 生成能力可随代码仓库稳定交付 |

## 验证结果

本次已经完成针对核心新链路的回归验证。以下测试已通过：

| 测试命令 | 结果 |
|---|---|
| `pytest -q tests/test_product_workflow.py` | 4 项通过 |
| `pytest -q tests/test_match_services.py tests/test_product_workflow.py` | 10 项通过 |

此外，我还运行了后端测试目录的完整测试集。结果表明，**与本次改造直接相关的单测已经通过**，但基础设施集成测试 `tests/test_infrastructure.py` 仍依赖本地 PostgreSQL、Milvus、Redis 的实际运行环境，因此在当前沙箱内没有把整套基础设施一起拉起时会失败。这属于环境依赖，不是本次新增业务接口本身的代码错误。

## 当前使用方式建议

如果你准备马上把这版能力接到前端产品，我建议前端按下面顺序接：先调用 `/api/v1/intent/parse` 展示解析结果；确认后调用 `/api/v1/match/retrieve`，并根据需要把 `enable_external_expansion` 与 `enable_greedy_degrade` 打开；如果想让运营或策略同学先审查外部请求结构，再单独调用 `/api/v1/pgy/payload/generate`；如果需要人工触发补库，则直接使用 `/api/v1/library/expand`。

这套设计与仓库现有产品路线是对齐的，但仍有两个后续增强点值得继续做。第一，当前新达人向量化是**文本冷启动**方案，适合先把产品链路跑通，后面可以再接你路线图中的图像/多模态特征流水线，把 `v_face`、`v_scene`、`v_overall_style` 变成真正的生产级多模态向量。第二，当前降级日志已经结构化，但还是同步返回，后续可以继续接 Redis/WebSocket，把降级过程实时推给前端终端组件。
