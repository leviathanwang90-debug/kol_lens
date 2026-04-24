# 测试阶段的向量库存储与向量匹配方式说明

**作者：Manus AI**  
**日期：2026-04-21**

我已经核对了你之前上传项目里的测试代码。结论是：**测试阶段的主方案不是把向量存在 PostgreSQL 或 Redis 里，而是使用 `Milvus 2.4 Standalone` 作为真正的向量数据库；向量匹配也主要是通过 `pymilvus` 调用 Milvus 的向量检索接口来完成。**[1] [2] [3]

| 维度 | 实际方式 | 代码依据 |
| --- | --- | --- |
| 向量库存储位置 | **Milvus Collection** | `test_infrastructure.py` 中直接调用 `milvus_mgr.create_collection()`、`milvus_mgr.insert(test_data)`。[1] |
| 测试环境部署形态 | **Docker Compose 启动的 Milvus Standalone**，并依赖 **etcd** 做元数据存储、**MinIO** 做对象存储 | `docker-compose.yml` 中定义了 `etcd`、`minio`、`milvus` 三个服务，Milvus 命令为 `milvus run standalone`。[2] |
| 向量字段 | `v_face`、`v_scene`、`v_overall_style` | `milvus/__init__.py` 的 Collection Schema 定义了三组 `FLOAT_VECTOR` 字段。[3] |
| 向量维度 | 人脸 `512` 维，场景 `768` 维，综合风格 `768` 维 | `config/__init__.py` 与 `milvus/__init__.py` 中有明确常量定义。[3] |
| 检索方式 | **Milvus `search` 检索 + 标量过滤** | `hybrid_search()` 内部调用 `col.search(...)`，并拼接 `region`、`gender`、`followers_min/max` 等过滤条件。[3] |
| 相似度度量 | 默认是 **COSINE** | `DEFAULT_METRIC = "COSINE"`，索引和检索参数默认都走该度量。[3] |
| 测试阶段索引类型 | **IVF_FLAT**，`nlist=128` | `_create_indexes()` 中明确写了开发阶段使用 `IVF_FLAT`。[3] |

## 一、测试是怎么“存”向量的

基础设施测试 `test_infrastructure.py` 会先连接 Milvus，然后创建 Collection，再构造 50 条测试数据写入进去。每条数据都包含一个主键 `id`、一些标量字段（如 `followers`、`region`、`gender`、`ad_ratio`），以及三组向量字段：`v_face`、`v_scene`、`v_overall_style`。[1]

> 测试数据不是临时存在 Python 内存列表后直接做暴力比对，而是**先插入 Milvus Collection**，再由 Milvus 执行检索。[1]

对应的底层部署不是单独一个 Milvus 容器。`docker-compose.yml` 很明确地把测试/开发环境的向量库基础设施定义为：**Milvus Standalone + etcd + MinIO**。其中，etcd 负责 Milvus 元数据，MinIO 负责对象存储，Milvus 自己暴露 `19530` 端口提供向量数据库服务。[2]

## 二、测试是怎么“做向量匹配”的

真正执行匹配的代码在 `milvus/__init__.py` 里。`hybrid_search()` 会根据指定的向量字段，例如 `v_overall_style`、`v_scene` 或 `v_face`，把查询向量传给 Milvus 的 `col.search(...)` 接口，同时叠加标量过滤条件，然后取回 Top-K 结果。[3]

测试代码里实际覆盖了几种典型场景：

| 测试场景 | 用法 |
| --- | --- |
| 综合风格检索 | `vector_field="v_overall_style"` |
| 带过滤的综合风格检索 | 在 `region="上海"`、`gender="女"` 的条件下做检索 |
| 场景向量检索 | `vector_field="v_scene"`，并加粉丝数区间过滤 |
| 人脸向量检索 | `vector_field="v_face"` |

也就是说，**测试阶段的向量匹配本质上是“Milvus ANN 检索 + 标量过滤”**，而不是在 PostgreSQL 里自己写 SQL 算距离，也不是 Redis 相似度检索。[1] [3]

## 三、测试里有没有“非 Milvus”的备用方案

有，但那是**回退方案**，不是主方案。

`match_service.py` 里写了一个 `_retrieve_from_db_only()`，如果 Milvus 检索失败，它会退回到 PostgreSQL 取出候选达人，然后把达人资料文本转成向量，再用 `NumPy` 做 `np.dot(...)` 点积打分。[4] 这说明项目在设计上留了一个“没有 Milvus 时也能凑合跑”的备选路径，但从测试文件本身看，**基础设施测试真正验证的是 Milvus 方案**。[1] [4]

另外，`test_match_services.py` 里的部分单元测试并不会真的连 Milvus，而是直接 `mock.patch("services.match_service.milvus_mgr")`，只验证业务流程是否调用了 Milvus 接口。[5] 所以你可以把测试分成两类理解：

| 测试类型 | 是否真实使用 Milvus |
| --- | --- |
| `test_infrastructure.py` | **是**，真实连 Milvus、建 Collection、插入向量并检索 |
| `test_match_services.py` | **否**，这里主要是 mock Milvus，验证调用链路 |

## 四、一句话结论

> **你之前那份压缩包里的测试，主方案是把向量存在 Milvus 2.4 Standalone 里，通过 `pymilvus` 调用 Milvus 的 `search` 做基于 COSINE 的 IVF_FLAT 向量检索，并可叠加地区、性别、粉丝数等标量过滤。**

如果你愿意，我下一步可以继续帮你把这个答案再往前推进一层，直接告诉你：**现在这套测试里的 Milvus 用法，在正式环境里应该如何迁移到阿里云托管 Milvus。**

## References

[1]: /home/ubuntu/work/kol_lens/backend/tests/test_infrastructure.py "基础设施测试中的 Milvus Collection 与混合检索"
[2]: /home/ubuntu/work/kol_lens/backend/docker-compose.yml "测试/开发环境中的 Milvus、etcd 与 MinIO 编排"
[3]: /home/ubuntu/work/kol_lens/backend/milvus/__init__.py "Milvus Collection、索引与 hybrid_search 实现"
[4]: /home/ubuntu/work/kol_lens/backend/services/match_service.py "Milvus 失败时的 PostgreSQL + NumPy 回退检索逻辑"
[5]: /home/ubuntu/work/kol_lens/backend/tests/test_match_services.py "匹配服务测试中对 Milvus 的 mock 调用"
