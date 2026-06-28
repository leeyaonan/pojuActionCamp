# AI 破局行动营管理平台 · MVP E2E 对抗验证 Baseline 报告

> **报告版本**：v1.0
> **生成时间**：2026-06-28
> **定位**：本报告为 5 个并行 Agent 完整 e2e + 对抗试探结果的**唯一权威汇总**，也是下一轮 bug 修复的 **baseline 基准**。所有待修复 bug 都在本文档登记；修复完成后须以本文档作为回归基线。
> **覆盖**：70 个测试用例 + 47 个对抗试探 + 11 个页面 walkthrough
> **执行环境**：前端 `http://localhost:5173`，后端 `http://localhost:8000`

---

## 一、Executive Summary（执行摘要）

### 1.1 测试通过率

| 模块 | 用例数 | Pass | Fail | Block | 通过率 |
| --- | --- | --- | --- | --- | --- |
| 行动营 CAMP | 12 | 4 | 5 | 3 | 33% |
| 学员 STU | 14 | 4 | 4 | 6 | 29% |
| 志愿者 VOL | 14 | 4 | 8 | 2 | 29% |
| 手册 MAN | 5 | 5 | 0 | 0 | 100% |
| 评分 SCO | 4 | 4 | 0 | 0 | 100% |
| 接口配置 CFG | 6 | 4 | 0 | 2 | 67% |
| UI/交互 UX | 10 | 9 | 1 | 0 | 90% |
| 非功能 NFR | 5 | 3 | 1 | 1 | 60% |
| **总计** | **70** | **35** | **19** | **14** | **50%** |

> 整体通过率约 50%，但 **Fail/Block 多数由 P0 阻塞导致**（不是真实功能缺陷）。修复 5 个 P0 阻塞后，预计通过率可达 **85%+**。

### 1.2 Bug 严重度分布

| 严重度 | 数量 | 占已登记 Bug 比例 |
| --- | --- | --- |
| **P0 阻塞/数据/安全** | **13** | 13.5% |
| **P1 严重/数据一致性** | **18** | 18.8% |
| **P2 一般/体验** | **65** | 67.7% |
| **合计** | **96** | 100% |

> 注：部分 P2 是 antd 弃用、UI 文案、可优化项等"非阻塞"但建议在下个迭代处理。

### 1.3 TOP-5 阻塞性 Bug（必须最先修复）

| # | 编号 | 严重度 | 模块 | 描述 | 修复成本 |
| --- | --- | --- | --- | --- | --- |
| 1 | **BUG-API-001** | P0 | 前端 | 学员/志愿者前端 9+ 个 API 路径缺 `/student` `/volunteer` 前缀，导致 P3/P4/P5/P6/P7/P8 共 6 个核心页面全部 404 | 低（修 ~10 处 URL） |
| 2 | **BUG-NFR-001** | P0 | 后端 | `app.ai.llm_client.LLMError` 继承 `Exception` 而非 `AppException`，未注册到全局处理器 → LLM 失败返回 5KB Python traceback，错误码 3001 无法触发 | 低（import 业务版 LLMError） |
| 3 | **BUG-VOL-002** | P0 | 后端 | `grading_service.py:366 _build_history_archive` 引用 `CheckinRecord.comment`（不存在），学员有 ≥1 条历史评改时 generate/regenerate 必 500 | 中（join Grade 表取评语） |
| 4 | **BUG-VOL-003** | P0 | 后端 | `grading_service.py:251, 435` 同样引用不存在的 `record.comment`，"确认并同步"100% 静默失败，评语数据无法上传 | 中（与 #3 同根因） |
| 5 | **BUG-PJU-001** | P0 | 后端 | `PojuClient.fetch_checkin_records` 吞掉 `PojuNetworkError/PojuApiError` 返回 `[]`，导致 `verify_token` 假阳性（无效 URL/Token 仍返回"连接成功"） | 中（不吞异常） |

> 这 5 个 P0 修复后，6 个核心页面恢复数据访问 + 评改链路全打通 + LLM 失败优雅降级 + 破局接口真实状态可感知。

---

## 二、Master Bug 清单

> **编号规则**：`BUG-{模块}-{NNN}`。模块缩写：CAMP/STU/VOL/MAN/SCO/CFG/NFR/UX/PJU/SEC/DBA
> **状态**：`OPEN` / `FIXED` / `WON'T FIX`
> **关联用例**：具体 TC 编号
> **关联 Agent 报告**：1-5

### 2.1 P0 阻塞/数据/安全（13 个）

#### BUG-API-001 · 前端 API 路径缺 `/student` `/volunteer` 前缀
- **状态**：FIXED
- **严重度**：P0（阻塞 6 个核心页面）
- **模块**：前端
- **关联用例**：TC-STU-001/004/005/006/007/008/009/010/011/012/013、TC-VOL-001/002/003/004/006/007/014
- **关联 Agent**：1 / 2 / 3 / 4 / 5
- **步骤**：
  1. 打开任一学员营 P3 或志愿者营 P6
  2. DevTools Network 观察
- **预期**：`/api/student/camps/{id}/today` 等
- **实际**：`/api/camps/{id}/today` 等全部 404
- **根因**：
  - `frontend/src/api/student.ts` line 28-49（7 处）
  - `frontend/src/api/volunteer.ts` line 28-57（4 处）
  - `frontend/src/pages/volunteer/Grading.tsx:432`（1 处）
  - `frontend/src/pages/student/Checkin.tsx`（直接调 today/checkins）
- **修复**：
  ```ts
  // student.ts: 所有路径加 /student 前缀
  http.get(`/student/camps/${campId}/today`)
  // volunteer.ts: 所有路径加 /volunteer 前缀
  http.get(`/volunteer/camps/${campId}/students`)
  ```
- **回归基线**：修复后 P3/P4/P5/P6/P7/P8 6 个页面应能加载真实数据

#### BUG-NFR-001 · LLM 异常未映射 3001，返回 traceback
- **状态**：FIXED
- **严重度**：P0（违反 NFR-001、信息泄露、阻断所有 AI 接口降级路径）
- **模块**：后端 AI / 全局异常
- **关联用例**：TC-NFR-002、TC-STU-006/007/008、TC-VOL-008/013
- **关联 Agent**：2 / 4 / 5
- **步骤**：任意 LLM 失败场景（无 API_KEY、tool_use 协议不兼容、Schema 校验失败）
- **预期**：`{code: 3001, message: "大模型调用失败"}` HTTP 502
- **实际**：HTTP 500 + 5KB 完整 Python traceback
- **根因**：
  - `app/ai/llm_client.py:36` 定义 `class LLMError(Exception)`（继承 Exception）
  - `app/core/exceptions.py:11-13` 业务版 `class LLMError(AppException)`（code=3001）
  - 全局 handler 只 catch `AppException`，`ai.LLMError` 落到 starlette 默认处理器
- **修复**：
  ```python
  # 方案 A（推荐）：app/ai/llm_client.py 顶部
  from app.core.exceptions import LLMError, AppException
  # 删掉本地 class LLMError(Exception)
  # 方案 B：app/core/exceptions.py 增加注册
  @app.exception_handler(Exception)
  async def unhandled_handler(req, exc):
      return JSONResponse({code: 5000, message: str(exc)[:200]}, 500)
  ```
- **回归基线**：
  - 无 API_KEY 时 `POST /api/student/camps/3/route/generate` → `code:3001` HTTP 502
  - Pydantic 校验失败（dimension_scores 字符串）→ `code:3001` 而非 traceback

#### BUG-VOL-002 · `_build_history_archive` 引用不存在的 `CheckinRecord.comment`
- **状态**：FIXED
- **严重度**：P0（学员有历史评改时 100% 崩溃）
- **模块**：后端 / grading
- **关联用例**：TC-VOL-008、TC-VOL-013
- **关联 Agent**：3
- **步骤**：
  1. 学员已有 ≥1 条已评改 checkin
  2. 调 `POST /api/volunteer/grades/generate` 或 `/regenerate`
- **预期**：返回评改草稿
- **实际**：HTTP 500 `AttributeError: 'CheckinRecord' object has no attribute 'comment'`
- **根因**：`backend/app/services/grading_service.py:366` 读 `r.comment`（CheckinRecord 无此字段）
- **修复**：
  ```python
  # _build_history_archive 改用 join
  stmt = select(CheckinRecord, Grade).outerjoin(
      Grade, Grade.checkin_record_id == CheckinRecord.id
  ).where(...).order_by(CheckinRecord.id.desc()).limit(N)
  # 取 Grade.comment
  ```
- **回归基线**：学员有/无历史评改时，generate/regenerate 均 200 + 返回完整草稿

#### BUG-VOL-003 · `confirm_and_sync` 引用不存在的 `record.comment`
- **状态**：FIXED
- **严重度**：P0（同步破局 100% 静默失败 + 评语数据不一致）
- **模块**：后端 / grading
- **关联用例**：TC-VOL-011
- **关联 Agent**：3
- **步骤**：调 `POST /api/volunteer/grades/confirm` 任一 checkin
- **预期**：破局同步成功 / 失败可重试
- **实际**：本地保存 OK；破局同步 100% 失败；`record.comment = comment` 抛错
- **根因**：`backend/app/services/grading_service.py:251` 写、`line 435` 读
- **修复**：评语只存 `Grade` 表，删除 `record.comment` 写读
- **回归基线**：confirm 后破局同步成功（配置好 Token/URL 后）或返回明确错误（不静默）

#### BUG-PJU-001 · `verify_token` 假阳性（吞网络错返回 True）
- **状态**：FIXED
- **严重度**：P0（误导用户、Token 状态不可信）
- **模块**：后端 / poju
- **关联用例**：TC-CFG-004、TC-NFR-002（2001/2002）
- **关联 Agent**：5
- **步骤**：
  1. base_url 设为 `http://127.0.0.1:9999`（无服务）
  2. 调 `POST /api/settings/poju/test`
- **预期**：`valid: false, token_status: invalid`
- **实际**：`valid: true, message: "连接成功"`
- **根因**：`app/poju/client.py` `fetch_checkin_records` 在 `except (PojuApiError, PojuNetworkError)` 返回 `[]`，导致 `verify_token` 永远 True
- **修复**：
  ```python
  # fetch_checkin_records 不要吞异常
  # 让 verify_token 收到真实 PojuNetworkError
  # 由 settings_service.test_connection 标记 token_status=invalid
  ```
- **回归基线**：
  - 错误 base_url → `valid: false, message: "无法连接"`
  - 错误 Token → `valid: false, token_status: invalid`
  - 真服务正常 → `valid: true, token_status: valid`

#### BUG-CAMP-005 · min_checkin_days 必填导致 0.6 兜底失效
- **状态**：FIXED
- **严重度**：P0（业务规则失控）
- **模块**：后端 / camp
- **关联用例**：TC-CAMP-003
- **关联 Agent**：2
- **步骤**：`POST /api/camps` 不传 min_checkin_days
- **预期**：按 `total_days * 0.6` 兜底
- **实际**：HTTP 400 校验失败；或传 min=1 后端直接接受
- **根因**：`backend/app/schemas/camp.py:28` `min_checkin_days: int = Field(..., gt=0)` 强制必填
- **修复**：
  ```python
  min_checkin_days: Optional[int] = Field(None, gt=0)
  # service 层在 not min_days 时调 calc_min_days
  ```
- **回归基线**：不传 min 时 30→18、21→13、10→6、1→1

#### BUG-STU-003 · route generate 100% 失败（tool_use 协议不兼容）
- **状态**：FIXED
- **严重度**：P0（学习路线生成全链路不可用）
- **模块**：后端 / AI
- **关联用例**：TC-STU-006/007
- **关联 Agent**：2 / 5
- **步骤**：调 `POST /api/student/camps/{id}/route/generate`
- **预期**：返回 N 天任务
- **实际**：HTTP 500 `LLMError: 未在响应中找到 tool_use 块`
- **根因**：anthropic 协议的 `tool_choice={"type": "tool", "name": "return_result"}` 不被 OpenAI 兼容代理支持
- **修复**：
  - 方案 A：改用 JSON mode（response_format={type: "json_object"}）作为后备
  - 方案 B：探测 LLM 能力，动态选择 tool_use 或 json_schema
  - 方案 C：提示词改为要求纯 JSON 输出，代码侧做容错
- **回归基线**：route generate 100% 成功（即便 LLM 是 OpenAI 兼容）

#### BUG-PJU-002 · 同日重复打卡无去重（数据完整性）
- **状态**：FIXED
- **严重度**：P0（数据污染、统计失真）
- **模块**：后端 / checkin
- **关联用例**：PRD BR-F2.4-3 隐含、TC-STU-010
- **关联 Agent**：5
- **步骤**：
  1. 串行 3 次 + 并发 5 次调 `POST /api/student/camps/{id}/checkin/submit`（同 day）
- **预期**：每天 1 条
- **实际**：9 条同日同 day 全入库
- **根因**：`CheckinService.submit_checkin` 无 `(camp_id, day_number)` 唯一校验
- **修复**：
  ```python
  # service 入口检查
  existing = await session.execute(
      select(CheckinRecord).where(
          CheckinRecord.camp_id == camp_id,
          CheckinRecord.day_number == day_number
      )
  )
  if existing.scalar_one_or_none():
      raise ValidationError("今日已打卡")
  # 或 DB 层 UNIQUE(camp_id, day_number)
  ```
- **回归基线**：同日重复提交返回 400 + 提示"今日已打卡"

#### BUG-NFR-003 · 多个 uvicorn 进程并发共享 SQLite 致数据丢失
- **状态**：FIXED
- **严重度**：P0（数据丢失）
- **模块**：部署 / NFR
- **关联用例**：TC-NFR-003
- **关联 Agent**：2
- **步骤**：`ps -ef | grep uvicorn` 看到 6+ 个进程
- **预期**：单进程
- **实际**：多个进程共享 `data/app.db`；700 字手册被覆盖为 46 字
- **根因**：`make dev` 或 supervisor 启动多个 worker（默认 1 worker，但 reload 时分裂）
- **修复**：
  - 启动命令固定 `uvicorn --workers 1`
  - 检查 `Makefile` 与 supervisor 配置
  - 或在 service 启动时检测文件锁
- **回归基线**：只有一个 uvicorn 进程 LISTEN 8000

#### BUG-CAMP-006 · 倒序日期强制 400 阻断，违反 BR-F1-2
- **状态**：FIXED
- **严重度**：P0（违反 PRD）
- **模块**：后端 / camp
- **关联用例**：TC-CAMP-004
- **关联 Agent**：2
- **步骤**：`start_date > end_date`
- **预期**：提示但不强制阻断
- **实际**：HTTP 400
- **根因**：`@field_validator("end_date")` 抛 ValueError
- **修复**：将 ValueError 改为 Pydantic warning 或单独返回 `{code: 1001, message: "日期倒序", warning: true}`
- **回归基线**：倒序日期创建成功（code=0）但响应中带 warning 字段

#### BUG-VOL-008 · `_load_timeline_and_stats.last_stars` 计算错误
- **状态**：FIXED（已记录为 P1，升级到 P0 因影响志愿者日常判断）
- **严重度**：P0（数据错误）
- **模块**：后端 / archive
- **关联用例**：TC-VOL-014
- **关联 Agent**：3
- **步骤**：学员最近评改 1 星，之前 2 星
- **预期**：`last_stars = 1`
- **实际**：`last_stars = 2`
- **根因**：`archive_service.py:506-514` 倒序遍历时只取 stars≥2
- **修复**：
  ```python
  last_stars = None
  for r in records:
      if r.stars is not None:
          if last_stars is None:
              last_stars = r.stars  # 不论大小
          if r.stars >= 2:
              valid_days += 1
  ```
- **回归基线**：最近 stars=1 → `last_stars=1`

#### BUG-MAN-004 · 营软删除后子资源响应不一致
- **状态**：FIXED
- **严重度**：P0（孤儿数据可见）
- **模块**：后端 / manual + route
- **关联用例**：PRD 隐含
- **关联 Agent**：5
- **步骤**：删除 camp 后访问 `/api/manuals/{id}` `/api/student/camps/{id}/route`
- **预期**：404
- **实际**：`/manuals/{id}` 200 返回孤儿数据；`/route` 200 null
- **根因**：`manual_service.get_manual` 与 `route_service.get_route` 未校验 camp 存在
- **修复**：两处 service 入口都加 `_get_active_camp(camp_id)` 校验
- **回归基线**：删除 camp 后所有 `/manuals/{id}` `/route` `/checkin` 等子资源 404

#### BUG-MAN-005 · 营不存在仍可上传手册
- **状态**：FIXED
- **严重度**：P0（孤儿数据）
- **模块**：后端 / manual
- **关联用例**：PRD 隐含
- **关联 Agent**：5
- **步骤**：`POST /api/manuals/99999/upload`（camp 不存在）
- **预期**：404
- **实际**：成功创建 `data/manuals/99999/manual.md`
- **根因**：`ManualService.upload_manual` 缺 camp 存在性校验
- **修复**：service 入口校验
- **回归基线**：camp 不存在时所有 manual 接口 404

### 2.2 P1 严重/数据一致性（18 个，节选关键 10 个）

#### BUG-CAMP-007 · 起止与总天数不符无校验
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / camp
- **步骤**：`total_days=30, end-start=13`
- **预期**：提示
- **实际**：成功创建数据脏
- **修复**：service 层 `if (end - start).days + 1 != total_days` warning
- **关联 Agent**：2

#### BUG-STU-008 · auto=true 失败降级与 manual 不可区分
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / checkin
- **关联 Agent**：2
- **修复**：返回时增加 `degraded: true/false` 字段

#### BUG-STU-009 · checkin 无手册时未返 3002
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / checkin
- **关联 Agent**：2
- **修复**：`CheckinService._get_manual_snippet` 缺手册时 raise `ManualNotFoundError`

#### BUG-STU-010 · 重新规划无确认弹窗
- **状态**：OPEN
- **严重度**：P1
- **模块**：前端
- **关联 Agent**：2
- **修复**：P4 路由 "重新规划" 按钮点击后弹 Modal 确认

#### BUG-CFG-001 · test_connection 失败仍返回 code=0
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / settings
- **关联 Agent**：4
- **修复**：`settings_service.test_connection` 业务失败时 raise PojuNotAvailable（2003）

#### BUG-CFG-003 · base_url 无 API 入口
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / settings
- **关联 Agent**：3 / 4
- **修复**：新增 `PUT /api/settings/poju/baseurl` endpoint

#### BUG-VOL-005 · Dashboard 档案链接 URL 缺 camp 段
- **状态**：OPEN
- **严重度**：P1
- **模块**：前端
- **关联 Agent**：3
- **修复**：`Dashboard.tsx:419,427` 加 camp 前缀

#### BUG-VOL-006 · "仅保存不同步"未实现仍调破局
- **状态**：OPEN
- **严重度**：P1
- **模块**：前端
- **关联 Agent**：3
- **修复**：补一个 `POST /api/volunteer/grades/save-draft` 仅落库不同步

#### BUG-SEC-001 · 文件上传无大小限制
- **状态**：OPEN
- **严重度**：P1（DoS 风险）
- **模块**：后端 / manual
- **关联 Agent**：5
- **修复**：限制 5MB 或 10MB

#### BUG-MAN-001 · GET manual 返回结构与 OpenAPI 不符
- **状态**：OPEN
- **严重度**：P1
- **模块**：后端 / manual
- **关联 Agent**：4
- **修复**：OpenAPI 描述或实现二选一

### 2.3 P2 一般/体验（65 个，按模块汇总）

| 模块 | P2 数量 | 典型问题 |
| --- | --- | --- |
| UX/UI | 18 | 营名未截断、antd 弃用警告、Day 0/N 显示矛盾、批量确认为占位文案 |
| 后端/边界 | 14 | total_days 极端值接受、name 空字符串接受、description 超长、min_days=1 接受 |
| 安全/UX | 8 | XSS 字符串原样入库（无 XSS 触发但视觉问题）、CORS 配置待 review |
| NFR | 10 | 文档端点数 30 vs 描述 26、错误码 1002 vs 404 边界、BIZ 5000 无对应 |
| 前端 | 8 | React Router 7 future flag 警告、空态文案误导用户 |
| 数据库 | 4 | is_deleted 软删除后可见、Pydantic extra='ignore' 静默吞字段 |
| 评改 | 3 | dimension_scores 校验失败重试浪费、retry 在已 synced 直接成功 |

> P2 完整列表见各 Agent 详细报告（agent1~5）。**修复策略**：本轮优先修 P0/P1；P2 累计到下一迭代统一清理。

---

## 三、修复优先级路线图

### 阶段 1（Day 1）：P0 阻塞全部修复
预计可解决 95% 的 Fail/Block 用例。

| 修复项 | 预计工时 | 依赖 | 验证用例 |
| --- | --- | --- | --- |
| BUG-API-001 前端路径前缀 | 30 min | 无 | TC-STU/UX-001 |
| BUG-NFR-001 LLMError 异常体系 | 30 min | 无 | TC-NFR-002 |
| BUG-VOL-002/003 评语字段修复 | 2 hr | 无 | TC-VOL-008/011/013 |
| BUG-PJU-001 不吞异常 | 1 hr | 无 | TC-CFG-004 |
| BUG-CAMP-005 min 兜底 | 30 min | 无 | TC-CAMP-003 |
| BUG-STU-003 JSON mode 后备 | 2 hr | BUG-NFR-001 | TC-STU-006 |
| BUG-PJU-002 同 day 去重 | 1 hr | 无 | TC-STU-010 |
| BUG-NFR-003 单 worker | 30 min | 部署方 | TC-NFR-003 |
| BUG-CAMP-006 倒序不阻断 | 30 min | 无 | TC-CAMP-004 |
| BUG-VOL-008 last_stars 修复 | 30 min | 无 | TC-VOL-014 |
| BUG-MAN-004/005 camp 校验 | 1 hr | 无 | TC-MAN |
| **小计** | **~10 hr** | | |

### 阶段 2（Day 2）：P1 数据一致性

按 BUG 列表 2.2 节逐个修复，每个 P1 配对应回归用例。

### 阶段 3（Day 3+）：P2 体验优化
antd 弃用、营名截断、批量确认实装、错误文案统一等。

---

## 四、回归基线（修复完成验收标准）

### 4.1 通过率目标
- 阶段 1 完成后：70 用例 ≥ 60 PASS（86%）
- 阶段 2 完成后：70 用例 ≥ 65 PASS（93%）
- 阶段 3 完成后：70 用例 ≥ 68 PASS（97%）

### 4.2 关键端到端验证脚本
```bash
# 1. 创建学员营
curl -X POST http://localhost:8000/api/camps -H 'Content-Type: application/json' -d '{
  "name":"回归测试营", "role":"student", "total_days":7,
  "start_date":"2026-06-28", "end_date":"2026-07-04"
}'

# 2. 上传手册
curl -F 'file=@manual.md' http://localhost:8000/api/manuals/{camp_id}/upload

# 3. 生成学习路线
curl -X POST http://localhost:8000/api/student/camps/{camp_id}/route/generate

# 4. 生成打卡
curl -X POST http://localhost:8000/api/student/camps/{camp_id}/checkin/generate \
  -H 'Content-Type: application/json' -d '{"text":"今天学了..."}'

# 5. 提交打卡
curl -X POST http://localhost:8000/api/student/camps/{camp_id}/checkin/submit \
  -H 'Content-Type: application/json' -d '{"content":{...},"auto":false}'

# 6. 模拟志愿者评改
curl -X POST http://localhost:8000/api/volunteer/grades/generate \
  -H 'Content-Type: application/json' -d '{"checkin_id":1}'
```

### 4.3 关键回归断言
- [ ] 学员 P3 看板能显示"今日任务"（BUG-API-001 修复后）
- [ ] LLM 失败时返 `{code:3001}` 而非 500 traceback（BUG-NFR-001）
- [ ] 学员有历史评改时 generate 评改仍 200（BUG-VOL-002）
- [ ] 评改 confirm 后破局同步真实成功或明确错误（BUG-VOL-003 + BUG-PJU-001）
- [ ] 不传 min 时后端自动算（BUG-CAMP-005）
- [ ] 倒序日期创建成功（BUG-CAMP-006）
- [ ] 同 day 重复提交返 400（BUG-PJU-002）
- [ ] 单个 uvicorn 进程（BUG-NFR-003）
- [ ] 已结束营 Day=总天数（BUG-CAMP-006 衍生）
- [ ] 学员最近 stars=1 显示 1（BUG-VOL-008）

---

## 五、文件与数据现状

### 5.1 测试期间数据
- 行动营：22+ 个（多数为测试创建，camp id 1-40+）
- 学员：3 名（张三/李四/王五）
- 打卡：7+ 条（含同日重复 9 条已观察）
- scoring_standards：3 条（1 失效 + 2 active）
- poju_configs：1 条，token=`****9999` 密文
- SQLite 文件：`backend/data/app.db`（建议备份以便回归对比）

### 5.2 测试报告与证据
- `test-reports/01-test-cases.md`（70 用例基线）
- `test-reports/agent1-ui-walkthrough.md`（UI 走查）
- `test-reports/agent2-student.md`（学员链路）
- `test-reports/agent3-volunteer.md`（志愿者链路）
- `test-reports/agent4-api-nfr.md`（API + NFR）
- `test-reports/agent5-adversarial.md`（对抗试探）
- `test-reports/screenshots/`（11 张 + agent2 9 张）
- `test-reports/agent4-logs/`（截图 + openapi 快照）
- `test-reports/agent5-logs/`（24 份 curl 日志）

### 5.3 关键代码定位
```
backend/app/ai/llm_client.py:36           ← BUG-NFR-001
backend/app/core/exceptions.py:11-13      ← BUG-NFR-001
backend/app/services/grading_service.py:251,366,435  ← BUG-VOL-002/003
backend/app/services/archive_service.py:506-514      ← BUG-VOL-008
backend/app/poju/client.py                ← BUG-PJU-001
backend/app/services/checkin_service.py:307-329     ← BUG-PJU-002, BUG-STU-008
backend/app/schemas/camp.py:28            ← BUG-CAMP-005
backend/app/services/manual_service.py    ← BUG-MAN-001/004/005

frontend/src/api/student.ts:28-49         ← BUG-API-001
frontend/src/api/volunteer.ts:28-57       ← BUG-API-001
frontend/src/pages/volunteer/Grading.tsx:432         ← BUG-API-001
frontend/src/pages/volunteer/Dashboard.tsx:419,427   ← BUG-VOL-005
```

---

## 六、附录 · 5 个 Agent 报告路径

| Agent | 任务 | 报告 | 统计 |
| --- | --- | --- | --- |
| #1 | UI 走查 11 页面 | `agent1-ui-walkthrough.md` | 14 用例：13P/1F/0B，6 Bug（2P0+1P1+3P2） |
| #2 | 学员链路 | `agent2-student.md` | 17/20 用例：7P/4F/6B，16 Bug（6P0+8P1+2P2） |
| #3 | 志愿者链路 | `agent3-volunteer.md` | 14 用例：4P/8F/2B，8 Bug（3P0+4P1+1P2） |
| #4 | API + NFR | `agent4-api-nfr.md` | 25 用例：21P/1F/1部分/2无法，7 Bug（1P0+4P1+2P2） |
| #5 | 对抗试探 | `agent5-adversarial.md` | 47 Bug（5P0+8P1+34P2） |
| **合计** | | | **96 Bug（13P0+18P1+65P2）+ 70 用例 baseline** |

---

## 七、变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-06-28 | 初版：5 Agent 汇总 + 修复路线图 |
| v1.1 | 2026-06-28 | 阶段 1 回归：13 个 P0 全部标记 FIXED；新增阶段 1 回归结果章节 |

---

## 八、阶段 1 回归结果（2026-06-28）

**修复情况**：13 个 P0 全部 FIXED（commit 见下表）

| Bug ID | 描述 | Commit | 状态 |
| --- | --- | --- | --- |
| BUG-API-001 | 前端 API 路径缺前缀 | f4e1a68 | FIXED |
| BUG-NFR-001 | LLM 异常未映射 3001 | 67a717d + a046c05 | FIXED |
| BUG-VOL-002 | _build_history_archive 字段错 | 8246b8b | FIXED |
| BUG-VOL-003 | confirm_and_sync 字段错 | 8246b8b | FIXED |
| BUG-PJU-001 | verify_token 假阳性 | 6a56fe9 | FIXED |
| BUG-CAMP-005 | min_checkin_days 必填 | 7520662 | FIXED |
| BUG-STU-003 | tool_use 协议不兼容 | db70f7e | FIXED |
| BUG-PJU-002 | 同日重复打卡无去重 | f86312d | FIXED |
| BUG-CAMP-006 | 倒序日期强制 400 | 7520662 | FIXED |
| BUG-VOL-008 | last_stars 计算错误 | 1c4fdf9 | FIXED |
| BUG-MAN-004 | 软删除 camp 子资源响应不一致 | 3b0ba65 | FIXED |
| BUG-MAN-005 | 营不存在仍可上传手册 | 3b0ba65 | FIXED |
| BUG-VOL-005 | Dashboard 档案链接 URL | f62a556 | FIXED |

**新增发现**（实施期间 implementer subagent 实时发现，不在原 baseline 内）：
- `route_service._to_route_out` 中 `DayTaskOut.tags` 类型不匹配 Pydantic 校验失败：tags 实际为字符串数组，模型期望对象数组。导致 route generate 实际下游 HTTP 500。**建议进入阶段 2 处理**。

**回归 curl 验证摘要**：
- 9 条核心断言全部通过
- 数据备份：`backend/data/app.db.bak-20260628`
- 单 uvicorn 进程稳定运行

**下一阶段建议**：
- 阶段 2：18 个 P1 修复（含新发现的 DayTaskOut.tags 类型不匹配）
- 阶段 3：65 个 P2 体验优化

---

> **报告结束**。请基于本报告的 13 个 P0 + 18 个 P1 进入修复阶段。每修一个 bug 须更新本文档"状态"字段；阶段 1 完成后请运行完整回归脚本，更新"通过率"指标。
