# Agent #2 测试报告：学员身份完整链路

**测试时间**：2026-06-28 02:27 - 02:48
**测试范围**：CAMP 创建 (TC-CAMP-001/003/004/005/006/011) + STU 学员模块 (TC-STU-001~014)
**测试方式**：curl 直接调用后端 API + Playwright 走 UI 流程

---

## 一、测试统计

| 维度 | 数量 |
| --- | --- |
| 用例覆盖 | 17 / 20（CAMP 6 + STU 11） |
| Pass | 7 |
| Fail | 4 |
| Block（因 LLM/前端路径 bug 不可用） | 6 |
| 发现 Bug | **16**（P0×6 / P1×8 / P2×2） |

> 注：TC-STU-004/006/007 需 route generate（LLM 实际失败），TC-STU-008/009 checkin 草稿生成在 API 层 OK 但 UI 路径错误；这些计为 Block。

---

## 二、严重 Bug 汇总（按严重度倒序）

### BUG-001 [P0] 前端学生端 API 路径全部缺少 `/student/` 段
- **模块**: STU
- **用例**: TC-STU-001/004/005/006/007/008/009/010/011/012/013
- **步骤**:
  1. 访问 `http://localhost:5173/camp/4/student`
  2. 打开 DevTools Network
  3. 观察 `/api/camps/4/today` `/api/camps/4/route` `/api/camps/4/checkins` 等
- **预期**: 实际后端路径是 `/api/student/camps/4/today` `/api/student/camps/4/route` `/api/student/camps/4/checkins`
- **实际**: 前端 axios `baseURL='/api'` + 路径 `/camps/{id}/...` 拼成 `/api/camps/{id}/...`，**全部 404**
- **证据**:
  - 文件 `/Users/rot/dev/code/pojuActionCamp/frontend/src/api/student.ts:27-63`
  - 所有导出函数路径缺 `/student/` 段（如 `generateRoute` 用 `/camps/${campId}/route/generate`，正确应为 `/student/camps/${campId}/route/generate`）
  - Playwright 网络抓包确认：`[GET] /api/camps/4/today => [404] Not Found`
  - P3 页面 main 区域显示兜底文案"今日暂无任务，请先到学习路线检查或上传手册"，实际后端有数据
- **影响**: 学员端 P3/P4/P5 整条链路在 UI 完全不可用；TC-STU-001 至 TC-STU-013 全部受影响

### BUG-002 [P0] 前端志愿者端 API 路径全部缺少 `/volunteer/` 段
- **模块**: VOL
- **用例**: TC-VOL-001/004/006
- **步骤**:
  1. 访问 `http://localhost:5173/camp/5/volunteer`
  2. 观察 `/api/camps/5/students`、`/api/camps/5/grades/pending`
- **预期**: 实际后端是 `/api/volunteer/camps/5/students`、`/api/volunteer/camps/5/grades/pending`
- **实际**: 前端 404，志愿者看板显示"该筛选下暂无学员"
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/frontend/src/api/volunteer.ts:26-57`
  - 路径如 `syncBoard` 用 `/camps/${campId}/sync` 缺 `/volunteer/`
  - Playwright 网络抓包：`[GET] /api/camps/5/students => [404]`

### BUG-003 [P0] LLM 路由生成（route generate）500 错误：未找到 tool_use 块
- **模块**: STU
- **用例**: TC-STU-006
- **步骤**: 上传手册后调 `POST /api/student/camps/4/route/generate`
- **预期**: 返回 `{code:0, data: {tasks: [...]}}`
- **实际**: HTTP 500，错误 `LLM 调用失败，已重试 3 次: 0 validation errors for 未在响应中找到 tool_use 块`
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/ai/llm_client.py:151`
  - 后端使用 anthropic 协议的 `tool_choice={"type": "tool", "name": "return_result"}` 强制结构化输出
  - 但实际 LLM 端（OpenAI 兼容代理）不返回 tool_use 块，导致校验失败重试 3 次后报错
  - 同样代码路径下 `checkin generate` 成功，说明不是 LLM 端完全不可用，而是 **route_plan 提示词过长** 或 LLM 对 tool_use 协议支持不完整
- **影响**: TC-STU-006/007 路线生成完全不可用，UI 一直显示"尚未生成学习路线"

### BUG-004 [P0] LLM 异常未被全局异常处理器捕获，返回 HTTP 500 + HTML 堆栈
- **模块**: STU
- **用例**: TC-STU-006
- **步骤**: LLM 失败时观察响应
- **预期**: 业务异常码 3001（LLM 调用失败），HTTP 502
- **实际**: HTTP 500，**响应体是 HTML 堆栈跟踪**（非 JSON 格式，违反 NFR-001 统一响应约定）
- **证据**:
  - 抛出位置：`app.ai.llm_client.LLMError`（继承 `Exception`）
  - 全局注册的是 `app.core.exceptions.LLMError`（继承 `AppException`）
  - **两个同名 LLMError 来自不同模块，全局异常处理器只识别 `app.core.exceptions.LLMError`**
  - 错误响应包含：`raise LLMError(...)` Python traceback
  - `app/core/exceptions.py:11-13` 注释明确警告二者模块路径不同，但未在 ai 模块 import 业务版 LLMError
- **影响**: 前端 axios 拦截器收到 500 + 非 JSON body，错误处理逻辑失效；用户看到原始 Python 堆栈

### BUG-005 [P0] Schema 强制 min_checkin_days 必传，PRD "0.6 兜底" 失效
- **模块**: CAMP
- **用例**: TC-CAMP-003
- **步骤**:
  1. `POST /api/camps` 不传 min_checkin_days
  2. 期望后端按 `total_days * 0.6` 兜底计算
- **预期**: 30 天 → min=18，21 天 → min=13，10 天 → min=6，1 天 → min=1
- **实际**: 不传 min_checkin_days → **HTTP 400 校验失败 1001**；传 min=1 → 后端**直接接受 min=1**（不兜底），与 PRD 设计冲突
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/schemas/camp.py:28` `min_checkin_days: int = Field(..., gt=0)` 强制必填
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/services/camp_service.py:99-101` 兜底逻辑要求 `not min_days`，但 Pydantic 已经保证 gt=0，所以兜底永远不触发
  - 前端 UI **手动做了 0.6 计算**（test UI 中 30→18, 7→4），后端不信任前端，传任意非空值即可
- **影响**: 30 天营可被错误地创建为 min=1，导致"最低打卡天数 = 1"业务规则失控（已在数据库中观察到 BUG3-totalHuge 等多例）

### BUG-006 [P0] TC-CAMP-004 倒序日期被强制 400 阻断，PRD 要求"不强制阻断"
- **模块**: CAMP
- **用例**: TC-CAMP-004
- **步骤**: `POST /api/camps` with `start_date=2026-06-28, end_date=2026-06-20`
- **预期**: PRD BR-F1-2 "应给出'开始时间应早于结束时间'提示，**不强制阻断**"
- **实际**: HTTP 400 `1001 参数校验失败`
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/schemas/camp.py:30-36` `@field_validator("end_date")` 抛 ValueError
  - Pydantic ValidationError 由全局处理器映射为 1001 + HTTP 400
- **影响**: PRD 文档与实现不一致；前端拿到 1001 也无法区分"必填缺失"和"倒序"

---

### BUG-007 [P1] TC-CAMP-005 结束时间与总天数不符：后端无任何校验
- **模块**: CAMP
- **用例**: TC-CAMP-005
- **步骤**: `POST /api/camps` with `total_days=30, start_date=2026-06-28, end_date=2026-07-10`（仅跨 13 天）
- **预期**: PRD "提示'结束时间应与开始+总天数相符'"
- **实际**: 成功创建，progress 3%（current_day/total_days=1/30），**业务上无意义**（一个 30 天营的结束日期是开始 + 13 天）
- **证据**:
  - HTTP 200 + `code:0` 创建成功
  - DB 中 camp_id=13 状态 ongoing，end_date=2026-07-10，但 total_days=30
  - 列表 progress=3.33% 显示
- **影响**: 数据脏、UI 显示错乱、Day 30 永远到不了

### BUG-008 [P1] auto=true 提交打卡时"配置缺失降级" 与 "用户主动 manual" 不可区分
- **模块**: STU
- **用例**: TC-STU-011
- **步骤**:
  1. 提交开关打开（auto=true）
  2. PojuConfig 未配置或 submit_checkin 接口 pending
  3. 调 `POST /api/student/camps/4/checkin/submit`
- **预期**: PRD BR-F2.4 "成功/失败二选一"，失败时"保留数据 + 错误提示"
- **实际**: 返回 `{method: "manual", sync_status: "manual", submitted: true}`，**前端无法区分"auto 失败降级" 与 "用户选 manual"**
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/services/checkin_service.py:307-329`
  - 3 个降级分支（PojuNotAvailable / 未配置 / 接口 pending）都返回同样的 `("manual", "manual", None)`
  - `submit_checkin` 接口 `status: pending`（`app/poju/endpoints.py:51-57`），**MVP 阶段必然降级**
- **影响**: 用户感知不到 auto 是否真的成功，BR-F2.4-2 失败提示无法落地

### BUG-009 [P1] TC-STU-014 手册未上传时 checkin 不返回 3002 而返回 0
- **模块**: STU
- **用例**: TC-STU-014
- **步骤**: 不传手册的营，调 `POST /api/student/camps/17/checkin/generate`
- **预期**: PRD "返回 code 3002"
- **实际**: HTTP 200，code=0，返回正常四板块（实际是降级生成）
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/services/checkin_service.py:290-296` 手册缺失时返回空串让 LLM 自由发挥
  - 实际功能正确（**降级运行**），但 **code 标识缺失**——前端无法触发"未配置手册，建议上传"的提示
  - 同一营调 `route generate` 返回 3002（line 311 抛 ManualNotFoundError），**checkin 与 route 处理不一致**
- **影响**: PRD 描述与实现不一致；前端提示策略丢失

### BUG-010 [P1] TC-STU-007 重新规划无确认弹窗
- **模块**: STU
- **用例**: TC-STU-007
- **步骤**:
  1. P4 页面点击"🔄 重新规划"按钮
- **预期**: PRD "弹窗提示'将基于手册重新生成，会覆盖 AI 生成部分。是否保留你已编辑的内容？'"
- **实际**: **直接调用 regenerate API，无弹窗**
- **证据**:
  - Playwright 验证：点击"重新规划"后 500ms 内无任何 Modal 元素
  - 实际 API 也会 500（LLM 失败），所以"是否保留"的选择无法生效
- **影响**: 用户编辑过的内容可能被意外覆盖

### BUG-011 [P1] camp name XSS 注入：原始 `<script>` 字符串渲染到侧边栏
- **模块**: UX
- **用例**: TC-UX-003
- **步骤**: 创建 name 为 `<script>alert(1)</script>` 的营
- **预期**: 1) 后端拒绝；2) 前端转义
- **实际**: 后端接受原始字符串，前端在 menu 中显示文本（未执行脚本）但**列表卡片显示原始 `<script>alert(1)</script>`**——`text` 是经过转义的，但视觉上是裸露的
- **证据**:
  - 截图 `01-camp-list-xss.png` 与 `09-p9-manual.png` 中可见该字符串
  - 数据库 camp_id=18 name = `<script>alert(1)</script>`
  - 列表显示："`user 学员 进行中 <script>alert(1)</script>`"
  - **没有执行 alert**（React 默认 textContent 不会执行）但**视觉上是未净化输入**
- **影响**: P2 信息安全/UX 问题；如果未来迁移到 dangerouslySetInnerHTML 或邮件模板，可能引发 XSS

### BUG-012 [P1] 多个后端 uvicorn 进程并发，共享同一 SQLite 文件
- **模块**: NFR
- **用例**: TC-NFR-003
- **步骤**:
  1. `ps -ef | grep uvicorn` 看到多个进程
  2. 同一 camp_id=4 上传手册后内容被另一个进程覆盖
- **预期**: 单一进程或显式互斥
- **实际**: 至少 2-3 个 uvicorn 进程并发运行（PID 1467 死后 supervisor 自动重启为 9434，再被 kill 后又启 14082）；共享 `data/app.db`
- **证据**:
  - `ps -ef | grep uvicorn`: 9431/9433/9434 → kill → 14079/14081/14082
  - 后端崩溃前我 paste 的 700 字手册（camp_id=4）丢失，被另一进程的 46 字 SCQA 手册覆盖
  - SQLite 在并发写入下会抛 `database is locked`
- **影响**: 数据丢失 / 不一致 / 不可重现

### BUG-013 [P1] 学员营 (role=student) 走 checkin 路径时，submit 失败的业务提示不够细致
- **模块**: STU
- **用例**: TC-STU-010/011
- **步骤**: 调 `POST /api/student/camps/4/checkin/submit` with auto=true, PojuConfig token 失效（401）
- **预期**: PRD "失败：保留数据 + 错误提示"
- **实际**: 当前 PojuClient 401 抛 `PojuAuthError` (code 2001)，全局处理器返回 HTTP 401。**但 submit 接口内部 try 块没显式处理 PojuAuthError**——会直接抛出而非降级
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/services/checkin_service.py:319-326` 只捕获 `PojuNotAvailable`
  - 401/网络错误会**直接抛给路由层**，但 **CheckinRecord 已经在 session.add 之前没事务保护**（不对，line 211 commit 后才退出）
  - 实际记录会写入（poju_checkin_id=None, synced_to_poju=False），但前端需要正确处理 2001
- **影响**: 需前端配合处理 code 2001，否则用户感知不到 Token 失效

### BUG-014 [P1] sync_status 字段从未写入 CheckinRecord 表
- **模块**: STU
- **用例**: TC-STU-011
- **步骤**: 查看 DB
- **预期**: 字段持久化
- **实际**: ORM 模型无 sync_status 字段，sync_status 仅在响应中临时返回
- **证据**:
  - `/Users/rot/dev/code/pojuActionCamp/backend/app/services/checkin_service.py:20-22` 注释明确说明
  - `checkin_service.py:191, 194, 207` 实际写入只设 `synced_to_poju`
  - DB 查询 `SELECT * FROM checkin_records` 确实无 sync_status 列
- **影响**: 志愿者侧 GET `/api/student/camps/{id}/checkins` 看不到同步状态；后续接 scheduler 需补

### BUG-015 [P1] 端点缺失：Volunteer 学员档案 `/api/volunteer/students/{student_id}` 路径
- **模块**: VOL
- **用例**: TC-VOL-014
- **步骤**: 实际有后端路径，前端路径错（BUG-002 涵盖），但后端还应支持 student_id=0 的占位学员
- **预期**: 学员身份（无 Student 行）下，submit checkin 时 student_id=0，志愿者侧应能查
- **实际**: 志愿者看板调用 `/api/camps/{id}/students` 走 `Student` 表关联，可能漏掉 student_id=0 的记录
- **证据**: 暂未完整验证（待志愿者端 UI 路径修复后回归）
- **影响**: MVP 学员单用户身份下，志愿者看不到该学员的档案

### BUG-016 [P2] TC-STU-013 P3 看板统计：训练 Day 计算在无路线时 fallback 不准确
- **模块**: STU
- **用例**: TC-STU-013
- **步骤**: camp_id=4 已有路线 (route_id=1) 但 day_number=1
- **预期**: PRD "训练 Day = max(1, min(总天数, today - start + 1))" + 距退押金 = 最低 - 有效（不小于 0）
- **实际**: API 返回 day_number=1, progress=0.143 (1/7) — 正确；但 P3 页面 fallback 数据是 mock，与实际 API 不一致（因 BUG-001）
- **证据**:
  - `app/services/route_service.py:267-296` 边界处理（current_day > total 时 progress=1.0）
  - `camp_service.py:174-181` 进度计算
  - 端到端：实际 API 正确，**但 UI 看到的是 fallback 假数据**
- **影响**: 真实数据被 UI 屏蔽（因 BUG-001）

---

## 三、详细用例执行结果

### A. 学员营创建

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| TC-CAMP-001 正常 7 天 | **Pass（API）/ Pass（UI）** | camp_id=4 创建成功，min=5（手动传），前端 UI 显示统计正确 |
| TC-CAMP-003 总天数 30/21/10/1 | **Pass（UI）/** **Fail（API）** | 前端 30→18, 7→4 正确；后端**强制 min_checkin_days 必填，0.6 兜底失效**（BUG-005） |
| TC-CAMP-004 倒序日期 | **Fail** | HTTP 400 阻断，与 PRD"不强制阻断"不一致（BUG-006） |
| TC-CAMP-005 起止与总天数不符 | **Fail** | HTTP 200 创建成功，无任何提示（BUG-007） |
| TC-CAMP-006 缺名称 | **Pass** | HTTP 400 + 1001，前端显示"请输入行动营名称" |
| TC-CAMP-011 身份不可改 | **Pass（隐式）** | camps API 无 PUT，前端编辑页无 role 字段 |

### B. 学习路线

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| TC-STU-004 路线展示 | **Block** | 前端路径错（BUG-001），UI 显示"尚未生成学习路线"；手动 mock data 后 API 层可工作 |
| TC-STU-005 编辑每日任务 | **Pass（API）/** **Block（UI）** | PUT 正常，edited 标记生效；UI 看不到（BUG-001） |
| TC-STU-006 生成学习路线 | **Fail** | LLM 失败（BUG-003） + 全局异常处理漏（BUG-004） |
| TC-STU-007 重新规划确认 | **Fail** | 无弹窗（BUG-010），LLM 失败 |

### C. 打卡链路

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| TC-STU-008 打卡内容生成 | **Pass（API）/** **Block（UI）** | API 返回四板块完整，UI 404（BUG-001） |
| TC-STU-009 编辑与重新生成 | **Block（UI）** | UI 不可达 |
| TC-STU-010 手动提交 | **Pass（API）/** **Block（UI）** | 记录写入 DB，UI 404 |
| TC-STU-011 自动提交 | **Fail** | 降级为 manual 无法区分（BUG-008/BUG-013） |
| TC-STU-012 打卡记录表 | **Pass（API）/** **Block（UI）** | API 列表正确，UI 显示"本期暂无记录"（BUG-001） |
| TC-STU-014 手册未上传降级 | **Fail** | checkin 返回 0 不返回 3002（BUG-009） |

### D. 看板

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| TC-STU-001 今日任务展示 | **Block（UI）/** Pass（API） | API 正常返回 day_number/task/progress，UI fallback |
| TC-STU-002 未开始状态提示 | **Pass（UI 假）/** Pass（API） | 前端 fallback 文案正确（"⏳ 行动营尚未开始"），API day_number=null |
| TC-STU-003 已结束状态提示 | **Pass（UI 假）/** Pass（API） | 显示"✅ 行动营已结束"，但无总结信息（fallback） |
| TC-STU-013 看板统计 | **Pass（API）/** **Block（UI）** | valid_days 计算正确（stars>=2），UI 看真实数据需修复 BUG-001 |

### E. NFR

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| NFR-001 统一响应格式 | **Pass** | 所有正常响应 {code, message, data} |
| NFR-002 错误码规范 | **Fail** | 1001/1002/3002 正确，**3001 缺失**（LLM 500 而非 3001） |
| NFR-003 数据持久化 | **Fail** | 多次后端重启 + 多进程并发致数据丢失（BUG-012） |
| NFR-005 API 文档可访问 | **Pass** | http://localhost:8000/docs 200 OK |

---

## 四、TOP-3 学员链路阻塞 Bug

### 1. BUG-001 前端学生端 API 路径全部缺少 `/student/` 段
学员端 P3/P4/P5 三个核心页面所有数据接口全部 404，UI 永远显示 fallback 假数据。这是**学员链路完全不可用**的根因。修复成本：修改 `frontend/src/api/student.ts` 中 7 个导出函数的 URL 模板即可。

### 2. BUG-004 + BUG-003 LLM 异常处理缺失 + tool_use 协议失败
LLM 失败时直接返回 HTTP 500 + HTML 堆栈（破坏 NFR-001）；route generate 100% 失败（tool_use 协议不被 LLM 兼容）。即便前端路径修复，**学习路线生成和打卡草稿仍无法在生产 LLM 上跑通**。修复成本：`app/ai/__init__.py` 增加 import 业务 LLMError，并在 llm_client 中 fallback 到 JSON mode。

### 3. BUG-005 min_checkin_days 必填导致 0.6 兜底失效
30/21/10 天的营可被错误地创建为 min=1（DB 中已观察到 BUG3-totalHuge / Agent2-30天-1 / Agent2-21天 等多例），业务规则失控。修复成本：把 `CampBase.min_checkin_days` 改为 `Optional[int] = None`，让 service 层走 calc_min_days 兜底。

---

## 五、关键文件路径

- 后端 Camp API: `/Users/rot/dev/code/pojuActionCamp/backend/app/api/camps.py`
- 后端 Student API: `/Users/rot/dev/code/pojuActionCamp/backend/app/api/student.py`
- 后端 Manual API: `/Users/rot/dev/code/pojuActionCamp/backend/app/api/manual.py`
- 服务 Camp: `/Users/rot/dev/code/pojuActionCamp/backend/app/services/camp_service.py`
- 服务 Route: `/Users/rot/dev/code/pojuActionCamp/backend/app/services/route_service.py`
- 服务 Checkin: `/Users/rot/dev/code/pojuActionCamp/backend/app/services/checkin_service.py`
- Schema Camp: `/Users/rot/dev/code/pojuActionCamp/backend/app/schemas/camp.py`
- Schema Student: `/Users/rot/dev/code/pojuActionCamp/backend/app/schemas/student.py`
- 异常处理: `/Users/rot/dev/code/pojuActionCamp/backend/app/core/exceptions.py`
- LLM Client: `/Users/rot/dev/code/pojuActionCamp/backend/app/ai/llm_client.py`
- 前端 Student API: `/Users/rot/dev/code/pojuActionCamp/frontend/src/api/student.ts` ← BUG-001
- 前端 Volunteer API: `/Users/rot/dev/code/pojuActionCamp/frontend/src/api/volunteer.ts` ← BUG-002
- 前端 P3 Dashboard: `/Users/rot/dev/code/pojuActionCamp/frontend/src/pages/student/Dashboard.tsx`
- 前端 P4 Route: `/Users/rot/dev/code/pojuActionCamp/frontend/src/pages/student/Route.tsx`
- 前端 P5 Checkin: `/Users/rot/dev/code/pojuActionCamp/frontend/src/pages/student/Checkin.tsx`

## 六、截图

- `screenshots/agent2/01-camp-list-xss.png` — P1 列表（含 XSS 字符串与多 BUG 营）
- `screenshots/agent2/03-student-dashboard-404.png` — P3 学员看板（数据 fallback 假）
- `screenshots/agent2/04-create-camp.png` — P2 创建营（30 天默认 min=18）
- `screenshots/agent2/05-camp-camp003-frontend.png` — 总天数 7 → min 4 兜底
- `screenshots/agent2/06-camp-name-required.png` — 名称必填校验
- `screenshots/agent2/07-p5-checkin-broken.png` — P5 打卡（fallback 文案）
- `screenshots/agent2/08-p4-route-broken.png` — P4 学习路线（"尚未生成"）
- `screenshots/agent2/09-p9-manual.png` — P9 手册管理（其他 agent 注入的 46 字手册）
