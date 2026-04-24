# 本轮交付说明：Fission 证据展示、时间衰减与 `library/history` 沉淀

## 一、这轮完成了什么

本轮继续沿着你给出的优先级推进，重点把 **Fission 的可解释性** 从“仅展示权重升降结果”，推进到了“展示升降原因、区分反馈来源、并将解释摘要沉淀到历史视图”。同时，后端的 Rocchio 进化逻辑也补上了 **时间衰减**，使较老的历史任务不会长期以同样强度影响推荐方向。

| 模块 | 本轮落地内容 | 结果 |
|---|---|---|
| 后端推荐进化 | 在历史反馈中加入时间衰减因子 | 已完成 |
| 后端证据结构 | 为 tag 升降补充 `positive_examples` / `negative_examples` 的达人级证据元数据 | 已完成 |
| 来源区分 | 在反馈证据中区分 `current` 与 `history`，并保留 `history_source` | 已完成 |
| 历史沉淀 | 把推荐进化摘要写入 `assets/commit` 的 `evolution_snapshot` 并回流到 `library/history` | 已完成 |
| 工作台前端 | Fission 后展示“本轮反馈 / 历史反馈”拆分和达人证据 | 已完成 |
| 资产库前端 | 改为真实消费 `library/list` / `library/history` 接口，展示历史摘要与证据预览 | 已完成 |

## 二、后端改造要点

本轮后端核心改造集中在 `backend/services/asset_service.py`。新的实现不再只保留聚合后的 `selected_rank` / `rejected_rank`，而是进一步保留了带有 **角色、时间戳、campaign_id、role_weight** 的事件级明细。这样在下一批推荐计算时，系统可以把历史反馈拆成“本轮反馈驱动”和“历史反馈驱动”两层，并进一步对历史反馈施加时间衰减。

其中最关键的变化有三类。第一类是 **记忆画像结构增强**。SPU 和记忆用户画像现在都返回 `selected_events`、`rejected_events`、`pending_events`，为后续解释链路和更细粒度的反馈策略提供数据基础。第二类是 **时间衰减策略接入**。下一批推荐请求新增 `role_time_decay_days` 和 `role_time_decay_min_factor`，用于控制历史反馈半衰期和最小保留系数。第三类是 **历史摘要沉淀**。`assets/commit` 现在支持提交 `evolution_snapshot`，后续在 `library/history` 查询时，接口会直接返回最近一次推荐偏移摘要、Rocchio 说明以及简化的证据预览。

| 文件 | 本轮修改 | 说明 |
|---|---|---|
| `backend/services/asset_service.py` | 大幅增强 | 加入时间衰减、事件级历史反馈、达人证据元数据、history 摘要拼装 |
| `backend/api/schemas.py` | 扩展字段 | 补齐 `role_time_decay_days`、`role_time_decay_min_factor`、`evolution_snapshot` 等请求契约 |

## 三、前端改造要点

工作台页面 `frontend/client/src/pages/Workspace.tsx` 已进一步增强为“结果可解释”模式。现在用户在执行 Fission 后，不仅能看到哪些 tag 被升权或降权，还能直接看到：**本轮反馈驱动了什么、历史反馈又驱动了什么**。在意图确认弹窗中，也会显示最近一次 Fission 的 tag 变化及对应的证据提示。

与此同时，`frontend/client/src/lib/api.ts` 的类型系统已同步增强，新增了达人证据结构、history 摘要结构，以及 `library/list` / `library/history` 的前端请求封装。这样前端不再依赖 mock 数据，而是可以直接消费真实接口。

资产库页面 `frontend/client/src/pages/Library.tsx` 本轮被改为真实接口驱动版本。页面现在可以调用 `library/list` 获取真实资产库列表，并在点击“查看推荐偏移”后，通过 `library/history` 展示某个品牌 / SPU 的历史推荐摘要、时间线以及证据预览。

| 文件 | 本轮修改 | 说明 |
|---|---|---|
| `frontend/client/src/pages/Workspace.tsx` | 增强 | 展示本轮/历史来源拆分、达人证据回显、提交时透传 evolution snapshot |
| `frontend/client/src/lib/api.ts` | 增强 | 增加达人证据类型、history 结果类型、真实资产库接口封装 |
| `frontend/client/src/pages/Library.tsx` | 重写 | 改为真实调用 `library/list` 与 `library/history`，展示推荐偏移摘要 |

## 四、验证结果

本轮已完成后端回归测试与前端构建验证。

| 验证项 | 命令 | 结果 |
|---|---|---|
| 后端资产服务测试 | `pytest -q tests/test_asset_services.py` | 通过，`12 passed` |
| 前端构建检查 | `pnpm build` | 通过 |

需要说明的是，前端构建中仍出现了既有环境变量提醒，例如 `VITE_ANALYTICS_ENDPOINT` 与 `VITE_ANALYTICS_WEBSITE_ID` 未定义，但这属于现有站点分析脚本配置提醒，不影响本轮功能编译与输出。

## 五、当前可直接感知到的产品变化

从产品使用角度看，这轮最重要的变化是：**用户终于可以看到“系统为什么这么推荐”**。此前用户只能看到 tag 权重从 1.0 变成 1.4 或从 1.0 变成 0.7；现在则可以进一步看到，这个变化是因为当前刚选中的达人，还是因为历史上某批次已经验证过的达人偏好。与此同时，在资产库历史页中，也能看到某次批次推荐为何发生偏移，而不只是看到一条孤立的“入库记录”。

## 六、建议下一步继续做什么

下一步最值得继续推进的是两件事。第一件事，是把 `library/history` 中的达人证据继续做成 **可点击下钻**，支持直接查看某位达人的完整历史时间线。第二件事，是把当前时间衰减从“统一半衰期”继续升级为 **按角色、按品牌阶段、按 campaign 新鲜度** 的更细粒度衰减规则，这会让最终推荐质量更接近你的产品目标。
