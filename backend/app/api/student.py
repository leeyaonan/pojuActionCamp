"""学员功能路由（学习路线 + 打卡，对应技术方案 11.2）。

已实现：学习路线（route）相关接口、打卡（checkin）相关接口。
"""
from __future__ import annotations

from datetime import date as _date_cls

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt_engine import PromptEngine
from app.config import Settings
from app.core.response import success
from app.deps import get_db, get_settings_dep
from app.schemas.student import (
    CheckinDraftOut,
    CheckinGenerateIn,
    CheckinRecordOut,
    CheckinSubmitIn,
    CheckinSubmitResult,
    DayTaskOut,
    DayTaskUpdate,
    RouteOut,
    RouteRegenerateIn,
    TodayOut,
)
from app.services.checkin_service import CheckinService
from app.services.route_service import RouteService

router = APIRouter()


# ---------------------------------------------------------------------------
# 依赖工厂
# ---------------------------------------------------------------------------


def _service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> RouteService:
    """构造 RouteService 的 FastAPI 依赖。"""
    return RouteService(db, settings)


# ---------------------------------------------------------------------------
# 学习路线：生成 / 获取 / 重生成
# ---------------------------------------------------------------------------


@router.post(
    "/camps/{camp_id}/route/generate",
    response_model=None,
    summary="生成学习路线（AI）",
)
async def generate_route(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: RouteService = Depends(_service),
) -> dict:
    """基于行动营手册生成按天拆分的每日任务。

    - 手册不存在或内容为空：raise ManualNotFoundError（错误码 3002）。
    - 已存在路线：覆盖重建（cascade 删除旧 day_tasks）。
    - 失败由统一异常处理器接管（如 LLMError → 错误码 3001）。
    """
    route: RouteOut = await service.generate_route(camp_id)
    return success(route.model_dump(mode="json"))


@router.get(
    "/camps/{camp_id}/route",
    response_model=None,
    summary="获取学习路线",
)
async def get_route(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: RouteService = Depends(_service),
) -> dict:
    """按 camp_id 取学习路线；不存在时返回 null（由前端识别「待生成」状态）。"""
    route = await service.get_route(camp_id)
    data = route.model_dump(mode="json") if route is not None else None
    return success(data)


@router.post(
    "/camps/{camp_id}/route/regenerate",
    response_model=None,
    summary="重新规划学习路线",
)
async def regenerate_route(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    keep_edits: bool = Query(
        True,
        description="true: 保留已编辑任务(edited=true) 仅重生成其余；false: 全量覆盖",
    ),
    service: RouteService = Depends(_service),
) -> dict:
    """重生成学习路线。

    - keep_edits=true：保留 edited=True 的 DayTask，其余按 AI 重生成。
    - keep_edits=false：全量删除旧路线并按 AI 重建（等价于 generate_route）。
    """
    route: RouteOut = await service.regenerate_route(camp_id, keep_edits=keep_edits)
    return success(route.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 学习路线：编辑每日任务
# ---------------------------------------------------------------------------


@router.put(
    "/route/tasks/{task_id}",
    response_model=None,
    summary="编辑每日任务",
)
async def update_day_task(
    payload: DayTaskUpdate,
    task_id: int = Path(..., gt=0, description="DayTask ID"),
    service: RouteService = Depends(_service),
) -> dict:
    """更新单个 DayTask。

    - 仅 title / description / tags 可改；任一字段被修改即标记 edited=True。
    - task 不存在时 raise NotFoundError。
    """
    task: DayTaskOut = await service.update_day_task(
        task_id,
        patch=payload.model_dump(exclude_unset=True),
    )
    return success(task.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 今日任务
# ---------------------------------------------------------------------------


@router.get(
    "/camps/{camp_id}/today",
    response_model=None,
    summary="今日任务+进度",
)
async def get_today_task(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    today: _date_cls | None = Query(
        None,
        description="目标日期(YYYY-MM-DD)；缺省=服务器当日(UTC 视角下本地日期)",
    ),
    service: RouteService = Depends(_service),
) -> dict:
    """按 today 推算 Day N 并返回当日任务。

    - 营未开始：day_number=null, task=null, progress=0.0。
    - 营已结束：day_number=null, task=null, progress=1.0。
    - 进行中无任务：task=null, progress=current_day/total_days。
    """
    target = today or _date_cls.today()
    out: TodayOut = await service.get_today_task(camp_id, target)
    return success(out.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# 打卡（checkin）：生成 / 提交 / 列表
# ---------------------------------------------------------------------------


def _checkin_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> CheckinService:
    """CheckinService 依赖：注入 DB session、Settings、PromptEngine。

    LLMClient 由 CheckinService 内部按激活厂商延迟获取（见 _ensure_llm）。
    """
    prompt_engine = PromptEngine()
    return CheckinService(
        session=db,
        settings=settings,
        prompt_engine=prompt_engine,
    )


@router.post(
    "/camps/{camp_id}/checkin/generate",
    response_model=None,
    summary="生成打卡内容（LLM 草稿，不入库）",
)
async def generate_checkin(
    payload: CheckinGenerateIn,
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: CheckinService = Depends(_checkin_service),
) -> dict:
    """根据学员输入 + 今日任务 + 手册片段调 LLM 生成四板块打卡草稿。

    - 草稿不入库；前端可编辑后调 ``submit``。
    - 营必须为学员身份（role='student'）。
    """
    draft: CheckinDraftOut = await service.generate_checkin(
        camp_id=camp_id,
        text=payload.text,
        images=payload.images,
    )
    return success(draft.model_dump(mode="json"))


@router.post(
    "/camps/{camp_id}/checkin/submit",
    response_model=None,
    summary="提交打卡",
)
async def submit_checkin(
    payload: CheckinSubmitIn,
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: CheckinService = Depends(_checkin_service),
) -> dict:
    """提交最终打卡内容。

    - MVP 学员身份下：CheckinRecord.student_id=0（占位）。
    - ``auto=True`` 时尝试调破局 submit_checkin；接口 pending 时降级为 manual。
    """
    result: CheckinSubmitResult = await service.submit_checkin(
        camp_id=camp_id,
        content=payload.content,
        auto=payload.auto,
    )
    return success(result.model_dump(mode="json"))


@router.get(
    "/camps/{camp_id}/checkins",
    response_model=None,
    summary="打卡记录列表",
)
async def list_checkins(
    camp_id: int = Path(..., gt=0, description="行动营 ID"),
    service: CheckinService = Depends(_checkin_service),
) -> dict:
    """按 camp_id 返回打卡记录（最新在前）。"""
    items: list[CheckinRecordOut] = await service.list_checkins(camp_id=camp_id)
    data = [item.model_dump(mode="json") for item in items]
    return success(data)
