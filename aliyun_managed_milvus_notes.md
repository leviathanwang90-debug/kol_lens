# 阿里云向量检索服务 Milvus 版调研笔记

## 1. 产品概览页已确认的信息

来源：<https://help.aliyun.com/zh/milvus/product-overview/what-is-the-vector-retrieval-milvus-version>

页面明确说明：

- 向量检索服务 Milvus 版是**全托管向量检索引擎**；
- 与开源 Milvus **完全兼容**，支持无缝迁移；
- 典型场景包括**多模态搜索、RAG、搜索推荐、内容风险识别**；
- 提供**高可用、弹性扩缩容、监控告警、VPC 专有网络访问、安全控制**；
- 提供 Attu 等生态兼容能力。

这些信息说明：从产品定位上看，它适合替代本机自建的 Milvus standalone，尤其适合“服务器资源紧张但又需要完整向量检索能力”的场景。

## 2. 比较页访问情况

尝试访问一条英文猜测路径的“Milvus 与 ECS 自建 Milvus 对比”页面时返回 404，说明不能依赖猜测 URL，需要改用目录页中可见的文档标题进行进一步检索或页面内跳转。

## 3. 官方对比页确认的信息

来源：<https://help.aliyun.com/zh/milvus/product-overview/comparison-between-alibaba-cloud-milvus-and-ecs-self-built-milvus>

官方对比页给出的核心结论包括：

- 托管 Milvus **无需额外自行承担 Kafka、etcd 等组件资源成本**；
- 支持**弹性伸缩**、一键升级、丰富监控告警；
- 提供 **99.9% 服务可靠性**；
- 支持 VPC、安全访问控制、数据加密、RAM / RBAC 等能力；
- 对比 ECS 自建方案，自建需要自行购买并维护更多基础组件与运维体系，人力和风险成本更高。

这对当前 `kol_lens` 很关键，因为我们现在最大的瓶颈不是磁盘，而是共享 ECS 的**内存余量不足以安全承载本地 Milvus standalone**。官方对比页实际上强化了一个结论：如果业务方希望减少自建运维和本机资源占用，托管 Milvus 是更合适的方向。

## 4. 网络访问与接入方式

来源：<https://help.aliyun.com/zh/milvus/user-guide/network-access-and-security-settings>

官方文档确认：

- 托管 Milvus 支持 **阿里云 VPC 内网访问** 和 **公网访问**；
- 默认开启的是 **VPC 内网访问**；
- 创建实例时系统会自动在所选 VPC 内构建终端节点；
- 若开启公网访问，则需要设置公网访问白名单；
- Proxy 访问端口仍为 **19530**，Attu 为 **3000**；
- 内网域名格式为 `{{clusterId}}-internal.milvus.aliyuncs.com:19530`。

这说明：**如果当前 ECS 与阿里云托管 Milvus 放在同地域、可互通 VPC 内，那么 `kol_lens` 后端几乎可以按“连一个远端 Milvus 地址”的方式接入，不需要保留本机 Milvus 容器。**
