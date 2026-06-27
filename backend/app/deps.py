"""依赖注入汇总。

集中导出常用依赖（DB session、Settings），供路由层通过 Depends 使用。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """DB session 依赖，透传 app.database.get_db。"""
    async for session in _get_db():
        yield session


def get_settings_dep() -> Settings:
    """Settings 依赖。"""
    return get_settings()
