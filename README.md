# KOL Lens — Σ.Match 智能寻星工作站

> 基于多模态 AI 的 KOL（关键意见领袖）智能匹配与资产管理平台

## 项目概述

Σ.Match 是 Σ.magic 旗下的智能达人匹配工作站，通过自然语言意图解析、多模态特征提取（YOLO + InsightFace + CLIP）、Milvus 向量检索和 Rocchio 反馈进化算法，实现"对话式寻星 → 沉浸式评审 → 资产化沉淀"的全链路 KOL 管理能力。

## 仓库结构

```
kol_lens/
├── docs/                          # 项目文档
│   ├── SigmaMatch_Frontend_PRD.md           # 前端产品需求文档（PRD）
│   ├── SigmaMatch_Development_Roadmap.md    # 开发路线图（6 Sprint）
│   ├── SigmaMatch_Sprint_Tasklist.md        # 详细任务清单（74 个任务）
│   ├── backend_logic_summary.md             # 后端逻辑摘要
│   ├── 原始需求_Gemini聊天记录.docx          # 原始需求文档
│   └── 创意逻辑_用户洞察_落地建议（极深全图景拆解）.docx
├── frontend/                      # 前端项目（React + TypeScript + Tailwind）
│   ├── client/                    # 客户端源码
│   │   ├── src/
│   │   │   ├── pages/             # 页面组件（Home / Workspace / Library）
│   │   │   ├── components/        # 通用组件（Navbar / ParticleBackground / UI）
│   │   │   ├── contexts/          # React Context（主题管理）
│   │   │   ├── hooks/             # 自定义 Hooks
│   │   │   └── lib/               # 工具函数与常量
│   │   └── index.html
│   ├── server/                    # 服务端入口（Express 静态服务）
│   ├── shared/                    # 前后端共享类型
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── ideas.md                   # 设计构思文档
└── assets/                        # 品牌资产
    └── logo.jpg                   # Σ.magic 公司 Logo
```

## 技术栈

### 前端（已实现）
- **框架**：React 19 + TypeScript
- **构建**：Vite 7
- **样式**：Tailwind CSS 4 + shadcn/ui
- **动效**：Framer Motion
- **路由**：Wouter
- **图表**：Recharts

### 后端（规划中）
- **API 框架**：FastAPI / Flask
- **向量数据库**：Milvus（HNSW 索引）
- **关系数据库**：PostgreSQL 15
- **缓存**：Redis 7
- **异步队列**：Celery + Redis Broker
- **AI 模型**：YOLO v8 + InsightFace + CLIP ViT-L/14

## 核心页面

| 页面 | 路由 | 功能 |
|------|------|------|
| 首页 Landing | `/` | 产品介绍、核心能力展示、数据维度矩阵 |
| 智能检索工作台 | `/workspace` | 对话式意图输入、弹性寻回终端、数据矩阵、沉浸式评审 |
| 达人资产库 | `/library` | 多维筛选、履约历史时间轴、智能导出 |

## 开发路线图

| Sprint | 阶段 | 工期 | 状态 |
|--------|------|------|------|
| Sprint 1 | 基建层（PostgreSQL + Milvus + Redis） | 2 周 | 待开发 |
| Sprint 2 | 解剖层（多模态特征提取 DAG） | 3 周 | 待开发 |
| Sprint 3 | 大脑层（Hybrid Ranking + Rocchio） | 2 周 | 待开发 |
| Sprint 4 | 调度层（Celery + API 接口） | 2 周 | 待开发 |
| Sprint 5 | 触点层（前后端联调 + LLM 集成） | 3 周 | 待开发 |
| Sprint 6 | 联调上线（测试 + 优化 + 部署） | 2 周 | 待开发 |

详细任务清单见 `docs/SigmaMatch_Sprint_Tasklist.md`（共 74 个任务，约 70.5 人天）。

## 本地开发

```bash
cd frontend
pnpm install
pnpm dev
```

访问 `http://localhost:3000` 查看前端页面。

## 设计风格

采用**暗夜星图（Dark Constellation）**设计语言：
- **色彩**：深空黑 `#080808` + 品牌红 `#D4001A` + 暖金 `#FFB800`
- **字体**：Space Grotesk（标题） + Noto Sans SC（正文）
- **特效**：Canvas 粒子连线背景 + 扫描线叠加层 + 发光边框
- **隐喻**：每个达人是一颗星，品牌偏好是星座连线

---

*Σ.magic © 2026*
