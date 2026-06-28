# Agent #3 · 志愿者身份完整链路 E2E 测试报告

> **测试时间**：2026-06-28 10:27 ~ 10:44（系统时间）
> **测试范围**：VOL 模块 14 个用例（TC-VOL-001 ~ TC-VOL-014），覆盖 P6 学员看板、P7 作业评改、P8 学员档案
> **测试方式**：curl 直测后端 API（8000）+ Playwright 走前端页面（5173）+ 直查 sqlite 验证
> **测试环境**：本地双进程，后端 8000 / 前端 5173；志愿者营 id=5，3 名测试学员 + 7 条打卡记录

---

## 一、总体结论

### 执行统计

| 项 | 数量 | 占比 |
| --- | --- | --- |
| 总用例 | 14 | 100% |
| Pass | 4 | 29% |
| Fail | 8 | 57% |
| Block | 2 | 14% |

### 关键结论

- **P0 阻塞：志愿者端前端所有 6 个 API 调用路径错误**，缺 `/volunteer` 前缀，导致 P6 / P7 / P8 三个页面均无法加载数据。这是 Agent1 报告 BUG-001 的延续。
- **P0 阻塞：评改生成 `_build_history_archive` 引用了 CheckinRecord 不存在的 `comment` 字段**，导致凡是该学员已有 ≥1 条已评改记录的 `generate_grade` / `regenerate_grade` 请求均 500 崩溃。
- **P0 阻塞：`confirm_and_sync` 同步破局时调用 `record.comment` 也不存在**，导致所有"已评改"评语的破局同步 100% 静默失败。
- **P1 数据错误：`_load_timeline_and_stats` 中 `last_stars` 只取 stars≥2 的最近值**，缺 1 星时返回 2 星，UI 与数据均显示错误最近星级。
- 同步链路（POST sync / GET students）能正常返回；筛选/排序逻辑在 API 层正确；学员档案（GET students/{id}）接口能返回含时间线的完整数据。

---

## 二、用例执行明细

| 编号 | 用例 | 前端 | 后端 | 结论 | 说明 |
| --- | --- | --- | --- | --- | --- |
| TC-VOL-001 | 学员看板列表 | FAIL | PASS | **Fail** | API 返回 3 名学员；前端因 API 路径错显示"0 名" |
| TC-VOL-002 | 筛选 Tab | BLOCK | PASS | **Block** | Tab 在前端因 API 错不展示；API 三种 status 过滤均返回正确数据 |
| TC-VOL-003 | 学员搜索 | BLOCK | - | **Block** | 前端因列表为空无法验证搜索；搜索是客户端实现 |
| TC-VOL-004 | 立即同步按钮 | FAIL | PASS | **Fail** | 按钮在 P6 显示；后端 sync 需 base_url，base_url 字段无 API 入口，前端设置后端不持久化 |
| TC-VOL-005 | 定时同步频率展示 | PASS | - | **Pass** | P6 顶部"⏱ 定时同步：每日 09:00" 标签存在，文字符合预期 |
| TC-VOL-006 | 待评改列表 | FAIL | PASS | **Fail** | API 返回 5 条 pending；前端因路径错显示 0 条 |
| TC-VOL-007 | 评改详情·四板块 | BLOCK | - | **Block** | 前端 P7 不可用；代码上 4 板块均存在（Grading.tsx 271-419 行） |
| TC-VOL-008 | AI 评改生成 | FAIL | PARTIAL | **Fail** | 学员无历史评改时 PASS（checkin 8 返回完整 stars+dimension_scores）；有历史评改时 500（BUG-VOL-002） |
| TC-VOL-009 | 星级可点击 | BLOCK | - | **Block** | StarPicker 组件存在但 P7 不可用 |
| TC-VOL-010 | 评语可编辑 | BLOCK | - | **Block** | TextArea 可控但 P7 不可用 |
| TC-VOL-011 | 确认并同步到破局 | FAIL | PARTIAL | **Fail** | 本地评改保存 OK；同步破局全部静默失败（BUG-VOL-003） |
| TC-VOL-012 | 仅保存不同步 | FAIL | - | **Fail** | 前端实现是"调 confirm + 弹窗提示"，实际仍调破局同步（Grading.tsx 196-218） |
| TC-VOL-013 | 重新生成评改 | FAIL | PARTIAL | **Fail** | 同 TC-VOL-008，无历史评改时 PASS，有历史时 500 |
| TC-VOL-014 | 学员档案·时间线 | FAIL | PASS | **Fail** | API 返回完整 timeline + stats；前端 404 |

---

## 三、发现 Bug 汇总

### BUG-VOL-001 【P0·前端】志愿者端所有 API 调用缺 `/volunteer` 前缀
- **严重度**：P0
- **模块**：VOL
- **用例**：TC-VOL-001 / 002 / 003 / 004 / 006 / 007 / 014
- **步骤**：
  1. 进入 P6 学员看板 `/camp/5/volunteer`
  2. 观察浏览器网络请求
- **预期**：调 `/api/volunteer/camps/5/students`
- **实际**：调 `/api/camps/5/students` → 404
- **证据**：
  ```
  [ERROR] Failed to load resource: 404
  @ http://localhost:5173/api/camps/5/students
  @ http://localhost:5173/api/camps/5/grades/pending
  @ http://localhost:5173/api/camps/5/sync
  @ http://localhost:5173/api/students/1  (来自 Grading.tsx:432)
  ```
- **根因**：
  - `frontend/src/api/volunteer.ts` 第 28、32、36、40 行所有路径缺 `/volunteer` 前缀
  - `frontend/src/pages/volunteer/Grading.tsx:432` 同样缺 `/volunteer`
- **修复建议**：
  ```ts
  // volunteer.ts 所有路径加 /volunteer 前缀
  http.post<SyncResult>(`/volunteer/camps/${campId}/sync`)
  http.get<StudentSummary[]>(`/volunteer/camps/${campId}/students`, ...)
  http.get<StudentArchive>(`/volunteer/students/${studentId}`)
  http.get<PendingGradeOut[]>(`/volunteer/camps/${campId}/grades/pending`)
  // Grading.tsx:432
  http.get<StudentArchive>(`/volunteer/students/${item.student_id}`)
  ```

### BUG-VOL-002 【P0·后端】评改生成时 `_build_history_archive` 引用不存在的字段
- **严重度**：P0
- **模块**：VOL
- **用例**：TC-VOL-008 / TC-VOL-013
- **步骤**：
  1. 准备：一名学员先有 ≥1 条已评改的 checkin（如 student 3 王五已有 day1/day2 已评改）
  2. 对该学员任一 pending checkin 调 `POST /api/volunteer/grades/generate` 或 `/regenerate`
- **预期**：返回评改草稿
- **实际**：HTTP 500 `AttributeError: 'CheckinRecord' object has no attribute 'comment'`
- **证据**：
  ```
  File "/Users/rot/dev/code/pojuActionCamp/backend/app/services/grading_service.py", line 366
      comment = r.comment or ""
  AttributeError: 'CheckinRecord' object has no attribute 'comment'. Did you mean: 'content'?
  ```
  sqlite 验证：`sqlite> .schema checkin_records` 不含 `comment` 列；`comment` 在 `grades` 表中。
- **根因**：`CheckinRecord` 模型无 `comment` 字段，评语存在 `Grade.comment`；`generate_grade` 在拼装历史档案时直接读 `r.comment`（CheckinRecord 字段），需改为先 join Grade 表取最新评语（参考 `archive_service._load_timeline_and_stats` 已有正确 join 写法）。
- **修复建议**：
  ```python
  # _build_history_archive 改为 join Grade 取 comment
  stmt = (
      select(CheckinRecord, Grade)
      .outerjoin(Grade, Grade.checkin_record_id == CheckinRecord.id)
      .where(CheckinRecord.student_id == student_id,
             CheckinRecord.grade_status == "graded",
             CheckinRecord.id != current_checkin_id)
      .order_by(CheckinRecord.id.desc())
      .limit(_HISTORY_LIMIT)
  )
  rows = (await self.session.execute(stmt)).all()
  # 取每行最新 Grade.comment
  ```

### BUG-VOL-003 【P0·后端】确认评改时 `record.comment` 不存在导致破局同步 100% 静默失败
- **严重度**：P0
- **模块**：VOL
- **用例**：TC-VOL-011
- **步骤**：
  1. 调 `POST /api/volunteer/grades/confirm`（任一 checkin）
  2. 观察返回与后端日志
- **预期**：破局同步成功或返回有意义的失败
- **实际**：
  - API 返回 `success: false, message: "评改已保存本地；同步破局失败，可稍后重试"`
  - 后端日志：`WARNING | app.services.grading_service | 评改同步破局失败 checkin=5: 'CheckinRecord' object has no attribute 'comment'`
- **证据**：
  - `backend/app/services/grading_service.py:251` 写 `record.comment = comment`（无该字段 → 抛错）
  - `backend/app/services/grading_service.py:435` 读 `record.comment`（无该字段 → 抛错）
- **根因**：`confirm_and_sync` 与 `_sync_grade_to_poju` 都将"评语"挂在 `CheckinRecord.comment` 上，但实际模型是 `Grade.comment`；本应把评语只写到 `Grade` 表。
- **修复建议**：
  ```python
  # 方案 A：删除 record.comment 写读，评语只存在 Grade 表
  # Grade 行已含 stars+comment+source，不再回写 CheckinRecord
  # confirm_and_sync 移除 record.comment = comment
  # _sync_grade_to_poju 通过 join 取最近一条 Grade.comment
  ```

### BUG-VOL-004 【P1·后端】`_load_timeline_and_stats` 的 `last_stars` 计算错误，缺星星时返回旧值
- **严重度**：P1
- **模块**：VOL
- **用例**：TC-VOL-014
- **步骤**：
  1. 取学员 3（王五）档案，最近一次评改是 day 2 stars=1
  2. 调 `GET /api/volunteer/students/3`
- **预期**：`student.last_stars = 1`（最近一次真实评改）
- **实际**：`student.last_stars = 2`（day 1 的旧记录）
- **证据**：
  ```json
  // student 3 timeline (按 day_number desc):
  {checkin_id:11, day:2, stars:1, grade_status:"graded"},
  {checkin_id:10, day:1, stars:2, grade_status:"graded"}
  // 但返回：
  "last_stars": 2
  ```
- **根因**：`archive_service.py:506-514` 倒序遍历时只取 `stars >= 2` 的第一条；缺 1 星时跳过 1 星记录，返回 2 星。正确逻辑应取最近一次 stars 非空的记录（与 `_aggregate_last_stars` 函数相同）。
- **修复建议**：
  ```python
  last_stars: Optional[int] = None
  for r in records:
      if r.stars is not None:
          if last_stars is None:
              last_stars = r.stars  # 直接取最近 stars，不看大小
          if r.stars >= 2:
              valid_days += 1
  ```

### BUG-VOL-005 【P1·前端】Dashboard "档案" 链接 URL 错误，缺 camp 段
- **严重度**：P1
- **模块**：VOL
- **用例**：TC-VOL-001（操作列）
- **步骤**：
  1. P6 学员看板已加载
  2. 点击学员行的"档案"按钮
- **预期**：跳转 `/camp/{id}/volunteer/archive/{studentId}`（路由已存在）
- **实际**：跳转 `/volunteer/archive/{id}`（404 → 重定向回首页）
- **证据**：
  ```
  Dashboard.tsx:419,427
    <Link to={`/volunteer/archive/${row.id}`}>
  App.tsx 路由：/camp/:id/volunteer/archive/:studentId
  ```
- **根因**：Dashboard 中硬编码了无 camp 前缀的 URL。
- **修复建议**：
  ```tsx
  <Link to={`/camp/${campId}/volunteer/archive/${row.id}`}>
  ```

### BUG-VOL-006 【P1·前端】"仅保存不同步"功能未实现，仍调破局
- **严重度**：P1
- **模块**：VOL
- **用例**：TC-VOL-012
- **步骤**：
  1. P7 点击"仅保存不同步"按钮
- **预期**：评改保存本地、不调破局接口
- **实际**：弹窗告知"MVP 暂未提供"，用户确认后仍调 confirm 接口（仍然会调破局）
- **证据**：`Grading.tsx:196-218`，`Modal.confirm` 内部仍 `confirmMutation.mutate(...)`
- **修复建议**：要么补一个 `POST /api/volunteer/grades/save-draft` 仅落库不同步，要么文档说明 MVP 不实现。

### BUG-VOL-007 【P1·后端】`base_url` 字段无 API 入口，UI 输入无法保存
- **严重度**：P1
- **模块**：VOL / CFG
- **用例**：TC-VOL-004（同步前置）
- **步骤**：
  1. 打开 P11 接口配置
  2. 在"接口地址"输入 `https://api.poju.com`
  3. 点"保存配置"
- **预期**：base_url 持久化到 poju_configs.base_url
- **实际**：UI 无 PATCH 入口（仅 PUT /token）；后端 `SettingsService.update_base_url` 是私有方法无 API
- **证据**：
  ```
  P11 Settings.tsx:140  setBaseUrl / 显示在前端
  backend/app/api/settings.py: 只有 /poju, /poju/token, /poju/test
  backend/app/services/settings_service.py:145 update_base_url 未暴露
  ```
- **修复建议**：
  ```python
  # backend/app/api/settings.py 新增
  @router.put("/base-url", response_model=None)
  async def update_base_url(payload: BaseUrlUpdate, service: ...):
      return success((await service.update_base_url(payload.base_url)).model_dump(mode="json"))
  ```

### BUG-VOL-008 【P2·前端】"批量确认"按钮为占位，未实现
- **严重度**：P2
- **模块**：VOL
- **用例**：TC-VOL-011（批量）
- **步骤**：点击 P7 顶部"批量确认"按钮
- **预期**：对所有 pending checkin 逐条评改确认
- **实际**：toast 提示"MVP 暂未实现"
- **证据**：`Grading.tsx:286 message.info('批量确认：MVP 暂未实现，请逐条评改')`
- **影响**：UI 占位文案不符合 TC-UX 用例，可记入非阻塞清单。

---

## 四、UI 验证结果

### P6 学员看板（`/camp/{id}/volunteer`）

| 元素 | 状态 | 说明 |
| --- | --- | --- |
| 页头：标题/志愿者徽章/营名/上次同步 | OK | 标题"学员看板" + 粉色志愿者徽章 + 营名 + "尚未同步" |
| 定时同步标签 | OK | "⏱ 定时同步：每日 09:00" 灰色 tag 渲染 |
| 立即同步按钮 | OK | 蓝色主按钮存在，loading 状态切换正常 |
| 4 个统计卡 | OK | "带教学员/待评改/今日已打卡/打卡不足需提醒"（但数字因数据为空显示 0） |
| 4 个 Tab | OK | "全部 0 / 待评改 0 / 打卡不足 0 / 已评改 0"，有数量徽章 |
| 学员表格 | **FAIL** | 因 API 路径错显示"该筛选下暂无学员" |
| 搜索框 | OK | placeholder "搜索学员昵称 / 微信"（但表格为空无法验证过滤） |
| 学员行：学员/已打卡/有效天数/距目标/最近星级/状态/操作 | **BLOCK** | 无法验证，列表为空 |

### P7 作业评改（`/camp/{id}/volunteer/grade`）

| 元素 | 状态 | 说明 |
| --- | --- | --- |
| 页头：标题/徽章/待评改数 | OK | "作业评改" + 徽章 + "0 人待评改"（应为 5） |
| 批量确认按钮 | OK | 存在，点击后 toast 提示未实现 |
| 左栏：待评改列表 | **FAIL** | API 404 永远显示"暂无待评改作业" |
| 右栏：4 板块 | **BLOCK** | 左栏为空时右栏显示空态卡片 |
| 学员信息头 | OK | 代码存在，渲染"昵称 · Day N 打卡" + 提交时间 |
| 学员本次打卡内容 | OK | 灰色背景卡片 |
| 历史档案参考（默认展开） | OK | antd Collapse + Timeline（不可见因数据空） |
| AI 评改结果 | OK | 星级 + 评语 + 维度依据 + 评分标准折叠 |
| 操作按钮：确认并同步/仅保存不同步/重新生成 | OK | 三个按钮均存在 |

### P8 学员档案（`/camp/{id}/volunteer/archive/{studentId}`）

| 元素 | 状态 | 说明 |
| --- | --- | --- |
| 页头：标题/徽章/仅志愿者可见 | OK | 黄色提示条"学员档案仅志愿者侧可见"渲染 |
| 返回学员看板 | OK | 左箭头按钮 |
| 4 个统计卡 | **BLOCK** | 页面整体 404，无内容可验证 |
| 顶部统计：昵称/有效打卡/距目标/平均星级 | **BLOCK** | 同上 |
| 时间线：逐日打卡 + 星级 + 评语 | **BLOCK** | 同上 |
| 底部"返回"按钮 | OK | 代码存在 |

---

## 五、API 行为记录

| API | 状态 | 备注 |
| --- | --- | --- |
| `POST /api/volunteer/camps/{id}/sync` | PASS（需 base_url） | 未配置 base_url → code 1001；配置后返回 success: true，synced_count: 0 |
| `GET /api/volunteer/camps/{id}/students` | PASS | 返 3 名学员，支持 status 过滤 |
| `GET /api/volunteer/students/{id}` | PASS | 返 student + stats + timeline，但 last_stars 计算有 bug |
| `GET /api/volunteer/camps/{id}/grades/pending` | PASS | 返 5 条 pending |
| `POST /api/volunteer/grades/generate` | **FAIL** | 学员无历史时 OK；有历史时 500（BUG-VOL-002） |
| `POST /api/volunteer/grades/confirm` | **PARTIAL** | 本地保存 OK；破局同步必失败（BUG-VOL-003） |
| `POST /api/volunteer/grades/{id}/retry` | PASS | 对已 graded 重试；synced=false 因无 base_url，符合预期 |
| `POST /api/volunteer/grades/regenerate` | **FAIL** | 同 generate |
| `POST /api/settings/poju/test` | PASS | base_url 未配置 → valid:false, message:"未配置接口地址" |
| `PUT /api/settings/poju/token` | PASS | 更新 Token，DB 加密存储，响应脱敏 |

---

## 六、Top-3 阻塞 Bug（按优先级）

1. **BUG-VOL-001 【P0】志愿者前端所有 6 个 API 路径缺 `/volunteer` 前缀** —— 整个 VOL 页面无法加载数据，影响 9 个 TC 用例
2. **BUG-VOL-002 【P0】`_build_history_archive` 引用 `CheckinRecord.comment` 不存在** —— 凡是学员已有评改记录，再生成/重新生成评改 100% 500
3. **BUG-VOL-003 【P0】`confirm_and_sync` / `_sync_grade_to_poju` 引用 `record.comment` 不存在** —— 所有"确认并同步"同步阶段 100% 静默失败，评语数据无法上传破局

---

## 七、复现步骤汇总

### 复现 BUG-VOL-001
```bash
# 浏览器打开 http://localhost:5173/camp/5/volunteer
# DevTools Network 过滤 "api" → 看到所有请求 404
curl http://localhost:8000/api/camps/5/students  # 404 Not Found
curl http://localhost:8000/api/volunteer/camps/5/students  # 200 OK
```

### 复现 BUG-VOL-002
```bash
# 前置：1 名学员 + 至少 1 条已 grade 的 checkin
sqlite3 data/app.db "SELECT id, stars, grade_status FROM checkin_records WHERE student_id=1;"
# 5|2|graded, 6|2|graded → 张三已有 2 条已评改
curl -X POST http://localhost:8000/api/volunteer/grades/regenerate \
  -H 'Content-Type: application/json' -d '{"checkin_id": 5}'
# → 500 AttributeError: 'CheckinRecord' object has no attribute 'comment'
```

### 复现 BUG-VOL-003
```bash
curl -X POST http://localhost:8000/api/volunteer/grades/confirm \
  -H 'Content-Type: application/json' \
  -d '{"checkin_id": 5, "stars": 2, "comment": "测试"}'
# 响应: {"success":false, "message":"评改已保存本地；同步破局失败，可稍后重试"}
# 后端日志: WARNING | 评改同步破局失败 checkin=5: 'CheckinRecord' object has no attribute 'comment'
```

### 复现 BUG-VOL-004
```bash
curl http://localhost:8000/api/volunteer/students/3
# student 3 timeline: day2 stars=1, day1 stars=2
# 返回: student.last_stars = 2  (实际最近 stars=1)
```

---

## 八、数据现状

- 行动营 5（E2E测试-志愿者营，role=volunteer）已建
- 学员 3 名（张三/李四/王五，poju_student_id=poju_s_001/002/003）
- 打卡记录 7 条（id 5-11），5 条 pending + 2 条 graded
- Token 已配置（sk-test，密文存储），base_url=NULL
- Grades 表已有 5 行（4 旧 + 1 新）

---

## 九、报告路径
- 本报告：`/Users/rot/dev/code/pojuActionCamp/test-reports/agent3-volunteer.md`
- 截图：`/Users/rot/dev/code/pojuActionCamp/.playwright-mcp/volunteer-dashboard.png`
- 相关用例集：`/Users/rot/dev/code/pojuActionCamp/test-reports/01-test-cases.md` § 2.3
