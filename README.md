# AI破局行动营自动化管理平台

MVP 本地单用户工具，针对"AI破局行动营"的学员/志愿者工作自动化。

## 文档体系

| 文档 | 用途 |
| --- | --- |
| [`AI破局行动营自动化管理平台-PRD(MVP).md`](./AI破局行动营自动化管理平台-PRD(MVP).md) | 需求文档（做什么） |
| [`ui-prototype/design.md`](./ui-prototype/design.md) | UI 设计规范与交互流程 |
| [`ui-prototype/index.html`](./ui-prototype/index.html) | UI 可交互原型（浏览器打开） |
| [`技术方案文档(MVP).md`](./技术方案文档(MVP).md) | 技术方案（怎么做） |

## 技术栈

- **后端**：Python 3.13 + FastAPI + SQLAlchemy 2.0(async) + Pydantic v2 + SQLite + APScheduler + httpx + Anthropic SDK
- **前端**：React 18 + TypeScript + Vite 5 + Ant Design 5 + React Query + Zustand + axios
- **存储**：SQLite 单文件（`backend/data/app.db`）
- **大模型**：直接调官方 SDK（默认 Claude），提示词外置 `app/ai/prompts/`

## 目录结构

```
pojuActionCamp/
├── AI破局行动营自动化管理平台-PRD(MVP).md    # 需求文档
├── 技术方案文档(MVP).md                     # 技术方案
├── ui-prototype/                            # UI 原型（HTML + design.md）
├── Makefile                                 # 一键命令
├── backend/                                 # 后端（FastAPI）
│   ├── pyproject.toml                       # uv 管理依赖
│   ├── alembic.ini + alembic/               # 数据库迁移
│   ├── data/                                # 运行时数据（不入库）
│   │   ├── app.db                           # SQLite 数据库
│   │   └── manuals/{camp_id}/               # 手册文件
│   └── app/
│       ├── main.py                          # FastAPI 入口
│       ├── config.py                        # pydantic-settings 配置
│       ├── database.py                      # async engine/session/Base
│       ├── core/                            # 异常/日志/统一响应
│       ├── models/                          # 9 个 ORM 模型
│       ├── schemas/                         # Pydantic 请求/响应
│       ├── services/                        # 业务服务层（8 个）
│       ├── api/                             # API 路由（6 个模块）
│       ├── ai/                              # AI 编排（LLMClient + 3 提示词）
│       ├── poju/                            # 破局接口适配（PojuClient）
│       └── scheduler/                       # APScheduler 定时任务
└── frontend/                                # 前端（Vite + React）
    ├── package.json
    ├── vite.config.ts                       # 含 /api → 8000 代理
    └── src/
        ├── main.tsx + App.tsx               # 入口与路由
        ├── api/                             # axios + 各模块 API
        ├── stores/                          # Zustand
        ├── hooks/                           # React Query 封装
        ├── components/                      # Layout / StarPicker / Tag
        ├── pages/                           # 11 个页面
        │   ├── Home.tsx
        │   ├── CreateCamp.tsx
        │   ├── student/                     # 学员 3 页面
        │   ├── volunteer/                   # 志愿者 3 页面
        │   ├── Manual.tsx
        │   ├── Scoring.tsx
        │   └── Settings.tsx
        └── styles/tokens.css                # 设计令牌
```

## 快速启动

### 环境要求
- Python 3.12+（推荐 3.13）
- Node.js 18+（推荐 22）
- [uv](https://docs.astral.sh/uv/) 管理 Python 依赖
- pnpm（或 npm）管理前端依赖

### 首次配置

1. **后端依赖与数据库**
   ```bash
   cd backend
   uv sync
   cp .env.example .env
   # 编辑 .env，至少填入 LLM_API_KEY（用于 AI 编排）
   uv run alembic upgrade head     # 初始化数据库 + 种子数据
   ```

2. **前端依赖**
   ```bash
   cd frontend
   pnpm install
   ```

### 一键启动（推荐）

回到项目根目录：
```bash
make dev
```
此命令同时拉起后端（`http://localhost:8000`）与前端（`http://localhost:5173`），Ctrl-C 全部停止。

### 分别启动

**后端**：
```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

**前端**：
```bash
cd frontend && pnpm dev
```

打开浏览器访问 **http://localhost:5173**，前端通过 Vite proxy 自动转发 `/api/*` 到后端 8000。

### 其他命令

```bash
make backup            # 打包 data/ 到 backups/
make backend-migrate   # 重新执行 alembic 迁移
```

## MVP 功能范围

### 行动营管理
- ✅ 创建/列表/删除行动营（学员或志愿者身份）
- ✅ 行动营状态自动流转（未开始/进行中/已结束）

### 学员身份
- ✅ 学习路线自动规划（基于手册 + 总天数，AI 自主拆分）
- ✅ 今日看板（每天该干什么 + 进度）
- ✅ 打卡内容 AI 生成（四板块：今日行动/收获/好事/下一步）
- ✅ 打卡提交（手动复制 / 自动调破局接口，开关切换）

### 志愿者身份
- ✅ 志愿者看板（学员列表 + 统计 + 同步）
- ✅ 学员档案（每学员×每营独立档案，含历史打卡）
- ✅ AI 作业评改（结合手册 + 学员档案生成星级 + 评语）
- ✅ 确认同步到破局（写接口失败可重试，**本地评改不丢失**）
- ✅ 定时拉取（APScheduler，默认每日 09:00）

### 全局
- ✅ 手册管理（上传/粘贴/预览，**与获取手段解耦**）
- ✅ 评分标准（5 维度初版 + 可配置）
- ✅ 破局 Token 配置 + 测试连接

### MVP 明确不包含
- ❌ 多用户/账号体系
- ❌ 云端部署（仅本地）
- ❌ 微信自动化（拉群/发通知/提醒）
- ❌ 手册自动 OCR/抓取（手动上传）

## 破局接口

接口来源为发起人通过浏览器抓包获取的内部接口，需 `Authorization` 请求头鉴权。MVP 手动登录后从浏览器复制 Token，配置到「接口配置」页（Token 加密存储）。

接口能力清单在 **接口配置页** 可视化：
- ✅ 拉取学员打卡记录（读，已验证）
- ✅ 给学员作业打分和评价（写，已验证）
- ⏳ 提交学员打卡（写，**待确认**）
- ⏳ 读取学员自身进度（读，**待确认**）

最新志愿者看板接口开放后，需更新 `backend/app/poju/endpoints.py` 的真实路径与字段映射。

## 降级策略

| 场景 | 降级行为 |
| --- | --- |
| 自动提交接口不可用 | 强制手动复制提交 + UI 提示 |
| 评改同步写接口失败 | 本地评改保留，`synced_to_poju=false`，可重试 |
| 读接口/Token 失效 | 标记失效状态，保留已有数据，支持手动重试 |
| 手册未配置 | AI 功能降级运行（仅基于输入生成）+ 提示 |
| 大模型调用失败 | 提示失败 + 重试，不影响已有数据 |

## 开发规范

- **代码与注释中文**（对齐全局 CLAUDE.md）
- **后端异步优先**（async/await + AsyncSession）
- **统一响应格式** `{code, message, data}` + 业务异常 → HTTP 状态码（详见技术方案 8.4）
- **错误码约定**：1001 校验失败 / 1002 资源不存在 / 2001 Token 失效 / 2002 接口错误 / 2003 接口待确认 / 3001 LLM 失败 / 3002 手册未配置 / 5000 服务器错误

## 数据备份

```bash
make backup
```
打包 `backend/data/` 到 `backups/poju-YYYYMMDD-HHMMSS.tar.gz`，含 SQLite 数据库与手册文件。

## 后续演进（MVP 之外）

预留能力（详见技术方案 16）：
- 多用户/账号体系
- 云端部署（SQLite 平滑换 PostgreSQL）
- 自动评改/自动提交（开关设计已就位）
- 手册自动获取（OCR 集成）
- 微信自动化
- 同一期多身份
- 跨期数据复盘
- RAG 检索增强（手册向量索引）

---

**当前状态**：MVP 完整实现，**13,828 行代码**（后端 56 Python 文件 + 前端 30 TS/CSS 文件），前后端联调通过。

提交历史：
```
02ed8ce feat(frontend): 完整前端 - 脚手架+11页面+AntD+React Query
6900ab3 feat(backend): W2 后端业务 - 8服务+6API+调度器端到端可用
cf8d784 feat(backend): W1 后端地基 - 基础设施/模型/Schema/AI层/破局客户端/迁移
fb8a8ae docs: PRD/UI原型/技术方案文档
```
