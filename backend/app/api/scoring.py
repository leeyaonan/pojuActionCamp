"""评分标准路由。

对应技术方案 11.5：
- GET  /scoring  获取当前生效评分标准
- PUT  /scoring  更新评分标准（保留历史版本）

统一返回 ``{code, message, data}``，由 response 中间件 / 异常处理器负责包裹。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success
from app.deps import get_db
from app.schemas.scoring import ScoringOut, ScoringUpdate
from app.services.scoring_service import ScoringService

router = APIRouter(tags=["scoring"])


@router.get("", summary="获取当前评分标准")
async def get_scoring(session: AsyncSession = Depends(get_db)) -> dict:
    """获取当前 is_active=True 的评分标准（全局唯一）。"""
    service = ScoringService(session)
    standard = await service.get_active()
    payload = ScoringOut.model_validate(standard).model_dump(mode="json")
    return success(payload)


@router.put("", summary="更新评分标准")
async def put_scoring(
    payload: ScoringUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """更新评分标准：保留历史，插入新 active 行。"""
    service = ScoringService(session)
    standard = await service.update(payload)
    out = ScoringOut.model_validate(standard).model_dump(mode="json")
    return success(out)
