"""定时任务定义。

对齐技术方案 9.1 / 9.3，实现两个 MVP 周期任务：

- ``sync_all_volunteer_boards``：每日定时拉取所有进行中志愿者营的学员打卡数据。
- ``verify_poju_token``：提前 5 分钟调读接口校验 Token，失效则在配置表标记。

约定：
- job 函数自建 AsyncSession（依赖 ``db_sessionmaker``），不依赖请求上下文。
- 单个营地同步失败不中断本轮整体执行；Token 失效（PojuAuthError）则
  立即终止本轮并记 error，避免在错误 Token 下空跑其余营地。
"""
from __future__ import annotations

import logging
from datetime import date as _date_cls

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.camp import Camp
from app.poju.exceptions import PojuAuthError
from app.services.archive_service import ArchiveService
from app.services.camp_service import calc_status
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


async def sync_all_volunteer_boards() -> None:
    """同步所有进行中的志愿者营。

    流程：
    1. 自建 AsyncSession，查询 ``is_deleted=False`` 的志愿者营。
    2. 对每个营按 ``calc_status`` 过滤出 ongoing 状态。
    3. 调 ``ArchiveService.sync_volunteer_board(camp_id)``。
       - 抛出 ``PojuAuthError`` → break 本轮并 log error（后续营地跳过）。
       - 单个营失败 → log warning，不中断本轮。
    """
    settings = get_settings()
    today = _date_cls.today()
    logger.info("开始同步所有志愿者营 (today=%s)", today)

    async with async_session_factory() as session:
        # 1) 取所有未软删的志愿者营
        stmt = select(Camp).where(
            Camp.is_deleted.is_(False),
            Camp.role == "volunteer",
        )
        camps = (await session.execute(stmt)).scalars().all()

        # 2) 过滤进行中
        ongoing_camps = [c for c in camps if calc_status(c, today) == "ongoing"]
        logger.info(
            "待同步志愿者营: total=%s ongoing=%s",
            len(camps),
            len(ongoing_camps),
        )

    # 3) 每个营独立 session，单营失败不中断
    for camp in ongoing_camps:
        try:
            async with async_session_factory() as session:
                service = ArchiveService(session=session, settings=settings)
                result = await service.sync_volunteer_board(camp.id)
                logger.info(
                    "志愿者营 %s 同步完成: %s", camp.id, result.message
                )
        except PojuAuthError as exc:
            # Token 失效：终止本轮，避免后续空跑
            logger.error(
                "破局 Token 失效，终止本轮同步 (camp_id=%s): %s",
                camp.id,
                exc,
            )
            break
        except Exception as exc:  # noqa: BLE001
            # 单营失败不中断
            logger.warning(
                "志愿者营 %s 同步失败（忽略，继续）: %s", camp.id, exc
            )

    logger.info("所有志愿者营同步任务结束")


async def verify_poju_token() -> None:
    """校验破局 Token 是否有效并更新配置表 token_status。

    使用 ``SettingsService.test_connection``：内部解密 Token → 调
    ``PojuClient.verify_token`` → 更新 ``token_status / last_checked_at``。
    """
    settings = get_settings()
    logger.info("开始校验破局 Token")

    try:
        async with async_session_factory() as session:
            service = SettingsService(session=session, settings=settings)
            result = await service.test_connection()
        logger.info(
            "破局 Token 校验完成: valid=%s message=%s",
            result.valid,
            result.message,
        )
    except Exception as exc:  # noqa: BLE001
        # 校验异常不抛出，避免 APScheduler 标记 job 失败导致反复重试
        logger.warning("破局 Token 校验异常（忽略）: %s", exc)