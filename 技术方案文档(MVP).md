# AI破局行动营自动化管理平台 · 技术方案文档（MVP）

| 项目 | 内容 |
| --- | --- |
| 文档名称 | 技术方案文档 |
| 版本 | v0.1（MVP） |
| 编写日期 | 2026-06-27 |
| 依赖文档 | 《AI破局行动营自动化管理平台-PRD(MVP).md》、《ui-prototype/design.md》 |
| 定位 | MVP 本地单用户工具，前后端分离，本地双进程运行 |
| 文档状态 | 技术方案稿，待评审 |

> 本文档是 PRD 与 UI 确认后的技术实现方案，覆盖系统架构、技术选型、目录结构、数据模型、模块设计、接口设计、AI 编排、定时任务、降级策略等。文档不展开到逐行代码，但提供足够的实现约束与关键代码示例，使后续开发可直接据此落地。

---

## 一、技术选型

### 1.1 选型总览

| 层 | 选型 | 版本 | 选型理由 |
| --- | --- | --- | --- |
| 后端框架 | FastAPI | 0.115+ | 异步、自带 OpenAPI 文档、类型友好、生态成熟 |
| 定时任务 | APScheduler | 3.10+ | Python 生态成熟，支持定时/间隔/持久化，适合本地常驻 |
| 大模型接入 | 官方 SDK（anthropic / openai） | latest | 前期灵活调提示词，避免框架抽象损耗 |
| ORM | SQLAlchemy 2.0 + Alembic | 2.0+ | 声明式模型 + 迁移管理，配合 SQLite |
| 数据库 | SQLite | 内置 | 单文件、零配置、关系型，本地单用户最佳平衡 |
| 数据校验 | Pydantic v2 | 2.x | FastAPI 原生集成，模型即文档 |
| HTTP 客户端 | httpx | 0.27+ | 异步、支持拦截器，用于调破局接口 |
| 前端框架 | React 18 + TypeScript | 18+ | 生态成熟，组件库丰富，原型迁移顺 |
| 前端构建 | Vite | 5+ | 极速 HMR，TS 原生支持 |
| 前端组件 | Ant Design 5 | 5+ | 表单/表格/统计/导航组件齐全，适配后台型工具 |
| 前端状态 | Zustand + React Query | latest | 轻量全局状态 + 服务端数据缓存 |
| 包管理 | pnpm（前端）/ uv（后端） | latest | 各生态最佳实践 |

### 1.2 关键决策说明

**为什么后端选 Python + FastAPI**
- 大模型 SDK、文档处理、提示词工程在 Python 生态最成熟。
- 发起人上一期已有 Python 自动化脚本经验，破局接口调用逻辑可复用。
- FastAPI 异步特性可并行调用大模型与破局接口，对评改批量场景友好。

**为什么直接调官方 SDK 而非 LangChain**
- MVP 核心是提示词调优与流程编排，LangChain 的抽象会增加调试成本。
- 官方 SDK 配合自封装的轻量 Prompt 模板层，灵活可控，便于前期迭代。
- 后续若需 RAG（手册内容检索增强），再按需引入向量库与检索层，不提前引入。

**为什么选 SQLite 而非 PostgreSQL**
- 单用户本地工具，无并发写入压力（SQLite 单写者模型够用）。
- 单文件随项目走，零运维，备份即拷贝文件。
- 关系型支持学员档案 × 打卡记录 × 行动营等多表关联查询。

**为什么前端选 React + Ant Design**
- 后台型工具，表单/表格/统计/导航为主，Ant Design 开箱即用。
- UI 原型已用 HTML/CSS 充分表达布局，迁移到 AntD 组件映射清晰。
- TS 类型贯穿前后端（FastAPI 自动生成 OpenAPI → 前端类型），减少联调成本。

---

## 二、系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      浏览器（本地访问）                        │
│                   http://localhost:5173                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│  前端  React + Vite + TS + AntD (5173)                        │
│  - 行动营管理 / 学员工作台 / 志愿者工作台                       │
│  - Zustand(全局状态) + React Query(服务端数据)                 │
│  - 调用 /api/* 与后端交互                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────▼──────────────────────────────────┐
│  后端  FastAPI (8000)                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────────┐ │
│  │ API 路由层   │ │ AI 编排层    │ │ 破局接口适配层           │ │
│  │ /camps      │ │ LLMClient    │ │ PojuClient(httpx)      │ │
│  │ /student/*  │ │ PromptEngine │ │ - 拉取看板(读)          │ │
│  │ /volunteer/*│ │ (路线/打卡/  │ │ - 提交打卡(写)          │ │
│  │ /manual     │ │  评改)       │ │ - 作业打分(写)          │ │
│  │ /scoring    │ │              │ │ - 鉴权/重试/降级        │ │
│  │ /settings   │ │              │ │                        │ │
│  └─────────────┘ └─────────────┘ └────────────────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────────┐ │
│  │ 业务服务层    │ │ 定时任务层    │ │ 基础设施层              │ │
│  │ CampService │ │ Scheduler    │ │ DB(SQLite+SQLAlchemy)  │ │
│  │ CheckinSvc  │ │ (APScheduler)│ │ Config(.env)           │ │
│  │ GradingSvc  │ │ - 定时拉看板  │ │ Logger                 │ │
│  │ ArchiveSvc  │ │ - Token校验  │ │ Error Handler          │ │
│  └─────────────┘ └─────────────┘ └────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────────┐
        │ 大模型API │ │ 破局平台  │ │ 本地文件系统  │
        │ Claude/  │ │ (抓包接口)│ │ - 手册md文件  │
        │ OpenAI   │ │          │ │ - SQLite库    │
        └──────────┘ └──────────┘ │ - 日志文件    │
                                   └──────────────┘
```

### 2.2 进程模型

MVP 为**本地双进程**：

| 进程 | 端口 | 启动命令 | 说明 |
| --- | --- | --- | --- |
| 后端 API | 8000 | `uv run uvicorn app.main:app` | FastAPI + APScheduler 常驻 |
| 前端 Dev | 5173 | `pnpm dev` | Vite 开发服务器，代理 /api → 8000 |

- 后端启动时自动初始化 APScheduler，定时任务随进程常驻。
- 前端通过 Vite proxy 将 `/api` 转发到后端 8000，开发无跨域问题。
- 一键启动脚本 `make dev` / `dev.sh` 同时拉起前后端。

### 2.3 请求流转示例（评改同步）

```
前端 [确认并同步]
  → POST /api/volunteer/grades {student_id, checkin_id, stars, comment}
    → GradingService.sync_grade()
      → 1. 写本地 DB（grades 表，status=pending_sync）
      → 2. 调 PojuClient.submit_grade()（带 Authorization）
        → 成功：更新 status=synced，写入 student_archive
        → 失败：保持 status=pending_sync，返回错误，前端提示重试
```

---

## 三、目录结构

### 3.1 项目根目录

```
pojuActionCamp/
├── AI破局行动营自动化管理平台-PRD(MVP).md      # 需求文档
├── ui-prototype/                              # UI 原型（已存在）
│   ├── index.html
│   └── design.md
├── 技术方案文档(MVP).md                        # 本文档
├── README.md
├── Makefile                                   # 一键命令
├── .gitignore
├── .env.example                               # 环境变量模板
│
├── backend/                                   # 后端（Python + FastAPI）
└── frontend/                                  # 前端（React + Vite + TS）
```

### 3.2 后端目录结构

```
backend/
├── pyproject.toml                             # uv 管理依赖
├── alembic.ini                                # 数据库迁移配置
├── .env                                       # 环境变量（不入库）
├── data/                                      # 运行时数据（不入库）
│   ├── app.db                                 # SQLite 数据库
│   ├── manuals/                               # 手册文件存储
│   │   └── {camp_id}/manual.md
│   └── logs/                                  # 日志文件
│
├── alembic/                                   # 数据库迁移
│   ├── env.py
│   └── versions/
│
└── app/
    ├── main.py                                # FastAPI 入口，挂载路由 + 启动调度器
    ├── config.py                              # 配置加载（pydantic-settings）
    ├── database.py                            # SQLAlchemy 引擎/会话
    ├── deps.py                                # 依赖注入（DB session 等）
    │
    ├── models/                                # SQLAlchemy ORM 模型
    │   ├── __init__.py
    │   ├── camp.py                            # 行动营
    │   ├── manual.py                          # 手册
    │   ├── study_route.py                     # 学习路线 + 每日任务
    │   ├── checkin.py                         # 打卡记录（学员）
    │   ├── student.py                         # 学员（志愿者带教）
    │   ├── archive.py                         # 学员档案/打卡评改记录
    │   ├── grade.py                           # 评改结果
    │   ├── scoring.py                         # 评分标准
    │   └── settings.py                        # 接口配置/Token
    │
    ├── schemas/                               # Pydantic 请求/响应模型
    │   ├── camp.py
    │   ├── student.py
    │   ├── volunteer.py
    │   ├── manual.py
    │   ├── grading.py
    │   └── common.py                          # 分页、统一响应等
    │
    ├── api/                                   # API 路由层
    │   ├── __init__.py
    │   ├── router.py                          # 路由聚合
    │   ├── camps.py                           # 行动营管理
    │   ├── student.py                         # 学员功能
    │   ├── volunteer.py                       # 志愿者功能
    │   ├── manual.py                          # 手册管理
    │   ├── scoring.py                         # 评分标准
    │   └── settings.py                        # 接口配置
    │
    ├── services/                              # 业务服务层
    │   ├── camp_service.py                    # 行动营 CRUD + 状态流转
    │   ├── route_service.py                   # 学习路线规划
    │   ├── checkin_service.py                 # 打卡内容生成 + 提交
    │   ├── grading_service.py                 # 作业评改生成 + 同步
    │   ├── archive_service.py                 # 学员档案维护
    │   ├── manual_service.py                  # 手册管理
    │   └── scoring_service.py                 # 评分标准
    │
    ├── ai/                                    # AI 编排层
    │   ├── llm_client.py                      # 大模型客户端封装
    │   ├── prompt_engine.py                   # 提示词管理/渲染
    │   ├── prompts/                           # 提示词模板（文本文件，便于调优）
    │   │   ├── route_plan.txt                 # 学习路线规划
    │   │   ├── checkin_gen.txt                # 打卡内容生成
    │   │   └── grading.txt                    # 作业评改
    │   └── schemas.py                         # AI 输出结构定义
    │
    ├── poju/                                  # 破局接口适配层
    │   ├── client.py                          # PojuClient(httpx)
    │   ├── endpoints.py                       # 接口定义（URL/方法/字段映射）
    │   ├── auth.py                            # Token 管理/校验
    │   └── exceptions.py                      # 接口异常定义
    │
    ├── scheduler/                             # 定时任务
    │   ├── scheduler.py                       # APScheduler 初始化
    │   ├── jobs.py                            # 任务定义
    │   └── store.py                           # 任务持久化（SQLAlchemyJobStore）
    │
    ├── core/                                  # 基础设施
    │   ├── exceptions.py                      # 业务异常 + 处理器
    │   ├── logging.py                         # 日志配置
    │   └── storage.py                         # 文件存储抽象（手册等）
    │
    └── tests/                                 # 测试
        ├── conftest.py
        ├── test_camps.py
        ├── test_grading.py
        └── test_poju_client.py
```

### 3.3 前端目录结构

```
frontend/
├── package.json
├── vite.config.ts                             # 含 /api 代理到 8000
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx                                # 根组件 + 路由
│   ├── api/                                   # API 客户端
│   │   ├── client.ts                          # axios 封装 + 拦截器
│   │   ├── camps.ts
│   │   ├── student.ts
│   │   ├── volunteer.ts
│   │   └── types.ts                           # 后端 OpenAPI 生成类型
│   ├── stores/                                # Zustand 全局状态
│   │   └── campStore.ts
│   ├── pages/                                 # 页面（对应 UI 11 个页面）
│   │   ├── Home.tsx                           # 行动营列表
│   │   ├── CreateCamp.tsx                     # 创建行动营
│   │   ├── student/
│   │   │   ├── Dashboard.tsx                  # 学员今日看板
│   │   │   ├── Route.tsx                      # 学习路线
│   │   │   └── Checkin.tsx                    # 打卡生成
│   │   ├── volunteer/
│   │   │   ├── Dashboard.tsx                  # 学员看板
│   │   │   ├── Grading.tsx                    # 作业评改
│   │   │   └── Archive.tsx                    # 学员档案
│   │   ├── Manual.tsx                         # 手册管理
│   │   ├── Scoring.tsx                        # 评分标准
│   │   └── Settings.tsx                       # 接口配置
│   ├── components/                            # 通用组件
│   │   ├── Layout.tsx                         # 侧边栏 + 主内容布局
│   │   ├── StatCard.tsx
│   │   ├── StarPicker.tsx
│   │   ├── Switch.tsx
│   │   └── ProgressBar.tsx
│   ├── hooks/                                 # React Query hooks
│   │   ├── useCamps.ts
│   │   ├── useGrading.ts
│   │   └── useCheckin.ts
│   └── styles/                                # 全局样式 + 设计变量
│       └── tokens.css                         # 配色/字号变量（对齐 design.md）
```

---

## 四、数据模型设计

### 4.1 ER 关系总览

```
┌──────────┐ 1   N ┌──────────┐
│   User   │───────│   Camp   │
│(单用户MVP)│       │(行动营)  │
└──────────┘       └────┬─────┘
                        │ 1
              ┌─────────┼─────────────┐
              │ 1       │ 1           │ 1
        ┌─────▼───┐ ┌───▼────┐  ┌─────▼─────┐
        │ Manual  │ │ Route  │  │  Student  │
        │ (手册)  │ │(学习路线)│  │ (学员,N) │
        └─────────┘ └───┬────┘  └─────┬─────┘
                        │ 1           │ 1
                        │ N           │ N
                   ┌────▼───┐    ┌────▼──────────┐
                   │DayTask │    │ CheckinRecord │(档案/评改记录)
                   │(每日任务)│   │ (打卡评改记录) │
                   └────────┘    └────┬──────────┘
                                        │ 1
                                        │ 1
                                   ┌────▼────┐
                                   │  Grade  │
                                   │(评改结果)│
                                   └─────────┘

全局独立：ScoringStandard(评分标准)、PojuConfig(接口配置)
```

### 4.2 核心表结构

> 以下为 SQLAlchemy 模型字段定义。所有表含 `id`(主键)、`created_at`、`updated_at`。时间字段统一存 UTC，展示时转本地。

#### 4.2.1 camps（行动营）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | Integer | PK, autoincrement | |
| name | String(100) | not null | 行动营名称 |
| role | String(20) | not null | 'student' / 'volunteer' |
| description | Text | nullable | 简介 |
| total_days | Integer | not null | 总天数 |
| start_date | Date | not null | 开始日期 |
| end_date | Date | not null | 结束日期 |
| min_checkin_days | Integer | not null | 最低打卡完成天数 |
| status | String(20) | not null, default 'not_started' | not_started/ongoing/ended（计算字段，按日期流转） |
| is_deleted | Boolean | default false | 软删除标记 |

- **status 计算逻辑**：按当前日期与 start/end 比较，查询时动态计算（不落库或落库但定时刷新），PRD BR-F1-4。

#### 4.2.2 manuals（手册）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | Integer | PK | |
| camp_id | Integer | FK camps.id, unique | 一个行动营一份手册 |
| filename | String(200) | | 原始文件名 |
| file_path | String(500) | | 本地存储路径 data/manuals/{camp_id}/ |
| content | Text | | 手册全文（提取后存库，供 AI 读取） |
| word_count | Integer | | 字数 |
| uploaded_at | DateTime | | 上传时间 |

- 手册内容存 DB（`content` 字段）+ 文件系统双存，AI 读取走 DB 字段，避免重复 IO。

#### 4.2.3 study_routes + day_tasks（学习路线，学员身份）

**study_routes**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| camp_id | Integer FK, unique | 一个学员行动营一份路线 |
| generated_at | DateTime | 生成时间 |
| source | String(20) | 'ai' / 'manual' | 

**day_tasks**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| route_id | Integer FK study_routes.id | |
| day_number | Integer | 第几天（1~N） |
| title | String(200) | 任务标题 |
| description | Text | 任务描述 |
| tags | JSON | 标签（手册章节/类型/时长） |
| is_completed | Boolean | 是否完成 |
| edited | Boolean | 是否被人工编辑过 |

#### 4.2.4 students（学员，志愿者身份）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| camp_id | Integer FK camps.id | |
| poju_student_id | String(64) | 破局平台学员唯一标识（接口返回） |
| nickname | String(100) | 昵称 |
| wechat | String(100) nullable | 微信（拉群用） |
| last_synced_at | DateTime | 最近同步时间 |
| unique(camp_id, poju_student_id) | | 跨拉取对齐同一学员 |

#### 4.2.5 checkin_records（打卡评改记录，即学员档案条目）

> 此表既是志愿者侧"学员档案"的数据来源，也记录每次打卡与评改。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| student_id | Integer FK students.id | |
| camp_id | Integer FK camps.id | 冗余，便于按营查询 |
| day_number | Integer | 第几天打卡 |
| checkin_date | Date | 打卡日期 |
| content | Text | 学员打卡内容 |
| images | JSON | 图片信息（URL/路径，来自破局接口） |
| submitted_at | DateTime | 学员提交时间（破局接口返回） |
| poju_checkin_id | String(64) | 破局打卡记录唯一标识 |
| grade_status | String(20) | 'pending'/'graded'（待评改/已评改） |
| stars | Integer nullable | 评改星级 1-3 |
| is_valid | Boolean | 是否有效（stars>=2），计算字段 |
| synced_to_poju | Boolean | 评改是否已同步破局 |
| synced_at | DateTime nullable | 同步时间 |

- **学员档案** = 某学生某营的所有 checkin_records，按日期排序（PRD F3.5）。

#### 4.2.6 grades（评改结果明细，可选合并入 checkin_records）

> MVP 可将评改结果（评语、依据、AI 原始输出）合并进 checkin_records 的扩展字段，避免过度拆表。若需保留 AI 多次生成历史，则独立 grades 表：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| checkin_record_id | Integer FK | |
| stars | Integer | 星级 |
| comment | Text | 评语 |
| dimension_scores | JSON | 维度得分依据 |
| ai_raw_output | Text | AI 原始返回（调试用） |
| source | String(20) | 'ai'/'manual' |
| created_at | DateTime | |

**MVP 决策**：grades 独立表，记录 AI 生成与人工修改历史，checkin_records 只存"最终生效"的星级评语。便于追溯与重评。

#### 4.2.7 scoring_standards（评分标准，全局）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| is_active | Boolean | 是否当前生效（全局一套） |
| dimensions | JSON | 评分维度数组 [{key,name,desc,depends_archive}] |
| star_rules | JSON | 星级判定 {three, two, one} 描述 |
| updated_at | DateTime | |

- 评分标准存 JSON，便于灵活增删维度（PRD BR-F5-1）。

#### 4.2.8 poju_configs（接口配置，全局）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | Integer PK | |
| token | String(500) | Authorization Token（加密存储，见 8.2） |
| base_url | String(200) | 接口基础地址 |
| token_status | String(20) | 'valid'/'invalid'/'unknown' |
| last_checked_at | DateTime | 上次校验时间 |
| updated_at | DateTime | |

#### 4.2.9 scheduler_jobs（APScheduler 持久化）

- APScheduler 用 SQLAlchemyJobStore，表由框架自动管理，存定时任务状态。

### 4.3 数据库迁移

- 使用 Alembic 管理迁移，每次模型变更生成迁移脚本。
- 初始化提供种子数据：默认评分标准（PRD F5 初版）、空接口配置。

---

## 五、模块设计

### 5.1 行动营管理模块（camp_service）

**职责**：行动营 CRUD、状态流转、身份分流。

**核心方法**：
```python
class CampService:
    async def create_camp(self, data: CampCreate) -> Camp
    async def list_camps(self) -> list[CampSummary]
    async def get_camp(self, camp_id: int) -> CampDetail
    async def delete_camp(self, camp_id: int) -> None  # 软删除
    def calc_status(self, camp: Camp, today: date) -> str  # not_started/ongoing/ended
    def calc_min_days(self, total_days: int) -> int  # round(total*0.6)
```

**业务规则实现**：
- 创建时若 role=student 但已结束，状态置 ended。
- 删除为软删除（`is_deleted=true`），关联数据（手册/路线/档案）保留不级联删，列表过滤已删除。
- 状态在查询时动态计算（`calc_status`），不单独落库，避免与日期不一致。

### 5.2 学习路线规划模块（route_service + ai）

**职责**：基于手册 + 总天数 + 起止，AI 规划每日任务；支持编辑/重新规划。

**核心方法**：
```python
class RouteService:
    async def generate_route(self, camp_id: int) -> StudyRoute
    async def get_route(self, camp_id: int) -> StudyRoute
    async def update_day_task(self, task_id: int, data: DayTaskUpdate) -> DayTask
    async def regenerate_route(self, camp_id: int, keep_edits: bool) -> StudyRoute
    def get_today_task(self, camp_id: int) -> DayTask | None  # 按当前日期算 Day N
```

**AI 编排**（见第六章）：
- 输入：手册全文 + 总天数 + 主题。
- 输出：结构化 JSON `[{day_number, title, description, tags}]`。
- 手册无固定结构，提示词要求 AI 按内容量与天数自主拆分（PRD BR-F2.1-1）。
- 重新规划：`keep_edits=true` 时保留人工编辑过的任务（`edited=true`），仅重生成未编辑部分；`false` 全量覆盖（提示确认）。

### 5.3 打卡生成与提交模块（checkin_service + ai + poju）

**职责**：学员输入所做 → AI 生成四板块 → 手动/自动提交。

**核心方法**：
```python
class CheckinService:
    async def generate_checkin(self, camp_id: int, text: str, images: list) -> CheckinDraft
    async def submit_checkin(self, camp_id: int, draft: CheckinDraft, auto: bool) -> SubmitResult
    async def list_checkins(self, camp_id: int) -> list[CheckinRecord]
```

**流程**：
1. `generate_checkin`：调用 AI，输入用户文字 + 今日任务 + 手册相关片段，输出四板块（今日行动/收获/好事/下一步）。返回草稿，不入库。
2. `submit_checkin`：
   - `auto=false`（默认）：将内容返回前端复制，本地记录一条 `checkin_records`（status=submitted, grade_status=pending），不调破局。
   - `auto=true`：调 `PojuClient.submit_checkin()`，成功后记录状态。
3. 自动提交接口不可用时，强制走手动并提示（降级，见第九章）。

### 5.4 作业评改模块（grading_service + ai + poju）

**职责**：AI 生成评改（星级+评语+依据）→ 人工确认 → 同步破局 → 写档案。

**核心方法**：
```python
class GradingService:
    async def list_pending(self, camp_id: int) -> list[PendingGrade]
    async def generate_grade(self, checkin_id: int) -> GradeDraft
    async def confirm_and_sync(self, checkin_id: int, grade: GradeInput) -> SyncResult
    async def regenerate_grade(self, checkin_id: int) -> GradeDraft
```

**`generate_grade` 流程**：
1. 取该学员本次打卡内容。
2. 取该学员本期历史档案（checkin_records，已评改的，按日期）。
3. 取手册相关内容 + 当前评分标准。
4. 组装提示词，调 AI，输出 `{stars, comment, dimension_scores}`。
5. 返回草稿，存 grades 表（source=ai）。

**`confirm_and_sync` 流程**（对应 PRD F3.4）：
1. 接收人工确认/修改后的 `{stars, comment}`。
2. 写 grades 表（source=manual 若有修改）。
3. 更新 checkin_records：`stars, comment, grade_status=graded, is_valid=(stars>=2)`。
4. 调 `PojuClient.submit_grade(student_poju_id, checkin_poju_id, stars, comment)`。
   - 成功：`synced_to_poju=true, synced_at=now`，返回成功。
   - 失败：保持 `synced_to_poju=false`，返回错误，支持重试（数据不丢失）。

### 5.5 学员档案模块（archive_service）

**职责**：维护学员×行动营档案，供评改参考。

**核心方法**：
```python
class ArchiveService:
    async def get_archive(self, student_id: int) -> StudentArchive  # 含统计+时间线
    async def get_history_for_grading(self, student_id: int) -> list[CheckinRecord]
    # 返回该学员已评改的历史打卡，作为 AI 评改上下文
```

- 档案数据来源即 checkin_records（按 student + camp 过滤）。
- `get_history_for_grading` 返回精简历史（日期、星级、内容摘要、评语），控制 token 用量。

### 5.6 手册管理模块（manual_service）

**职责**：上传/替换/预览手册文本，供 AI 读取。

**核心方法**：
```python
class ManualService:
    async def upload_manual(self, camp_id: int, file: UploadFile) -> Manual
    async def save_paste(self, camp_id: int, content: str) -> Manual
    async def get_manual(self, camp_id: int) -> Manual
    async def preview(self, camp_id: int, n: int = 500) -> str
```

- 支持 .md/.txt 上传，或粘贴文本。
- 文件存 `data/manuals/{camp_id}/`，内容同时入库 `manuals.content`。
- 替换时旧文件删除/归档，content 更新。

### 5.7 评分标准模块（scoring_service）

**职责**：管理可配置评分标准，供评改提示词使用。

**核心方法**：
```python
class ScoringService:
    async def get_active(self) -> ScoringStandard
    async def update(self, data: ScoringUpdate) -> ScoringStandard
```

- 全局一套生效标准，修改即生效，不回溯已评改记录（PRD BR-F5-4）。

### 5.8 接口配置模块（settings_service + poju.auth）

**职责**：Token 配置/更新/校验。

**核心方法**：
```python
class SettingsService:
    async def get_config(self) -> PojuConfig
    async def update_token(self, token: str) -> PojuConfig
    async def test_connection(self) -> ConnectionResult  # 调读接口验证
```

- Token 加密存储（见 8.2）。
- `test_connection` 调一次读接口验证有效性，更新 `token_status`。

---

## 六、AI 编排层设计

### 6.1 总体设计

```
prompts/*.txt  ──┐
                 ├──▶ PromptEngine.render(template, vars) ──▶ LLMClient.chat(messages, schema) ──▶ 结构化输出
业务数据(手册/档案)┘
```

- **提示词外置**：所有提示词模板放 `app/ai/prompts/*.txt`，用变量占位，便于不改动代码调优。
- **LLMClient 封装**：统一封装 anthropic/openai SDK，支持流式与非流式、结构化输出（JSON schema）、重试、超时。
- **结构化输出**：评改、路线规划要求 AI 返回 JSON，用 SDK 的 tool-use / response_format 约束，配合 Pydantic 校验。

### 6.2 LLMClient 设计

```python
class LLMClient:
    def __init__(self, config: LLMConfig):
        self.provider = config.provider  # 'anthropic' | 'openai'
        self.model = config.model
        self.client = Anthropic(...) or OpenAI(...)  # 按 provider 初始化

    async def chat(
        self,
        system: str,
        messages: list[dict],
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> BaseModel | str:
        """若提供 response_schema，强制结构化输出并 Pydantic 校验"""
        ...

    async def chat_stream(self, ...):
        """流式输出，用于打卡生成等需要渐进展示的场景"""
        ...
```

- provider 与 model 从 `.env` 配置，默认推荐 Claude（claude-opus-4-8 / claude-sonnet-4-6）。
- 重试策略：指数退避，最多 3 次，超时 60s。

### 6.3 提示词设计（关键三处）

#### 6.3.1 学习路线规划（route_plan.txt）

**输入变量**：`{manual_content}`, `{total_days}`, `{camp_name}`, `{start_date}`, `{end_date}`

**提示词要点**：
- 角色：行动营学习规划专家。
- 任务：阅读手册全文，按 `{total_days}` 天自主规划每日任务。
- 约束：手册无固定按天结构，需根据内容量与逻辑递进合理拆分；每天任务可执行、有递进；输出 JSON 数组。
- 输出 schema：`[{day_number, title, description, tags[]}]`

#### 6.3.2 打卡内容生成（checkin_gen.txt）

**输入变量**：`{today_input}`, `{today_task}`, `{manual_snippet}`

**提示词要点**：
- 角色：帮学员整理每日打卡的助手。
- 任务：根据学员输入的真实所做，生成四板块打卡内容。
- 模板：今日行动 / 今日收获 / 好事分享 / 下一步行动。
- 约束：无强制格式字数，贴合学员真实情况，不编造；参考今日任务与手册主题。
- 输出 schema：`{today_action, today_gain, good_thing, next_step}`

#### 6.3.3 作业评改（grading.txt）

**输入变量**：`{checkin_content}`, `{history_archive}`, `{manual_snippet}`, `{scoring_standard}`, `{current_day}`

**提示词要点**：
- 角色：行动营作业评改志愿者。
- 任务：根据学员本次打卡 + 历史档案 + 手册 + 评分标准，评改打分。
- 重点判断（依赖档案）：是否抄袭/重复历史作业、是否有进步、内容真实性。
- 评分标准：注入当前 `scoring_standard` 的维度与星级规则。
- 输出 schema：`{stars(1-3), comment, dimension_scores[{key, score, reason}]}`

### 6.4 上下文与 token 控制

- 手册内容可能较长，AI 调用前做**分块/摘要**：
  - 路线规划：用手册全文（若超长则先摘要再规划，提示词说明）。
  - 打卡生成：仅注入"今日任务相关"手册片段（按 day 关联章节，MVP 可注入全文或前 N 字）。
  - 评改：注入手册相关片段 + 历史档案（档案按近 N 条限制 token）。
- 历史档案注入：取该学员最近 5~10 条已评改记录，含日期、星级、内容摘要、评语，控制总 token。

### 6.5 提示词调优闭环

- 提示词外置 txt，修改即生效（重启或热加载）。
- grades 表存 `ai_raw_output`，便于回溯 AI 输出与调优对比。
- MVP 前期：评改与打卡生成均默认人工确认（开关关闭），积累样本后调优，再开启自动。

---

## 七、破局接口适配层设计

### 7.1 PojuClient 设计

```python
class PojuClient:
    def __init__(self, config: PojuConfig):
        self.base_url = config.base_url
        self._client = httpx.AsyncClient(timeout=30)
        self.token = config.token

    def _headers(self) -> dict:
        return {"Authorization": self._get_token(), "Content-Type": "application/json"}

    async def fetch_checkin_records(self, camp_id, ...) -> list[PojuCheckin]:
        """拉取学员打卡记录（读）"""
        ...

    async def submit_grade(self, student_id, checkin_id, stars, comment) -> bool:
        """给学员作业打分和评价（写）"""
        ...

    async def submit_checkin(self, ...) -> bool:
        """提交学员打卡（写，待确认接口）"""
        ...

    async def verify_token(self) -> bool:
        """校验 Token 有效性"""
        ...
```

### 7.2 接口定义管理（endpoints.py）

```python
@dataclass
class PojuEndpoint:
    name: str
    method: str
    path: str
    capability: str  # 'read' / 'write'
    status: str      # 'verified' / 'pending'  对应 PRD 待确认

ENDPOINTS = {
    "fetch_checkins": PojuEndpoint("拉取学员打卡记录", "GET", "/api/volunteer/checkins", "read", "verified"),
    "submit_grade":   PojuEndpoint("给学员作业打分和评价", "POST", "/api/volunteer/grades", "write", "verified"),
    "submit_checkin": PojuEndpoint("提交学员打卡", "POST", "/api/student/checkin", "write", "pending"),
    "fetch_self_progress": PojuEndpoint("读取学员自身进度", "GET", "/api/student/progress", "read", "pending"),
}
```

- 接口 URL/字段在 `endpoints.py` 集中管理，破局接口定义明确后只改此处。
- `status=pending` 的接口，调用时检查并触发降级（见第九章）。

### 7.3 鉴权与异常处理

```python
class PojuAuthError(PojuException): ...      # 401/403 Token 失效
class PojuApiError(PojuException): ...       # 接口业务错误
class PojuNetworkError(PojuException): ...   # 网络超时
class PojuNotAvailable(PojuException): ...   # 接口 pending/未开放
```

- 统一异常 → API 层映射为 HTTP 状态码与错误码（见 8.4）。
- 401 触发：更新 `poju_configs.token_status=invalid`，前端提示更新 Token。
- 重试：网络错误指数退避 3 次；鉴权错误不重试。

---

## 八、基础设施设计

### 8.1 配置管理（config.py）

使用 `pydantic-settings` 从 `.env` 加载：

```python
class Settings(BaseSettings):
    # 应用
    app_name: str = "破局行动营管理平台"
    debug: bool = True
    database_url: str = "sqlite:///./data/app.db"

    # 大模型
    llm_provider: str = "anthropic"          # anthropic | openai
    llm_api_key: str
    llm_model: str = "claude-sonnet-4-6"
    llm_timeout: int = 60

    # 破局接口（初始可空，运行时从 DB 读取覆盖）
    poju_base_url: str = ""

    # 定时任务
    scheduler_enabled: bool = True
    sync_cron_hour: int = 9                   # 每日 9 点拉取
    sync_cron_minute: int = 0

    # 安全
    secret_key: str                           # Token 加密用

    class Config:
        env_file = ".env"
```

- 破局 Token 不放 `.env`，存 DB（可在界面更新），见 8.2。

### 8.2 敏感数据存储

- **破局 Token**：存 `poju_configs.token`，用 `secret_key`（来自 .env）对称加密后存储，读取时解密。
- **大模型 API Key**：放 `.env`（不入库）。
- `.env` 与 `data/` 加入 `.gitignore`。

### 8.3 日志

- 结构化日志，按模块分 logger，输出到 `data/logs/app.log` + 控制台。
- 关键操作（接口调用、AI 调用、定时任务）记录 INFO；异常记录 ERROR + 堆栈。

### 8.4 统一响应与错误处理

**统一响应格式**：
```json
{ "code": 0, "message": "ok", "data": {...} }
```

**错误码约定**：

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 1001 | 400 | 参数校验失败 |
| 1002 | 404 | 资源不存在 |
| 2001 | 401 | 破局 Token 失效 |
| 2002 | 502 | 破局接口不可用/网络错误 |
| 2003 | 503 | 破局接口待确认（pending） |
| 3001 | 502 | 大模型调用失败 |
| 3002 | 503 | 手册未配置（降级提示） |
| 5000 | 500 | 服务器内部错误 |

- 全局异常处理器将业务异常映射为上述响应。

### 8.5 跨域与代理

- 后端配置 CORSMiddleware 允许 `localhost:5173`（开发）。
- 前端 Vite proxy `/api` → `http://localhost:8000`，无跨域。

---

## 九、定时任务设计

### 9.1 任务清单

| 任务 | 触发 | 功能 | 对应模块 |
| --- | --- | --- | --- |
| 志愿者看板同步 | 每日 09:00（可配） | 拉取所有进行中志愿者营的学员打卡数据 | archive_service + poju |
| Token 有效性校验 | 每日 08:55 | 调读接口校验 Token，失效则标记 | settings_service + poju |
| 行动营状态刷新 | 每日 00:05 | 刷新行动营状态（虽然动态计算，可冗余刷缓存） | camp_service |

### 9.2 APScheduler 配置

```python
# app/scheduler/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

def init_scheduler(settings: Settings):
    jobstore = SQLAlchemyJobStore(url=settings.database_url)
    scheduler = AsyncIOScheduler(jobstores={"default": jobstore}, timezone="Asia/Shanghai")
    if settings.scheduler_enabled:
        scheduler.add_job(sync_volunteer_boards, "cron",
                          hour=settings.sync_cron_hour, minute=settings.sync_cron_minute,
                          id="sync_boards", replace_existing=True)
        scheduler.add_job(verify_poju_token, "cron",
                          hour=settings.sync_cron_hour, minute=settings.sync_cron_minute-5,
                          id="verify_token", replace_existing=True)
    scheduler.start()
    return scheduler
```

- 用 `AsyncIOScheduler` 配合 FastAPI 的 async 事件循环。
- `SQLAlchemyJobStore` 持久化任务，重启不丢调度。
- 时区 `Asia/Shanghai`，匹配本地。

### 9.3 同步任务逻辑（sync_volunteer_boards）

```
1. 查所有 status=ongoing 且 role=volunteer 的行动营
2. 对每个营：
   a. 调 PojuClient.fetch_checkin_records(camp)
   b. 按 poju_student_id 对齐本地 students，新增/更新
   c. 按 poju_checkin_id 对齐 checkin_records，新增新打卡（grade_status=pending）
   d. 更新 students.last_synced_at
3. 失败：记录日志，标记错误，不中断其他营；Token 失效则标记并停止本轮
```

### 9.4 手动触发

- API `POST /api/volunteer/camps/{id}/sync` 立即触发单个营同步。
- API `POST /api/settings/poju/test` 手动校验 Token。

---

## 十、降级与容错策略实现

对应 PRD 第九章，技术实现层面：

| 场景 | 检测 | 降级实现 |
| --- | --- | --- |
| 破局读接口失败/Token失效 | PojuAuthError/PojuNetworkError | 同步任务记日志、标记 token_status；前端看板显示"上次同步时间+失败提示"；保留已有数据；支持手动重试 |
| 提交打卡写接口不可用（pending） | endpoint.status=='pending' | 自动提交开关禁用，强制手动复制；返回 code 2003 提示 |
| 评改同步写接口失败 | PojuApiError/Network | 评改结果存本地（synced_to_poju=false），前端显示"未同步，可重试"；提供重试 API |
| 手册未上传 | manual 为空 | 路线规划/打卡生成/评改在调用前检查，返回 code 3002，前端提示"未配置手册"且允许降级运行（仅基于输入生成） |
| 大模型调用失败 | LLM 超时/异常 | 返回 code 3001，前端提示失败+重试；不影响已存数据 |
| Token 过期 | 401 | 标记 token_status=invalid，前端全局提示更新 Token |

**重试机制**：
- 评改同步失败：`POST /api/volunteer/grades/{id}/retry`，重新调破局写接口。
- 同步任务失败：下次定时自动重试 + 手动立即同步。

**数据不丢失原则**：所有写操作先落本地 DB，再调外部接口；外部失败不影响本地数据完整性（PRD BR-G-7）。

---

## 十一、API 接口设计

> 完整 OpenAPI 文档由 FastAPI 自动生成（`/docs`）。以下列核心接口。统一前缀 `/api`，统一响应 `{code,message,data}`。

### 11.1 行动营管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/camps` | 创建行动营 |
| GET | `/api/camps` | 行动营列表（含状态、进度） |
| GET | `/api/camps/{id}` | 行动营详情 |
| DELETE | `/api/camps/{id}` | 删除（软删除） |

**创建请求体**：
```json
{
  "name": "AI写作破局营",
  "role": "student",
  "description": "...",
  "total_days": 30,
  "start_date": "2026-06-15",
  "end_date": "2026-07-14",
  "min_checkin_days": 18
}
```

### 11.2 学员功能

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/student/camps/{id}/route/generate` | 生成学习路线 |
| GET | `/api/student/camps/{id}/route` | 获取学习路线 |
| PUT | `/api/student/route/tasks/{task_id}` | 编辑每日任务 |
| POST | `/api/student/camps/{id}/route/regenerate` | 重新规划 |
| GET | `/api/student/camps/{id}/today` | 今日任务+进度 |
| POST | `/api/student/camps/{id}/checkin/generate` | 生成打卡内容 |
| POST | `/api/student/camps/{id}/checkin/submit` | 提交打卡（含 auto 开关） |
| GET | `/api/student/camps/{id}/checkins` | 打卡记录列表 |

**打卡生成请求**：`{ text, images[] }` → 返回 `{ today_action, today_gain, good_thing, next_step }`

**打卡提交请求**：`{ content, auto: bool }` → 返回 `{ submitted, method: 'auto'|'manual', sync_status }`

### 11.3 志愿者功能

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/volunteer/camps/{id}/sync` | 手动触发同步 |
| GET | `/api/volunteer/camps/{id}/students` | 学员看板列表（支持筛选） |
| GET | `/api/volunteer/students/{id}` | 学员档案 |
| GET | `/api/volunteer/camps/{id}/grades/pending` | 待评改列表 |
| POST | `/api/volunteer/grades/generate` | 生成评改 `{ checkin_id }` |
| POST | `/api/volunteer/grades/confirm` | 确认并同步 `{ checkin_id, stars, comment }` |
| POST | `/api/volunteer/grades/{id}/retry` | 重试同步 |
| POST | `/api/volunteer/grades/regenerate` | 重新生成评改 |

### 11.4 手册管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/manuals/{camp_id}/upload` | 上传手册文件（multipart） |
| POST | `/api/manuals/{camp_id}/paste` | 粘贴手册文本 |
| GET | `/api/manuals/{camp_id}` | 获取手册元信息+预览 |
| DELETE | `/api/manuals/{camp_id}` | 删除手册 |

### 11.5 评分标准与配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/scoring` | 获取当前评分标准 |
| PUT | `/api/scoring` | 更新评分标准 |
| GET | `/api/settings/poju` | 获取接口配置（token 脱敏） |
| PUT | `/api/settings/poju/token` | 更新 Token |
| POST | `/api/settings/poju/test` | 测试连接 |

---

## 十二、前端架构设计

### 12.1 路由结构

```
/                       → 行动营列表
/create                 → 创建行动营
/camp/:id/student       → 学员今日看板
/camp/:id/student/route → 学习路线
/camp/:id/student/checkin → 打卡生成
/camp/:id/volunteer     → 学员看板
/camp/:id/volunteer/grade → 作业评改
/student/:id/archive    → 学员档案
/camp/:id/manual        → 手册管理
/scoring                → 评分标准
/settings               → 接口配置
```

- 用 React Router v6，按 `camp.role` 守卫（学员营不能进志愿者页面，反之亦然）。
- 侧边栏导航根据当前行动营身份动态渲染（对齐 UI 原型）。

### 12.2 数据层

- **React Query**：管理所有服务端数据（列表/详情），自动缓存、失效重取。
- **Zustand**：仅管理纯前端状态（当前选中行动营、提交开关等）。
- **API client**：axios 实例 + 拦截器，统一处理 `{code,message,data}`，错误码统一 toast。

### 12.3 UI 原型迁移

- UI 原型（`index.html`）的设计变量、配色、组件映射到 AntD：
  - `StatCard` → AntD `Statistic` + Card
  - `StarPicker` → 自定义组件（AntD 无原生星级输入，Rate 组件适配）
  - `Switch` → AntD `Switch`
  - `ProgressBar` → AntD `Progress`
  - 徽章 → AntD `Tag`（按颜色映射）
  - 表格 → AntD `Table`
  - 时间线 → AntD `Timeline`
- 设计变量（`tokens.css`）对齐 design.md 配色，作为 AntD 主题 token 覆盖。

### 12.4 交互细节落地

- **打卡生成**：生成中按钮 loading + 状态徽章；自动提交开关变化联动按钮文案。
- **作业评改**：星级 Rate 可选；档案/评分标准折叠（AntD Collapse）；确认同步成功 toast + 列表刷新。
- **降级提示**：axios 拦截器按错误码 toast（2001 Token 失效、2003 接口待确认、3002 手册未配等）。

---

## 十三、安全设计

| 项 | 措施 |
| --- | --- |
| 破局 Token | 加密存 DB，前端展示脱敏（仅末 4 位） |
| 大模型 Key | 仅存 `.env`，不进 DB 不出后端 |
| 本地访问 | 监听 127.0.0.1，不对外暴露（MVP 无需鉴权，单用户） |
| 输入校验 | Pydantic 严格校验所有入参 |
| SQL 注入 | SQLAlchemy 参数化查询，禁用裸字符串拼接 |
| 文件上传 | 限制手册类型（.md/.txt）与大小，路径校验防穿越 |
| 日志脱敏 | Token/Key 不写日志 |

---

## 十四、测试策略

| 层 | 策略 | 工具 |
| --- | --- | --- |
| 单元测试 | 服务层逻辑（状态计算、最低天数、有效性判断） | pytest |
| 接口测试 | API 路由 + 参数校验 | pytest + httpx (AsyncClient) |
| 破局接口 | Mock PojuClient，验证调用与降级 | pytest + respx |
| AI 编排 | Mock LLMClient，验证提示词组装与输出解析 | pytest |
| 前端 | 组件渲染 + 关键交互（开关、星级、提交） | Vitest + Testing Library |

**关键测试用例**：
- 行动营状态流转（未开始/进行中/已结束）。
- 最低打卡天数计算（30→18）。
- 评改有效性（2★有效，1★无效）。
- 评改同步失败重试（数据不丢失）。
- Token 失效降级（标记 + 提示）。
- 手册未配降级（允许运行 + 提示）。

---

## 十五、开发与部署

### 15.1 本地启动

**后端**：
```bash
cd backend
uv sync                          # 安装依赖
cp .env.example .env             # 配置 LLM key 等
uv run alembic upgrade head      # 初始化数据库
uv run uvicorn app.main:app --reload --port 8000
```

**前端**：
```bash
cd frontend
pnpm install
pnpm dev                         # 5173，代理 /api → 8000
```

**一键启动**（Makefile）：
```makefile
dev:
    @trap 'kill 0' EXIT; \
    cd backend && uv run uvicorn app.main:app --reload --port 8000 & \
    cd frontend && pnpm dev
```

### 15.2 配置清单（.env.example）

```env
DEBUG=true
DATABASE_URL=sqlite:///./data/app.db
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-xxx
LLM_MODEL=claude-sonnet-4-6
LLM_TIMEOUT=60
POJU_BASE_URL=
SCHEDULER_ENABLED=true
SYNC_CRON_HOUR=9
SYNC_CRON_MINUTE=0
SECRET_KEY=change-me-to-random-string
```

### 15.3 数据备份

- SQLite 单文件，备份即复制 `data/app.db`。
- 手册文件在 `data/manuals/`，一并备份。
- 可提供 `make backup` 脚本打包 `data/` 目录。

---

## 十六、演进与预留

对应 PRD 第十一章，技术层面的预留：

| 演进方向 | 预留设计 |
| --- | --- |
| 多用户 | 模型已含 user_id 外键位（MVP 单用户硬编码）；API 加中间件即可 |
| 云端部署 | 配置全部 .env 化；SQLite 可平滑换 PostgreSQL（SQLAlchemy 抽象） |
| 自动评改/提交 | 开关已设计（grading/checkin），成熟后开启即可 |
| 手册自动获取 | `manual_service` 预留 `import_from_ocr` 接口位 |
| 微信自动化 | 独立模块预留，不影响现有架构 |
| 多身份并发 | 营×身份关系已支持，前端守卫放宽即可 |
| RAG 检索 | 手册内容入库后可加向量索引字段，LLMClient 预留 retrieval 注入位 |

---

## 十七、待确认事项（承接 PRD）

技术方案落地前需与 PRD 待确认事项对齐：

1. **破局接口字段定义**：`endpoints.py` 中 URL/请求体/响应字段为占位，待接口开放后填充真实定义，并据此调整 `PojuClient` 与 `schemas`。
2. **提交打卡接口是否存在**：决定 `submit_checkin` 是真实调用还是永久降级为手动复制。
3. **学员自身进度读取**：决定学员看板打卡进度是否真实展示。
4. **Token 有效期**：影响定时校验频率与失效检测策略。
5. **图片处理**：学员输入图片是仅参考还是需提交破局（破局打卡是否支持图片），影响 `submit_checkin` 字段。
6. **大模型选型**：默认 Claude sonnet，待确认是否需用 opus（评改等高质量场景）或混用。

---

## 十八、里程碑建议

> 非强制，供参考的分阶段实施。

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| M1 基础骨架 | 项目结构、DB 模型与迁移、配置、日志、统一响应 | 可启动空壳前后端 |
| M2 行动营+手册 | 行动营 CRUD、手册上传/预览 | 跑通营管理与手册 |
| M3 学员链路 | 路线规划、今日看板、打卡生成、手动提交 | 学员主链路可用 |
| M4 志愿者链路 | 破局接口对接、看板同步、评改生成、确认同步、档案 | 志愿者主链路可用 |
| M5 定时任务+降级 | APScheduler、Token 校验、降级提示、重试 | 自动化与健壮性 |
| M6 评分标准+配置 | 评分标准管理、接口配置页 | 全局配置闭环 |
| M7 联调与打磨 | 前后端联调、提示词调优、测试补全 | MVP 可用版本 |

---

> 文档结束。请评审技术方案，特别关注**第四章数据模型**、**第六章 AI 编排**、**第七章破局接口适配**与**第十七章待确认事项**。确认后即可按第十八章里程碑进入开发。
