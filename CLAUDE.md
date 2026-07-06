# CLAUDE.md

## 语言
所有会话、文档、代码注释均使用中文

## Git 分支铁律（绝对禁令）

> ⚠️ 一次违反就把代码直接推到了 master/main，必须零容忍。

1. **从 master/main 拉新分支时，upstream 必须关联到新分支自身，绝不可以是 master 或 main。**
   - 错误：`git checkout -b bugfix-xxx origin/master`（会自动 track 到 `origin/master`，之后 `git push` 会把提交直接灌进 master）
   - 正确：`git checkout -b bugfix-xxx origin/master --no-track`，随后 `git push -u origin bugfix-xxx`
   - 或：`git fetch origin master && git checkout -b bugfix-xxx FETCH_HEAD --no-track`
2. **任何 `git push` 之前，必须显式核对目标分支**：确认当前分支 upstream 指向同名远程分支，而非 `origin/master` / `origin/main`。可用 `git rev-parse --abbrev-ref --symbolic-full-name @{u}` 或 `git status -sb` 核对。若 upstream 是 master/main，必须先 `git branch --unset-upstream` 或 `git push -u origin <当前分支名>` 修正，再 push。
3. **绝不允许向 `master` / `main` 直接 push**，无论是显式 `git push origin HEAD:master` 还是因为 upstream 配置错误导致的隐式推送。
4. 用户说"从 master 拉分支"，默认语义是：基于 master 最新代码创建新分支，并把该新分支推到远程同名分支、关联 upstream 到该同名分支。绝非关联到 master。

## 分支策略（MVP 阶段硬规则）

> 本项目当前 MVP 阶段**所有开发、bug 修复、特性迭代一律在 `feat/mvp-implementation` 分支上进行**。

- **唯一开发分支**：`feat/mvp-implementation`。不要再创建 `fix/xxx`、`feat/xxx`、`hotfix/xxx` 等任何额外分支。
- **不在 main 上直接开发**：main 只作为发布/集成的稳定快照，不接受任何形式的直接提交。
- **同步关系**：`feat/mvp-implementation` 必须**保持与 `main` 一致，或者领先 `main`**。换言之：
  - 每次开发开始前：`git fetch origin && git checkout feat/mvp-implementation && git merge --ff-only origin/main`（如落后则快进同步）
  - 阶段性里程碑完成后：将 `feat/mvp-implementation` fast-forward 合并到 `main` 并推送，保持 main = feat HEAD
- **禁止操作**：
  - ❌ `git checkout -b fix/xxx` 创建新修复分支
  - ❌ 在 `main` 分支上 `commit` / `push`
  - ❌ 出现本地 main 领先 `feat/mvp-implementation` 的状态（即所有改动都必须先落到 feat 再合并回 main）
- **必须操作**：
  - ✅ 所有改动：`git checkout feat/mvp-implementation` → 修改 → `git add` → `git commit` → `git push -u origin feat/mvp-implementation`
  - ✅ 阶段性同步到 main：在 feat 干净工作树状态下 `git checkout main && git merge --ff-only feat/mvp-implementation && git push origin main`
  - ✅ 切换到 feat 前先核对 upstream：`git rev-parse --abbrev-ref --symbolic-full-name @{u}` 必须等于 `origin/feat/mvp-implementation`，否则修正后再操作