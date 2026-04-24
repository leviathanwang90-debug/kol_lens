# `kol_lens` 云服务器部署清单与启动顺序

## 一、部署目标

这份清单按你给定的目标整理：代码直接落在服务器 **`/home/red/work/kol_lens`**，域名使用 **`lens.red-magic.cn`**，Nginx 配置风格参考你提供的 `ctmagic.red-magic.cn.conf`，后端服务监听 **`127.0.0.1:3007`**，由 Nginx 对外暴露 HTTPS 域名入口。

当前项目最适合采用的部署拓扑，是 **Nginx 直接托管前端静态产物**，并把 `/api/` 路由反向代理到本机 FastAPI 服务。这样与你给的参考配置保持一致，也最适合当前仓库结构。

| 层 | 建议部署方式 | 实际路径 / 端口 |
|---|---|---|
| 代码目录 | Git 克隆到固定目录 | `/home/red/work/kol_lens` |
| 前端 | `pnpm build` 后由 Nginx 直接托管静态文件 | `/home/red/work/kol_lens/frontend/dist/public` |
| 后端 | `uvicorn` + `systemd` 常驻运行 | `127.0.0.1:3007` |
| 域名入口 | Nginx `server_name lens.red-magic.cn` | 80/443 |
| 数据库 | PostgreSQL | 建议本机 `5432` |
| 缓存 | Redis | 建议本机 `6379` |
| 向量库 | Milvus | 建议本机 `19530` |

## 二、部署前置检查清单

在正式执行启动前，建议先把下面这些基础条件确认完整。这里面前四项是硬条件，后面的几项决定你能否测完整链路。

| 类别 | 必须性 | 说明 |
|---|---|---|
| Git 权限 | 必须 | 服务器需要能拉取 `leviathanwang90-debug/kol_lens` 仓库 |
| Python 3.11+ | 必须 | 后端依赖 `fastapi`、`uvicorn`、`pymilvus`、`psycopg2-binary` |
| Node.js 22+ 与 `pnpm` | 必须 | 用于前端安装依赖与构建 |
| Nginx | 必须 | 域名反代与 HTTPS 入口 |
| PostgreSQL | 必须 | 资产库、历史、模板与履约记录都依赖它 |
| Redis | 强烈建议 | 虽然有降级路径，但缓存和部分任务链路最好启用 |
| Milvus | 必须 | 检索、向量匹配、Fission 下一批推荐都依赖它 |
| OpenAI 兼容密钥 | 建议 | 意图解析与部分补充能力更稳定 |
| 蒲公英扩库鉴权 | 视测试范围而定 | 若要测扩库与补库，必须配置 |
| 全量达人补充接口 Cookie / Header | 视测试范围而定 | 若要测“一键补充数据 / 导出”，必须配置 |

## 三、推荐目录结构

建议在服务器上保持如下目录结构。这样既利于后续更新，也利于 systemd 与 Nginx 配置引用固定路径。

```text
/home/red/work/
└── kol_lens/
    ├── backend/
    │   ├── app.py
    │   ├── requirements.txt
    │   ├── .venv/
    │   └── .env.production
    ├── frontend/
    │   ├── package.json
    │   ├── client/
    │   └── dist/public/
    └── logs/
```

## 四、首次部署启动顺序

### 第 1 步：创建工作目录并拉代码

如果服务器上还没有仓库，建议先进入工作目录，然后直接克隆到目标位置。

```bash
mkdir -p /home/red/work
cd /home/red/work
git clone <你的仓库地址> kol_lens
cd /home/red/work/kol_lens
```

如果你已经在服务器上配置好了 GitHub CLI，也可以使用：

```bash
gh repo clone leviathanwang90-debug/kol_lens /home/red/work/kol_lens
```

### 第 2 步：准备后端 Python 虚拟环境

后端建议独立虚拟环境，不要把依赖直接装到系统 Python。

```bash
cd /home/red/work/kol_lens/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 第 3 步：准备前端依赖并构建

当前前端可直接构建为静态文件，然后由 Nginx 托管，不需要额外常驻 Node 前端进程。

```bash
cd /home/red/work/kol_lens/frontend
pnpm install
pnpm build
```

构建产物会输出到：

```text
/home/red/work/kol_lens/frontend/dist/public
```

### 第 4 步：准备后端环境变量文件

建议在下面这个位置放生产环境变量文件：

```text
/home/red/work/kol_lens/backend/.env.production
```

建议模板如下。

```bash
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=sigma_match
POSTGRES_USER=sigma
POSTGRES_PASSWORD=请替换为真实密码

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=请替换为真实密码

MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

OPENAI_API_KEY=请替换为真实值
KOL_LENS_INTENT_MODEL=gpt-4.1-mini
KOL_LENS_EMBEDDING_MODEL=text-embedding-3-small
KOL_LENS_DISABLE_LLM=0

PGY_AUTHORIZATION=如需扩库请配置
PGY_COOKIE=如需扩库请配置
PGY_TRACE_ID=可选
PGY_BRAND_USER_ID=可选
PGY_BLOGGER_SEARCH_URL=可选，若不填则走代码默认值

PGY_COOKIE_HEADER=如需全量达人补充数据请配置
PGY_COOKIE_HEADERS=可选多行配置
PGY_COOKIE_FILE=可选，本地 cookie 文件路径
CREATOR_DATA_VL_MODEL=gpt-4.1-mini
```

## 五、基础设施启动顺序

当前项目不是“只启动一个 Web 服务”就能完整可用，而是依赖数据库、缓存和向量库。建议严格按下面顺序处理。

| 顺序 | 组件 | 说明 |
|---|---|---|
| 1 | PostgreSQL | 先保证业务主库可连接 |
| 2 | Redis | 再启动缓存与任务状态依赖 |
| 3 | Milvus | 再启动向量检索依赖 |
| 4 | 执行数据库初始化 | 导入表结构与基础字典 |
| 5 | 启动 FastAPI 后端 | 监听 `127.0.0.1:3007` |
| 6 | 构建前端静态文件 | 生成 Nginx root 所需产物 |
| 7 | 配置并重载 Nginx | 将 `lens.red-magic.cn` 对外开放 |
| 8 | 执行人工联调 | 从页面到 API 做完整手测 |

### 数据库初始化命令

如果数据库是新建的，至少先执行项目里的初始化 SQL。

```bash
psql -h 127.0.0.1 -p 5432 -U sigma -d sigma_match -f /home/red/work/kol_lens/backend/db/migrations/init.sql
```

如果你的数据库用户名、库名和密码不同，请替换成真实值。

## 六、后端启动方式

### 方案 A：先手工启动验证

第一次建议先手工跑起来，确认依赖和环境变量没有问题。

```bash
cd /home/red/work/kol_lens/backend
source .venv/bin/activate
set -a
source .env.production
set +a
uvicorn app:app --host 127.0.0.1 --port 3007
```

如果你看到服务成功监听在 `127.0.0.1:3007`，说明后端主进程已经可以运行。

### 方案 B：改为 systemd 常驻

建议创建：

```text
/etc/systemd/system/kol-lens-backend.service
```

参考内容如下。

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

然后执行：

```bash
mkdir -p /home/red/work/kol_lens/logs
sudo systemctl daemon-reload
sudo systemctl enable kol-lens-backend
sudo systemctl start kol-lens-backend
sudo systemctl status kol-lens-backend
```

## 七、Nginx 部署方式

你给的参考配置是“**HTTP 强制跳 HTTPS + HTTPS server 直接托管前端静态目录 + `/api/` 反代后端**”结构。`kol_lens` 很适合直接沿用这一模式，只需要把域名、root 路径和 API 端口改掉即可。

建议新增文件：

```text
/etc/nginx/conf.d/lens.red-magic.cn.conf
```

我已经按你的要求整理了一份可直接参考的版本，见附件 `lens.red-magic.cn.conf`。核心思路如下。

| 配置项 | 建议值 |
|---|---|
| `server_name` | `lens.red-magic.cn` |
| `root` | `/home/red/work/kol_lens/frontend/dist/public` |
| `location /` | `try_files $uri $uri/ /index.html;` |
| `location /api/` | `proxy_pass http://127.0.0.1:3007;` |
| 证书路径 | 先按你现有通配符证书目录写，如 `/etc/nginx/ssl/red-magic.cn/` |

Nginx 生效命令：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 八、建议的人工测试顺序

云上服务起来之后，不建议一上来就测最复杂的链路，而是按以下顺序逐层验证。

| 顺序 | 手测项 | 通过标准 |
|---|---|---|
| 1 | 访问 `https://lens.red-magic.cn` | 前端首页正常打开 |
| 2 | 访问 `/api/v1/...` 基础接口 | Nginx 能反代到 3007 |
| 3 | 自然语言解析 | 意图确认弹窗能拿到结构化 tag 与指标 |
| 4 | 首轮检索 | 能正常返回达人列表 |
| 5 | Fission 下一批推荐 | `selected/rejected` 后能拿到下一批与解释信息 |
| 6 | `assets/commit` | 确认入库后 `library/list`、`library/history` 可见 |
| 7 | 历史下钻 | 达人时间线、履约详情和素材详情能打开 |
| 8 | 一键补充数据 | 选中达人后能补齐字段表格 |
| 9 | 字段导出 + 模板保存 | CSV 导出成功，模板能保存并复用 |
| 10 | 扩库与补库 | 若已配置 PGY 鉴权，则扩库链路可测通 |

## 九、更新发布顺序

后续你如果只是更新代码，建议使用下面这套发布顺序，避免把线上状态打乱。

| 顺序 | 操作 |
|---|---|
| 1 | `cd /home/red/work/kol_lens && git pull` |
| 2 | 后端有依赖变化时：重新 `pip install -r requirements.txt` |
| 3 | 前端有变更时：`cd frontend && pnpm install && pnpm build` |
| 4 | 后端有代码变更时：`sudo systemctl restart kol-lens-backend` |
| 5 | Nginx 配置有变更时：`sudo nginx -t && sudo systemctl reload nginx` |
| 6 | 最后做一次关键链路冒烟测试 |

## 十、最推荐你直接执行的落地顺序

如果你想要一版最省事、最不容易出错的实际执行路径，我建议就是下面这 12 步，按顺序做。

```bash
mkdir -p /home/red/work
cd /home/red/work

# 1) 拉代码
# git clone <repo> kol_lens

# 2) 后端环境
cd /home/red/work/kol_lens/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 3) 写 .env.production
# vim /home/red/work/kol_lens/backend/.env.production

# 4) 初始化数据库
psql -h 127.0.0.1 -p 5432 -U sigma -d sigma_match -f /home/red/work/kol_lens/backend/db/migrations/init.sql

# 5) 前端构建
cd /home/red/work/kol_lens/frontend
pnpm install
pnpm build

# 6) 创建日志目录
mkdir -p /home/red/work/kol_lens/logs

# 7) 写 systemd 服务
# vim /etc/systemd/system/kol-lens-backend.service
sudo systemctl daemon-reload
sudo systemctl enable kol-lens-backend
sudo systemctl start kol-lens-backend

# 8) 写 Nginx 配置
# vim /etc/nginx/conf.d/lens.red-magic.cn.conf
sudo nginx -t
sudo systemctl reload nginx

# 9) 冒烟测试
curl http://127.0.0.1:3007/docs
curl -I https://lens.red-magic.cn
```

## 十一、当前最需要你提前准备的配置项

真正上云时，最容易卡住的不是代码，而是下面这几类外部参数。建议你在动手部署前先准备齐。

| 类别 | 你需要准备的内容 |
|---|---|
| Git | 仓库拉取权限 |
| HTTPS | `lens.red-magic.cn` 的证书或可复用通配符证书 |
| PostgreSQL | 库名、用户名、密码 |
| Redis | 密码 |
| Milvus | 地址与端口 |
| LLM | `OPENAI_API_KEY` |
| 扩库 | `PGY_AUTHORIZATION` / `PGY_COOKIE` |
| 达人全量数据补充 | `PGY_COOKIE_HEADER` 或 `PGY_COOKIE_FILE` |

## 十二、结论

按当前项目状态，**完全可以开始部署到云服务器做手动测试**。最稳妥的方式，就是采用这份文档里的结构：**Nginx 托管前端静态文件，FastAPI 后端跑在 3007，PostgreSQL / Redis / Milvus 作为内网依赖服务**。这样既符合你给的参考配置，也与当前仓库代码结构最匹配。

如果你愿意，我下一步可以继续帮你补两份可以直接拿到服务器上用的文件：其一是 **`kol-lens-backend.service` 的完整 systemd 文件**，其二是 **最终可直接落盘的 `lens.red-magic.cn.conf` 正式版**。
