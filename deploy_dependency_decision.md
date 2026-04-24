# `kol_lens` 部署依赖取舍说明

## 结论先说

你问的三个问题，可以直接归纳成下面这张表。

| 组件 | 能否先替代/省略 | 当前建议 | 原因 |
| --- | --- | --- | --- |
| PostgreSQL | **不建议换成 SQLite** | 测试环境也尽量保留 PostgreSQL | 当前后端数据库层已经直接写死为 `psycopg2 + ThreadedConnectionPool`，不是抽象 ORM 层，现状并不兼容 SQLite |
| Redis | **可以临时不启** | 手动测试早期可先跳过，联调稳定后再补上 | 当前部分服务已经提供内存降级路径，但缓存、任务状态与多进程一致性会变差 |
| Milvus | **不建议省略** | 要测真实检索与 Fission，就必须部署 | 当前首轮向量匹配、下一批推荐、Rocchio 进化都依赖向量库 |

> 如果你的目标是“尽快把页面跑起来并做最浅层人工联调”，最小可行组合可以是：**PostgreSQL + Milvus + 后端 + 前端**，Redis 暂时先不启。如果你的目标是“按当前产品真实链路完整手测”，推荐组合仍然是：**PostgreSQL + Redis + Milvus + 后端 + 前端**。

---

## 一、PostgreSQL 可不可以先换成 SQLite？

我的判断是：**当前这版代码不适合直接换成 SQLite**。

原因不是概念上不能用，而是**你当前仓库代码已经明确按 PostgreSQL 写死了连接与游标层**。数据库封装直接依赖 `psycopg2`、`psycopg2.extras.RealDictCursor` 和 `ThreadedConnectionPool`，配置层也明确生成的是 PostgreSQL DSN，这意味着它不是一个“换个连接串就能跑”的状态，而是一个**需要改数据库访问层实现**的状态。

| 代码位置 | 现状 | 对 SQLite 的影响 |
| --- | --- | --- |
| `backend/db/__init__.py` | 直接 `import psycopg2`，并使用连接池 | SQLite 不支持这一套连接方式 |
| `backend/config/__init__.py` | 生成 `postgresql://...` 与 `postgresql+asyncpg://...` DSN | 现有配置模型就是 PostgreSQL 定向 |
| `backend/db/migrations/init.sql` | 初始化脚本按 PostgreSQL 思路组织 | 需要逐条检查兼容性 |

所以如果你问的是：

> “我现在为了尽快部署手测，能不能不装 PostgreSQL，直接拿 SQLite 顶一下？”

我的建议是：**不要这么做**。因为这不是“低风险替换”，而是会把数据库层再改一轮，反而比直接装 PostgreSQL 更慢。

### 最实际的建议

如果服务器资源允许，**直接安装 PostgreSQL** 是最省事的。当前项目的资产库、历史、模板、履约记录、达人时间线等数据都依赖这层关系型存储，继续沿用 PostgreSQL 成本最低。

---

## 二、Redis 能不能也先不用？

这里和 PostgreSQL 不一样。**Redis 当前可以临时不启，但属于“测试期可接受降级”，不是正式推荐方案。**

原因是当前匹配服务里已经明确写了降级逻辑：当 Redis 基础设施未就绪时，允许退化到**进程内内存缓存**。这说明单机、单进程、短时手测时，确实可以先不装 Redis。

| 场景 | 不启 Redis 是否可行 | 影响 |
| --- | --- | --- |
| 单机手工点页面 | 可以 | 结果缓存与任务状态只存在当前进程内 |
| 重启服务后继续追历史状态 | 不理想 | 内存缓存会丢失 |
| 多进程 / 多实例部署 | 不建议 | 各实例状态不一致 |
| 要观察较稳定的任务日志与缓存行为 | 不建议 | 无法获得真实缓存表现 |

### 什么时候可以先跳过 Redis

如果你现在只是想做这些验证：

1. 页面是否能打开；

1. 后端 API 是否能通；

1. 首轮检索是否能返回；

1. Fission 能否跑通基本结果；

那么 Redis 可以先不启。

### 什么时候最好补上 Redis

如果你准备开始验证这些能力，就建议补上 Redis：

1. 任务状态稳定性；

1. 搜索缓存命中；

1. 更接近真实部署的服务行为；

1. 未来的多进程 systemd / gunicorn / 多实例扩展。

---

## 三、Milvus 必须吗？

**如果你要测真实的向量匹配、下一批推荐和 Rocchio 进化，Milvus 基本是必须的。**

当前项目里，Milvus 不是一个可有可无的附加件，而是核心检索基础设施。代码已经直接使用 `pymilvus`、`connections.connect()`、`Collection()` 等接口管理向量集合，配置中默认集合名为 **`influencer_multimodal_vectors`**。Milvus 官方也提供了最常见的单机部署方式，即使用 Docker / Docker Compose 运行 standalone 实例。[1] [2]

### 当前项目对 Milvus 的最小配置要求

| 项 | 建议值 |
| --- | --- |
| 部署模式 | Standalone |
| 地址 | `127.0.0.1` |
| 端口 | `19530` |
| 环境变量 | `MILVUS_HOST=127.0.0.1`、`MILVUS_PORT=19530` |
| Collection 名称 | `influencer_multimodal_vectors` |

### 最简单的配置思路

最省事的方式，是直接在服务器上用 **Docker Compose 启一个 standalone Milvus**。官方文档推荐使用 Docker / Docker Compose 方式启动单机实例，同时要求 Docker 运行环境至少具备基本 CPU 和内存资源。[1] [2] [3]

你可以把下面这份文件保存为：

```
/home/red/work/milvus/docker-compose.yml
```

参考配置如下。

```yaml
version: '3.5'

services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - ./volumes/etcd:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    container_name: milvus-minio
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9001:9001"
    volumes:
      - ./volumes/minio:/minio_data
    command: minio server /minio_data --console-address ":9001"

  standalone:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.4.4
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - ./volumes/milvus:/var/lib/milvus
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
      - minio
```

然后执行：

```bash
mkdir -p /home/red/work/milvus
cd /home/red/work/milvus
docker compose up -d
```

### 后端如何接上 Milvus

在后端环境变量里加上：

```bash
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
```

然后重启后端服务即可 。当前代码会在真正发生检索或写入时连接 Milvus，并在需要时创建 / 获取 Collection。

### 如何验证 Milvus 是否通了

建议按下面顺序验。

| 检查项 | 命令 |
| --- | --- |
| 容器是否在运行 | `docker ps |
| 端口是否监听 | `ss -lntp |
| 后端是否能连上 | 看后端日志中是否出现 Milvus 连接成功 |
| 业务是否真的用了 Milvus | 发起一次首轮检索或下一批推荐请求 |

---

## 四、给你的最小可行部署建议

如果你现在的目标是**尽快上线测试环境、马上开始手工联调**，我建议这样取舍。

| 方案 | 组件组合 | 是否推荐 |
| --- | --- | --- |
| 最省事可手测版 | PostgreSQL + Milvus + 后端 + 前端 | **推荐** |
| 再稳一点的测试版 | PostgreSQL + Redis + Milvus + 后端 + 前端 | **最推荐** |
| SQLite 替代 PostgreSQL 版 | SQLite + 其他组件 | **不推荐** |
| 不上 Milvus 版 | PostgreSQL + Redis + 后端 + 前端 | **不推荐** |

### 我给你的直接结论

1. **PostgreSQL 不建议换 SQLite**，因为当前代码不是可平滑切换数据库引擎的状态。

1. **Redis 可以先不启**，但只适合单机短时手测。

1. **Milvus 建议必须配上**，最简单就是 Docker Compose 跑 standalone，然后后端通过 `MILVUS_HOST` / `MILVUS_PORT` 连接。

如果你愿意，我下一步可以继续直接给你两份可以落服务器的文件：

1. 一份 **Milvus 的完整 ****`docker-compose.yml`**** 正式版**；

1. 一份 **`/home/red/work/kol_lens/backend/.env.production`**** 可直接填写的模板**。

## References

[1]: https://milvus.io/docs/install_standalone-docker.md "Run Milvus in Docker (Linux ) - Milvus"

[2]: https://milvus.io/docs/install_standalone-docker-compose.md "Run Milvus with Docker Compose (Linux ) - Milvus"

[3]: https://milvus.io/docs/prerequisite-docker.md "Requirements for Installing Milvus Standalone - Milvus"

