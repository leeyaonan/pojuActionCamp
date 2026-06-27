.PHONY: dev backend-install backend-migrate backend-dev frontend-install frontend-dev backup

# 一键启动：同时拉起后端(uvicorn --port 8000)与前端(pnpm dev)
# 使用 trap 'kill 0' EXIT 确保任一进程退出时一并终止另一进程
dev:
	@trap 'kill 0' EXIT; \
	( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
	( cd frontend && pnpm dev ); \
	wait

# 后端：安装依赖
backend-install:
	cd backend && uv sync

# 后端：执行数据库迁移到最新版本
backend-migrate:
	cd backend && uv run alembic upgrade head

# 后端：单独启动开发服务器（热重载，端口 8000）
backend-dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

# 前端：安装依赖
frontend-install:
	cd frontend && pnpm install

# 前端：单独启动 Vite 开发服务器（5173）
frontend-dev:
	cd frontend && pnpm dev

# 备份：将 data/ 目录打包到 backups/
backup:
	@mkdir -p backups; \
	timestamp=$$(date +%Y%m%d_%H%M%S); \
	tar -czf "backups/data_backup_$${timestamp}.tar.gz" data/ 2>/dev/null && \
	echo "已备份 data/ 到 backups/data_backup_$${timestamp}.tar.gz" || \
	echo "data/ 目录不存在，无内容可备份"
