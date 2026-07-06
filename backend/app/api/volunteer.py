"""志愿者功能路由（空桩 + W2 archive 阶段实现）。

- POST /camps/{id}/sync                  手动触发同步（拉打卡）
- POST /camps/{id}/archive/init          初始化档案（拉学员名单）
- POST /camps/{id}/archive/refresh       刷新档案（覆盖式更新）
- GET  /camps/{id}/students              学员看板列表（支持筛选）
- GET  /students/{id}                    学员档案
- GET  /camps/{id}/grades/pending        待评改列表
- POST /grades/generate                  生成评改
- POST /grades/confirm                   确认并同步
- POST /grades/save-draft                仅保存评改（不同步破局）— BUG-VOL-006
- POST /grades/{id}/retry                重试同步
- POST /grades/regenerate                重新生成评改
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.response import success
from app.deps import get_db, get_settings_dep
from app.schemas.volunteer import (
    GradeConfirmIn,
    GradeDraftOut,
    GradeGenerateIn,
    InitResult,
    PendingGradeOut,
    StudentArchive,
    StudentStatus,
    StudentSummary,
    SyncResult,
)
from app.services.archive_service import ArchiveService
from app.services.grading_service import GradingService

router = APIRouter()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 依赖工厂
# ---------------------------------------------------------------------------


def _archive_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> ArchiveService:
    """ArchiveService 依赖：注入 DB session + Settings。"""
    return ArchiveService(db, settings)


# ---------------------------------------------------------------------------
# 同步 / 看板 / 档案（W2 archive 阶段）
# ---------------------------------------------------------------------------


@router.post(
    "/camps/{camp_id}/sync",
    response_model=None,
    summary="手动触发同步：拉取破局学员与打卡记录",
)
async def sync_board(
    camp_id: int = Path(..., gt=0, description="行动营 ID（志愿者营）"),
    service: ArchiveService = Depends(_archive_service),
) -> dict:
    """从破局拉取学员与打卡记录并 upsert。

    - camp 必须为志愿者身份（role='volunteer'）。
    - PojuAuthError 由统一异常处理器映射为 401。
    - 其它破局异常（网络/业务）由统一异常处理器映射为 502。
    """
    result: SyncResult = await service.sync_volunteer_board(camp_id)
    return success(result.model_dump(mode="json"))


@router.get(
    "/camps/{camp_id}/students",
    response_model=None,
    summary="学员看板列表（支持状态筛选）",
)
async def list_board_students(
    camp_id: int = Path(..., gt=0, description="行动营 ID（志愿者营）"),
    status: Optional[StudentStatus] = Query(
        None,
        description=(
            "状态筛选：ongoing=进行中 / unqualified=未达标 / qualified=已达标"
        ),
    ),
    service: ArchiveService = Depends(_archive_service),
) -> dict:
    """学员看板列表。

    - 支持按 status 筛选。
    - camp 必须为志愿者身份。
    """
    # StudentSummary.status -> grading 语义映射（pending/insufficient/graded）
    status_filter: Optional[str] = None
    if status is not None:
        mapping = {
            "ongoing": "pending",
            "unqualified": "insufficient",
            "qualified": "graded",
        }
        status_filter = mapping[status]
    items: list[StudentSummary] = await service.list_students(
        camp_id=camp_id,
        status_filter=status_filter,  # type: ignore[arg-type]
    )
    data = [item.model_dump(mode="json") for item in items]
    return success(data)


@router.post(
    "/camps/{camp_id}/archive/init",
    response_model=None,
    summary="初始化学员档案（拉破局名单 → upsert）",
)
async def init_volunteer_archive(
    camp_id: int = Path(..., gt=0, description="行动营 ID（志愿者营）"),
    service: ArchiveService = Depends(_archive_service),
) -> dict:
    """从破局 query-people 拉本期学员名单并 upsert 到 students 表。

    - camp 必须为志愿者身份。
    - camp.poju_action_id 必须已填写（否则抛 1001）。
    - 单页网络/业务错误被跳过并写入 InitResult.errors，不阻断。
    - 不动 checkin_records（与打卡同步完全解耦）。
    - PojuAuthError 由统一异常处理器映射为 401。
    """
    result: InitResult = await service.init_volunteer_archive(camp_id)
    return success(result.model_dump(mode="json"))


@router.post(
    "/camps/{camp_id}/archive/refresh",
    response_model=None,
    summary="刷新学员档案（覆盖式更新）",
)
async def refresh_volunteer_archive(
    camp_id: int = Path(..., gt=0, description="行动营 ID（志愿者营）"),
    service: ArchiveService = Depends(_archive_service),
) -> dict:
    """刷新本期学员档案，按 (camp_id, poju_student_id) 覆盖式更新扩展字段。

    与 init_volunteer_archive 实现相同，仅 API 语义不同（UI 用以区分按钮）。
    """
    result: InitResult = await service.refresh_volunteer_archive(camp_id)
    return success(result.model_dump(mode="json"))


@router.get(
    "/students/{student_id}",
    response_model=None,
    summary="学员档案（统计 + 时间线）",
)
async def get_student_archive(
    student_id: int = Path(..., gt=0, description="学员 ID"),
    service: ArchiveService = Depends(_archive_service),
) -> dict:
    """学员档案：摘要 + 统计 + 倒序时间线。"""
    archive: StudentArchive = await service.get_archive(student_id)
    return success(archive.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 评改（W2 grading 阶段）
# ---------------------------------------------------------------------------


def _grading_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> GradingService:
    """GradingService 依赖：注入 DB session + Settings。"""
    return GradingService(db, settings)


@router.get(
    "/camps/{camp_id}/grades/pending",
    response_model=None,
    summary="待评改列表（grade_status=pending）",
)
async def list_pending_grades(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: GradingService = Depends(_grading_service),
) -> dict:
    """列出指定行动营下所有待评改的 CheckinRecord，含学员昵称 join。"""
    items: list[PendingGradeOut] = await service.list_pending(camp_id)
    data = [item.model_dump(mode="json") for item in items]
    return success(data)


@router.post(
    "/grades/generate",
    response_model=None,
    summary="生成评改草稿（LLM）",
)
async def generate_grade(
    payload: GradeGenerateIn,
    service: GradingService = Depends(_grading_service),
) -> dict:
    """调 LLM 生成评改草稿，存入 grades 表（source='ai'）。"""
    draft: GradeDraftOut = await service.generate_grade(payload.checkin_id)
    return success(draft.model_dump(mode="json"))


@router.post(
    "/grades/confirm",
    response_model=None,
    summary="确认评改并同步破局",
)
async def confirm_grade(
    payload: GradeConfirmIn,
    service: GradingService = Depends(_grading_service),
) -> dict:
    """写入最终评改并尝试同步破局；同步失败时本地评改保留，可重试。"""
    result: SyncResult = await service.confirm_and_sync(
        checkin_id=payload.checkin_id,
        stars=payload.stars,
        comment=payload.comment,
    )
    return success(result.model_dump(mode="json"))


class GradeSaveDraftIn(BaseModel):
    """仅保存评语（不调破局）请求体。"""

    checkin_id: int = Field(..., gt=0)
    stars: int = Field(..., ge=1, le=3)
    comment: Optional[str] = None


@router.post(
    "/grades/save-draft",
    response_model=None,
    summary="仅保存评语（不同步破局）",
)
async def save_grade_draft(
    payload: GradeSaveDraftIn,
    service: GradingService = Depends(_grading_service),
) -> dict:
    """仅落本地 Grade 表 + CheckinRecord，不调破局同步。

    用于"仅保存不同步"按钮（BUG-VOL-006）。
    """
    result: SyncResult = await service.save_draft_only(
        checkin_id=payload.checkin_id,
        stars=payload.stars,
        comment=payload.comment,
    )
    return success(result.model_dump(mode="json"))


@router.post(
    "/grades/{checkin_id}/retry",
    response_model=None,
    summary="重试同步评改到破局",
)
async def retry_grade_sync(
    checkin_id: int = Path(..., gt=0, description="打卡记录 ID"),
    service: GradingService = Depends(_grading_service),
) -> dict:
    """对已评改但未同步的记录重新调破局同步。"""
    result: SyncResult = await service.retry_sync(checkin_id)
    return success(result.model_dump(mode="json"))


@router.post(
    "/grades/regenerate",
    response_model=None,
    summary="重新生成评改草稿",
)
async def regenerate_grade(
    payload: GradeGenerateIn,
    service: GradingService = Depends(_grading_service),
) -> dict:
    """重新调 LLM 生成评改（覆盖 grades 表最新记录）。"""
    draft: GradeDraftOut = await service.regenerate_grade(payload.checkin_id)
    return success(draft.model_dump(mode="json"))
