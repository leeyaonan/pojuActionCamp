"""APScheduler 调度器初始化。

对齐技术方案 9.2：
- 使用 ``AsyncIOScheduler`` 配合 FastAPI 事件循环（uvicorn asyncio）。
- ``SQLAlchemyJobStore`` 持久化任务到本地 SQLite（同步 url）。
- 时区 ``Asia/Shanghai``。
- ``settings.scheduler_enabled`` 控制是否注册并启动 cron 任务。

提供模块级单例 ``scheduler``，供 lifespan 管理（启动 / 关闭）。
"""
from __future__ import annotations

import logging

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.scheduler.jobs import sync_all_volunteer_boards, verify_poju_token

logger = logging.getLogger(__name__)

# 模块级单例，供 lifespan / 测试使用
scheduler: AsyncIOScheduler | None = None


def _to_sync_sqlite_url(url: str) -> str:
    """将异步 aiosqlite url 转为同步 sqlite url，供 SQLAlchemyJobStore 使用。

    - ``sqlite+aiosqlite:///./data/app.db`` → ``sqlite:///./data/app.db``
    - 已是 ``sqlite:///`` 前缀则原样返回。
    """
    if url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    return url


def init_scheduler(settings: Settings) -> AsyncIOScheduler:
    """初始化并启动调度器。

    - 构造 ``AsyncIOScheduler`` + ``SQLAlchemyJobStore`` + ``AsyncIOExecutor``。
    - 时区 ``Asia/Shanghai``。
    - 若 ``settings.scheduler_enabled``，注册两个 cron 任务：
        * ``sync_boards``  : ``sync_all_volunteer_boards`` 每日 ``sync_cron_hour:minute``。
        * ``verify_token`` : ``verify_poju_token`` 提前 5 分钟触发。
    - 启动调度器并写入模块单例 ``scheduler``。
    - 关闭时由 lifespan 调 ``scheduler.shutdown(wait=False)``。

    Returns:
        已启动的 ``AsyncIOScheduler`` 实例（同时写入模块单例）。
    """
    global scheduler

    jobstores = {
        "default": SQLAlchemyJobStore(
            url=_to_sync_sqlite_url(settings.database_url),
        ),
    }
    executors = {
        "default": AsyncIOExecutor(),
    }

    sched = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        timezone="Asia/Shanghai",
    )

    if settings.scheduler_enabled:
        # Token 校验在看板同步前 5 分钟触发；分钟为负时回退到前一日 23:xx
        verify_minute = settings.sync_cron_minute - 5
        verify_hour = settings.sync_cron_hour
        if verify_minute < 0:
            verify_minute += 60
            verify_hour -= 1
            if verify_hour < 0:
                verify_hour = 23

        sched.add_job(
            sync_all_volunteer_boards,
            CronTrigger(
                hour=settings.sync_cron_hour,
                minute=settings.sync_cron_minute,
                timezone="Asia/Shanghai",
            ),
            id="sync_boards",
            replace_existing=True,
        )
        sched.add_job(
            verify_poju_token,
            CronTrigger(
                hour=verify_hour,
                minute=verify_minute,
                timezone="Asia/Shanghai",
            ),
            id="verify_token",
            replace_existing=True,
        )
        logger.info(
            "调度任务已注册: sync_boards=%02d:%02d verify_token=%02d:%02d",
            settings.sync_cron_hour,
            settings.sync_cron_minute,
            verify_hour,
            verify_minute,
        )
    else:
        logger.info("scheduler_enabled=False，跳过注册 cron 任务")

    sched.start()
    scheduler = sched
    logger.info("调度器已启动 (timezone=Asia/Shanghai)")
    return sched