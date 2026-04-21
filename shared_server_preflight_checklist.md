# `kol_lens` 共享云服务器部署前核查清单

## 一、目标与原则

你的目标不是“把服务先跑起来”，而是要在**已有很多产品正在运行**的服务器上，新增一套 `kol_lens` 的前后端与依赖环境，并且**不影响现有产品、现有数据库、现有 Nginx 站点和现有缓存服务**。

因此这次部署最重要的原则只有三条：**路径隔离、服务名隔离、数据隔离**。路径隔离是指代码、日志、静态文件都放在独立目录中；服务名隔离是指 `systemd`、Nginx `server_name`、端口都要独立；数据隔离是指 PostgreSQL、Redis、Milvus 不能直接“和别的产品混着用默认配置”。

## 二、先给结论：每一项怎么隔离最安全

| 组件 | 是否可复用现有实例 | 最安全做法 | 当前建议 |
|---|---|---|---|
| 代码目录 | 不复用 | 独立目录 `/home/red/work/kol_lens` | 必须独立 |
| 前端静态文件 | 不复用 | 独立构建目录 `frontend/dist/public` | 必须独立 |
| 后端进程 | 不复用 | 独立 `systemd` 服务名 `kol-lens-backend` | 必须独立 |
| Nginx 站点 | 可共用 Nginx 主程序 | 新增独立 conf 文件 `lens.red-magic.cn.conf` | 必须独立 server block |
| PostgreSQL 实例 | **可复用** | 同一 PostgreSQL 实例下创建**新库 + 新用户** | 推荐复用实例，但必须隔离库和账号 |
| Redis 实例 | **理论可复用，但当前代码不建议直接混用** | 最好独立 Redis 实例或独立端口 | 强烈建议隔离 |
| Milvus | 不建议混现有业务 Collection | 独立 Milvus standalone 或至少独立 Collection 与端口规划 | 推荐独立实例 |
| 域名 | 不复用 | 新域名 `lens.red-magic.cn` | 必须独立 |
| 应用端口 | 不复用 | 后端固定 `127.0.0.1:3007` | 必须先确认未占用 |

## 三、正式部署前的确认顺序

建议你严格按下面顺序做核查，而不是直接开始安装和启动。因为在共享服务器里，**先看现状，再决定是否复用**，比“先装再改”安全得多。

| 顺序 | 核查对象 | 要确认什么 | 目标 |
|---|---|---|---|
| 1 | 目录 | `/home/red/work/kol_lens` 是否不存在或可安全创建 | 避免覆盖旧项目 |
| 2 | 端口 | 3007、5432、6379、19530、80、443 是否已被谁占用 | 避免端口冲突 |
| 3 | Nginx | 是否已有 `lens.red-magic.cn` 相关配置 | 避免域名冲突 |
| 4 | PostgreSQL | 是否已有可复用实例；能否只新增数据库与用户 | 避免误改别的业务库 |
| 5 | Redis | 是否已有共享实例；是否允许新开独立实例或端口 | 避免污染共享缓存 |
| 6 | Milvus | 是否已有 Milvus；是否已被别的业务使用 | 避免共用 Collection 导致数据污染 |
| 7 | systemd | 服务名 `kol-lens-backend` 是否已存在 | 避免覆盖已有服务 |
| 8 | SSL 证书 | `lens.red-magic.cn` 是否可直接复用当前证书 | 避免 HTTPS 不可用 |

## 四、你应该先在服务器上执行的环境核查命令

### 1）目录与代码落位核查

```bash
mkdir -p /home/red/work
ls -la /home/red/work
ls -la /home/red/work/kol_lens
```

如果 `kol_lens` 已存在，要先确认它是不是旧版本项目，而不是直接覆盖。

### 2）端口占用核查

```bash
ss -lntp | egrep ':80|:443|:3007|:5432|:6379|:19530'
```

你需要重点确认三件事：

| 端口 | 用途 | 结论标准 |
|---|---|---|
| 3007 | `kol_lens` 后端 | 没有其他服务占用才可直接使用 |
| 5432 | PostgreSQL | 可被现有 PostgreSQL 占用，这属于正常复用 |
| 6379 | Redis | 若是共享 Redis，需额外判断是否适合复用 |
| 19530 | Milvus | 若已有 Milvus，要先确认是否能共存或需改单独端口 |
| 80 / 443 | Nginx | 正常应由 Nginx 占用 |

### 3）Nginx 站点核查

```bash
sudo nginx -T | grep -n "lens.red-magic.cn"
sudo ls -la /etc/nginx/conf.d/
```

如果已经存在 `lens.red-magic.cn` 配置，不能直接覆盖，必须先比对是不是旧版站点。

### 4）PostgreSQL 实例核查

```bash
sudo systemctl status postgresql
psql -U postgres -lqt
psql -U postgres -c "\du"
```

如果 PostgreSQL 已运行，最安全的做法不是新装第二套数据库，而是**在现有 PostgreSQL 实例里新建一个独立数据库和独立用户**。

建议命名如下：

| 项 | 建议值 |
|---|---|
| 数据库名 | `kol_lens` 或 `sigma_match_lens` |
| 用户名 | `kol_lens_user` |
| 权限 | 仅授权该数据库 |

建议创建方式：

```sql
CREATE USER kol_lens_user WITH PASSWORD '请替换为强密码';
CREATE DATABASE kol_lens OWNER kol_lens_user;
GRANT ALL PRIVILEGES ON DATABASE kol_lens TO kol_lens_user;
```

### 5）Redis 实例核查

```bash
sudo systemctl status redis
redis-cli INFO keyspace
redis-cli INFO server
```

这里要特别注意：**当前 `kol_lens` 代码里的 Redis 默认写法是固定连到 DB 0**，不是通过环境变量灵活切不同 DB。虽然 key 前缀有 `task:`、`search:`、`influencer:`、`ws:`，理论上能降低冲突概率，但如果这是别的产品在共享使用的 Redis，仍然不建议直接共用。

因此，面向“不要影响其他产品”的目标，我建议：

| 方案 | 是否推荐 | 原因 |
|---|---|---|
| 直接共用现有 `6379` 和 DB 0 | 不推荐 | 当前项目没有把 Redis DB index 做成正式隔离参数 |
| 共用 Redis 主程序，但新增独立实例/配置文件/端口 | 推荐 | 能彻底隔离 key 空间、密码和连接 |
| 新开 Docker Redis 容器并映射新端口 | 推荐 | 部署最简单，隔离也最清晰 |

如果你想最稳妥，我建议给 `kol_lens` 单独开一个 Redis 端口，例如 `6387`。

### 6）Milvus 实例核查

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
ss -lntp | grep 19530
```

Milvus 的核心风险不只是端口占用，而是**向量库实例和 Collection 的数据污染**。如果服务器上已经有别的产品在用 Milvus，那么最安全的方式仍然是：

1. 要么新开一套 standalone Milvus；
2. 要么至少确认 `kol_lens` 使用独立 Collection，不碰别人的 Collection；
3. 如果默认 19530 已占用，可改成比如 19531，然后在 `.env.production` 里同步设置 `MILVUS_PORT=19531`。

### 7）systemd 服务名核查

```bash
systemctl list-unit-files | grep kol-lens
systemctl status kol-lens-backend
```

如果已经有同名服务，先不要覆盖。

### 8）证书与域名解析核查

```bash
nslookup lens.red-magic.cn
sudo ls -la /etc/nginx/ssl/red-magic.cn/
```

你要确认两件事：一是 `lens.red-magic.cn` 已正确解析到这台服务器；二是参考证书目录是否真的可复用。

## 五、真正适合你的部署隔离方案

结合你“服务器上有很多其他产品”的前提，我建议你按下面方案落地，而不是偷懒共用默认配置。

### 1. PostgreSQL：复用实例，但绝不复用业务库

PostgreSQL 最适合的做法，是**复用现有 PostgreSQL 服务进程**，但是新建：

- 独立数据库；
- 独立用户名；
- 独立密码；
- 只导入 `kol_lens` 的初始化表结构。

这意味着你不用新装 PostgreSQL，但也不会碰现有产品的数据。

### 2. Redis：优先独立实例或独立端口

因为当前项目并没有把 Redis DB index 做成正式环境变量，因此如果共享 Redis，实际上还是会把数据写到默认 DB。为了避免对其他产品造成影响，**最稳妥是给 `kol_lens` 单独开一个 Redis 实例**。

你可以选择两种方式：

| 方式 | 建议 |
|---|---|
| systemd 新实例 | 适合服务器已经有 Redis 管理体系 |
| Docker 新容器 | 更简单，隔离更清晰 |

建议端口示例：`6387`。

### 3. Milvus：优先独立 standalone

Milvus 如果只是“连接现有一个正在承载别的业务的实例”，你后续会很难判断：某次检索异常，到底是 `kol_lens` 自己的问题，还是共享实例资源被其他产品吃掉了。因此如果服务器资源足够，**优先单独部署一套 standalone Milvus**。

如果必须复用现有 Milvus，也至少要满足：

| 条件 | 必须满足 |
|---|---|
| Collection 独立 | 是 |
| 账号或访问控制清晰 | 最好有 |
| 不会与他人批量写入互相影响 | 是 |
| 端口和资源占用已评估 | 是 |

### 4. Nginx：只新增 conf，不改其他站点

这一点很关键。**不要直接改已有站点文件**，而是新建：

```text
/etc/nginx/conf.d/lens.red-magic.cn.conf
```

只让这个新文件承载 `lens.red-magic.cn`，这样即使配错，影响范围也只在新域名，不会波及其他站点。

## 六、推荐的最终环境变量规划

如果你按“共享 PostgreSQL、独立 Redis、独立 Milvus”来做，建议环境变量如下：

```bash
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=kol_lens
POSTGRES_USER=kol_lens_user
POSTGRES_PASSWORD=请替换

REDIS_HOST=127.0.0.1
REDIS_PORT=6387
REDIS_PASSWORD=请替换

MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

OPENAI_API_KEY=请替换
KOL_LENS_INTENT_MODEL=gpt-4.1-mini
KOL_LENS_EMBEDDING_MODEL=text-embedding-3-small
KOL_LENS_DISABLE_LLM=0

PGY_AUTHORIZATION=
PGY_COOKIE=
PGY_TRACE_ID=
PGY_BRAND_USER_ID=

PGY_COOKIE_HEADER=
PGY_COOKIE_HEADERS=
PGY_COOKIE_FILE=
CREATOR_DATA_VL_MODEL=gpt-4.1-mini
```

如果 Milvus 已占用 `19530`，你就把 `MILVUS_PORT` 改成新端口，例如 `19531`，并确保 Docker 或服务也监听相同端口。

## 七、你现在最应该先做的“确认动作”

如果目标是稳妥推进，我建议你不要立刻开始部署，而是先在服务器上把下面这组检查做完，并把结果整理出来。

| 检查项 | 需要的结果 |
|---|---|
| `3007` 是否空闲 | 确认后端可直接用该端口 |
| PostgreSQL 是否已运行 | 确认可复用实例 |
| 能否新建独立库和用户 | 确认不会碰现有数据库 |
| Redis 是否共享其他业务 | 若是，则改为独立实例/端口 |
| Milvus 是否已存在 | 若已存在，则评估是否独立新开 |
| Nginx 是否已有 `lens.red-magic.cn` | 若无，则可新增 conf |
| SSL 证书目录是否可复用 | 若不可复用，要先申请证书 |

## 八、最适合你的实际落地顺序

在共享服务器场景下，推荐顺序不是“先装服务”，而是：

| 顺序 | 动作 |
|---|---|
| 1 | 核查端口、现有数据库、Redis、Milvus、Nginx 状态 |
| 2 | 决定哪些实例复用、哪些实例隔离 |
| 3 | 先创建 PostgreSQL 独立数据库与用户 |
| 4 | 再准备 Redis 独立实例或容器 |
| 5 | 再准备 Milvus 独立实例或端口 |
| 6 | 再拉代码到 `/home/red/work/kol_lens` |
| 7 | 再配置 `.env.production` |
| 8 | 再启动后端 systemd 服务 |
| 9 | 再构建前端并接入 Nginx |
| 10 | 最后做人工联调 |

## 九、我的直接建议

针对你当前的诉求，我的建议非常明确：

> **PostgreSQL 复用实例但新建独立库和独立账号；Redis 不要直接混共享默认实例，最好单独起一个端口；Milvus 优先单独部署 standalone；Nginx 只新增新域名 conf，不改已有站点。**

这是一条最稳妥、最不容易伤到其他产品的路径。

如果你愿意，我下一步可以继续直接帮你产出三份“可直接拿到服务器上用”的文件：

1. **共享服务器核查命令清单的可执行版**；
2. **适合 `kol_lens` 的 `.env.production` 最终版模板**；
3. **Redis 独立实例 + Milvus standalone 的建议配置文件**。
