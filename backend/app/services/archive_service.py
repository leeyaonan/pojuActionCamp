"""学员档案与志愿者看板同步服务。

对应技术方案 5.4 / 5.5 / 11.3。

职责：
- ``get_archive(student_id)``：组装学员档案（统计 + 倒序时间线）。
- ``get_history_for_grading(student_id, limit=10)``：精简历史（供评改 prompt 上下文）。
- ``sync_volunteer_board(camp_id)``：从破局拉取打卡记录 → 标准化 → upsert Student /
  CheckinRecord；返回 SyncResult。
- ``list_students(camp_id, status_filter)``：学员看板列表，支持按 status 过滤。

约定：
- 学员唯一性：``(camp_id, poju_student_id)`` 唯一约束，跨次拉取对齐。
- 打卡记录唯一性：``poju_checkin_id`` 唯一；已存在则保留原 ``stars``（人工评改不被覆盖）。
- Token 失效：抛 ``PojuAuthError`` 由调用方/异常处理器统一接管。
"""
from __future__ import annotations

import logging
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.camp import Camp
from app.models.checkin import CheckinRecord
from app.models.settings import PojuConfig
from app.models.student import Student
from app.poju.client import PojuClient
from app.poju.exceptions import PojuAuthError
from app.schemas.volunteer import (
    ArchiveStats,
    ArchiveTimelineItem,
    StudentArchive,
    StudentStatus,
    StudentSummary,
    SyncResult,
)

logger = logging.getLogger(__name__)

# 学员状态判定阈值（与 PRD BR-V-1 对齐）
_VALID_DAY_PENDING = "pending"      # valid_days < min_checkin_days 且 camp 未结束
_VALID_DAY_INSUFFICIENT = "insufficient"  # valid_days < min_checkin_days 且 camp 已结束
_VALID_DAY_QUALIFIED = "qualified"  # valid_days >= min_checkin_days


# ---------------------------------------------------------------------------
# 纯函数工具
# ---------------------------------------------------------------------------


def _calc_status_by_valid_days(
    valid_days: int, min_checkin_days: int, camp_ended: bool
) -> StudentStatus:
    """根据 valid_days / min_checkin_days / 营是否结束 推算学员状态。

    - valid_days >= min：qualified
    - valid_days < min 且营未结束：ongoing（进行中）
    - valid_days < min 且营已结束：unqualified
    """
    if valid_days >= min_checkin_days:
        return _VALID_DAY_QUALIFIED  # type: ignore[return-value]
    if camp_ended:
        return "unqualified"  # type: ignore[return-value]
    return "ongoing"  # type: ignore[return-value]


def _to_student_status(grading_status: str) -> StudentStatus:
    """把 grading status 字符串映射到 StudentStatus。

    仅用于 list_students 的 status_filter：
    - 'pending'  → 进行中
    - 'insufficient' → 未达标
    - 'graded'   → 已达标
    """
    mapping: dict[str, StudentStatus] = {
        "pending": "ongoing",
        "insufficient": "unqualified",
        "graded": "qualified",
    }
    return mapping.get(grading_status, "ongoing")  # type: ignore[return-value]


def _grading_status_from_valid_days(
    valid_days: int, min_checkin_days: int, camp_ended: bool
) -> str:
    """把 valid_days 转 grading 状态字符串（供 list_students 过滤）。"""
    if valid_days >= min_checkin_days:
        return "graded"
    if camp_ended:
        return "insufficient"
    return "pending"


def _truncate(text: Optional[str], max_len: int = 100) -> Optional[str]:
    """截断字符串到 max_len 字符（None 透传）。"""
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------


class ArchiveService:
    """学员档案与志愿者看板同步业务。

    使用方式：``ArchiveService(session, settings).xxx(...)``。
    写操作由本服务 commit/refresh；session 由调用方管理生命周期。
    """

    def __init__(self, session: AsyncSession, settings: Any) -> None:
        self.session = session
        self.settings = settings

    # ------------------------------------------------------------------
    # 读：学员档案
    # ------------------------------------------------------------------

    async def get_archive(self, student_id: int) -> StudentArchive:
        """取学员档案：摘要 + 统计 + 倒序时间线。

        - student 不存在：raise NotFoundError。
        - timeline：CheckinRecord 按 day_number 倒序（最新在前）。
        - 状态：valid_days / min_checkin_days / 营是否结束 推算。
        """
        student = await self._get_student(student_id)
        camp = await self._get_active_camp(student.camp_id)

        timeline_items, valid_days, total_checkins, last_stars, last_synced_at = (
            await self._load_timeline_and_stats(student_id, camp.id)
        )

        # 缺口 = min - valid（负值表示已超额）
        gap_to_min = camp.min_checkin_days - valid_days

        # 当前第几天
        today = _date_cls.today()
        current_day: Optional[int] = None
        if camp.start_date <= today <= camp.end_date:
            current_day = (today - camp.start_date).days + 1
        camp_ended = today > camp.end_date

        status: StudentStatus = _calc_status_by_valid_days(
            valid_days, camp.min_checkin_days, camp_ended
        )

        # 平均星级（仅对已评改记录计算）
        avg_stars: Optional[float] = await self._calc_avg_stars(student_id)

        summary = StudentSummary(
            id=student.id,
            camp_id=student.camp_id,
            nickname=student.nickname,
            wechat=student.wechat,
            current_day=current_day,
            valid_days=valid_days,
            gap_to_min=gap_to_min,
            last_stars=last_stars,
            status=status,
            last_synced_at=student.last_synced_at,
        )
        stats = ArchiveStats(
            total_checkins=total_checkins,
            valid_days=valid_days,
            gap_to_min=gap_to_min,
            avg_stars=avg_stars,
            status=status,
        )
        return StudentArchive(
            student=summary,
            stats=stats,
            timeline=timeline_items,
        )

    async def get_history_for_grading(
        self, student_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """精简历史（供 grading prompt 上下文）。

        返回字段：``[{date, stars, content_summary, comment_summary}]``。
        - date  ：checkin_date（ISO 字符串）
        - stars ：星级（无则 None）
        - content_summary：截断到 80 字的打卡内容
        - comment_summary：最近一次 grade 的 comment 截断到 80 字
        - 倒序、按 checkin_date 降序、limit 默认 10
        """
        if limit <= 0:
            raise ValidationError("limit 必须为正整数")

        # 取最近 limit 条
        stmt = (
            select(CheckinRecord)
            .where(CheckinRecord.student_id == student_id)
            .order_by(CheckinRecord.checkin_date.desc(), CheckinRecord.id.desc())
            .limit(limit)
        )
        records = (await self.session.execute(stmt)).scalars().all()
        if not records:
            return []

        # 批量取这些 record 的最近一次 grade comment
        record_ids = [r.id for r in records]
        from app.models.grade import Grade

        comment_map: dict[int, Optional[str]] = {}
        if record_ids:
            grade_stmt = (
                select(Grade)
                .where(Grade.checkin_record_id.in_(record_ids))
                .order_by(Grade.checkin_record_id.asc(), Grade.id.desc())
            )
            grade_rows = (await self.session.execute(grade_stmt)).scalars().all()
            for g in grade_rows:
                # 每条 checkin_record 只保留最新一条 comment
                if g.checkin_record_id not in comment_map:
                    comment_map[g.checkin_record_id] = g.comment

        history: list[dict[str, Any]] = []
        for r in records:
            history.append(
                {
                    "date": r.checkin_date.isoformat() if r.checkin_date else None,
                    "stars": r.stars,
                    "content_summary": _truncate(r.content, 80),
                    "comment_summary": _truncate(comment_map.get(r.id), 80),
                }
            )
        return history

    # ------------------------------------------------------------------
    # 写：同步志愿者看板
    # ------------------------------------------------------------------

    async def sync_volunteer_board(self, camp_id: int) -> SyncResult:
        """从破局拉取打卡记录并 upsert 到本地。

        流程：
        1. 校验 camp 存在且 role='volunteer'。
        2. 取 PojuConfig（token+base_url）；未配置 → ValidationError。
        3. 构建 PojuClient，调用 fetch_checkin_records(camp_id)。
           - PojuAuthError 上抛由统一异常处理器接管。
        4. 按 poju_student_id upsert Student（创建或更新昵称/wechat/last_synced_at）。
        5. 按 poju_checkin_id upsert CheckinRecord：
           - 新增：grade_status='pending'，stars 取接口返回值（若有）。
           - 已存在：保留原 grade_status/stars（避免覆盖人工评改）。
        6. 返回 SyncResult(success=True, synced_count, message)。
        """
        camp = await self._get_active_camp(camp_id)
        if camp.role != "volunteer":
            raise ValidationError(
                f"camp {camp_id} 不是志愿者行动营（role={camp.role}），无法同步"
            )

        config = await self._get_poju_config()
        if config is None or not config.base_url or not config.token:
            raise ValidationError("破局接口未配置（缺少 token 或 base_url）")

        plaintext_token: str = config.token
        client = PojuClient(base_url=config.base_url, token=plaintext_token)
        try:
            try:
                records = await client.fetch_checkin_records(camp_id=camp_id)
            except PojuAuthError:
                # 直接上抛，由统一异常处理器映射为 401
                raise
        finally:
            await client.close()

        synced_count = 0
        now = datetime.now(timezone.utc)
        for item in records or []:
            poju_student_id = (item.get("poju_student_id") or "").strip()
            poju_checkin_id = (item.get("poju_checkin_id") or "").strip()
            if not poju_student_id or not poju_checkin_id:
                # 关键字段缺失跳过（避免脏数据）
                logger.warning(
                    "跳过缺失关键字段的打卡记录: student=%r checkin=%r",
                    poju_student_id,
                    poju_checkin_id,
                )
                continue

            # upsert Student（按 camp_id + poju_student_id）
            student = await self._upsert_student(
                camp_id=camp_id,
                poju_student_id=poju_student_id,
                nickname=(item.get("nickname") or "").strip() or poju_student_id,
                last_synced_at=now,
            )

            # upsert CheckinRecord（按 poju_checkin_id）
            created = await self._upsert_checkin(
                student_id=student.id,
                camp_id=camp_id,
                item=item,
            )
            if created:
                synced_count += 1

        return SyncResult(
            success=True,
            synced_count=synced_count,
            synced_at=now,
            message=f"同步成功，新增 {synced_count} 条打卡记录（共处理 {len(records or [])} 条）",
        )

    # ------------------------------------------------------------------
    # 读：学员看板列表
    # ------------------------------------------------------------------

    async def list_students(
        self,
        camp_id: int,
        status_filter: Optional[Literal["pending", "insufficient", "graded"]] = None,
    ) -> list[StudentSummary]:
        """学员看板列表。

        - 校验 camp 存在（志愿者营）。
        - 预聚合：按 student_id 计算 valid_days（is_valid=True 计数）。
        - status_filter 接受 pending/insufficient/graded：
          - pending      → valid_days < min 且营未结束（进行中）
          - insufficient → valid_days < min 且营已结束（未达标）
          - graded       → valid_days >= min（已达标）
        - 按 status/id 排序。
        """
        camp = await self._get_active_camp(camp_id)
        if camp.role != "volunteer":
            raise ValidationError(
                f"camp {camp_id} 不是志愿者行动营（role={camp.role}），无法查看学员列表"
            )

        # 取所有学员
        stmt = (
            select(Student)
            .where(Student.camp_id == camp_id)
            .order_by(Student.id.asc())
        )
        students = (await self.session.execute(stmt)).scalars().all()
        if not students:
            return []

        # 预聚合：每个 student 的 valid_days
        student_ids = [s.id for s in students]
        valid_count_map = await self._aggregate_valid_days(student_ids, camp_id)

        today = _date_cls.today()
        current_day: Optional[int] = None
        if camp.start_date <= today <= camp.end_date:
            current_day = (today - camp.start_date).days + 1
        camp_ended = today > camp.end_date

        # 取每个学员最近一次评改星级
        last_stars_map = await self._aggregate_last_stars(student_ids)

        result: list[StudentSummary] = []
        for s in students:
            valid_days = valid_count_map.get(s.id, 0)
            gap_to_min = camp.min_checkin_days - valid_days
            grading_status = _grading_status_from_valid_days(
                valid_days, camp.min_checkin_days, camp_ended
            )
            if status_filter is not None and grading_status != status_filter:
                continue
            result.append(
                StudentSummary(
                    id=s.id,
                    camp_id=s.camp_id,
                    nickname=s.nickname,
                    wechat=s.wechat,
                    current_day=current_day,
                    valid_days=valid_days,
                    gap_to_min=gap_to_min,
                    last_stars=last_stars_map.get(s.id),
                    status=_to_student_status(grading_status),
                    last_synced_at=s.last_synced_at,
                )
            )

        # 排序：未达标的在前（gap_to_min 降序），再按 id 升序
        result.sort(key=lambda x: (-x.gap_to_min, x.id))
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _get_student(self, student_id: int) -> Student:
        """取 Student；不存在 raise NotFoundError。"""
        stmt = select(Student).where(Student.id == student_id)
        student = (await self.session.execute(stmt)).scalar_one_or_none()
        if student is None:
            raise NotFoundError(f"学员 {student_id} 不存在")
        return student

    async def _get_active_camp(self, camp_id: int) -> Camp:
        """取未软删的 camp；找不到抛 NotFoundError。"""
        stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        camp = (await self.session.execute(stmt)).scalar_one_or_none()
        if camp is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")
        return camp

    async def _get_poju_config(self) -> Optional[PojuConfig]:
        """取全局 PojuConfig（不存在或 id 全部为空时返回 None）。"""
        stmt = select(PojuConfig).order_by(PojuConfig.id.asc())
        return (await self.session.execute(stmt)).scalars().first()

    async def _upsert_student(
        self,
        *,
        camp_id: int,
        poju_student_id: str,
        nickname: str,
        last_synced_at: datetime,
    ) -> Student:
        """按 (camp_id, poju_student_id) upsert Student。"""
        stmt = select(Student).where(
            and_(Student.camp_id == camp_id, Student.poju_student_id == poju_student_id)
        )
        student = (await self.session.execute(stmt)).scalar_one_or_none()
        if student is None:
            student = Student(
                camp_id=camp_id,
                poju_student_id=poju_student_id,
                nickname=nickname,
                wechat=None,
                last_synced_at=last_synced_at,
            )
            self.session.add(student)
            await self.session.flush()
        else:
            # 已存在：仅更新昵称（以最新一次同步为准）与 last_synced_at
            if student.nickname != nickname:
                student.nickname = nickname
            student.last_synced_at = last_synced_at
            await self.session.flush()
        return student

    async def _upsert_checkin(
        self,
        *,
        student_id: int,
        camp_id: int,
        item: dict[str, Any],
    ) -> bool:
        """按 poju_checkin_id upsert CheckinRecord。

        Returns:
            True 表示新增；False 表示已存在（不覆盖 stars）。
        """
        poju_checkin_id = (item.get("poju_checkin_id") or "").strip()
        stmt = select(CheckinRecord).where(
            CheckinRecord.poju_checkin_id == poju_checkin_id
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            # 已存在：不覆盖 grade_status / stars（保留人工评改）
            # 但可以更新 last_synced 标志：沿用原值，避免接口写回干扰
            return False

        # 新增
        record = CheckinRecord(
            student_id=student_id,
            camp_id=camp_id,
            day_number=int(item.get("day_number") or 0)
            if item.get("day_number") is not None
            else 0,
            checkin_date=self._parse_date(item.get("checkin_date")),
            content=item.get("content") or None,
            images=item.get("images") or None,
            submitted_at=self._parse_datetime(item.get("submitted_at")),
            poju_checkin_id=poju_checkin_id,
            grade_status="pending",
            stars=item.get("stars"),
            synced_to_poju=False,
            synced_at=None,
        )
        self.session.add(record)
        await self.session.flush()
        return True

    async def _load_timeline_and_stats(
        self, student_id: int, camp_id: int
    ) -> tuple[list[ArchiveTimelineItem], int, int, Optional[int], Optional[datetime]]:
        """取学员 timeline + valid_days + total + last_stars + last_synced_at。

        一次查询拿全部：避免 N+1。
        """
        stmt = (
            select(CheckinRecord)
            .where(CheckinRecord.student_id == student_id)
            .order_by(CheckinRecord.day_number.desc(), CheckinRecord.id.desc())
        )
        records = (await self.session.execute(stmt)).scalars().all()

        total = len(records)
        valid_days = 0
        last_stars: Optional[int] = None
        # 倒序遍历（records 已按 day_number desc, id desc 排序）：
        # - last_stars: 最近一次评改的 stars（不论大小，1/2/3 都取）
        # - valid_days: stars >= 2 的有效打卡总数
        for r in records:
            if r.stars is not None:
                if last_stars is None:
                    # 第一个非空 stars 即最近一次评改的星级
                    last_stars = r.stars
                if r.stars >= 2:
                    valid_days += 1

        # 学员 last_synced_at（从 student 表读）
        student_stmt = select(Student.last_synced_at).where(Student.id == student_id)
        last_synced_at = (
            await self.session.execute(student_stmt)
        ).scalar_one_or_none()

        timeline = [
            ArchiveTimelineItem(
                checkin_id=r.id,
                day_number=r.day_number,
                checkin_date=r.checkin_date,
                content=r.content,
                stars=r.stars,
                is_valid=(r.stars is not None and r.stars >= 2),
                grade_status=r.grade_status,
                synced_to_poju=r.synced_to_poju,
            )
            for r in records
        ]
        return timeline, valid_days, total, last_stars, last_synced_at

    async def _calc_avg_stars(self, student_id: int) -> Optional[float]:
        """学员平均星级（仅对已评改记录计算）。无评改时 None。"""
        stmt = select(func.avg(CheckinRecord.stars)).where(
            CheckinRecord.student_id == student_id,
            CheckinRecord.stars.is_not(None),
        )
        avg = (await self.session.execute(stmt)).scalar_one_or_none()
        if avg is None:
            return None
        return round(float(avg), 2)

    async def _aggregate_valid_days(
        self, student_ids: list[int], camp_id: int
    ) -> dict[int, int]:
        """按 student_id 聚合 valid_days（stars>=2 计数）。"""
        if not student_ids:
            return {}
        stmt = (
            select(
                CheckinRecord.student_id,
                func.count(CheckinRecord.id),
            )
            .where(
                CheckinRecord.student_id.in_(student_ids),
                CheckinRecord.camp_id == camp_id,
                CheckinRecord.stars.is_not(None),
                CheckinRecord.stars >= 2,
            )
            .group_by(CheckinRecord.student_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {sid: int(cnt) for sid, cnt in rows}

    async def _aggregate_last_stars(
        self, student_ids: list[int]
    ) -> dict[int, int]:
        """按 student_id 取最近一次评改的 stars。

        MVP 简化：直接取 CheckinRecord.stars 最新（按 day_number 倒序第一条非空）。
        """
        if not student_ids:
            return {}
        # 取每个学员的最大 day_number 的非空 stars
        # 一次取所有 stars 记录，按 day_number 倒序，内存聚合
        stmt = (
            select(CheckinRecord.student_id, CheckinRecord.day_number, CheckinRecord.stars)
            .where(
                CheckinRecord.student_id.in_(student_ids),
                CheckinRecord.stars.is_not(None),
            )
            .order_by(CheckinRecord.day_number.desc(), CheckinRecord.id.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        result: dict[int, int] = {}
        for sid, _day, stars in rows:
            if sid not in result and stars is not None:
                result[sid] = int(stars)
        return result

    @staticmethod
    def _parse_date(value: Any) -> _date_cls:
        """把接口返回的 checkin_date 解析为 date；失败回退 today。"""
        if isinstance(value, _date_cls):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value:
            # 兼容 'YYYY-MM-DD' 与 ISO 时间字符串
            try:
                return _date_cls.fromisoformat(value[:10])
            except ValueError:
                pass
        return _date_cls.today()

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """把接口返回的 submitted_at 解析为 datetime；失败返回 None。"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str) and value:
            try:
                # 处理 'Z' 后缀
                v = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(v)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None
