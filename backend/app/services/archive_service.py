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

from app.core.crypto import decrypt, ensure_fernet_key
from app.core.exceptions import NotFoundError, ValidationError
from app.models.camp import Camp
from app.models.checkin import CheckinRecord
from app.models.settings import PojuConfig
from app.models.student import Student
from app.poju.client import PojuClient
from app.poju.exceptions import (
    PojuApiError,
    PojuAuthError,
    PojuNetworkError,
    PojuNotAvailable,
)
from cryptography.fernet import Fernet, InvalidToken
from app.schemas.volunteer import (
    ArchiveStats,
    ArchiveTimelineItem,
    InitResult,
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


def _build_fernet(secret_key: str) -> Fernet:
    """根据 secret_key 构造 Fernet 实例（poju Token 解密用）。"""
    return Fernet(ensure_fernet_key(secret_key))


def _decrypt_poju_token(fernet: Fernet, ciphertext: Optional[str]) -> Optional[str]:
    """把 PojuConfig 里加密的 token 解密为明文。

    PojuConfig.token 在数据库里以 Fernet 密文存储，所有 PojuClient 调用
    必须传明文 token。本函数失败抛 ValidationError（与 SettingsService 风格
    对齐），解密前为空时透传 None。
    """
    if ciphertext is None:
        return None
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.error("PojuConfig.token 解密失败，secret_key 可能已变更: %s", exc)
        raise ValidationError("破局 Token 解密失败，请到接口配置重新填写") from exc


def _student_field_for_clockin_key(item_key: str) -> str:
    """把 clock-in _apply 用的 item key 映射到 Student ORM 列名（保持一致）。"""
    mapping: dict[str, str] = {
        "user_name": "user_name",
        "user_number": "user_number",
        "wechat_id": "wechat_id",
        "full_name": "full_name",
        "wechat_name": "wechat_name",
        "phone": "phone",
        "volunteer_name": "volunteer_name",
        "avatar": "avatar",
    }
    return mapping.get(item_key, item_key)


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
            # 迁移 0004 档案扩展字段（query-people 拉取后落到 Student 列）
            full_name=student.full_name,
            wechat_id=student.wechat_id,
            phone=student.phone,
            wechat_name=student.wechat_name,
            user_name=student.user_name,
            user_number=student.user_number,
            leader_name=student.leader_name,
            leader_user_name=student.leader_user_name,
            leader_wechat_id=student.leader_wechat_id,
            volunteer_name=student.volunteer_name,
            volunteer_user_name=student.volunteer_user_name,
            volunteer_wechat_id=student.volunteer_wechat_id,
            data_officer_name=student.data_officer_name,
            data_officer_user_name=student.data_officer_user_name,
            data_officer_wechat_id=student.data_officer_wechat_id,
            clock_in_count=student.clock_in_count,
            camp_days=student.camp_days,
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

    async def sync_volunteer_board(
        self,
        camp_id: int,
        score: Optional[str] = "0",
    ) -> SyncResult:
        """从破局 clock-in 接口拉取打卡记录并 upsert 到本地。

        流程（2026-07-11 修订，对齐真实 clock-in 接口）：
        1. 校验 camp 存在且 role='volunteer'，且 camp.poju_action_id 已填写。
        2. 取 PojuConfig（token+base_url）；未配置 → ValidationError。
        3. 构建 PojuClient，调用 fetch_clockin_records(action_id, score)：
           - score="0"（默认）→ 仅未评改；score="" → 全部
           - PojuAuthError 上抛由统一异常处理器接管。
        4. 对每条记录联级拉附件（list_attachments），拼装 images_json。
           - 单条附件失败 → 写 errors，整体流程不中断。
        5. upsert Student：clock-in 接口 records[].id 是打卡 UUID；学员 UUID
           在 createdBy。优先 (camp_id, createdBy) 精确命中，否则按 userName/
           userNumber/wechatId 模糊匹配，都没有则新建占位。
        6. upsert CheckinRecord：始终以破局为准（用户决策 Q1）。
           - poju_score=0/None → stars=null + grade_status='pending'
           - poju_score=1/2/3 → stars=score + grade_status='graded' + 写 comment
           - 全字段覆盖（today_action/today_achievement/.../images_json 等）
        7. 返回 SyncResult(total_from_poju, synced_count, errors, ...)。
        """
        camp = await self._get_active_camp(camp_id)
        if camp.role != "volunteer":
            raise ValidationError(
                f"camp {camp_id} 不是志愿者行动营（role={camp.role}），无法同步"
            )
        if not camp.poju_action_id or not camp.poju_action_id.strip():
            raise ValidationError(
                "尚未填写破局行动营 ID (actionId)，请到「行动营设置」补填后再同步"
            )

        config = await self._get_poju_config()
        if config is None or not config.base_url or not config.token:
            raise ValidationError("破局接口未配置（缺少 token 或 base_url）")

        plaintext_token: str = _decrypt_poju_token(
            _build_fernet(self.settings.secret_key), config.token
        )
        client = PojuClient(base_url=config.base_url, token=plaintext_token)
        try:
            try:
                (
                    records,
                    page_errors,
                    pages_fetched,
                    total_from_poju,
                ) = await client.fetch_clockin_records(
                    action_id=camp.poju_action_id,
                    score=score,
                )
            except PojuAuthError:
                raise
        finally:
            await client.close()

        all_errors: list[str] = list(page_errors)
        synced_count = 0
        now = datetime.now(timezone.utc)

        for item in records or []:
            poju_checkin_id = (item.get("poju_checkin_id") or "").strip()
            if not poju_checkin_id:
                logger.warning("跳过缺失 poju_checkin_id 的打卡记录: %r", item.get("id"))
                continue

            # 联级拉附件（如有 groupCode）
            images_ref = (item.get("images_ref") or "").strip()
            if images_ref:
                try:
                    attachments = await client.list_attachments(images_ref)
                    item["images_json"] = attachments
                except PojuAuthError:
                    raise
                except (PojuApiError, PojuNetworkError, PojuNotAvailable) as exc:
                    logger.warning(
                        "拉取附件失败（groupCode=%s）: %s", images_ref, exc
                    )
                    all_errors.append(f"附件 {images_ref} 拉取失败：{exc}")
                    item["images_json"] = None

            # 解析本地 Student（clock-in 的 poju_student_id 实为 createdBy）
            poju_student_id = (item.get("poju_student_id") or "").strip()
            student = await self._resolve_student_for_clockin(
                camp_id=camp_id,
                item=item,
                poju_student_id=poju_student_id,
                last_synced_at=now,
            )

            # upsert CheckinRecord：以破局为准
            await self._upsert_checkin(
                student_id=student.id,
                camp_id=camp_id,
                item=item,
            )
            synced_count += 1

        await self.session.commit()

        message = (
            f"同步完成：破局共 {total_from_poju} 条，本地新增/更新 {synced_count} 条"
            + (f"，{len(all_errors)} 个失败" if all_errors else "")
        )
        return SyncResult(
            success=True,
            synced_count=synced_count,
            synced_at=now,
            total_from_poju=total_from_poju,
            errors=all_errors,
            message=message,
        )

    async def _resolve_student_for_clockin(
        self,
        *,
        camp_id: int,
        item: dict[str, Any],
        poju_student_id: str,
        last_synced_at: datetime,
    ) -> Student:
        """把 clock-in 单条记录解析成本地 Student 行。

        解析优先级（用户决策 Q1：始终以破局为准）：
        1. (camp_id, poju_student_id) 命中 → 直接复用，覆盖式更新档案字段。
        2. 用 userName/userNumber/wechatId 模糊匹配已有 Student。
        3. 都没有 → 新建占位 Student。
        """
        # 优先级 1：(camp_id, poju_student_id) 精确命中
        if poju_student_id:
            stmt = select(Student).where(
                and_(Student.camp_id == camp_id, Student.poju_student_id == poju_student_id)
            )
            hit = (await self.session.execute(stmt)).scalar_one_or_none()
            if hit is not None:
                self._apply_clockin_to_student(hit, item, last_synced_at)
                return hit

        # 优先级 2：userName / userNumber / wechatId 模糊匹配
        for key in ("user_name", "user_number", "wechat_id"):
            val = (item.get(key) or "").strip() if item.get(key) else ""
            if not val:
                continue
            stmt = select(Student).where(
                and_(
                    Student.camp_id == camp_id,
                    getattr(Student, _student_field_for_clockin_key(key)) == val,
                )
            )
            hit = (await self.session.execute(stmt)).scalar_one_or_none()
            if hit is not None:
                if poju_student_id and hit.poju_student_id != poju_student_id:
                    hit.poju_student_id = poju_student_id
                self._apply_clockin_to_student(hit, item, last_synced_at)
                return hit

        # 优先级 3：新建占位 Student
        nickname = (
            (item.get("nickname") or "").strip()
            or (item.get("user_name") or "").strip()
            or poju_student_id
            or "unknown"
        )
        student = Student(
            camp_id=camp_id,
            poju_student_id=poju_student_id
            or (item.get("user_name") or "").strip()
            or f"clockin-{item.get('poju_checkin_id','')}",
            nickname=nickname,
            wechat=(item.get("wechat_id") or "").strip() or None,
            last_synced_at=last_synced_at,
        )
        self._apply_clockin_to_student(student, item, last_synced_at)
        self.session.add(student)
        await self.session.flush()
        return student

    def _apply_clockin_to_student(
        self,
        student: Student,
        item: dict[str, Any],
        last_synced_at: datetime,
    ) -> None:
        """把 clock-in 单条记录里的学员身份字段覆盖式写入 Student。"""
        new_nick = (item.get("nickname") or "").strip()
        if new_nick:
            student.nickname = new_nick
        new_wechat = (item.get("wechat_id") or "").strip()
        if new_wechat:
            student.wechat = new_wechat

        for key in (
            "full_name", "wechat_id", "phone", "wechat_name",
            "user_name", "user_number",
            "volunteer_name",
            "avatar",
        ):
            v = item.get(key)
            if v is not None and str(v).strip():
                setattr(student, key, str(v).strip())

        student.last_synced_at = last_synced_at

    # ------------------------------------------------------------------
    # 写：学员档案初始化/刷新（W4 query-people）
    # ------------------------------------------------------------------

    async def init_volunteer_archive(self, camp_id: int) -> InitResult:
        """从破局 query-people 拉取本期全部学员，按 (camp_id, poju_student_id) upsert。

        与 sync_volunteer_board（拉打卡）解耦：本方法只写 students 表，不动
        checkin_records（即便该学员在本地已存在打卡记录）。

        行为：
        - camp.role != 'volunteer' → ValidationError。
        - camp.poju_action_id 为空 → ValidationError（前端引导用户去填写）。
        - PojuConfig 缺 token/base_url → ValidationError。
        - 调用 client.fetch_volunteer_people()（带分页与错误容忍）。
        - 遍历 records，每条做 upsert：
          - 不存在 → 新增（imported++）
          - 已存在 → 更新扩展字段（updated++）；不动 nickname/wechat 的
            最小历史语义（如接口未返回则保留本地值，由 _normalize_people
            返回 None 实现"只覆盖有值的字段"）。
        - 返回 InitResult（success + imported/updated/skipped/errors/message）。

        Raises:
            NotFoundError: camp 不存在/已软删。
            ValidationError: 角色不符 / 缺 actionId / 缺 token/base_url。
            PojuAuthError: Token 失效。
        """
        return await self._upsert_volunteer_archive(camp_id)

    async def refresh_volunteer_archive(self, camp_id: int) -> InitResult:
        """刷新学员档案（覆盖式更新）。实现同 init_volunteer_archive。

        命名区分仅为 API 语义清晰：UI 上"刷新"按钮区别于"初始化"按钮，
        但内部均按 (camp_id, poju_student_id) upsert，无差别。
        """
        return await self._upsert_volunteer_archive(camp_id)

    async def _upsert_volunteer_archive(self, camp_id: int) -> InitResult:
        """init / refresh 共用实现。"""
        camp = await self._get_active_camp(camp_id)
        if camp.role != "volunteer":
            raise ValidationError(
                f"camp {camp_id} 不是志愿者行动营（role={camp.role}），无法初始化档案"
            )
        if not camp.poju_action_id or not camp.poju_action_id.strip():
            raise ValidationError(
                "尚未填写破局行动营 ID (actionId)，请到「行动营设置」补填后再初始化"
            )

        config = await self._get_poju_config()
        if config is None or not config.base_url or not config.token:
            raise ValidationError("破局接口未配置（缺少 token 或 base_url）")

        plaintext_token: str = _decrypt_poju_token(
            _build_fernet(self.settings.secret_key), config.token
        )
        client = PojuClient(base_url=config.base_url, token=plaintext_token)
        try:
            records, errors, pages_fetched = await client.fetch_volunteer_people(
                camp.poju_action_id
            )
        finally:
            await client.close()

        now = datetime.now(timezone.utc)
        imported = 0
        updated = 0
        skipped = 0
        for item in records or []:
            poju_sid = (item.get("poju_student_id") or "").strip()
            if not poju_sid:
                skipped += 1
                logger.warning(
                    "跳过缺失 poju_student_id 的学员条目（query-people）: %r",
                    item.get("poju_student_id"),
                )
                continue
            was_created = await self._upsert_student_profile(
                camp_id=camp_id,
                poju_student_id=poju_sid,
                profile=item,
                last_synced_at=now,
            )
            if was_created:
                imported += 1
            else:
                updated += 1

        # 0 条 时打 WARNING 显眼：通常是 actionId 不匹配或响应未被解析
        if imported + updated == 0 and not errors:
            logger.warning(
                "query-people 调用成功但 0 条 upsert：records=%d pages_fetched=%d "
                "action_id=%s。请检查响应结构（看上面 query-people: 日志）。",
                len(records or []),
                pages_fetched,
                camp.poju_action_id,
            )

        # 显式 commit：async session 默认不自动 commit，否则 yield 结束后被回滚
        await self.session.commit()

        message = (
            f"成功处理 {imported + updated} 名学员"
            f"（新增 {imported}，更新 {updated}，跳过 {skipped}）"
            + (f"，{len(errors)} 个分页失败" if errors else "")
        )
        return InitResult(
            success=True,
            imported=imported,
            updated=updated,
            skipped=skipped,
            total_from_poju=len(records or []),
            pages_fetched=pages_fetched,
            errors=errors,
            message=message,
            synced_at=now,
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
                    # 迁移 0004 档案扩展字段（与 get_archive 对齐）
                    full_name=s.full_name,
                    wechat_id=s.wechat_id,
                    phone=s.phone,
                    wechat_name=s.wechat_name,
                    user_name=s.user_name,
                    user_number=s.user_number,
                    leader_name=s.leader_name,
                    leader_user_name=s.leader_user_name,
                    leader_wechat_id=s.leader_wechat_id,
                    volunteer_name=s.volunteer_name,
                    volunteer_user_name=s.volunteer_user_name,
                    volunteer_wechat_id=s.volunteer_wechat_id,
                    data_officer_name=s.data_officer_name,
                    data_officer_user_name=s.data_officer_user_name,
                    data_officer_wechat_id=s.data_officer_wechat_id,
                    clock_in_count=s.clock_in_count,
                    camp_days=s.camp_days,
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

    async def _upsert_student_profile(
        self,
        *,
        camp_id: int,
        poju_student_id: str,
        profile: dict[str, Any],
        last_synced_at: datetime,
    ) -> bool:
        """按 (camp_id, poju_student_id) upsert Student 档案全字段。

        与历史最小同步路径（_upsert_student）不同：本方法写迁移 0004 起的所有
        扩展字段，且对 None 字段保持"缺失则保留本地值"的语义（不向下覆盖
        已存在数据），符合 PRD BR-F3.2-3 / 用户要求"覆盖式更新从接口来的
        最新数据，但本地独有的快照不被回滚"。

        Args:
            camp_id: 行动营 ID。
            poju_student_id: 破局学员 UUID。
            profile: _normalize_people() 标准化的字段字典。
            last_synced_at: 同步时间戳。

        Returns:
            True 表示新增；False 表示更新。
        """
        stmt = select(Student).where(
            and_(Student.camp_id == camp_id, Student.poju_student_id == poju_student_id)
        )
        student = (await self.session.execute(stmt)).scalar_one_or_none()

        # 字段映射：profile key → Student column
        # 仅当 profile[key] 非 None 时覆盖本地值（不向下覆盖）
        upsert_fields: list[str] = [
            "full_name", "wechat_id", "phone", "wechat_name",
            "user_name", "user_number",
            "leader_name", "leader_user_name", "leader_wechat_id",
            "volunteer_name", "volunteer_user_name", "volunteer_wechat_id",
            "data_officer_name", "data_officer_user_name", "data_officer_wechat_id",
            "clock_in_count", "camp_days",
        ]

        if student is None:
            # 新增：nickname/wechat 优先用 profile 的 fullName / wechatId
            nickname = profile.get("nickname") or profile.get("full_name") or poju_student_id
            student = Student(
                camp_id=camp_id,
                poju_student_id=poju_student_id,
                nickname=nickname,
                wechat=profile.get("wechat") or profile.get("wechat_id"),
                last_synced_at=last_synced_at,
            )
            for f in upsert_fields:
                v = profile.get(f)
                if v is not None:
                    setattr(student, f, v)
            self.session.add(student)
            await self.session.flush()
            return True

        # 已存在：覆盖式更新（仅在 profile 提供新值时覆盖）
        new_nick = profile.get("nickname") or profile.get("full_name")
        if new_nick:
            student.nickname = new_nick
        new_wechat = profile.get("wechat") or profile.get("wechat_id")
        if new_wechat:
            student.wechat = new_wechat
        for f in upsert_fields:
            v = profile.get(f)
            if v is not None:
                setattr(student, f, v)
        student.last_synced_at = last_synced_at
        await self.session.flush()
        return False

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
        """按 poju_checkin_id upsert CheckinRecord（始终以破局为准）。

        业务约定（用户决策 Q1，2026-07-11 锁定）：
        - 始终以破局数据为准：本地人工评改也会被破局值覆盖。
        - poju_score=0/None → stars=null + grade_status='pending'
        - poju_score=1/2/3 → stars=score + grade_status='graded' + 写 comment
        - 全字段覆盖：today_action/today_achievement/good_things_share/
          next_action/images_json/.../submitted_at_ms/sign_up_id/user_name/...
        - 旧字段 day_number/checkin_date 保留（沿用原有 _parse_date / 缺省 0 逻辑）。
        - synced_to_poju / synced_at 不动（由 submit_grade 路径管理）。

        Returns:
            True 表示新增或更新（始终返回 True，调用方可据此计 synced_count）。
        """
        poju_checkin_id = (item.get("poju_checkin_id") or "").strip()
        poju_score = item.get("poju_score")  # 0/1/2/3/None
        stars = poju_score if poju_score in (1, 2, 3) else None
        grade_status = "graded" if stars is not None else "pending"

        stmt = select(CheckinRecord).where(
            CheckinRecord.poju_checkin_id == poju_checkin_id
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        # 待写入字段全集（不动 synced_to_poju / synced_at）
        new_fields: dict[str, Any] = {
            # 旧字段（保留）
            "student_id": student_id,
            "camp_id": camp_id,
            "day_number": int(item.get("day_number") or 0)
            if item.get("day_number") is not None
            else 0,
            "checkin_date": self._parse_date(item.get("checkin_date")),
            "content": item.get("content") or None,
            "images": item.get("images") or None,
            "submitted_at": self._parse_datetime(item.get("submitted_at")),
            "poju_checkin_id": poju_checkin_id,
            "grade_status": grade_status,
            "stars": stars,
            # 迁移 0007 新字段
            "sign_up_id": item.get("sign_up_id"),
            "user_name": item.get("user_name"),
            "user_number": item.get("user_number"),
            "wechat_id": item.get("wechat_id"),
            "wechat_name": item.get("wechat_name"),
            "avatar": item.get("avatar"),
            "today_action": item.get("today_action"),
            "today_achievement": item.get("today_achievement"),
            "good_things_share": item.get("good_things_share"),
            "next_action": item.get("next_action"),
            "poju_score": poju_score,
            "volunteer_name": item.get("volunteer_name"),
            "images_ref": item.get("images_ref"),
            "images_json": item.get("images_json"),
            "submitted_at_ms": item.get("submitted_at_ms"),
        }

        if existing is None:
            record = CheckinRecord(
                **new_fields,
                synced_to_poju=False,
                synced_at=None,
            )
            self.session.add(record)
            await self.session.flush()
            return True

        # 已存在：全字段覆盖（始终以破局为准），主键/归属字段不重写
        for k, v in new_fields.items():
            if k in ("student_id", "camp_id", "poju_checkin_id"):
                continue
            setattr(existing, k, v)
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
