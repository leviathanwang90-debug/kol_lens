# KOL Lens Windows 本地补丁说明

本次补丁的目标，是把项目改成**更接近你现有测试脚本的使用方式**，同时尽量降低你在 Windows 本地首次部署时需要手动整理的配置量。尤其针对你提出的三个问题，我已经分别处理：第一，**达人补充数据的视觉识别默认流程**已经改成更贴近你 `bug.py` 的方式；第二，**PGY Cookie 的获取方式**已经支持你 `bug.py` 里的 `OSS -> token.txt -> Cookie` 路线；第三，项目里原来只出现在文档中的环境变量，已经被整理进真正可用的 `.env.production` 与 `.env.example` 模板中，避免你再自己拼配置。

需要特别说明的是，**我没有把你 `bug.py` 中出现的 OSS AccessKey 和密钥直接写死进交付包**。原因不是技术上做不到，而是这样会把敏感凭据永久写进代码和压缩包，后续很容易在本地备份、Git、聊天记录或服务器迁移过程中扩散。这个补丁已经把你的调用方式完整兼容进来，但仍然把真正的密钥保留为可填配置项，这是安全上更稳妥的做法。

| 你关心的问题 | 本次处理结果 |
| --- | --- |
| 为什么不直接用你测试脚本里的视觉模型流程 | 已改为默认使用 `CREATOR_DATA_VL_MODEL=qwen-vl-max-2025-01-25`，并支持 `CREATOR_DATA_VL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 为什么 PGY Cookie 不走 `bug.py` 里的 OSS 下载方式 | 已新增 OSS token 下载支持，程序会尝试读取 `data/token.txt`，若不存在则可通过 OSS 参数自动下载 |
| 为什么还要配那么多 PGY 参数 | 已把 `PGY_BLOGGER_SEARCH_URL`、`PGY_BRAND_USER_ID`、OSS endpoint/bucket/object 默认值内置；现在通常只需要补真实密钥或 Cookie |
| 为什么嵌入模型没有直接改成 `bug.py` 的模型 | 因为你的 `bug.py` 只覆盖了**视觉识别**，没有实现项目主检索链路所需的**文本嵌入**；因此检索主链路仍保留文本 embedding 配置 |

这次补丁中，**视觉识别链路**和**检索主链路**被刻意分开处理。你的 `bug.py` 主要解决的是“从 PGY 拉取达人明细，再用视觉模型识别图片中的宝宝年龄”这一段，因此我把这部分默认切到了更接近你现有脚本的实现；但 `kol_lens` 的核心检索还依赖文本向量来做意图向量化、Milvus 检索和 PostgreSQL 回退匹配，所以不能把它直接替换成视觉模型，否则会破坏主搜索能力。

| 这次实际改动的关键文件 | 作用 |
| --- | --- |
| `backend/services/pgy_cookie_source.py` | 新增统一的 PGY Cookie 来源管理，支持环境变量、本地 `data/token.txt`、OSS 三种来源 |
| `backend/services/openai_compat.py` | 新增兼容 OpenAI 风格网关的客户端构造逻辑，便于不同子流程独立走不同模型网关 |
| `backend/services/creator_data_service.py` | 默认改成更接近 `bug.py` 的视觉识别方式，并接入统一 Cookie 来源 |
| `backend/services/pgy_service.py` | 扩库搜索与嵌入阶段支持统一 Cookie 和独立模型网关配置 |
| `backend/app.py` | 启动时自动加载 `.env` 与 `.env.production` |
| `backend/.env.production` | 新增可直接落地的 Windows 本地部署模板 |
| `backend/.env.example` | 从“仅基础设施模板”升级为“完整运行模板” |
| `backend/data/token.txt.sample` | 给出可直接套用的 token 文件样例 |
| `backend/requirements.txt` | 补充 `oss2` 依赖 |

关于你提到的 **C 盘突然少了几个 G**，这个现象与我前面建议“尽量把运行数据放到 E 盘”并不矛盾。原因在于，Docker Desktop 在 Windows 上启用 WSL 2 backend 后，**默认会把 WSL 2 引擎数据先放在 `C:\Users\[用户名]\AppData\Local\Docker\wsl`**；即使你之后把 **Disk image location** 切换到 E 盘，安装程序本体、部分缓存、以及 WSL 初始化时已经创建过的内容，仍然可能先占用一部分 C 盘空间[1]。与此同时，Microsoft 官方也明确说明，**WSL 2 会为发行版创建会自动扩张的 `ext4.vhdx` 虚拟磁盘文件**，因此安装 WSL、首次启动 `docker-desktop` 或构建镜像后，C 盘出现数 GB 级别增长是常见现象[2]。

> 也就是说，你这次看到的 C 盘下降，**大概率不是项目代码占用的**，而是 Docker Desktop 安装体、WSL 发行版虚拟盘、以及 Docker/WSL 初始化时产生的缓存共同造成的短期增长。

如果你后续还想继续把 C 盘压回去，建议先不要立刻大清理，而是优先确认以下三件事：第一，Docker Desktop 的 **Disk image location** 是否已经稳定指向 `E:\kol_lens\runtime\docker-data`；第二，`C:\Users\你的用户名\Downloads` 下是否还保留着 Docker Desktop 安装器；第三，`C:\Users\你的用户名\AppData\Local\Docker\wsl` 是否还残留初始化阶段的旧数据。等你把这份压缩包解压到 Windows 后，我可以再继续带你做**不伤当前环境的定点瘦身**。

本压缩包适合你的使用方式是：先解压到 `E:\kol_lens\repo`，然后优先编辑 `backend/.env.production`。如果你想继续沿用自己原来的 PGY token 方式，最简单的做法不是再手填一堆环境变量，而是**把 token 文件放到 `backend/data/token.txt`**；如果你想完全复用现有的 OSS 下载链路，就只需要把 `PGY_OSS_ACCESS_KEY_ID` 与 `PGY_OSS_ACCESS_KEY_SECRET` 填进去即可。视觉识别链路则默认已经为你切到兼容 DashScope 的 Qwen-VL 配置。

## References

[1]: https://docs.docker.com/desktop/features/wsl/ "Docker Docs - WSL 2 backend on Windows"
[2]: https://learn.microsoft.com/en-us/windows/wsl/disk-space "Microsoft Learn - How to manage WSL disk space"
