"""Alembic 迁移环境配置。

采用同步 alembic（非 async run_migrations），保证命令行可直接运行：
`uv run alembic upgrade head`。

关键点：
- 从 app.config.Settings 读取 database_url。
- 把 sqlite+aiosqlite:/// 转为 sqlite:///（alembic 用同步驱动）。
- target_metadata = Base.metadata，确保迁移覆盖全部模型。
- 通过 `from app.models import *` 触发所有模型导入，注册到 Base.metadata。
"""
from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic 配置对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# 导入 Base 与全部模型，确保 Base.metadata 包含所有表
from app.database import Base  # noqa: E402
from app.config import get_settings  # noqa: E402

try:  # pragma: no cover - 模型未实现时不应阻断 alembic 基础功能
    from app import models  # noqa: F401, E402
except ImportError:  # pragma: no cover
    logger.warning("app.models 尚未创建，迁移将基于当前已注册的表")

# 触发 models 子模块导入（若 app.models 为包且内部按表拆分）
try:  # pragma: no cover
    from app.models import *  # noqa: F401, F403, E402
except Exception:  # pragma: no cover
    # app/models/__init__.py 可能尚未创建，忽略
    pass

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """将异步 URL 转为同步 sqlite URL 供 alembic 使用。"""
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    return url


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL 脚本，不连接数据库。"""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 支持 ALTER 受限，batch 模式更稳
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    # 注入同步 URL
    config.set_main_option("sqlalchemy.url", _get_sync_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER 受限，启用 batch
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
