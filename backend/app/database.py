"""数据库初始化模块。

SQLAlchemy 2.0 异步引擎 + 会话工厂 + 声明式基类。
- 引擎使用 aiosqlite 异步驱动。
- Base 为所有 ORM 模型的声明式基类，供 alembic 读取 metadata。
- get_db 为 FastAPI 依赖，生成异步 session。

所有表含 id/created_at/updated_at，时间字段统一存 UTC。

注意：models/ai 等其它模块仅依赖 ``Base``，本文件保持 ``Base`` 导出不变，
额外提供异步引擎与会话工厂，向后兼容。
"""
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


settings = get_settings()


def ensure_db_dir(url: str) -> None:
    """确保 SQLite 数据库文件所在目录存在。

    SQLite 不会自动创建父目录，若 ``data/`` 缺失会在建库/连接时报
    ``unable to open database file``。此处从 DATABASE_URL 解析出文件路径并预建父目录，
    方便新人 clone 后直接 ``alembic upgrade head`` 或启动应用即可使用。
    """
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            db_path = Path(url[len(prefix):])
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return


# 预建数据目录（默认 data/），避免首次建库/连接时因目录缺失报错
ensure_db_dir(settings.async_database_url)

# 异步引擎：sqlite+aiosqlite:///，供 aiosqlite 异步驱动使用
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    future=True,
)

# 异步会话工厂
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：生成一个异步 DB session，请求结束自动关闭。

    出现异常时回滚，由上层异常处理器统一转换为 JSON 响应。
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
