# 阿里云数据库采购调研笔记

## 一、项目侧依赖结论

基于 `kol_lens` 当前代码实现，可以确认三项基础设施的依赖程度并不相同。

| 组件 | 代码依赖强度 | 结论 |
| --- | --- | --- |
| PostgreSQL | 很高 | 当前后端直接使用 `psycopg2` 和 `ThreadedConnectionPool`，并使用 `jsonb` 与 `ON CONFLICT` 等 PostgreSQL 特性，等同于默认绑定 PostgreSQL。 |
| Redis | 中等 | 用于任务状态、缓存和会话通道；对完整服务推荐保留，但存在一定降级空间。 |
| Milvus | 很高 | 当前后端直接通过 `pymilvus` 连接，维护三组向量字段和向量索引，是完整向量检索链路的核心组件。 |

## 二、阿里云 RDS PostgreSQL 官方计费信息

来源：
- <https://help.aliyun.com/zh/rds/product-overview/billing-overview>
- <https://help.aliyun.com/zh/rds/apsaradb-rds-for-postgresql/billing-1/>

官方文档确认：

| 项目 | 结论 |
| --- | --- |
| 计费方式 | 支持包年包月、按量付费；文档页列出 Serverless 选项，但当前说明中明确“仅 RDS MySQL 实例可将按量付费变更为 Serverless”，因此 PostgreSQL 采购时应优先按普通实例理解。 |
| 计费组成 | 由计算资源费用和存储资源费用组成。 |
| 长期场景 | 包年包月更适合长期稳定使用。 |
| 价格查询方式 | 官方建议在购买页面或价格计算器中，根据地域、规格、存储空间等参数查看实时价格。 |
| 附加成本 | 可能存在备份、SQL 审计、代理等增值费用。 |

另外，搜索结果中的阿里云官方产品页摘要显示：RDS PostgreSQL 页面当前存在“新人特惠年付 3 折起”与“起步价”营销信息，但产品页浏览时遇到验证码拦截，因此最终采购仍应以实际购买页实时价格为准。

## 三、阿里云 Redis（Tair / 兼容 Redis）官方计费信息

来源：
- <https://help.aliyun.com/zh/redis/product-overview/billing-methods>
- 用户提供的 Redis 产品文档入口：<https://help.aliyun.com/zh/redis/getting-started/overview>

官方文档确认：

| 项目 | 结论 |
| --- | --- |
| 计费方式 | 支持按量付费、按量付费+资源包、包年包月。 |
| 计费粒度 | 按量付费按小时结算，不足 1 小时按 1 小时收费。 |
| 收费口径 | 按“开通的实例容量规格”计费，而不是按实际已使用缓存容量计费。 |
| 长期场景 | 长期稳定使用建议包年包月，临时试运行可先按量。 |
| 成本优化 | 按量实例可配合资源包。 |

搜索结果中的阿里云官方产品页摘要显示，Tair 产品页当前强调可提供 Redis 开源版与 Tair 企业版免费试用，而某些活动页出现了“低至 554.26 元/年”等营销价，但这些属于活动页展示，不适合作为最终标准报价，只能作为预算下限参考。

## 四、阿里云托管 Milvus 官方计费信息

来源：
- <https://help.aliyun.com/zh/milvus/product-overview/what-is-the-vector-retrieval-milvus-version>
- <https://help.aliyun.com/zh/milvus/product-overview/comparison-between-alibaba-cloud-milvus-and-ecs-self-built-milvus>
- <https://help.aliyun.com/zh/milvus/user-guide/network-access-and-security-settings>
- <https://help.aliyun.com/zh/milvus/product-overview/billing-item>

官方文档确认：

| 项目 | 结论 |
| --- | --- |
| 产品定位 | 阿里云 Milvus 是全托管、兼容开源 Milvus 的向量检索服务。 |
| 自建对比 | 官方明确写明无需自担 Kafka、etcd 等组件资源成本，运维与高可用成本明显低于 ECS 自建。 |
| 网络方式 | 支持 VPC 内网访问和公网访问；Proxy 端口仍为 19530。 |
| 计费组成 | 费用由 CU 与存储两部分组成。 |
| 华北2（北京）CU 单价 | 服务节点 157 元/CU/月；计算节点性能型 157 元/CU/月；计算节点容量型 211 元/CU/月。 |
| 存储示例 | 文档示例给出杭州地域 100GB 存储约 18 元/月。 |

搜索结果中的阿里云官方产品页摘要还显示，Milvus 页面存在“59 元 / 6 月”的节省计划展示，但这是节省计划优惠信息，并不等于完整实例的月度总成本。

## 五、当前采购判断的关键前提

结合前面服务器盘点，当前 ECS 为北京地域、4 vCPU / 8 GiB，且是共享服务器场景。因此真正影响采购方案的不是磁盘，而是“是否继续把状态型基础设施放在本机”。

| 组件 | 当前是否更适合托管购买 |
| --- | --- |
| PostgreSQL | 如果希望降低运维风险、避免本机安装和备份维护，适合购买 RDS PostgreSQL。 |
| Redis | 如果希望缓存、任务状态更稳定，也适合购买托管 Redis；但预算紧时可以先本机部署或短期降级。 |
| Milvus | 在当前共享 ECS 上最适合购买托管版，因为本机 Milvus 对内存压力最大。 |

## 六、Milvus 进一步选型与价格补充

来源：
- <https://help.aliyun.com/zh/milvus/product-overview/compute-node-specifications>
- <https://help.aliyun.com/zh/milvus/user-guide/milvus-resource-estimation-and-configuration-recommendations>
- <https://help.aliyun.com/zh/milvus/getting-started/>
- <https://developer.aliyun.com/article/1715462>

新增关键结论：

| 项目 | 结论 |
| --- | --- |
| 1 CU 定义 | Milvus 计费文档说明 1 CU = 1 个 CPU 核 + 4 GiB 内存。 |
| 计算节点类型 | 性能型适合高 QPS、低延迟；容量型适合大数据量但对延迟要求较低。 |
| 节点数量 | 官方文档说明计算节点可选 1~50，且对生产环境建议不少于 2 个节点。 |
| 单机版定位 | 官方快速创建文档明确：单机版仅建议开发学习、功能验证或初期测试，不建议用于生产环境。 |
| 标准版定位 | 官方快速创建文档明确：标准版面向生产环境、大规模数据和更高 SLA。 |
| 单机版最低规格与价格 | 阿里云开发者社区官方文章显示：Milvus 单机版 4CU 起配，月付 628 元起，首年低至 3768 元起，并给出 4CU 约支持 900 万条中低维向量（如 768 维）的参考值。 |

## 七、RDS PostgreSQL 与 Redis 价格信息的可用性说明

此次调研中，阿里云产品营销页（`aliyun.com` 域名）在浏览器访问时多次触发验证码拦截，因此未能稳定进入购买页读取实时选配价格。当前可直接确认的价格来源主要包括：

| 产品 | 已确认价格信息 |
| --- | --- |
| RDS PostgreSQL | 搜索结果中的阿里云官方产品页摘要显示存在“新人特惠年付 3 折起”和年付起步价信息，但由于产品页验证码拦截，不能将其当作严格报价，只能视为营销价线索。 |
| Redis（Tair） | 搜索结果中的阿里云官方活动页摘要显示存在“低至 554.26 元/年”等活动价线索；同样由于营销页验证码拦截，只能作为预算下限参考，实际价格应以购买页为准。 |
| Milvus | 官方文档已给出明确 CU 单价；官方开发者社区文章还给出 4CU 单机版月付 628 元起，可作为当前最可执行的预算依据。 |

因此，后续给用户的采购建议应采用“官方文档确定的计费结构 + 官方可读取页面中的已知起步价 + 明确标注实际下单以购买页为准”的写法，避免伪精确报价。
