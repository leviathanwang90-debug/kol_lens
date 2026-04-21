# `kol_lens` 本地服务器部署前配置检查清单

**作者：Manus AI**  
**日期：2026-04-21**

如果你准备先把 `kol_lens` 部署到一台本地服务器，无论这台机器是办公室服务器、家用主机，还是一台临时 Linux 主机，最重要的不是先跑命令，而是先确认这台机器是否满足 **完整链路运行条件**。结合当前项目代码与已有部署方案，`kol_lens` 的完整服务至少涉及 **前端静态站点、Python 后端、PostgreSQL、Redis、Milvus**，其中 Milvus 还依赖 `etcd + MinIO`。[1] [2]

因此，本地部署前建议按“**资源 → 运行时 → 基础服务 → 网络与反向代理 → 环境变量 → 数据持久化与安全**”的顺序检查。这样做的好处是，你可以尽早判断这台机器究竟适合“全量本地部署”，还是更适合“本地先跑 Web + PostgreSQL + Redis，把 Milvus 放远端”。

## 一、先看这台机器能不能承载完整服务

本地部署时，第一步不是软件安装，而是判断资源够不够。因为对 `kol_lens` 来说，真正容易成为瓶颈的不是 Nginx 或前端，而是 **Milvus**。

| 检查项 | 建议标准 | 为什么要看 |
| --- | --- | --- |
| CPU | **至少 4 核，建议 8 核** | Milvus、PostgreSQL 与后端并发会持续占用 CPU。 |
| 内存 | **至少 16GB，建议 32GB** | Milvus Standalone 官方最低要求已到 8GB，推荐 16GB；而你的完整链路还要再叠加 PostgreSQL、Redis 和后端。[3] |
| 磁盘 | **至少 100GB SSD，建议 200GB** | 数据库、向量数据、日志和镜像都会持续占空间。 |
| 磁盘类型 | **SSD / NVMe** | 向量检索、数据库写入、MinIO 对随机读写更敏感。 |
| Swap | **建议配置 4GB~8GB 兜底** | 防止偶发内存峰值直接把进程打死，但不能替代真实内存。 |

如果这台本地服务器只有 **4C8G**，那它更适合作为“开发验证机”而不是“完整产品承载机”。这种规格下，前端、后端、PostgreSQL、Redis 通常还能跑，但再叠加 Milvus 就会比较吃紧。[3]

## 二、检查操作系统和运行时环境

项目当前更适合 Linux 服务器环境。结合你已有环境和现有文档，优先推荐 **Ubuntu 22.04 LTS**、**Alibaba Cloud Linux 3**、**Rocky Linux 9** 或 **CentOS Stream 9** 这类仍在维护周期内的系统。新机器不建议再选 CentOS 7 这一代已经停更的系统。

| 检查项 | 建议值 | 说明 |
| --- | --- | --- |
| 操作系统 | Ubuntu 22.04 / Rocky 9 / CentOS Stream 9 / Alibaba Cloud Linux 3 | 选维护中的发行版，避免后续包依赖问题。 |
| Python | **3.11 优先** | 当前项目部署路线按 Python 3.10+ / 3.11 更稳。 |
| Node.js | **20.x LTS** | 用于前端构建。 |
| pnpm | 已安装且可用 | 当前前端构建依赖 pnpm。 |
| Docker / Podman | 二选一，但要确认可正常编排 Milvus 依赖 | Milvus、etcd、MinIO 更适合走容器化。 |

你至少需要确认下面几件事：

1. `python3.11 --version` 能正常返回；
2. `node -v` 与 `pnpm -v` 可用；
3. 如果准备本地拉起 Milvus，则 `docker compose` 或等价容器编排方案必须可用；
4. `systemctl` 正常，便于后端和数据库做系统服务托管。

## 三、确认 PostgreSQL、Redis、Milvus 是否都准备本地部署

根据代码配置，后端默认直接读取如下环境变量：`POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`MILVUS_HOST`、`MILVUS_PORT`。[1] 这意味着部署前，你必须先决定这三类依赖的落位方式。

| 组件 | 本地部署前要确认什么 | 项目中的角色 |
| --- | --- | --- |
| PostgreSQL | 是否本机安装；端口 `5432` 是否空闲；数据库名、用户、密码如何规划 | 主业务数据层 |
| Redis | 是否本机安装；端口 `6379` 是否空闲；是否设置密码 | 缓存 / broker / 状态存储 |
| Milvus | 是否本机部署；端口 `19530` 是否空闲；是否连同 `etcd + MinIO` 一起部署 | 向量存储与检索主链路 |

这里有一个关键判断：**如果本地机器资源不够，不要强行三者都本地化。** 你可以先采用下面这条更稳的组合：

| 情况 | 推荐做法 |
| --- | --- |
| 本地机器 ≥ 4C16G，且你想尽量完整验证 | PostgreSQL + Redis + Milvus 都可尝试本地部署 |
| 本地机器只有 4C8G 或长期共享给其他服务 | PostgreSQL + Redis 本地，Milvus 远端 |
| 只是前后端联调验证 | PostgreSQL 本地，Redis 可本地，Milvus 先用远端或跳过相关链路 |

## 四、核查端口、域名和反向代理

本地服务器部署时，经常不是程序不能跑，而是端口、域名或 HTTPS 没想清楚。建议你先统一端口规划，再开始安装。

| 服务 | 推荐监听位置 | 端口 | 是否直接暴露公网 |
| --- | --- | --- | --- |
| Nginx | `0.0.0.0` | `80/443` | 是 |
| 后端 Uvicorn / Gunicorn | `127.0.0.1` | `3007` | **否** |
| PostgreSQL | `127.0.0.1` 或内网 IP | `5432` | **否** |
| Redis | `127.0.0.1` | `6379` | **否** |
| Milvus | `127.0.0.1` 或内网 IP | `19530` | **否** |
| MinIO Console | `127.0.0.1` | `9001` | **否** |

如果你准备通过域名访问前端页面，应提前确认：

1. 域名是否能解析到本地服务器公网 IP；
2. 80 / 443 是否可开放；
3. 证书申请方式是否确定，例如 Let’s Encrypt；
4. 后端是否通过 Nginx 反向代理到 `127.0.0.1:3007`。

## 五、检查环境变量是否和代码一致

这是最容易忽略、但最容易导致“服务启动了却连不上依赖”的部分。根据当前代码，建议你至少准备一份生产环境变量文件，确保下面这些值全部明确。[1]

| 变量 | 是否必须 | 建议检查内容 |
| --- | --- | --- |
| `POSTGRES_HOST` | 是 | 本地部署时通常填 `127.0.0.1` 或 `localhost` |
| `POSTGRES_PORT` | 是 | 默认 `5432` |
| `POSTGRES_DB` | 是 | 建议单独库名，例如 `sigma_match` |
| `POSTGRES_USER` | 是 | 不要直接用超级管理员做业务账号 |
| `POSTGRES_PASSWORD` | 是 | 必须改掉默认弱口令 |
| `REDIS_HOST` | 是 | 本地一般填 `127.0.0.1` |
| `REDIS_PORT` | 是 | 默认 `6379` |
| `REDIS_PASSWORD` | 是 | 必须设置，避免裸奔 |
| `MILVUS_HOST` | 完整向量链路必填 | 本地部署填 `127.0.0.1`，远端部署则填实际地址 |
| `MILVUS_PORT` | 完整向量链路必填 | 默认 `19530` |

如果你只是先做“半完整部署”，那么最重要的是先把 **是否启用 Milvus 主链路** 这件事想清楚。因为业务测试代码里虽然留有 PostgreSQL + NumPy 的简化回退路径，但主向量检索链路仍然是 Milvus。[4]

## 六、检查数据目录、备份和持久化

本地部署不是只看“能启动”，还要看重启和断电之后数据是否还在。`docker-compose.yml` 已经明确把 PostgreSQL、Redis、etcd、MinIO、Milvus 分别挂了持久化卷。[2] 如果你改用本机目录部署，同样要把这些数据目录单独规划出来。

| 数据 | 建议目录 | 备注 |
| --- | --- | --- |
| PostgreSQL 数据 | `/data/postgresql` | 单独磁盘或单独目录更稳 |
| Redis 数据 | `/data/redis` | 需要 AOF / RDB 持久化 |
| Milvus 数据 | `/data/milvus` | 向量数据体积增长会比较快 |
| MinIO 数据 | `/data/minio` | Milvus 对象存储依赖 |
| 项目代码 | `/srv/kol_lens` 或 `/opt/kol_lens` | 不建议混放在临时目录 |
| 日志 | `/var/log/kol_lens` | 方便排障和轮转 |

同时建议你在部署前就确认：

1. 系统盘是否足够；
2. 数据目录是否可写；
3. 是否需要单独数据盘；
4. 是否有最小备份策略，例如每日数据库备份和配置文件备份。

## 七、检查安全与隔离策略

如果这台本地服务器不仅仅给 `kol_lens` 使用，而是共享给其他产品，那么部署前必须先想好隔离边界。否则最容易出现的问题不是装不上，而是把旧业务带崩。

| 检查项 | 推荐做法 |
| --- | --- |
| Linux 用户 | 为项目单独建运行用户，不要所有服务都用 `root` |
| 防火墙 | 只开放 `22`、`80`、`443`，其余内网或本机访问 |
| Nginx 站点 | 为 `kol_lens` 单独建站点配置，不要覆盖现有站点 |
| 数据库账号 | 为项目单独建库、单独建用户 |
| Redis | 必须设置密码，最好只监听本机 |
| Milvus / MinIO | 非必要不要直接对公网开放 |

## 八、建议你实际按这个顺序检查

如果你想提高效率，我建议你按照下面这条顺序做，而不是一上来就安装一堆包。

| 顺序 | 先检查什么 | 检查目标 |
| --- | --- | --- |
| 1 | CPU / 内存 / 磁盘 / Swap | 判断能否完整本地化 |
| 2 | 操作系统、Python 3.11、Node、pnpm | 判断运行时是否齐全 |
| 3 | `5432` / `6379` / `19530` / `3007` / `80` / `443` | 判断端口是否冲突 |
| 4 | PostgreSQL、Redis 落位方式 | 决定先装系统服务还是容器 |
| 5 | Milvus 是否本地部署 | 决定是否需要 `etcd + MinIO + Docker Compose` |
| 6 | 域名、Nginx、证书 | 决定外部访问方式 |
| 7 | 环境变量文件 | 保证代码连接参数一致 |
| 8 | 数据目录与备份 | 保证不是一次性试跑 |

## 九、最简单的判断结论

> **如果你的本地服务器达到 4C16G，并且是独占或基本独占环境，那么可以尝试把 `kol_lens` 的完整链路都放本地。**
>
> **如果你的本地服务器只有 4C8G，或者还要和其他业务共享，那就优先检查 PostgreSQL、Redis、Python、Node、Nginx，Milvus 建议先远端化。**

如果你愿意，下一步我可以继续直接给你两种内容中的任意一种：一份是 **“本地服务器一键盘点命令清单”**，另一份是 **“检查通过后的完整部署顺序”**。

## References

[1]: /home/ubuntu/work/kol_lens/backend/config/__init__.py "后端环境变量配置定义"
[2]: /home/ubuntu/work/kol_lens/backend/docker-compose.yml "PostgreSQL、Redis、Milvus、etcd、MinIO 编排配置"
[3]: https://milvus.io/docs/prerequisite-docker.md "Requirements for Installing Milvus Standalone | Milvus Documentation"
[4]: /home/ubuntu/work/kol_lens/test_vector_storage_and_matching_summary.md "测试阶段向量库存储与匹配方式总结"
