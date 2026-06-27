"""评分标准服务。

对应技术方案 4.2.7 / 5.7 / 11.5。
全局仅一套生效标准：更新时将当前 active 行置为 is_active=False，
再插入新行 is_active=True，保留历史以便回溯（PRD BR-F5-4：对后续评改生效，
已评改记录不回溯）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.scoring import ScoringStandard
from app.schemas.scoring import ScoringUpdate


class ScoringService:
    """评分标准业务逻辑。

    使用方式：``ScoringService(session).get_active()`` / ``.update(payload)``。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> ScoringStandard:
        """获取当前生效的评分标准。

        Raises:
            NotFoundError: 全局尚无任何生效标准。
        """
        stmt = select(ScoringStandard).where(ScoringStandard.is_active.is_(True))
        result = await self.session.execute(stmt)
        standard = result.scalar_one_or_none()
        if standard is None:
            raise NotFoundError("评分标准未配置")
        return standard

    async def update(self, payload: ScoringUpdate) -> ScoringStandard:
        """更新评分标准：保留历史，新插入一条 active 行。

        流程：
        1. 查所有 is_active=True 行置为 False。
        2. 插入新行 is_active=True。
        3. commit + refresh 后返回新行。
        """
        # 1. 将历史 active 行置为 inactive
        deactivate_stmt = select(ScoringStandard).where(
            ScoringStandard.is_active.is_(True)
        )
        rows = (await self.session.execute(deactivate_stmt)).scalars().all()
        for row in rows:
            row.is_active = False

        # 2. 插入新 active 行（dimensions/star_rules 走 model_dump 存原始结构）
        new_standard = ScoringStandard(
            is_active=True,
            dimensions=[dim.model_dump() for dim in payload.dimensions],
            star_rules=payload.star_rules.model_dump(),
        )
        self.session.add(new_standard)

        await self.session.commit()
        await self.session.refresh(new_standard)
        return new_standard
