# kol_lens 后端服务改写交付说明

本次改写将压缩包中用于验证**自然语言格式化**与**达人向量匹配**的测试流程，迁移为 `kol_lens` 项目可直接接入的后端服务实现。改写重点不是复刻测试脚本的实验输出形式，而是把其中的核心链路沉淀为项目内可复用的服务层与 API 层，包括自然语言意图解析、结构化 query plan 生成、查询向量构建、Milvus 检索执行、任务状态封装以及测试覆盖。

| 模块 | 新增/修改文件 | 作用 |
| --- | --- | --- |
| 应用入口 | `backend/app.py` | 提供健康检查、意图解析、达人检索与任务查询接口 |
| API 模型 | `backend/api/schemas.py` | 统一请求与响应模型 |
| 意图解析服务 | `backend/services/intent_parser.py` | 将自然语言需求改写为结构化字段和检索计划 |
| 检索服务 | `backend/services/match_service.py` | 构建查询向量、执行 Milvus 检索、补充达人资料、管理任务状态 |
| 服务包导出 | `backend/services/__init__.py`、`backend/api/__init__.py` | 便于后续模块化扩展 |
| 测试 | `backend/tests/test_match_services.py` | 覆盖解析、检索和 API 路由 |
| 依赖 | `backend/requirements.txt` | 补充 FastAPI、OpenAI 客户端、测试与数值依赖 |
| 兼容修复 | `backend/redis/__init__.py` | 修复本地模块与第三方同名包冲突导致的导入问题 |

## 这次实现的核心接口

新接口遵循“先解析、再检索、可回查任务状态”的服务化思路。`POST /api/v1/intent/parse` 接收原始自然语言需求，输出 `hard_filters`、`elastic_weights`、`soft_vectors` 与 `query_plan`。其中 `query_plan` 包含 `long_sentence_query`、`formatted_query_json`、`formatted_query_text` 和 `formatted_tags`，可直接被后续检索服务复用。

`POST /api/v1/match/retrieve` 则承接解析结果或原始查询文本，支持 `long_sentence`、`field_tags`、`field_tags_weighted`、`field_tags_explicit_weight_text` 四种查询向量构造模式，并统一落到项目现有的 `v_overall_style` 向量检索流程中。接口会自动合并从查询文本中抽取出的硬筛选条件与额外传入的标量过滤条件，再调用 Milvus 执行向量检索，并尝试补充 PostgreSQL 中的达人资料。

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/healthz` | `GET` | 健康检查 |
| `/api/v1/intent/parse` | `POST` | 自然语言需求解析与格式化 |
| `/api/v1/match/retrieve` | `POST` | 向量检索任务提交与结果返回 |
| `/api/v1/tasks/{task_id}` | `GET` | 查询任务状态与结果 |

## 与测试脚本流程的对应关系

原测试脚本的两个关键步骤是：第一步，将自然语言需求改写成便于检索的结构化查询；第二步，围绕不同实验模式构造查询文本或标签权重，生成向量后匹配达人库。现在这两步已经分别下沉为 `IntentParserService` 与 `MatchService`。

| 测试流程概念 | 项目内服务化实现 |
| --- | --- |
| 自然语言格式化 | `IntentParserService.parse()` |
| 结构化字段 JSON | `query_plan.formatted_query_json` |
| 长句检索模式 | `experiment_mode=long_sentence` |
| 标签平均模式 | `experiment_mode=field_tags` |
| 标签加权模式 | `experiment_mode=field_tags_weighted` |
| 显式权重文本模式 | `experiment_mode=field_tags_explicit_weight_text` |
| 检索任务状态 | `submit_retrieve_task()` + `/api/v1/tasks/{task_id}` |

## 当前实现中的工程化处理

考虑到你当前仓库后端基础设施尚未完全成型，这次服务化改写增加了两层**开发期降级能力**。第一层是当 Redis 不可用时，任务状态与检索缓存会自动回落到内存实现，保证本地联调和单元测试不被基础设施阻塞。第二层是查询向量构建使用了可复现的本地哈希向量方案，将文本稳定映射到 768 维查询向量，从而与现有 `v_overall_style` 检索接口对接，便于你后续替换成正式的 CLIP Text Encoder 或线上 embedding 服务。

这意味着当前版本已经具备**完整的服务链路**，但如果你后续要上线生产环境，建议优先把 `embed_text_to_style_vector()` 替换为正式的文本向量模型，并根据你们真实的人群标签体系继续细化 `IntentParserService` 中的规则与提示词。

## 验证结果

本次新增实现已在 `backend/tests/test_match_services.py` 中补充单元测试，并实际执行通过。执行命令如下：

```bash
cd /home/ubuntu/work/kol_lens/backend
python3.11 -m unittest discover -s tests -v
```

测试覆盖了解析服务、检索服务以及 API 路由三部分，当前结果为 **6 个测试全部通过**。

## 建议的下一步

如果你准备继续推进这部分功能，我建议下一步直接做三件事。第一，把前端或调用方约定的请求体正式固定下来，尤其是 `tag_weights` 的 key 命名规则。第二，把当前本地哈希向量替换成真实的文本 embedding 服务。第三，如果你希望和现有任务队列体系保持一致，可以把 `submit_retrieve_task()` 再拆成同步 API + 异步 worker 两层。
