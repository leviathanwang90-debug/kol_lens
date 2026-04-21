# 当前产品已实现功能完整流程图与分层输入输出说明

## 总览

基于当前仓库已落地的前后端能力，产品主流程已经形成一个从**自然语言需求输入**、到**意图理解与确认**、到**库内检索 / 外部扩库 / Fission 下一批推荐**、再到**确认入库、资产库历史沉淀、达人全量数据补充与导出模板复用**的闭环。

下图给出当前版本的完整流程图。其后我按层级展开说明每一步的输入、处理、输出，以及前后端联调时可直接参考的字段格式。

```mermaid
flowchart TD
    A[前端入口\nWorkspace / Library\n输入: brand_name, spu_name, operator_id, role] --> B[自然语言需求输入\nraw_text]
    A --> A1[预加载记忆\nGET /api/v1/spu/memory\nGET /api/v1/user/memory]
    A1 --> A2[输出\nSPU 推荐特征\n用户私有偏好\n历史已看达人/偏好标签]

    B --> C[意图解析\nPOST /api/v1/intent/parse]
    C --> C1[输出 intent\nquery_plan\ndata_requirements\nstyle tags\nhard_filters]
    C1 --> D[前端意图确认面板\n可调 tag 权重 0-2\n可改数据指标范围]

    D --> E[首轮检索\nPOST /api/v1/match/retrieve]
    E --> E1[向量检索 / 标量过滤]
    E1 --> E2{库内结果是否足够}
    E2 -- 是 --> F[返回候选达人列表]
    E2 -- 否 --> G[外部扩库\nPOST /api/v1/library/expand\n内部可先生成 PGY payload]
    G --> G1[外部达人入库 + 向量化]
    G1 --> H{补库后是否足够}
    H -- 是 --> F
    H -- 否 --> I[贪心降级\n放宽 tag / filter / query]
    I --> F

    F --> J[工作台评审\nselected / rejected / pending]
    J --> K[可解释 Fission\nPOST /api/v1/match/next-batch]
    A2 --> K
    D --> K
    J --> K
    K --> K1[反馈进化\nRocchio\n当前反馈 + 历史反馈\n角色/品牌阶段/campaign 新鲜度衰减]
    K1 --> K2[输出\n下一批达人\nweight_changes\npositive_examples\nnegative_examples\nrocchio_meta]
    K2 --> J

    J --> L[确认入库\nPOST /api/v1/assets/commit]
    D --> L
    K2 --> L
    L --> L1[输出\ncampaign_id\nfulfillment_records\nSPU 记忆更新\n用户记忆更新\nhistory explanation snapshot]

    L1 --> M[资产库列表\nGET /api/v1/library/list]
    L1 --> N[资产库历史\nGET /api/v1/library/history]
    N --> N1[查询模式\nbrand+spu / campaign_id / influencer_id / record_id]
    N1 --> N2[输出\n批次时间线\n达人完整时间线\n履约详情\n素材资产\n历史解释摘要]

    J --> O[全量达人数据补充\nGET /api/v1/creator-data/catalog\nPOST /api/v1/creator-data/enrich]
    O --> O1[输出\n字段目录\n补充结果表 rows]
    O1 --> P[字段勾选导出]
    P --> Q[模板管理\nGET/POST /api/v1/export/templates]
    P --> R[生成导出文件\nPOST /api/v1/export/creators]
    Q --> R
    R --> S[下载 CSV\nGET /api/v1/export/download/{file_name}]
```

## 分层流程说明

### 第一层：上下文初始化与记忆加载

这一层的目标，是在用户正式发起检索前，把当前品牌、SPU、操作角色，以及系统已沉淀的 SPU 记忆和用户私有偏好记忆先加载出来。前端工作台会基于这些返回结果预先展示“SPU 推荐特征”“用户私有标签”“历史已看达人”等信息，从而让后续 Fission 不只是重复检索，而是建立在历史沉淀之上。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 前端上下文初始化 | `brand_name`, `spu_name`, `operator_id`, `operator_role` | 工作台加载当前业务上下文 | 当前检索会话上下文 | `{"brand_name":"雅诗兰黛","spu_name":"小棕瓶","operator_id":12,"operator_role":"策划"}` |
| SPU 记忆查询 | `brand_name`, `spu_name` | 调用 `/api/v1/spu/memory` 聚合历史 campaign 与已选达人反馈 | `preferred_tags`, `recommended_tag_weights`, `history_selected_ids` 等 | `GET /api/v1/spu/memory?brand_name=雅诗兰黛&spu_name=小棕瓶` |
| 用户记忆查询 | `operator_id`, `brand_name`, `spu_name` | 调用 `/api/v1/user/memory` 聚合当前用户的个人偏好 | 用户私有偏好标签、历史反馈摘要 | `GET /api/v1/user/memory?operator_id=12&brand_name=雅诗兰黛&spu_name=小棕瓶` |

### 第二层：自然语言需求理解与意图确认

这一层的目标，是把用户的一句话需求拆成系统可执行的结构化意图，并在前端弹窗中允许用户继续微调。这里已经不是纯文本输入，而是把需求拆成**风格 tag、数据要求、硬筛选条件、query plan** 等结构，供后续检索和扩库直接使用。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 原始需求输入 | `raw_text` | 用户输入自然语言需求 | 原始检索语句 | `"找上海 10-50 万粉的高级感护肤女博主，图文 CPM 不超过 300"` |
| 意图解析 | `raw_text`, `brand_name`, `spu_name` | 调用 `/api/v1/intent/parse`，提取数据需求、风格要求、query plan 与 hard filters | `intent` 结构化对象 | 见下方 `IntentParse` 示例 |
| 意图确认面板 | `intent` + SPU / 用户记忆 | 前端展示 tag、权重、指标范围；用户可调整 | 最终确认后的 `tag_weights`、`data_requirements`、`intent` | `tag_weights: {"高级感":1.4,"护肤":1.2}` |

> **IntentParse 请求示例**
>
> ```json
> {
>   "raw_text": "找上海 10-50 万粉的高级感护肤女博主，图文 CPM 不超过 300",
>   "brand_name": "雅诗兰黛",
>   "spu_name": "小棕瓶"
> }
> ```
>
> **IntentParse 返回示例**
>
> ```json
> {
>   "success": true,
>   "intent": {
>     "data_requirements": {
>       "region": "上海",
>       "followers_min": 100000,
>       "followers_max": 500000,
>       "image_cpm_max": 300,
>       "gender": "female"
>     },
>     "query_plan": {
>       "core_tags": ["高级感", "护肤"],
>       "style_tags": ["精致", "白领", "成分党"]
>     },
>     "hard_filters": {
>       "platform": "xiaohongshu"
>     }
>   }
> }
> ```

### 第三层：首轮检索、外部扩库与贪心降级

这一层是首轮召回主链路。前端会把已经确认过的意图对象、tag 权重和标量过滤条件传给检索接口。检索服务优先尝试库内向量匹配；若结果不足，则触发蒲公英扩库；若扩库后仍不够，再走贪心降级。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 首轮检索请求 | `raw_text`, `intent`, `tag_weights`, `scalar_filters`, `top_k` | 调用 `/api/v1/match/retrieve` 执行库内检索 | 候选达人列表、任务状态、检索元信息 | 见下方 `MatchRetrieve` 示例 |
| 外部扩库 | `data_requirements`, `query_plan`, `needed_count` | `/api/v1/library/expand` 调外部库、入 PG、向量化入 Milvus | 新入库达人、扩库数量、补库状态 | `{"needed_count":20,"brand_name":"雅诗兰黛"}` |
| 贪心降级 | 同检索上下文 | 逐步放宽 tag/filter/query | 降级后的补足结果 | 结果仍返回在检索结果 `result` 内 |

> **MatchRetrieve 请求示例**
>
> ```json
> {
>   "raw_text": "找上海 10-50 万粉的高级感护肤女博主，图文 CPM 不超过 300",
>   "brand_name": "雅诗兰黛",
>   "spu_name": "小棕瓶",
>   "intent": {
>     "data_requirements": {
>       "region": "上海",
>       "followers_min": 100000,
>       "followers_max": 500000,
>       "image_cpm_max": 300
>     },
>     "query_plan": {
>       "core_tags": ["高级感", "护肤"]
>     }
>   },
>   "top_k": 20,
>   "tag_weights": {
>     "高级感": 1.4,
>     "护肤": 1.2
>   },
>   "scalar_filters": {
>     "region": "上海"
>   },
>   "enable_external_expansion": true,
>   "enable_greedy_degrade": true
> }
> ```
>
> **MatchRetrieve 返回示例**
>
> ```json
> {
>   "success": true,
>   "task_id": "retrieve_20260421_001",
>   "status": "completed",
>   "result": {
>     "items": [
>       {
>         "internal_id": 101,
>         "nickname": "Luna",
>         "followers": 286000,
>         "region": "上海",
>         "score": 0.873,
>         "tags": ["高级感", "护肤", "成分党"]
>       }
>     ],
>     "used_external_expansion": false,
>     "used_greedy_degrade": false
>   }
> }
> ```

### 第四层：人工评审与可解释 Fission 下一批推荐

这一层是当前产品区别于普通检索的关键闭环。用户会先对返回达人进行人工评审，形成 `selected / rejected / pending` 三类反馈。随后系统调用 `/api/v1/match/next-batch`，在当前反馈、SPU 记忆、用户记忆与历史批次基础上计算新的 tag 升降、Rocchio 进化向量，并返回下一批达人。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 评审动作 | 当前结果列表 | 用户在工作台上点选 / 淘汰 / 待定 | `selected_ids`, `rejected_ids`, `pending_ids` | `{"selected_ids":[101,105],"rejected_ids":[109],"pending_ids":[113]}` |
| Fission 请求 | 评审反馈 + intent + tag_weights + 记忆 + 衰减策略 | `/api/v1/match/next-batch` 执行当前轮 + 历史轮的反馈进化 | 新一批达人、权重变化、证据样本、Rocchio 摘要 | 见下方 `NextBatch` 示例 |
| 可解释输出 | `weight_changes`, `positive_examples`, `negative_examples`, `rocchio_meta` | 前端展示解释条、升降权标签、证据来源、本轮/历史来源区分 | 用户可理解“为什么推荐变了” | `weight_changes.up = [{"tag":"高级感","from":1.0,"to":1.4}]` |

> **NextBatch 请求示例**
>
> ```json
> {
>   "brand_name": "雅诗兰黛",
>   "spu_name": "小棕瓶",
>   "brand_stage": "放量",
>   "operator_id": 12,
>   "operator_role": "策划",
>   "intent": {
>     "data_requirements": {
>       "region": "上海",
>       "followers_min": 100000,
>       "followers_max": 500000
>     },
>     "query_plan": {
>       "core_tags": ["高级感", "护肤"]
>     }
>   },
>   "tag_weights": {
>     "高级感": 1.4,
>     "护肤": 1.2
>   },
>   "selected_ids": [101, 105],
>   "rejected_ids": [109],
>   "pending_ids": [113],
>   "top_k": 10,
>   "use_memory_feedback": true,
>   "current_feedback_factor": 1.0,
>   "history_feedback_decay": 0.55,
>   "role_time_decay_days": 21,
>   "brand_stage_match_factor": 1.0,
>   "brand_stage_mismatch_factor": 0.72,
>   "campaign_freshness_decay_days": 14,
>   "campaign_freshness_min_factor": 0.6,
>   "rocchio_alpha": 1.0,
>   "rocchio_beta": 0.65,
>   "rocchio_gamma": 0.3
> }
> ```
>
> **NextBatch 返回关键结构示例**
>
> ```json
> {
>   "success": true,
>   "result": {
>     "items": [{"internal_id": 221, "nickname": "Mia", "score": 0.842}],
>     "weight_changes": {
>       "up": [{"tag": "高级感", "from": 1.0, "to": 1.4, "source": "current_feedback"}],
>       "down": [{"tag": "学生感", "from": 1.0, "to": 0.7, "source": "history_feedback"}],
>       "positive_examples": [{"influencer_id": 101, "nickname": "Luna", "tags": ["高级感", "护肤"]}],
>       "negative_examples": [{"influencer_id": 109, "nickname": "Kiki", "tags": ["学生感"]}]
>     },
>     "rocchio_meta": {
>       "current_feedback_count": 3,
>       "history_feedback_count": 6,
>       "operator_role": "策划"
>     }
>   }
> }
> ```

### 第五层：确认入库与记忆沉淀

这一层负责把本轮结果正式沉淀为资产库与历史。它既记录用户选了哪些达人，也记录当时的意图、tag 权重、数据要求、Rocchio 进化快照、内容摘要、素材资产与履约链接。后续 SPU 记忆、用户记忆和历史复盘都基于这里沉淀的数据。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 资产提交 | `brand_name`, `spu_name`, `intent`, `tag_weights`, `selected_ids`, `rejected_ids`, `pending_ids`, `evolution_snapshot`, `content_summary`, `material_assets` 等 | `/api/v1/assets/commit` 落库并写履约快照 | `campaign_id`, `record_ids`, 提交状态 | 见下方 `AssetsCommit` 示例 |
| SPU 记忆更新 | 提交快照 | 聚合到 SPU 维度 | 推荐特征、已看达人、推荐 tag 权重 | 下次 `GET /api/v1/spu/memory` 读取 |
| 用户记忆更新 | 提交快照 + `operator_id` | 聚合到用户维度 | 私有标签偏好、历史解释 | 下次 `GET /api/v1/user/memory` 读取 |

> **AssetsCommit 请求示例**
>
> ```json
> {
>   "brand_name": "雅诗兰黛",
>   "spu_name": "小棕瓶",
>   "brand_stage": "放量",
>   "raw_text": "找上海 10-50 万粉的高级感护肤女博主，图文 CPM 不超过 300",
>   "intent": {"data_requirements": {"region": "上海"}, "query_plan": {"core_tags": ["高级感", "护肤"]}},
>   "tag_weights": {"高级感": 1.4, "护肤": 1.2},
>   "data_requirements": {"followers_min": 100000, "followers_max": 500000},
>   "selected_ids": [101, 105],
>   "rejected_ids": [109],
>   "pending_ids": [113],
>   "operator_id": 12,
>   "operator_role": "策划",
>   "evolution_snapshot": {
>     "weight_changes": {"up": [{"tag": "高级感", "from": 1.0, "to": 1.4}]},
>     "rocchio_meta": {"current_feedback_count": 3}
>   },
>   "content_summary": "首批种草达人合作，主打修护与夜间精华场景。",
>   "collaboration_note": "优先观察高客单修护场景的点击反馈。",
>   "material_assets": [{"type": "note_link", "url": "https://example.com/note/123", "title": "首批投放笔记"}],
>   "delivery_links": [{"type": "report", "url": "https://example.com/report/1"}]
> }
> ```

### 第六层：资产库列表、历史时间线与履约详情下钻

这一层是沉淀后的复盘与复用中心。`library/list` 用于看资产库当前达人；`library/history` 用于看某个品牌/SPU、某个 campaign、某位达人、或某条履约记录的历史。现在时间线节点已经可以继续下钻到具体履约内容、素材资产和关联达人。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 资产库列表 | 分页、地区、粉丝范围、性别、标签、排序 | `/api/v1/library/list` 查询 | 标准达人库列表 | `GET /api/v1/library/list?page=1&page_size=20&tags=护肤,高级感` |
| 历史总览 | `brand_name + spu_name` | 返回品牌/SPU 维度的批次历史 | campaign timeline、解释摘要 | `GET /api/v1/library/history?brand_name=雅诗兰黛&spu_name=小棕瓶` |
| campaign 历史 | `campaign_id` | 返回单批次详细历史 | timeline、达人列表、历史解释 | `GET /api/v1/library/history?campaign_id=88` |
| 达人时间线 | `influencer_id` | 返回某位达人完整历史时间线 | timeline nodes、品牌/SPU 上下文 | `GET /api/v1/library/history?influencer_id=101` |
| 履约详情下钻 | `record_id` | 返回某条履约记录的内容详情、素材资产、笔记预览、关联达人 | `record_detail` | `GET /api/v1/library/history?record_id=5001` |

> **Record Detail 返回关键结构示例**
>
> ```json
> {
>   "success": true,
>   "result": {
>     "mode": "fulfillment_detail",
>     "record_detail": {
>       "campaign": {
>         "campaign_id": 88,
>         "brand_name": "雅诗兰黛",
>         "spu_name": "小棕瓶"
>       },
>       "brand_stage": "放量",
>       "history_explanation": {
>         "summary": "系统因前两轮高客单修护内容表现较好，上调了高级感与成分党权重。"
>       },
>       "content_detail": {
>         "content_summary": "首批种草达人合作，主打修护与夜间精华场景。",
>         "collaboration_note": "优先观察高客单修护场景的点击反馈。"
>       },
>       "material_assets": [
>         {"type": "note_link", "title": "首批投放笔记", "url": "https://example.com/note/123"}
>       ],
>       "influencer_cards": [
>         {"influencer_id": 101, "nickname": "Luna"}
>       ]
>     }
>   }
> }
> ```

### 第七层：全量达人数据补充、字段级导出与模板复用

这一层是当前产品最新完成的能力。它发生在**用户已经选中达人**之后，允许工作台调用外部全量数据接口，为已选达人补齐更细的维度，然后让用户按字段导出并保存字段模板。

| 层级 | 输入 | 处理 | 输出 | 参考格式 |
|---|---|---|---|---|
| 字段目录获取 | 无 | `GET /api/v1/creator-data/catalog` | 字段目录、分组、默认字段 | 见下方 `Catalog` 示例 |
| 一键补充数据 | 已选达人 + 字段列表 | `POST /api/v1/creator-data/enrich` 调用全量数据服务 | `rows` 表格数据 | 见下方 `Enrich` 示例 |
| 模板列表 | `operator_id`, `brand_name`, `spu_name` | `GET /api/v1/export/templates` | 模板列表 | `GET /api/v1/export/templates?operator_id=12&brand_name=雅诗兰黛&spu_name=小棕瓶` |
| 模板保存 | `template_name`, `field_keys` 等 | `POST /api/v1/export/templates` | 模板对象 | `{"template_name":"投放复盘模板","field_keys":["nickname","followers","avg_cpm"]}` |
| 生成导出文件 | 已选达人 + 行数据 + 字段列表 | `POST /api/v1/export/creators` | 下载路径、文件名、行数 | `download_url: "/api/v1/export/download/creator_export_xxx.csv"` |
| 下载 CSV | `file_name` | 下载导出结果 | CSV 文件 | `GET /api/v1/export/download/creator_export_xxx.csv` |

> **Catalog 返回示例**
>
> ```json
> {
>   "success": true,
>   "result": {
>     "fields": [
>       {"key": "nickname", "label": "达人昵称", "group": "基础信息", "default": true},
>       {"key": "followers", "label": "粉丝数", "group": "基础信息", "default": true},
>       {"key": "avg_cpm", "label": "平均 CPM", "group": "投放表现", "default": false}
>     ],
>     "default_field_keys": ["nickname", "followers"]
>   }
> }
> ```
>
> **Enrich 请求示例**
>
> ```json
> {
>   "brand_name": "雅诗兰黛",
>   "spu_name": "小棕瓶",
>   "creators": [
>     {
>       "creator_id": 101,
>       "creator_uid": "abc123",
>       "nickname": "Luna",
>       "redbook_id": "luna_sh",
>       "region": "上海",
>       "followers": 286000,
>       "tags": ["高级感", "护肤"],
>       "raw": {"platform": "xiaohongshu"}
>     }
>   ],
>   "field_keys": ["nickname", "followers", "avg_cpm", "category_distribution"],
>   "template_id": ""
> }
> ```
>
> **Enrich 返回示例**
>
> ```json
> {
>   "success": true,
>   "result": {
>     "field_keys": ["nickname", "followers", "avg_cpm", "category_distribution"],
>     "rows": [
>       {
>         "creator_id": 101,
>         "creator_uid": "abc123",
>         "fields": {
>           "nickname": "Luna",
>           "followers": 286000,
>           "avg_cpm": 268.5,
>           "category_distribution": ["护肤", "成分党"]
>         },
>         "display_fields": {
>           "达人昵称": "Luna",
>           "粉丝数": "28.6万",
>           "平均 CPM": "268.5",
>           "类目分布": "护肤、成分党"
>         }
>       }
>     ]
>   }
> }
> ```

## 当前产品的完整闭环

如果把当前已实现功能合并成一个完整用户旅程，那么它已经可以被表述为以下闭环：用户进入工作台，先加载品牌/SPU/用户记忆；随后输入自然语言需求，由系统解析并在意图确认面板中展示结构化 tag 与指标；用户确认后发起首轮检索，系统优先库内召回，不足时扩库，再不足时降级；前端展示结果后，用户通过 selected/rejected/pending 形成反馈，触发可解释 Fission；系统基于本轮反馈、SPU 历史、用户历史和衰减策略给出下一批，并显式解释“哪些 tag 被升权或降权、证据达人是谁”；用户确认后执行资产提交，将本轮选择、推荐进化摘要、履约内容与素材沉淀进资产库；随后资产库和历史页提供 brand/SPU、campaign、influencer、record 四种维度的复盘与下钻；最后，用户还可以对选中达人一键补充全量数据，按字段生成导出文件，并将字段组合保存为模板，供后续品牌/SPU 场景重复使用。

## 建议你后续如何使用这份流程图

如果你下一步是给产品、前端、后端一起开评审会，那么这份图最适合作为“**当前版本真实已实现能力**”的基线图。前端可以对照它检查是否已经把所有返回字段消费到位，后端可以对照它检查哪些输入输出已经稳定，产品则可以在这张图上直接继续标注“下一阶段准备新增的分支”。

如果你愿意，我下一步可以继续基于这份当前版流程图，再给你补两份衍生物：一份是**面向产品经理的简化版流程图**，只保留用户可感知节点；另一份是**面向研发联调的接口时序图**，把每个 API 的先后顺序和依赖关系画得更细。
