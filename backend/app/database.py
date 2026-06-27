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
