"""行动营服务。

对应技术方案 4.2.1 / 5.1 / 11.1。

职责：
- 行动营的创建 / 软删除。
- 列表与详情：状态（运行期计算）/ 进度 / 已有效打卡天数等均在此层填充到 Schema。
- 单用户 MVP：学员营的有效打卡天数 = 该 camp_id 下 CheckinRecord.is_valid=True 的数量；
  志愿者营的有效天数 = 营内所有学员的 avg(valid_days)（无学员时为 0）。

约定：
- 所有写入不显式 commit 时由调用方（路由层 Depends(get_db)）的事务负责；
  本服务对 commit/refresh 负责到底，确保返回的对象对调用方即时可见。
- 时间统一 UTC 入库；status / current_day / progress / valid_days 不落库，按调用时刻现算。
"""
from __future__ import annotations

import logging
from datetime import date as _date_cls

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.camp import Camp
from app.models.checkin import CheckinRecord
from app.models.manual import Manual
from app.models.student import Student
from app.models.study_route import StudyRoute
from app.schemas.camp import CampCreate, CampOut, CampSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 纯函数工具
# ---------------------------------------------------------------------------


def calc_min_days(total_days: int) -> int:
    """计算默认最低打卡天数 = round(total_days * 0.6)。

    约定：MVP 默认按总天数的 60% 兜底；用户也可在创建时显式覆盖。
    """
    if total_days <= 0:
        raise ValidationError("total_days 必须为正整数")
    return round(total_days * 0.6)


def calc_status(camp: Camp, today: _date_cls | None = None) -> str:
    """根据 today 与 camp.start_date/end_date 计算运行期状态。

    Returns:
        "not_started" | "ongoing" | "ended"
    """
    if today is None:
        today = _date_cls.today()
    if today < camp.start_date:
        return "not_started"
    if today > camp.end_date:
        return "ended"
    return "ongoing"


def _calc_current_day(camp: Camp, today: _date_cls) -> int | None:
    """计算 current_day：仅在 ongoing 时有意义，否则 None。"""
    if today < camp.start_date or today > camp.end_date:
        return None
    return (today - camp.start_date).days + 1


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------


class CampService:
    """行动营业务逻辑。

    使用方式：``CampService(session).create_camp(payload)`` 等。
    所有方法按需 commit/refresh；session 由调用方管理生命周期。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 写：创建
    # ------------------------------------------------------------------

    async def create_camp(self, payload: CampCreate) -> Camp:
        """创建行动营。

        - 倒序日期仅警告不阻断（对齐 PRD BR-F1-2）。
        - min_checkin_days 缺省时按 calc_min_days(total_days) 兜底。
        """
        # 倒序日期仅记录警告，不阻断（修复 BUG-CAMP-006）
        if payload.end_date < payload.start_date:
            logger.warning(
                "camp 日期倒序: start=%s > end=%s（仅警告）",
                payload.start_date, payload.end_date,
            )
        # 兜底：min_checkin_days 缺省时按 0.6 计算
        min_days = payload.min_checkin_days
        if not min_days or min_days <= 0:
            min_days = calc_min_days(payload.total_days)
        if min_days > payload.total_days:
            raise ValidationError("min_checkin_days 不能大于 total_days")

        camp = Camp(
            name=payload.name,
            role=payload.role,
            description=payload.description,
            total_days=payload.total_days,
            start_date=payload.start_date,
            end_date=payload.end_date,
            min_checkin_days=min_days,
            is_deleted=False,
        )
        self.session.add(camp)
        await self.session.commit()
        await self.session.refresh(camp)
        return camp

    # ------------------------------------------------------------------
    # 读：列表 / 详情
    # ------------------------------------------------------------------

    async def list_camps(self) -> list[CampSummary]:
        """列出所有未软删的行动营，附带运行期计算字段。

        单用户 MVP：
        - 学员营（role=student）：valid_days = camp_id 下 CheckinRecord.is_valid=True 数。
        - 志愿者营（role=volunteer）：valid_days = 该营所有 Student.avg(valid_days)，无学员时为 0。
          （Student 自身的 valid_days 字段属后续志愿者服务的统计范畴，本期若无则返回 0。）
        - progress = current_day / total_days（ongoing 时；未开始/已结束为 0.0/1.0）。
        """
        stmt = select(Camp).where(Camp.is_deleted.is_(False)).order_by(Camp.id.desc())
        camps = (await self.session.execute(stmt)).scalars().all()
        if not camps:
            return []

        today = _date_cls.today()
        # 批量预聚合：学员营 - 按 camp_id 聚合 is_valid=True 的 CheckinRecord 数
        camp_ids = [c.id for c in camps]
        valid_count_map: dict[int, int] = {}
        student_camp_ids = [c.id for c in camps if c.role == "student"]
        if student_camp_ids:
            cnt_stmt = (
                select(
                    CheckinRecord.camp_id,
                    func.count(CheckinRecord.id),
                )
                .where(
                    CheckinRecord.camp_id.in_(student_camp_ids),
                    CheckinRecord.stars.is_not(None),
                    CheckinRecord.stars >= 2,
                )
                .group_by(CheckinRecord.camp_id)
            )
            rows = (await self.session.execute(cnt_stmt)).all()
            valid_count_map = {camp_id: int(cnt) for camp_id, cnt in rows}

        # 志愿者营：本 MVP 阶段尚无 Student.avg valid_days 字段定义，
        # 直接给 0，后续志愿者服务接入后再切换到 AVG 聚合。
        # 当前 data 模型中 Student 表尚无 valid_days 字段，故志愿者营 valid_days 暂为 0。
        # 如后续 Student 上线该聚合，可在此处补一次 AVG 查询。

        summaries: list[CampSummary] = []
        for camp in camps:
            status = calc_status(camp, today)
            current_day = _calc_current_day(camp, today)
            if camp.role == "student":
                valid_days = valid_count_map.get(camp.id, 0)
            else:
                valid_days = 0

            # progress：未开始=0.0；进行中=current_day/total；已结束=1.0
            if status == "not_started":
                progress = 0.0
            elif status == "ended":
                progress = 1.0
            else:
                # ongoing 时 current_day 必定非 None
                progress = (current_day or 0) / camp.total_days if camp.total_days else 0.0

            summaries.append(
                CampSummary(
                    id=camp.id,
                    name=camp.name,
                    role=camp.role,
                    total_days=camp.total_days,
                    start_date=camp.start_date,
                    end_date=camp.end_date,
                    min_checkin_days=camp.min_checkin_days,
                    status=status,  # type: ignore[arg-type]
                    current_day=current_day,
                    valid_days=valid_days,
                    progress=progress,
                    created_at=camp.created_at,
                )
            )

        return summaries

    async def get_camp(self, camp_id: int) -> CampOut:
        """获取单个行动营详情。

        - 不存在 / 已软删：raise NotFoundError。
        - 含 has_manual（当前 camp 是否已上传手册）。
        - status / current_day / valid_days 同样按运行期计算。
        """
        camp = await self._get_active_camp(camp_id)

        # 手册 / 学习路线是否存在（显式查询，避免访问关系触发 lazy-load）
        manual_stmt = select(Manual.id).where(Manual.camp_id == camp_id)
        has_manual = (await self.session.execute(manual_stmt)).scalar_one_or_none() is not None
        route_stmt = select(StudyRoute.id).where(StudyRoute.camp_id == camp_id)
        has_route = (await self.session.execute(route_stmt)).scalar_one_or_none() is not None

        today = _date_cls.today()
        status = calc_status(camp, today)
        current_day = _calc_current_day(camp, today)

        if camp.role == "student":
            valid_stmt = select(func.count(CheckinRecord.id)).where(
                CheckinRecord.camp_id == camp_id,
                CheckinRecord.stars.is_not(None),
                CheckinRecord.stars >= 2,
            )
            valid_days = int((await self.session.execute(valid_stmt)).scalar_one() or 0)
        else:
            valid_days = 0

        return CampOut(
            id=camp.id,
            name=camp.name,
            role=camp.role,  # type: ignore[arg-type]
            description=camp.description,
            total_days=camp.total_days,
            start_date=camp.start_date,
            end_date=camp.end_date,
            min_checkin_days=camp.min_checkin_days,
            status=status,  # type: ignore[arg-type]
            current_day=current_day,
            valid_days=valid_days,
            has_manual=has_manual,
            has_route=has_route,
            created_at=camp.created_at,
            updated_at=camp.updated_at,
        )

    # ------------------------------------------------------------------
    # 写：软删除
    # ------------------------------------------------------------------

    async def delete_camp(self, camp_id: int) -> Camp:
        """软删除：is_deleted=True，不级联。

        - 不存在 / 已软删：raise NotFoundError（重复删除视为错误，便于前端感知）。
        - 不级联：关联的手册 / 学习路线 / 学员 / 打卡记录保留，
          列表接口按 is_deleted=False 自动过滤掉本 camp，对历史数据无破坏。
        """
        camp = await self._get_active_camp(camp_id)
        camp.is_deleted = True
        await self.session.commit()
        await self.session.refresh(camp)
        return camp

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _get_active_camp(self, camp_id: int) -> Camp:
        """取未软删的 camp；找不到抛 NotFoundError。"""
        stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        camp = (await self.session.execute(stmt)).scalar_one_or_none()
        if camp is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")
        return camp