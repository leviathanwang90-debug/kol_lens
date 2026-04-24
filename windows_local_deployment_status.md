# KOL Lens Windows 本地部署状态与续接文档

## 文档目的

本文档用于记录 **当前仓库代码状态**、**已经完成的 Windows 本地部署进度**、**下一步启动顺序** 以及 **需要补齐的配置项**。其目标是让后续在新的对话中继续推进部署时，可以直接基于本文件恢复上下文，而不需要重新回忆此前已经完成的步骤。

## 当前结论

当前已经准备出一份可用于 Windows 本地继续部署的代码状态，工作目录以本仓库当前分支为准。此次调整的重点不是把项目彻底改写成 `creator_multimodal_v1` 或 `creator_multimodal_v2`，而是**将其中与模型调用、PGY Cookie 来源、PGY 扩库 payload 组织和达人补充数据抓取有关的关键思路，按 `kol_lens` 现有后端结构重新落地**。

从部署进度看，**Windows 主机侧的 Docker Desktop 与 WSL 2 已经成功启动并可用**，同时 Docker 磁盘镜像位置已经切换到 `E:\kol_lens\runtime\docker-data`。这意味着最难处理的容器运行基础已经打通，后续重点已经转移为 **项目目录就位、环境变量补齐、基础设施容器启动、后端启动、前端启动与联调验证**。

## 本次已落地的代码改动

| 模块 | 文件 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| OpenAI 兼容调用 | `backend/services/openai_compat.py` | 已新增 | 用统一客户端工厂封装兼容式模型网关，便于分别为意图模型、embedding 模型、视觉模型配置独立的 API Key 与 Base URL。 |
| PGY Cookie 统一来源 | `backend/services/pgy_cookie_source.py` | 已新增 | 统一支持 `PGY_COOKIE`、`PGY_COOKIE_HEADER`、`PGY_COOKIE_HEADERS`、`PGY_COOKIE_FILE`、以及通过 OSS 下载 `token.txt`。 |
| 意图解析 | `backend/services/intent_parser.py` | 已修改 | 已改为支持独立模型网关配置，不再强耦合单一默认调用方式。 |
| PGY 扩库服务 | `backend/services/pgy_service.py` | 已修改 | 已吸收 `creator_multimodal_v2` 中较关键的 `brandUserId`、`trackId`、`contentTag`、图文/视频报价拆分、CPM 范围映射等思路。 |
| 达人补充数据 | `backend/services/creator_data_service.py` | 已修改 | 已改为复用统一 Cookie 池，并支持以独立视觉模型配置做图片理解与达人补充。 |
| 环境加载 | `backend/app.py` | 已修改 | 启动时会优先加载 `.env` 与 `.env.production`，方便解压后直接落地配置。 |
| 环境模板 | `backend/.env.example` 与 `backend/.env.production` | 已修改/新增 | 已整理为更适合 Windows 本地启动的模板。 |
| Cookie 样例 | `backend/data/token.txt.sample` | 已新增 | 方便按现有 `token.txt` 形式提供 PGY Cookie。 |
| 依赖项 | `backend/requirements.txt` | 已修改 | 已补充支持 OSS 下载 Cookie 文件所需依赖。 |

## 与 creator_multimodal v1 / v2 的参考关系

当前仓库**参考了** `creator_multimodal_v1.zip` 与 `creator_multimodal_v2.zip`，但不是整包复制。参考关系可概括如下。

| 参考对象 | 已吸收内容 | 未直接照搬内容 |
| --- | --- | --- |
| `creator_multimodal_v1` | `token.txt` / OSS 刷新思路、多模态视觉调用习惯、PGY Cookie 轮换思路 | 没有直接把其整套 `qwen_client.py`、本地索引工程和脚本式目录结构整体并入 `kol_lens`。 |
| `creator_multimodal_v2` | `contentTag` 映射、PGY payload 组织方式、图文/视频价格与 CPM 拆分、fallback 扩库思路、达人补充数据方向 | 没有把 `find_kols` 子工程按原样整体搬入，而是把其中最有价值的逻辑拆解后适配进当前后端服务层。 |

换言之，当前状态是 **“按 `kol_lens` 的结构重构吸收 v1 / v2 的关键思路”**，而不是 **“把项目替换成 v1 / v2”**。

## Windows 主机已完成进度

| 项目 | 当前状态 | 备注 |
| --- | --- | --- |
| Docker Desktop 启动 | 已完成 | 用户已确认 Docker Desktop 正常启动。 |
| WSL 2 运行 | 已完成 | 用户已确认 `docker-desktop` 在 WSL 中正常运行。 |
| Docker 数据位置迁移到 E 盘 | 已完成 | 已将磁盘镜像位置切换到 `E:\kol_lens\runtime\docker-data`。 |
| 项目代码通过 GitHub 直接克隆 | 未完成 | 用户机器访问 GitHub `443` 不稳定，`git clone` 失败。 |
| 改用压缩包交付 | 已完成 | 已生成可解压部署包供本地落地。 |
| 项目代码正式解压到 `E:\kol_lens\repo` | 待执行 | 这是下一阶段应优先完成的动作。 |
| 基础设施容器启动 | 待执行 | PostgreSQL、Redis、Milvus 尚未在用户机器正式启动。 |
| 后端启动 | 待执行 | 依赖 `.env.production` 先补齐。 |
| 前端启动 | 待执行 | 需在后端启动后联调验证。 |

## Windows 本地部署推荐目录

建议继续沿用以下目录结构，以保持与当前部署思路一致。

| 路径 | 用途 |
| --- | --- |
| `E:\kol_lens\repo` | 项目代码目录 |
| `E:\kol_lens\runtime\docker-data` | Docker Desktop 磁盘镜像目录 |
| `E:\kol_lens\runtime\downloads` | 临时下载目录，可选 |
| `E:\kol_lens\backups` | 手工备份目录，可选 |

## 下一阶段建议启动顺序

下面的顺序是后续在新对话中继续部署时，**最推荐沿用的执行顺序**。这样可以避免同时改太多变量，便于逐步确认每一步是否成功。

### 第一步：将项目代码落到 E 盘

先将当前仓库对应版本的代码解压到：

```powershell
E:\kol_lens\repo
```

解压完成后，应至少能看到以下关键目录和文件：

| 关键路径 | 用途 |
| --- | --- |
| `E:\kol_lens\repo\backend` | 后端代码 |
| `E:\kol_lens\repo\frontend` | 前端代码 |
| `E:\kol_lens\repo\backend\docker-compose.yml` | 基础设施容器编排 |
| `E:\kol_lens\repo\backend\.env.production` | Windows 本地部署环境模板 |

### 第二步：补齐后端配置

重点需要编辑：

```powershell
E:\kol_lens\repo\backend\.env.production
```

当前最关键的几项如下。

| 变量 | 是否必须 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 必须 | 必须替换为真实值。 |
| `KOL_LENS_INTENT_MODEL` | 建议确认 | 当前默认已改成可独立配置。 |
| `KOL_LENS_EMBEDDING_MODEL` | 建议确认 | 当前默认以兼容式方式配置。 |
| `CREATOR_DATA_VL_MODEL` | 建议确认 | 当前默认值偏向你已有脚本的视觉模型使用方式。 |
| `PGY_COOKIE` 或 `PGY_COOKIE_HEADER` | 二选一或多选一 | 若直接手填 Cookie，可直接用这里。 |
| `PGY_COOKIE_HEADERS` | 可选 | 可放多行 Cookie。 |
| `PGY_COOKIE_FILE` | 推荐 | 可指向 `backend/data/token.txt`。 |
| `PGY_OSS_ACCESS_KEY_ID` / `PGY_OSS_ACCESS_KEY_SECRET` | 可选 | 若希望自动从 OSS 下载 `token.txt`，则补齐。 |

如果你更习惯使用 `token.txt`，推荐将你的现有内容保存到：

```powershell
E:\kol_lens\repo\backend\data\token.txt
```

### 第三步：启动基础设施容器

在 Windows PowerShell 中进入后端目录后执行：

```powershell
cd E:\kol_lens\repo\backend
docker-compose up -d
docker-compose ps
```

当前编排文件会启动以下服务。

| 服务 | 默认端口 | 用途 |
| --- | --- | --- |
| PostgreSQL | `5432` | 主数据库 |
| Redis | `6379` | 缓存与任务状态 |
| MinIO | `9000` / `9001` | Milvus 对象存储 |
| Milvus | `19530` / `9091` | 向量库与健康检查 |
| etcd | `2379` / `2380` | Milvus 元数据依赖 |

若这一步成功，说明本地数据库和向量库基础层已经起来。

### 第四步：安装后端依赖并启动后端

```powershell
cd E:\kol_lens\repo\backend
pip install -r requirements.txt
python app.py
```

如果需要更稳定，后续也可以切换到虚拟环境，但为了先完成部署验证，当前优先级更高的是先确认服务能跑起来。

### 第五步：启动前端

```powershell
cd E:\kol_lens\repo\frontend
pnpm install
pnpm dev
```

前端起来后，需要重点验证以下页面或能力是否联通：工作台、达人资产库、与后端 API 的联调、PGY 扩库触发、达人补充数据读取。

## 当前阻塞点

当前最主要的阻塞并不在 Docker 或 WSL，而在 **代码尚未正式落地到 `E:\kol_lens\repo`，以及生产配置尚未填入真实值**。只要这两件事完成，后续推进速度会明显变快。

| 阻塞项 | 当前状态 | 处理建议 |
| --- | --- | --- |
| GitHub 直连不稳定 | 已确认存在 | 继续优先使用压缩包落地，不再依赖实时 `git clone`。 |
| OpenAI / 兼容网关真实配置未填 | 待处理 | 先补 `OPENAI_API_KEY` 与必要 Base URL。 |
| PGY Cookie 来源未最终确定 | 待处理 | 推荐优先使用 `backend/data/token.txt`，其次才是直接写入 `.env.production`。 |
| 基础设施容器未实际启动验证 | 待处理 | 在代码目录落地后，优先执行 `docker-compose up -d`。 |

## 关于 C 盘空间突然减少的说明

虽然 Docker 的磁盘镜像目录已经改到 E 盘，但 Windows 上 **Docker Desktop 与 WSL 相关的部分组件、缓存、基础虚拟磁盘与程序文件仍然可能保留在 C 盘**。因此，切换数据目录后并不等于 **所有** Docker / WSL 占用都会完全离开 C 盘。当前理解应是：**后续新增的大头运行数据尽量落 E 盘，但 C 盘仍可能保留一部分历史缓存、程序文件和 WSL 相关占用。**

因此，在新的对话中，如果需要继续处理 C 盘瘦身，建议单独做以下事项：先识别 Docker Desktop 程序目录、WSL 发行版 VHDX 位置、历史镜像缓存目录，再决定是否做清理或导出迁移。

## 建议在新对话中直接接续的任务

为了让后续对话更快进入执行阶段，建议下一次直接以下面的目标作为起点：

> 请基于仓库中的 `windows_local_deployment_status.md`，继续推进 `E:\kol_lens\repo` 的 Windows 本地部署，先检查代码是否已经解压到位，然后逐步补 `.env.production`、启动 `backend/docker-compose.yml`、再启动后端与前端。

## 建议优先查看的文件

| 文件 | 作用 |
| --- | --- |
| `PATCH_README.md` | 本次补丁说明，解释模型与 PGY 改造方向。 |
| `backend/.env.production` | Windows 本地运行的主要配置入口。 |
| `backend/services/pgy_service.py` | PGY 扩库与 payload 组织逻辑。 |
| `backend/services/creator_data_service.py` | 达人补充数据逻辑。 |
| `backend/services/pgy_cookie_source.py` | Cookie / token / OSS 统一来源。 |
| `backend/services/openai_compat.py` | 兼容式模型客户端封装。 |
| `backend/docker-compose.yml` | PostgreSQL、Redis、Milvus 等基础设施编排。 |

## 续接建议

在新的对话中，不建议一开始就同时处理模型、Cookie、Docker、前后端所有问题。更稳妥的方式是按照本文档记录的顺序，先确认代码目录，再确认配置文件，再确认容器，最后才进入应用层启动与联调。这样每一步都有明确的“成功/失败”边界，便于快速定位问题。
