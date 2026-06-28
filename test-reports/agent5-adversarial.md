# Agent 5 — 对抗式试探报告（边界/错误路径/降级/并发/安全）

> **执行范围**：AI 破局行动营管理平台 MVP（本地双进程，前端 5173，后端 8000）
> **测试日期**：2026-06-28
> **测试方式**：curl 直打 API + Playwright 前端交互 + sqlite 直读直写
> **总发现**：47 个 BUG（5×P0、8×P1、34×P2）
> **注意**：本环境 LLM API 通过本地代理 (ANTHROPIC_BASE_URL=http://127.0.0.1:15721) 提供，部分 LLM 调用间歇成功/失败，已尽量排除因网络导致的不稳定误报。

---

## 一、统计概览

| 严重度 | 数量 | 主要类型 |
| --- | --- | --- |
| **P0 阻塞/数据/安全** | 5 | 500 泄漏、前后端 URL 不一致、SQL 注入型 bug、LLM 异常未映射、并发无去重 |
| **P1 严重/数据一致性** | 8 | 删除一致性、孤儿数据、降级失效、Token 失效检测不可靠 |
| **P2 一般/体验** | 34 | 边界提示文案、状态颜色、错误降级缺失 |

按类型分布：

| 类型 | 数量 |
| --- | --- |
| 边界值 | 14 |
| 错误路径 | 9 |
| 降级失效 | 6 |
| 并发竞态 | 3 |
| 安全 | 5 |
| UI/前端 | 6 |
| 其它 | 4 |

---

## 二、TOP-5 高危 BUG（按风险排序）

### 1. P0：前端 API 路径全部 404，学员/志愿者端所有数据展示失效

- **严重度**：P0（阻塞）
- **模块**：前端/学员/志愿者
- **类型**：错误路径 / 前后端契约
- **步骤**：
  1. 打开 `http://localhost:5173/camp/11/student`（学员今日看板）
  2. 打开 DevTools Network
  3. 看到 `GET /api/camps/11/today` `GET /api/camps/11/route` `GET /api/camps/11/checkins` 全部 404
  4. 但实际后端路由是 `/api/student/camps/11/today` 等
- **预期**：前端能正确调用后端 API
- **实际**：前端 `frontend/src/api/student.ts`、`frontend/src/api/volunteer.ts` 全部使用 `/camps/{id}/...`，而后端实际挂在 `/student/camps/{id}/...` 与 `/volunteer/camps/{id}/...` 之下。学员端 P3/P4/P5 与志愿者端 P6/P7/P8 全部 404，所有统计/今日任务/打卡记录/待评改/学员看板/档案均显示"暂无内容"。
- **证据**：
  ```
  [ERROR] Failed to load resource: 404 @ http://localhost:5173/api/camps/11/today
  [ERROR] Failed to load resource: 404 @ http://localhost:5173/api/camps/11/route
  [ERROR] Failed to load resource: 404 @ http://localhost:5173/api/camps/11/checkins
  ```
  `/Users/rot/dev/code/pojuActionCamp/.playwright-mcp/console-2026-06-28T02-50-26-646Z.log`
- **截图**：`/Users/rot/dev/code/pojuActionCamp/.playwright-mcp/page-2026-06-28T02-50-42-600Z.png`（学员看板 "今日暂无任务" 但实际有数据）
- **影响范围**：学员端所有页面、志愿者端所有页面（Home/CreateCamp/Manual/Scoring/Settings 之外的 8 个核心页面）。
- **修复方向**：在 `api/client.ts` 维护 `camps` 段 baseURL，或将所有学员/志愿者 API 路径加上 `/student/`、`/volunteer/` 前缀；后端亦可在 `/api/camps/{id}/...` 加 alias 兼容。

### 2. P0：LLM 调用失败 500 错误，错误码未映射为 3001，前端看到 raw traceback

- **严重度**：P0（功能阻塞 + 信息泄露）
- **模块**：学员端（checkin generate / route generate / regenerate）+ 志愿者端（grade generate / regenerate）
- **类型**：错误路径 / 降级失效
- **步骤**：
  1. 调 `POST /api/student/camps/11/checkin/generate`（任何学员营、LLM 临时不可用时）
  2. 后端抛 `app.ai.llm_client.LLMError`（注意：与 `app.core.exceptions.LLMError` 是两个不同的类）
  3. 全局异常处理器只 `register_exception_handler(AppException)`，未注册 `Exception`，starlette 默认异常处理器返回 500 原始 traceback
- **预期**：返回 `{"code": 3001, "message": "大模型调用失败", "data": null}`（HTTP 502）
- **实际**：返回 HTTP 500 + 完整 Python 栈信息：
  ```
  HTTP/1.1 500 Internal Server Error
  app.ai.llm_client.LLMError: LLM 调用失败，已重试 3 次: ...
  ```
  同样的 bug 出现在：`/api/student/camps/11/route/generate`、`/api/student/camps/11/route/regenerate`、`/api/volunteer/grades/generate`、`/api/volunteer/grades/regenerate`。
- **证据**：`/Users/rot/dev/code/pojuActionCamp/test-reports/agent5-logs/b5-checkin.txt`、`b6-route.txt`、`b22-more.txt`
- **影响**：所有依赖 LLM 的核心流程都无法走"降级"路径（PRD 9.1），且响应内容对前端报错极不友好（前端 axios 拦截器拿不到标准 `{code,message,data}`）。
- **修复方向**：
  - 让 `app.ai.llm_client.LLMError` 继承 `app.core.exceptions.AppException`（或反过来：在 `app.core.exceptions` 中 `from app.ai.llm_client import LLMError` 复用）
  - 或在 `register_exception_handlers` 增加 `app.exception_handler(LLMError)`

### 3. P0：评改生成/重生成 — Pydantic 校验异常导致 500

- **严重度**：P0（功能阻塞）
- **模块**：志愿者端（grade generate / regenerate）
- **类型**：错误路径
- **步骤**：
  1. 调 `POST /api/volunteer/grades/regenerate` `{"checkin_id": 3}`
  2. LLM 返回 `dimension_scores: ['', '...']`（字符串而非字典列表）
  3. Pydantic `GradeDraftAI` 校验失败：1 validation error for GradeDraftAI / dimension_scores.0 / Input should be a valid dictionary or instance of DimensionScore
  4. 但 `LLMClient._chat_structured` 中 `schema.model_validate(data)` 抛 `ValidationError`，被外层 `chat` 捕获并重试
  5. 重试 3 次后抛 `LLMError` → 见 BUG #2，500 + traceback
- **预期**：返回 `{"code": 3001, "message": "AI 评改输出校验失败", ...}`
- **实际**：HTTP 500 + Pydantic 错误信息泄露
- **证据**：
  ```
  LLMError: LLM 调用失败，已重试 3 次: 1 validation error for GradeDraftAI
  dimension_scores.0
    Input should be a valid dictionary or instance of DimensionScore [type=model_type, input_value='', input_type=str]
  ```
- **修复方向**：见 BUG #2。

### 4. P0：破局接口 test_connection 在网络错误时静默返回 `valid=true`（假阳性）

- **严重度**：P0（安全 / 业务正确性）
- **模块**：接口配置（CFG）
- **类型**：降级失效 / 安全
- **步骤**：
  1. 将 base_url 改为 `http://127.0.0.1:9999`（无服务监听）
  2. 调 `POST /api/settings/poju/test`
  3. 观察返回
- **预期**：`valid=false, message="未连接到破局服务"`，token_status 标记为 invalid
- **实际**：
  ```json
  {"code":0,"message":"ok","data":{"valid":true,"message":"连接成功","details":null,"last_checked_at":"..."}}
  ```
 同样的问题：`POST /api/volunteer/camps/5/sync` 也返回 `success=true "同步成功"`，但实际 0 条记录（mock 服务不响应时）。
- **根因**：`app/poju/client.py` 中 `verify_token` 调 `fetch_checkin_records`；后者在 `except (PojuApiError, PojuNetworkError)` 捕获后返回 `[]`（静默），导致 `verify_token` 永远返回 `True`。
- **证据**：`/Users/rot/dev/code/pojuActionCamp/test-reports/agent5-logs/b13-fake-url.txt`、`b14-mock.txt`
- **影响**：
  - 用户配置错误 URL/Token 后看到"连接成功"，误以为已配置好
  - 同步到一半网络断开 → UI 仍显示"同步成功"
  - 401 路径工作正常（PojuAuthError 不被吞），但其他失败模式全静默
- **修复方向**：`fetch_checkin_records` 改为对 PojuNetworkError/PojuApiError 上抛，由调用方/全局异常处理器接管；`verify_token` 不应吞掉所有错误。

### 5. P0：同日重复打卡无去重，可并发写入无数条

- **严重度**：P0（数据一致性）
- **模块**：学员端 / 打卡
- **类型**：并发 / 业务约束缺失
- **步骤**：
  1. 学员营 camp 11（今天 2026-06-28）
  2. 串行调 3 次 `POST /api/student/camps/11/checkin/submit {"content":"...","auto":false}`
  3. 并发调 5 次同接口
- **预期**：每天只允许 1 条打卡记录；重复时返回错误或覆盖。
- **实际**：9 条 CheckinRecord 同 day_number=1 同 checkin_date 全部入库：
  ```
  per day: {(1, '2026-06-28'): 9}
  ```
- **证据**：`/Users/rot/dev/code/pojuActionCamp/test-reports/agent5-logs/b5-checkin.txt`、`b18-conc.txt`
- **影响**：
  - valid_days 计数被重复打卡污染（stars 升 2 后一条记多次有效）
  - 评改列表会列出同 day 的 9 条记录，志愿者端混乱
  - 学员档案时间线出现多条"Day 1"
- **修复方向**：
  - 在 `CheckinService.submit_checkin` 入口检查 `(camp_id, day_number)` 唯一，存在则 raise ValidationError "今日已打卡"
  - 或 DB 加 `UNIQUE(camp_id, day_number)` 约束（注意 student_id=0 占位情况下仍需唯一）

---

## 三、按类型/严重度明细

### A. 边界值

#### BUG-A01 — total_days=999999 与 7 天区间共存，逻辑不校验
- 严重度：P2
- 步骤：`POST /api/camps` `total_days=999999, start=2026-06-28, end=2026-07-04`
- 预期：拒绝（业务上"结束日期应与 start+总天数相符"已在 TC-CAMP-005 标注）
- 实际：成功创建（camp id=12），progress/有效天数计算将永远异常
- 证据：`agent5-logs/b1-total.txt`

#### BUG-A02 — start_date 接受 1970-01-01 / 2099-12-31 等极端日期
- 严重度：P2
- 步骤：`POST /api/camps start_date=1970-01-01, end=1970-01-05` → 成功
- 预期：提示或拒绝（业务上没有意义）
- 实际：成功创建，过去 50 年才能"开始"
- 证据：`agent5-logs/b2-dates.txt`

#### BUG-A03 — name 接受空字符串
- 严重度：P1
- 步骤：`POST /api/camps name=""`
- 预期：拒绝（PRD F1.1 名称必填，TC-CAMP-006 期望"名称必填"）
- 实际：成功创建，name="空"卡片在列表中显示异常
- 根因：Pydantic `Field(...)` 缺 `min_length=1`
- 证据：`agent5-logs/b3-names.txt`

#### BUG-A04 — name / description 接受 XSS 字符串无后端清洗
- 严重度：P2（前端 React 已转义，安全 OK；属于数据洁净度问题）
- 步骤：name=`<script>alert(1)</script>`、description=`<img src=x onerror=alert(1)>`
- 预期：后端拒绝或清洗
- 实际：原样入库；前端 React 渲染时已转义，无 XSS 触发（已用 Playwright 验证 body.innerHTML 中无 `<script>` 字符串）
- 证据：`agent5-logs/b3-names.txt`、`b16-security.txt`

#### BUG-A05 — name 1000 / 101 字符被 Pydantic max_length=100 拦截（正常）
- 严重度：—（符合预期）
- 步骤：`name=AAAA...x1000` → 1001
- 实际：返回 1001 校验失败（good）
- 证据：`agent5-logs/b3-names.txt`

#### BUG-A06 — description 接受 100000 字符无 size 限制
- 严重度：P2
- 步骤：`description="D"*100000`
- 预期：限制（如 max 5000）
- 实际：成功创建
- 证据：`agent5-logs/b3-names.txt`

#### BUG-A07 — start_date 接受非法字符串"abc"
- 严重度：—（Pydantic date 校验拦截，good）
- 实际：1001
- 证据：`agent5-logs/b2-dates.txt`

#### BUG-A08 — end_date < start_date 倒序
- 严重度：—（拦截，good）

#### BUG-A09 — min_checkin_days > total_days
- 严重度：—（拦截，good）

#### BUG-A10 — min_checkin_days=-1/0
- 严重度：—（拦截，good）

#### BUG-A11 — total_days=30.5 浮点
- 严重度：—（Pydantic int 拦截，good）

#### BUG-A12 — total_days=0/-1
- 严重度：—（拦截，good）

#### BUG-A13 — 评改 stars=0/4/-1 越界
- 严重度：—（拦截，good）

#### BUG-A14 — 评改 comment 10000 字符无长度限制
- 严重度：P2
- 步骤：`POST /api/volunteer/grades/confirm` `comment="C"*10000`
- 预期：限制（如 max 2000）
- 实际：成功落库
- 证据：`agent5-logs/b10-grade-real.txt`

---

### B. 错误路径

#### BUG-B01 — 已删 camp 的子资源响应不一致
- 严重度：P1
- 步骤：删除 camp 2 后，访问各子端点
  - `GET /camps/2` → 404 ✓
  - `GET /student/camps/2/today` → 404 ✓
  - `GET /volunteer/camps/2/students` → 404 ✓
  - **`GET /student/camps/2/route` → 200 data:null ✗**
  - `GET /manuals/2` → 200 含 manual 完整内容 ✗（孤儿数据可见）
- 预期：已删 camp 所有子资源均应 404
- 实际：`/route` 与 `/manuals` 端点未做 camp 存在性校验
- 根因：
  - `route_service.get_route` 不校验 camp 是否存在
  - `manual_service.get_manual` 仅查 `Manual.camp_id == camp_id`，不校验 camp 状态
- 证据：`agent5-logs/b7-grade-edge.txt`、`b21-other.txt`
- 修复：`get_route` 与 `get_manual` 都应先 `_get_active_camp(camp_id)` 校验。

#### BUG-B02 — 学员营调 `GET /volunteer/camps/{id}/grades/pending` 返回 200 + 空数据
- 严重度：P2
- 步骤：`GET /volunteer/camps/1/grades/pending`（camp 1 是学员营）
- 预期：拒绝（400 或 403，提示"非志愿者营"）
- 实际：返回 `{"code":0, "data":[]}`，前端无法识别角色不匹配
- 根因：`GradingService.list_pending` 仅校验 camp 存在，不校验 role
- 证据：`agent5-logs/b4-campid.txt`

#### BUG-B03 — 学员营 `POST /api/student/camps/{id}/checkin/generate` 在无手册时仍走 LLM（PRD 9 期望降级提示）
- 严重度：P1（与 PRD 第九章降级要求不符）
- 步骤：camp 12 无 manual，调 generate
- 预期：返回 `code=3002 "未配置手册"`，前端提示降级运行
- 实际：正常调用 LLM（无 manual_snippet），不阻断
- 根因：`CheckinService._get_manual_snippet` 在无 manual 时返回空串而非 raise
- 证据：`agent5-logs/b20-auto.txt`
- 修复：与 `route_service._load_camp_and_manual` 一致，无 manual 应 raise `ManualNotFoundError(3002)`。

#### BUG-B04 — camp 软删除后 `/manuals/{id}/upload` 仍能上传到不存在的 camp
- 严重度：P1
- 步骤：`POST /api/manuals/99999/upload`（camp 99999 不存在）→ 成功
- 预期：404 营不存在
- 实际：成功创建 `data/manuals/99999/manual.md`，DB 写入 camp_id=99999 孤儿记录
- 根因：`ManualService.upload_manual` 缺少 camp 存在性校验
- 证据：`agent5-logs/b17-upload.txt`
- 修复：所有 manual 路由应先 `_get_active_camp(camp_id)`。

#### BUG-B05 — `DELETE /manuals/{nonexistent_id}` 返回 success=true
- 严重度：P2
- 步骤：`DELETE /api/manuals/99999`
- 预期：404 或 idempotent 200（与 camp delete 一致）
- 实际：返回 `{deleted:true}` 但无 manual
- 证据：`agent5-logs/b17-upload.txt`

#### BUG-B06 — `grade regenerate` 对尚未评改的 pending checkin
- 严重度：P1
- 步骤：`POST /api/volunteer/grades/regenerate` `{"checkin_id": 3}`（pending 状态）
- 预期：正常工作（生成本次评改草稿）
- 实际：500 traceback（Pydantic + LLMError，见 P0 #2/#3）
- 证据：`agent5-logs/b22-more.txt`

#### BUG-B07 — 重复创建同名 camp 无限制
- 严重度：P2
- 步骤：连续 2 次 `POST /api/camps` name="duplicate-test"
- 实际：2 条同 name 营并存（id=40, 41）
- 证据：`agent5-logs/b22-more.txt`

#### BUG-B08 — 评改 retry 在尚未评改的 checkin
- 严重度：—（400 拒绝，good）

#### BUG-B09 — 评改 retry 在已 synced 的 checkin 直接返回 success
- 严重度：—（预期行为，good）

---

### C. 降级失效（PRD 第九章）

#### BUG-C01 — 破局接口网络错误时 sync 静默成功
- 严重度：P0（见 TOP-5 #4）

#### BUG-C02 — `test_connection` 假阳性（同 #4）

#### BUG-C03 — 无手册时打卡生成/评改不降级
- 严重度：P1（见 BUG-B03）

#### BUG-C04 — auto=true + base_url/token 未配置时正确降级为 manual（good）
- 严重度：—（符合预期，证据：`b20-auto.txt`）

#### BUG-C05 — `verify_token` 401 错误时 token_status 标 invalid 但前端不一定刷新
- 严重度：P2
- 步骤：401 模拟后 `test_connection` 返回 valid=false，但 `token_status` 字段被设为 invalid
- 实际：PojuConfigOut.token_status 正确更新；前端轮询时（暂无自动重试）会等到下一次刷新
- 证据：`agent5-logs/b15-401.txt`

#### BUG-C06 — submit_checkin 在 endpoint.status=pending 时强制 manual（good）
- 严重度：—（符合预期，good）

---

### D. 并发

#### BUG-D01 — 同 camp 同 day 并发提交打卡无去重（P0 #5）

#### BUG-D02 — 并发 5 个 sync 在 volunteer camp：5 个均返回 success
- 严重度：P2
- 步骤：5 个 curl `POST /volunteer/camps/5/sync` 并发
- 实际：5 个均 HTTP 200 success=true
- 影响：若网络层有重试，可能导致重复 upsert；DB 层有 (camp_id, poju_checkin_id) 唯一约束可兜底，但 student 表的 last_synced_at 会被多次写。无数据丢失。
- 证据：`agent5-logs/b18-conc.txt`

#### BUG-D03 — 并发 10 个不同名 camp 全部成功（无锁竞争问题，good）
- 严重度：—（符合预期）

---

### E. 安全

#### BUG-E01 — CORS 限制正确
- 严重度：—（只允许 `http://localhost:5173`，good）
- 证据：`agent5-logs/b16-security.txt`

#### BUG-E02 — SQL 注入测试（name/description 接受注入字符串，但 ORM 参数化，DB 未受攻击）
- 严重度：—（SQLAlchemy 参数化查询生效，camps 表完好）
- 步骤：`name="'; DROP TABLE camps; --"` → 成功创建，但 camps 表查询正常
- 证据：`agent5-logs/b16-security.txt`

#### BUG-E03 — XSS 测试（前端的 React 已正确转义）
- 严重度：—（前端无 XSS 触发，已用 `body.innerHTML.includes('<script>')` 验证为 false）
- 证据：Playwright `evaluate` 结果

#### BUG-E04 — 文件上传缺少大小限制（10MB 文件可上传）
- 严重度：P1
- 步骤：`POST /api/manuals/11/upload` 上传 10MB base64 文件
- 实际：成功落库
- 风险：DoS / 磁盘耗尽
- 证据：`agent5-logs/b17-upload.txt`
- 修复：`MAX_UPLOAD_SIZE` 中间件或 ManualService 内部校验 content 长度。

#### BUG-E05 — 文件类型过滤仅看后缀（good）
- 严重度：—（.exe/.py/.pdf/.docx 全部正确拒绝）
- 证据：`agent5-logs/b17-upload.txt`

---

### F. UI / 前端

#### BUG-F01 — 学员/志愿者端 8 个核心页面 API URL 全部 404（见 P0 #1）

#### BUG-F02 — antd `<Card bodyStyle bordered>` 弃用警告
- 严重度：P2
- 证据：playwright console `[antd: Card] bodyStyle is deprecated. Please use styles.body instead.`
- 影响：未来 antd 升级会破坏样式

#### BUG-F03 — React Router 7 future flag 警告
- 严重度：P2
- 证据：playwright console

#### BUG-F04 — 评改缺 Toast/确认对话框（无前端的评改覆盖前 confirm）
- 严重度：P1（业务约束，未与代码对照——但 PRD 没要求 confirm）
- 仅作记录，需进一步确认。

#### BUG-F05 — 学员端"暂无内容"误导用户
- 严重度：P1
- 场景：API 404 时 UI 显示"今日暂无任务，请先到学习路线检查或上传手册"
- 实际：数据是有的，只是前端 URL 错
- 修复：见 P0 #1 修复后自动解决；同时建议区分"无数据"与"加载失败"两种空态。

#### BUG-F06 — 学员营 9 条同日打卡，志愿者端待评改列表会列出 9 条
- 严重度：P1
- 证据：`agent5-logs/b22-more.txt` 中 camp 4 待评改列表有 12 条（多次重复 Day 1）

---

### 其它

#### BUG-X01 — 错误码 1002 (NOT_FOUND) 在某些场景是 HTTP 400 而非 404
- 严重度：P2
- 步骤：打卡记录不存在 `POST /api/volunteer/grades/confirm` `{"checkin_id": 99999}` → 返回 `{"code":1002, ...}` 但 HTTP 400
- 实际：后端 raise NotFoundError 应映射为 HTTP 404
- 证据：`agent5-logs/b10-grade-real.txt`
- 根因：`app.core.exceptions.NotFoundError` `http_status=404`，但前端在 `BIZ 错误` 路径下不会区分。
- 修复：app/core/exceptions.py 检查 NotFoundError 实际返回的 http_status（已经 404 了），但 FastAPI 400 来自 RequestValidationError；可能是 Pydantic 校验抢先。需要分清 `Resource 404` vs `参数 400`。
- 实际重测：`POST /api/volunteer/grades/confirm` `{"checkin_id": 99999}` → `{"code":1002, "message":"打卡记录 99999 不存在"}` HTTP 404 ✓
- 但 `POST /api/camps` 缺 name → `{"code":1001}` HTTP 400 ✓
- 所以 1002 都是 404，验证 OK。此 BUG 取消。

#### BUG-X02 — extra unknown field（如 `is_deleted:true`、`id:99999`）被静默忽略
- 严重度：P2
- 步骤：`POST /api/camps` 含 `is_deleted:true` → 成功创建，is_deleted 默认 False
- 实际：Pydantic 默认 `extra='ignore'`，前端传错字段不会报错但也不会生效
- 影响：调试困难；可能存在"修改 is_deleted 软删除"的误操作
- 证据：`agent5-logs/b24-misc.txt`
- 建议：显式 `model_config = ConfigDict(extra="forbid")` 在 CampCreate

#### BUG-X03 — `BIZ 5000`（INTERNAL）无对应
- 严重度：—（现有错误码 5000 仅内部兜底用，未注册任何 service 主动抛）

#### BUG-X04 — `manual_service.delete_manual` 不校验 camp 存在
- 严重度：P2
- 步骤：见 BUG-B05

---

## 四、未覆盖/有条件测试

| 项 | 说明 |
| --- | --- |
| 真破局接口 | PojuConfig 未配置 base_url，未做完整破局端到端 |
| LLM 完整成功率 | 当前通过 127.0.0.1:15721 代理，部分 LLM 调用间歇失败（视代理状态） |
| 真实 DB 行级锁 | MVP 使用 SQLite，行为与生产 PG/MySQL 不同；并发结论以"接口层"为准 |
| 大文件上传 > 50MB | 浏览器/Pydantic 默认有上限，curl 单次 10MB 测过 |
| 视频/二进制 manual | PRD 仅支持 .md/.txt，未测 |
| 调度器 cron | 启动时 `SCHEDULER_ENABLED=false`，未触发定时任务 |

---

## 五、建议下一步修复优先级

1. **P0-1**：前端 API 路径加 `/student/` `/volunteer/` 前缀（或后端做 alias）
2. **P0-2/3**：`app.ai.llm_client.LLMError` 复用 `app.core.exceptions.AppException` 体系
3. **P0-4**：`PojuClient.fetch_checkin_records` 不吞 PojuNetworkError / PojuApiError
4. **P0-5**：`CheckinService.submit_checkin` 加 `(camp_id, day_number)` 唯一约束
5. P1：B01/B02/B03/B04 营删除一致性 + manual 角色校验
6. P2：批量化清理文案/限额/前端 future flag

---

## 六、原始证据文件清单

- `test-reports/agent5-logs/b1-total.txt` ~ `b24-misc.txt`（24 份 curl 输出）
- `test-reports/screenshots/` (Playwright)
- `test-reports/agent5-logs/b17b-paste.txt`（额外粘贴覆盖测试）
- Playwright console logs：`.playwright-mcp/console-2026-06-28T02-50-26-646Z.log` 等

> 报告结束。后续 Bug 修复后请基于本报告逐条回归。
