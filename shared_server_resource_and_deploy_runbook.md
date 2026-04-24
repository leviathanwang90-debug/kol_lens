# `kol_lens` 共享服务器资源盘点与完整部署流程

## 一、当前已知服务器状态

根据你已经贴出来的服务器信息，当前可以确认的事实如下。

| 项目 | 当前状态 | 结论 |
|---|---|---|
| 操作系统 | `CentOS Stream 9` | 属于 **RHEL 9 家族**，适合按 `dnf` / `systemd` 路线部署 PostgreSQL、Redis 等服务 |
| `80/443` 端口 | 已监听 | Nginx 正常运行，属于共享服务器已有入口层 |
| `3007` 端口 | 空闲 | 可作为 `kol_lens` 后端监听端口 |
| `5432` 端口 | 空闲 | 当前 PostgreSQL 完全未安装，可安全本机安装 |
| `6379` 端口 | 空闲 | Redis 可独立安装，不会与现有实例冲突 |
| `19530` 端口 | 空闲 | Milvus 可独立部署 |
| Nginx 站点 | 尚无 `lens.red-magic.cn` 配置 | 可以新增独立 conf，不会覆盖现有站点 |

这些信息说明：**从端口与服务冲突层面看，当前服务器是适合新增一套 `kol_lens` 依赖栈的。** 但如果要进一步确认“是否不会影响其他产品”，还缺一类关键信息：**资源余量**。这里的资源余量主要指 **CPU、内存、磁盘、Docker 现有负载、现有高峰进程占用**。特别是 Milvus 官方对 Standalone 模式给出的资源要求中，**RAM 最低 8GB，推荐 16GB，CPU 推荐 4 核以上**，这意味着共享服务器是否适合直接上完整链路，核心取决于“在现有业务跑着的情况下，还剩多少可用资源”。[1]

## 二、为什么现在不能直接拍板说“一定不会影响其他产品”

你现在已经把“端口冲突”和“服务是否已安装”查清楚了，但这还只能回答 **“能不能装”**，还不能完整回答 **“装上之后会不会挤占其他业务资源”**。

在当前完整产品链路里，资源压力最大的不只是 FastAPI 后端，而是 **Milvus + etcd + MinIO** 这一组向量基础设施。PostgreSQL 与 Redis 的单机压力通常相对可控，但 Milvus 在索引、加载集合、检索以及写入时，对内存和磁盘 I/O 更敏感。[1] 因此，真正要判断是否“不会影响其他产品”，至少要看下面四组信息。

| 维度 | 为什么重要 | 风险最大的组件 |
|---|---|---|
| 可用内存 | 决定能否安全承载 Milvus standalone | Milvus / etcd / MinIO |
| CPU 峰值与平均负载 | 决定检索、构建索引、并发请求是否会抢占现有业务 | Milvus / Python 后端 |
| 磁盘余量与 I/O | 决定 PostgreSQL、Redis AOF、MinIO、Milvus 数据文件是否安全落盘 | PostgreSQL / Redis / Milvus |
| Docker 现有占用 | 决定是否适合再拉起 3~5 个容器 | Milvus 相关容器 |

所以最稳妥的方式，不是现在立刻下结论，而是先执行一份**一次性盘点脚本**，把资源余量抓出来，再按判断标准做部署分层。

## 三、你现在先执行的资源盘点脚本

我已经给你准备好一个脚本：

```text
/home/ubuntu/work/kol_lens/server_resource_audit_for_kol_lens.sh
```

你可以把它拷到服务器上执行，或者直接参考里面的命令逐条跑。它会一次性收集：

| 采集项 | 作用 |
|---|---|
| OS / Kernel / Host | 确认系统基线 |
| Uptime / Load | 看当前整体繁忙程度 |
| CPU | 看核数与架构 |
| Memory | 看总内存、可用内存、Swap |
| Disk / Filesystem | 看容量余量与挂载结构 |
| I/O / 目录占用 | 看 `/home`、`/var/lib` 是否已接近吃满 |
| 端口监听 | 看新服务端口是否仍空闲 |
| 现有进程 / 运行服务 | 看是否已有 Python、Node、Redis、Docker 业务占资源 |
| Docker / Containers | 看容器数量、资源占用、磁盘占用 |
| Nginx sites | 看现有站点分布 |
| Runtime availability | 看 `python3.11`、`node`、`pnpm` 是否已具备 |
| SELinux / Firewall | 看部署时是否会被系统安全策略拦截 |

建议在服务器上这样执行：

```bash
chmod +x /path/to/server_resource_audit_for_kol_lens.sh
/path/to/server_resource_audit_for_kol_lens.sh
```

如果你想直接贴进 shell，也可以先执行下面这组最核心命令：

```bash
uptime
free -h
cat /proc/meminfo | egrep 'MemTotal|MemAvailable|SwapTotal|SwapFree'
nproc
lscpu | egrep 'Architecture|CPU\(s\)|Model name'
df -hT
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -n 30
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream
systemctl list-units --type=service --state=running | egrep 'nginx|redis|postgres|docker|containerd|milvus'
ss -lntp | egrep ':80|:443|:3007|:5432|:6379|:19530|:9000|:9001|:9091'
```

## 四、如何判断“不会影响其他产品”

这里我给你的是**部署判断标准**，不是绝对真理，而是针对你当前这个项目和共享服务器场景的稳妥建议。

### 1. 内存判断标准

| 条件 | 结论 | 部署建议 |
|---|---|---|
| **可用内存 ≥ 10GB**，且平时波动不大 | 风险较低 | 可以考虑完整部署：PostgreSQL + Redis + Milvus + 后端 + 前端 |
| **可用内存 6GB ~ 10GB** | 有风险但可操作 | 先上 PostgreSQL + Redis + 后端 + 前端，Milvus 需要谨慎评估或限量测试 |
| **可用内存 < 6GB** | 风险较高 | 不建议在同机完整部署 Milvus |
| **Swap 已大量使用** | 风险高 | 说明内存已经紧张，不建议再加 Milvus |

这里要特别注意，Milvus 官方对 Standalone 模式给出的 **最低内存要求就是 8GB**，推荐 16GB。[1] 因此在共享服务器上，**不是机器总内存达到 8GB 就够了，而是现有业务运行后仍要有足够剩余内存**。

### 2. CPU 判断标准

| 条件 | 结论 | 部署建议 |
|---|---|---|
| `CPU(s)` ≥ 8，且平均 load 不高 | 安全性较好 | 可以部署完整链路 |
| `CPU(s)` = 4，且现有服务不重 | 勉强可用 | 可部署，但要避免同时进行大批量向量写入 |
| `CPU(s)` < 4 或长期高 load | 风险高 | 不建议上完整 Milvus 链路 |

Milvus 官方对 Standalone 模式推荐 **4 core 或以上**。[1] 如果服务器核数本来不多，而上面又已经跑了多个站点，那么向量检索和索引构建时比较容易和现有业务抢 CPU。

### 3. 磁盘判断标准

| 条件 | 结论 | 部署建议 |
|---|---|---|
| 系统盘 / 数据盘剩余空间 ≥ 40GB | 较稳妥 | 可完整部署 |
| 剩余空间 20GB ~ 40GB | 可尝试 | 先做小规模数据联调 |
| 剩余空间 < 20GB | 风险高 | 不建议上完整依赖栈 |

这是因为当前完整链路里会持续落盘的内容不少，包括：

| 组件 | 会落盘的内容 |
|---|---|
| PostgreSQL | 业务表、索引、WAL |
| Redis | AOF / RDB |
| MinIO | Milvus 相关对象存储数据 |
| Milvus | segment / index / metadata |
| 前端构建与后端日志 | 构建产物与运行日志 |

### 4. Docker 判断标准

| 条件 | 结论 | 部署建议 |
|---|---|---|
| Docker 尚未承载重业务 | 可用 | 适合将 Milvus 相关组件放进 Docker |
| Docker 已运行很多高占用容器 | 有风险 | 先评估已有容器的 CPU / Memory / Disk 占用 |
| Docker 未安装 | 可补装 | 但要确认不会影响现有运维体系 |

## 五、最适合你当前阶段的部署策略

基于你已经确认的服务器状态，我认为现在最合理的策略不是“一步到位猛上所有组件”，而是按 **共享服务器友好型顺序** 部署。

### 路线一：最推荐的共享服务器部署策略

| 阶段 | 目标 | 是否推荐 |
|---|---|---|
| 阶段 A | 先做资源盘点 | 必须 |
| 阶段 B | 先装 PostgreSQL + Redis | 强烈推荐 |
| 阶段 C | 先起后端手测基础 API | 强烈推荐 |
| 阶段 D | 构建前端并接入 Nginx | 强烈推荐 |
| 阶段 E | 最后再上 Milvus 并测向量检索 | 推荐 |

这个顺序的好处在于：即便后面发现 Milvus 资源压力偏大，你前面的站点、后端、数据库、缓存与大部分非向量链路也已经完成落位，不需要推倒重来。

### 路线二：只有在资源非常充足时再考虑的一步到位策略

如果你执行资源盘点后发现：

| 条件 | 说明 |
|---|---|
| 可用内存明显充足 | 比如长期有 10GB 以上余量 |
| CPU 至少 8 核且负载轻 | 不容易和现有站点抢资源 |
| Docker 当前占用不高 | 可再拉起 Milvus 相关容器 |
| 磁盘余量明显充足 | 能承载 Milvus 数据增长 |

那么可以直接走：**PostgreSQL + Redis + Milvus + 后端 + 前端** 的完整部署路径。

## 六、面向当前项目的完整部署流程

下面这部分是我为你按当前代码仓库实际结构整理的“尽可能完整”的部署流程。它不是只让页面打开，而是尽量覆盖你现在产品链路的主要能力。

### 第 1 步：资源盘点，确认能否承受完整链路

先不要上服务，先跑盘点脚本并把结果留档。只有当内存、CPU、磁盘都还比较健康时，才建议继续上 Milvus。

### 第 2 步：准备代码目录

```bash
mkdir -p /home/red/work
cd /home/red/work
gh repo clone leviathanwang90-debug/kol_lens /home/red/work/kol_lens
```

如果目录已存在，就改用：

```bash
cd /home/red/work/kol_lens
git pull
```

### 第 3 步：安装 PostgreSQL

PostgreSQL 官方说明，如果当前环境没有 PostgreSQL，可以自行安装；Red Hat 家族 Linux 也支持直接通过系统仓库安装 `postgresql-server`。[2] [3]

```bash
sudo dnf install -y postgresql-server postgresql
sudo postgresql-setup --initdb
sudo systemctl enable postgresql.service
sudo systemctl start postgresql.service
sudo -u postgres psql -c "CREATE USER kol_lens_user WITH PASSWORD '请替换强密码';"
sudo -u postgres psql -c "CREATE DATABASE kol_lens OWNER kol_lens_user;"
sudo -u postgres psql -d kol_lens -f /home/red/work/kol_lens/backend/db/migrations/init.sql
```

### 第 4 步：安装 Redis

如果你希望尽量贴近真实链路，建议直接装 Redis。由于当前代码连接 Redis 时固定用 `db=0`，最稳妥的思路是给 `kol_lens` 使用独立 Redis 实例，而不是共享未知现有实例。

```bash
sudo dnf install -y redis
sudo systemctl enable redis
sudo systemctl start redis
sudo systemctl status redis --no-pager
```

如果后面你要加密码，再改 `/etc/redis/redis.conf` 或系统实际配置路径。

### 第 5 步：安装 Docker，并为 Milvus 做准备

如果资源盘点通过，再部署 Milvus。当前仓库已经有 `backend/docker-compose.yml`，其中除了 Milvus 本体，还会一起拉起：

| 组件 | 作用 |
|---|---|
| `etcd` | Milvus 元数据存储 |
| `minio` | Milvus 对象存储 |
| `milvus` | 向量数据库本体 |

因此这一步是完整链路里最需要谨慎观察资源的部分。

### 第 6 步：准备后端 Python 运行环境

```bash
cd /home/red/work/kol_lens/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

如果服务器上还没有 `python3.11`，需要先补装，否则不要直接用系统旧版本 Python 顶替。

### 第 7 步：写生产环境变量

根据代码中的 `backend/config/__init__.py`，核心变量至少包括下面这些：

```bash
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=kol_lens
POSTGRES_USER=kol_lens_user
POSTGRES_PASSWORD=请替换

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
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
PGY_BLOGGER_SEARCH_URL=

PGY_COOKIE_HEADER=
PGY_COOKIE_HEADERS=
PGY_COOKIE_FILE=
CREATOR_DATA_VL_MODEL=gpt-4.1-mini
```

建议位置：

```text
/home/red/work/kol_lens/backend/.env.production
```

### 第 8 步：手工启动后端验证依赖

```bash
cd /home/red/work/kol_lens/backend
source .venv/bin/activate
set -a
source .env.production
set +a
uvicorn app:app --host 127.0.0.1 --port 3007
```

如果这里都起不来，先不要写 systemd。共享服务器上最怕“把错误配置做成常驻服务后反复重启刷日志”。

### 第 9 步：前端构建

前端的 `vite.config.ts` 已明确把构建产物输出到：

```text
/home/red/work/kol_lens/frontend/dist/public
```

因此部署方式可以继续使用 **Nginx 直接托管静态文件** 的模式。

```bash
cd /home/red/work/kol_lens/frontend
pnpm install
pnpm build
```

### 第 10 步：写后端 systemd 服务

建议服务名独立，不要和现有产品混名。

```ini
[Unit]
Description=kol_lens backend service
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=red
WorkingDirectory=/home/red/work/kol_lens/backend
EnvironmentFile=/home/red/work/kol_lens/backend/.env.production
ExecStart=/home/red/work/kol_lens/backend/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 3007
Restart=always
RestartSec=5
StandardOutput=append:/home/red/work/kol_lens/logs/backend.out.log
StandardError=append:/home/red/work/kol_lens/logs/backend.err.log

[Install]
WantedBy=multi-user.target
```

### 第 11 步：写 Nginx 站点配置

你当前已经确认 `/etc/nginx/conf.d/` 下没有 `lens.red-magic.cn` 相关配置，因此可以新增一个独立 conf，而不需要改已有站点文件。

建议核心结构如下：

| 配置项 | 建议值 |
|---|---|
| `server_name` | `lens.red-magic.cn` |
| `root` | `/home/red/work/kol_lens/frontend/dist/public` |
| `/` | `try_files $uri $uri/ /index.html;` |
| `/api/` | 反代 `http://127.0.0.1:3007` |

### 第 12 步：最后再接入 Milvus 完整链路

只有当你确认下面几项都稳定后，再把 Milvus 接入到完整业务链路里：

| 先决条件 | 说明 |
|---|---|
| PostgreSQL 已正常工作 | 资产、历史、模板、履约明细都依赖它 |
| Redis 已工作 | 更接近真实缓存链路 |
| 后端基础接口可用 | 确认不是后端本身配置问题 |
| 前端站点可访问 | 页面链路已打通 |
| 服务器资源余量充足 | 避免 Milvus 抢资源 |

## 七、我对你当前服务器的实际建议

如果你现在问我：**在还没看内存 / CPU / 磁盘数据之前，最稳妥的落地策略是什么？**

我的建议会非常明确：

> **先做资源盘点，再分层部署。不要一上来直接把 PostgreSQL、Redis、Milvus、后端、前端一起全开。**
>
> 当前从端口和服务冲突角度看，这台 `CentOS Stream 9` 服务器是适合部署 `kol_lens` 的；但从“是否影响其他产品”的角度，真正决定成败的是资源余量，尤其是 Milvus 所需的内存与 CPU。[1]
>
> 因此最推荐的顺序是：**资源盘点 → PostgreSQL → Redis → 后端手测 → 前端 + Nginx → 最后再上 Milvus**。

## 八、下一步你只需要给我这些输出

为了让我继续帮你做“是否安全上线完整链路”的判断，你下一步只需要把下面这组结果贴给我即可。

| 最关键输出 | 用途 |
|---|---|
| `free -h` | 看内存余量 |
| `cat /proc/meminfo | egrep 'MemTotal|MemAvailable|SwapTotal|SwapFree'` | 看可用内存与 Swap |
| `uptime` | 看平均负载 |
| `nproc` + `lscpu` 关键信息 | 看 CPU 核数 |
| `df -hT` | 看磁盘余量 |
| `ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -n 30` | 看谁最吃资源 |
| `docker ps -a` + `docker stats --no-stream` | 看现有容器负载 |

你把这些贴过来之后，我就可以进一步帮你判断：

1. **这台机器能不能直接上完整链路**；
2. **Milvus 是否会挤压现有业务**；
3. **是否应先分阶段部署**；
4. **下一步该用哪一套最稳妥的安装命令。**

## References

[1]: https://milvus.io/docs/prerequisite-docker.md "Requirements for Installing Milvus Standalone | Milvus Documentation"
[2]: https://www.postgresql.org/docs/current/tutorial-install.html "PostgreSQL Documentation: 1.1 Installation"
[3]: https://www.postgresql.org/download/linux/redhat/ "PostgreSQL: Linux downloads (Red Hat family)"
