"""APScheduler 调度器初始化（空桩，W2 填充）。

对齐技术方案 9.2：
- 使用 AsyncIOScheduler 配合 FastAPI 事件循环。
- SQLAlchemyJobStore 持久化任务。
- 时区 Asia/Shanghai。

当前为空实现，仅打日志，保证后端可独立启动。
"""
from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def init_scheduler(settings: Settings) -> None:
    """初始化调度器（空桩）。

    W2 将实现：
    - 创建 AsyncIOScheduler + SQLAlchemyJobStore。
    - 注册定时任务：志愿者看板同步、Token 校验、行动营状态刷新。
    - 按 settings.scheduler_enabled 控制是否启用。
    """
    logger.info(
        "调度器初始化（空桩实现）, scheduler_enabled=%s, sync_cron=%02d:%02d",
        settings.scheduler_enabled,
        settings.sync_cron_hour,
        settings.sync_cron_minute,
    )
