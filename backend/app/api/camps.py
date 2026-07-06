"""行动营管理路由。

对应技术方案 11.1：
- POST   /api/camps        创建行动营
- GET    /api/camps        行动营列表（含运行期状态、进度、有效打卡天数）
- GET    /api/camps/{id}   行动营详情（含 has_manual / has_route）
- PUT    /api/camps/{id}   部分更新（poju_action_id 等）
- DELETE /api/camps/{id}   软删除（is_deleted=True，不级联）

所有路由统一返回 ``success()`` 包裹的 dict，由 response_wrap_middleware 进一步
确保输出格式为 {code, message, data}。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success
from app.deps import get_db
from app.schemas.camp import CampCreate, CampOut, CampSummary, CampUpdate
from app.services.camp_service import CampService

router = APIRouter()


@router.post(
    "",
    response_model=None,
    summary="创建行动营",
)
async def create_camp(
    payload: CampCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """创建行动营。

    - start_date < end_date；min_checkin_days 未传或非法时按 total_days*0.6 兜底。
    - is_deleted=False；返回完整 CampDetail（无 has_manual / 进度补算）。
    """
    service = CampService(db)
    camp = await service.create_camp(payload)
    detail = await service.get_camp(camp.id)
    data = detail.model_dump(mode="json")
    return success(data)


@router.get(
    "",
    response_model=None,
    summary="行动营列表",
)
async def list_camps(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """列出所有未软删的行动营，含运行期计算的 status / progress / valid_days。"""
    service = CampService(db)
    summaries = await service.list_camps()
    data = [item.model_dump(mode="json") for item in summaries]
    return success(data)


@router.get(
    "/{camp_id}",
    response_model=None,
    summary="行动营详情",
)
async def get_camp(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取单个行动营详情。不存在或已软删时 404。"""
    service = CampService(db)
    detail = await service.get_camp(camp_id)
    data = detail.model_dump(mode="json")
    return success(data)


@router.put(
    "/{camp_id}",
    response_model=None,
    summary="部分更新行动营（poju_action_id 等）",
)
async def update_camp(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    payload: CampUpdate = ...,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """部分更新行动营字段。

    - 仅更新 payload 中显式提供的字段（None=不修改，空串=清空）。
    - 角色（role）不可更新。
    """
    service = CampService(db)
    camp = await service.update_camp(camp_id, payload)
    detail = await service.get_camp(camp.id)
    data = detail.model_dump(mode="json")
    return success(data)


@router.delete(
    "/{camp_id}",
    response_model=None,
    summary="删除（软删除）行动营",
)
async def delete_camp(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """软删除：is_deleted=True，不级联清理关联数据。

    重复删除返回 404，便于前端识别幂等语义。
    """
    service = CampService(db)
    await service.delete_camp(camp_id)
    return success({"camp_id": camp_id, "deleted": True})