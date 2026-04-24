# `kol_lens` Windows 本地 `E:` 盘完整部署流程

**作者：Manus AI**  
**日期：2026-04-21**

## 一、结论先说清楚

结合你已经贴出来的盘点结果，我建议你在这台 Windows 机器上采用如下部署策略：

> **项目代码、日志、运行时目录统一落在 `E:\kol_lens`；PostgreSQL、Redis、Milvus 尽量统一纳入 Docker Desktop + WSL2 管理；前端和后端代码也从 `E:` 盘启动。**

这样做有三个直接好处。第一，`C:` 盘当前只剩约 `12.9GB`，不适合再放项目、镜像和数据库数据。第二，你当前已有的 PostgreSQL Windows 服务虽然显示 `Running`，但并没有实际监听 `5432`，继续在这套旧实例上缠斗，成本会高于直接采用一套可控的新部署结构。第三，项目代码层面默认依赖 **PostgreSQL 5432、Redis 6379、Milvus 19530**，并且前后端部署结构已经比较清晰：前端构建产物输出到 `frontend/dist/public`，后端建议监听 `127.0.0.1:3007`。

## 二、推荐的 Windows 本地目录结构

建议你把所有与 `kol_lens` 有关的内容统一收拢到 `E:` 盘。

| 目录 | 用途 | 是否建议立即创建 |
| --- | --- | --- |
| `E:\kol_lens` | 项目根目录 | 是 |
| `E:\kol_lens\repo` | Git 仓库代码 | 是 |
| `E:\kol_lens\logs` | 后端日志、部署日志 | 是 |
| `E:\kol_lens\runtime` | 运行时数据根目录 | 是 |
| `E:\kol_lens\runtime\postgres` | PostgreSQL 数据目录或导出目录 | 是 |
| `E:\kol_lens\runtime\redis` | Redis 数据目录 | 是 |
| `E:\kol_lens\runtime\milvus` | Milvus 数据目录 | 是 |
| `E:\kol_lens\runtime\minio` | MinIO 数据目录 | 是 |
| `E:\kol_lens\runtime\etcd` | etcd 数据目录 | 是 |
| `E:\kol_lens\runtime\docker-data` | Docker Desktop 数据根目录候选 | 建议 |
| `E:\kol_lens\env` | `.env`、凭据配置文件 | 是 |
| `E:\kol_lens\tools` | Nginx、辅助脚本 | 建议 |

## 三、最推荐的部署方式

我不建议你继续修复当前已经“服务在、端口不在”的 Windows PostgreSQL 旧实例，再加上单独安装 Windows 版 Redis、Windows 版 Nginx、以及 Milvus 若干依赖。那条路线能做，但不够干净，也不够好维护。

对你现在这台机器，我更推荐下面这个结构。

| 组件 | 推荐部署方式 | 原因 |
| --- | --- | --- |
| PostgreSQL | **Docker Compose** | 彻底避开当前异常 Windows 服务实例 |
| Redis | **Docker Compose** | 与项目默认结构一致，易于统一管理 |
| Milvus + etcd + MinIO | **Docker Compose** | 与项目现有 `backend/docker-compose.yml` 一致 |
| 后端 FastAPI | Windows 本机 Python 虚拟环境 | 调试最方便 |
| 前端 React / Vite | Windows 本机 Node + `pnpm build` | 构建最直接 |
| Nginx | 先不急着装；待前后端跑通后再装 | 先保证核心链路可用 |

## 四、完整部署顺序

为了减少排错成本，建议你按下面顺序来，而不是一口气全部装完。

| 阶段 | 目标 | 通过标准 |
| --- | --- | --- |
| 第 1 阶段 | 创建 `E:` 盘工作目录并放好代码 | 代码已进入 `E:\kol_lens\repo` |
| 第 2 阶段 | 安装并确认 Docker Desktop + WSL2 | `docker` 命令可用 |
| 第 3 阶段 | 用 Docker 启动 PostgreSQL / Redis / Milvus | 5432 / 6379 / 19530 开始监听 |
| 第 4 阶段 | 初始化数据库 | `init.sql` 成功执行 |
| 第 5 阶段 | 启动后端 | `127.0.0.1:3007` 可访问 |
| 第 6 阶段 | 构建前端 | `frontend/dist/public` 生成成功 |
| 第 7 阶段 | 安装并配置 Nginx | `http://localhost` 正常打开页面 |
| 第 8 阶段 | 手工联调完整链路 | 检索、提交、历史、导出等核心路径可跑 |

## 五、第一批就要准备好的环境变量

项目代码当前默认使用下面这组关键配置。

| 变量 | 默认值 / 推荐值 | 作用 |
| --- | --- | --- |
| `POSTGRES_HOST` | `127.0.0.1` | PostgreSQL 地址 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 |
| `POSTGRES_DB` | `sigma_match` | 数据库名 |
| `POSTGRES_USER` | `sigma` | 数据库用户名 |
| `POSTGRES_PASSWORD` | 自定义强密码 | 数据库密码 |
| `REDIS_HOST` | `127.0.0.1` | Redis 地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_PASSWORD` | 自定义强密码 | Redis 密码 |
| `MILVUS_HOST` | `127.0.0.1` | Milvus 地址 |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `OPENAI_API_KEY` | 你的真实值 | 模型能力 |
| `KOL_LENS_INTENT_MODEL` | `gpt-4.1-mini` | 意图识别模型 |
| `KOL_LENS_EMBEDDING_MODEL` | `text-embedding-3-small` | 向量嵌入模型 |

## 六、为什么我建议先不用现有 PostgreSQL Windows 服务

你刚才已经验证了几件关键事实：

| 现象 | 说明 |
| --- | --- |
| `Get-Service postgresql-x64-16` 显示 `Running` | 服务注册确实存在 |
| `Get-Process postgres` 能看到多个 postgres 进程 | 进程层面确实被拉起 |
| `netstat -ano | findstr :5432` 没有任何输出 | **它没有在默认端口提供 TCP 监听** |
| `psql -U postgres -l` 得到 `Connection refused` | **当前实例不能按默认方式被项目使用** |
| 默认 `C:\Program Files\PostgreSQL\16\data` 路径不存在 | 安装布局不是标准默认结构，后续定位和维护成本偏高 |

这意味着当前这套 PostgreSQL 不是完全不能修，而是**不适合作为你这次全量本地部署的基础**。为了节省时间，建议你新的 `kol_lens` 环境不要依赖它。

## 七、我建议你采用的实际落地方式

### 方案 A：我最推荐

> **所有新部署内容全部放到 `E:\kol_lens`，基础设施统一走 Docker，旧 PostgreSQL 服务暂时不碰。**

这条路线最干净，最方便后续维护，也最容易统一备份。

### 方案 B：不推荐但可做

> 修现有 PostgreSQL，再单独安装 Redis、Docker、Milvus 和 Nginx。

这条路线的问题在于：排错点更多，而且现有 PostgreSQL 本身已经表现异常。

## 八、我们接下来就按“你做一步，我带一步”来执行

我建议现在就从 **第 1 步：创建 `E:` 盘目录结构** 开始，而不是先碰 PostgreSQL。

你第一步只需要执行下面这些命令：

```powershell
New-Item -ItemType Directory -Force E:\kol_lens | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\repo | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\logs | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\env | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\tools | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\postgres | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\redis | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\milvus | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\minio | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\etcd | Out-Null
New-Item -ItemType Directory -Force E:\kol_lens\runtime\docker-data | Out-Null
Get-ChildItem E:\kol_lens -Recurse | Select-Object FullName
```

如果这些目录都创建成功，下一步我就带你做：

> **第 2 步：确认 Git 拉代码路径，并检查 Docker Desktop / WSL2 是否就绪。**

## 九、当前阶段不要急着做的事

为了避免把环境越弄越乱，下面这些动作我建议你先不要做，等我带你进入对应步骤时再做。

| 暂时不要做的事 | 原因 |
| --- | --- |
| 继续折腾当前 Windows PostgreSQL 服务 | 容易浪费时间 |
| 把项目代码放到 `C:` 盘 | 空间紧张 |
| 先装 Nginx | 前端和后端都没跑通前意义不大 |
| 先修改一堆系统环境变量 | 先把基础链路跑通再整理 |
| 先做 HTTPS / 域名映射 | 本地调试阶段不急 |

## 十、结论

从现在开始，你完全可以把这台 Windows 机器当成 `kol_lens` 的本地部署环境，而且采用 **`E:` 盘统一承载 + Docker 管基础设施 + 本机 Python / Node 跑业务代码** 的方式，是当前最省事、最稳、最容易继续推进的一条路。

我建议我们就严格按阶段推进，不跳步。现在先完成 **目录初始化**，然后我继续带你做下一步。
