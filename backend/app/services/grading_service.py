"""志愿者作业评改服务。

对应技术方案 5.4 / 11.3。

职责：
- list_pending: 列出某行动营下 grade_status='pending' 的待评改条目（含学员昵称 join）。
- generate_grade: 调 LLM 生成评改草稿，写入 grades 表（source='ai'）。
- confirm_and_sync: 落库最终评改并尝试同步破局；失败保留本地结果。
- retry_sync: 对已 grade 但未 synced 的记录重新同步。
- regenerate_grade: 重新生成评改并覆盖 grades 表最新记录。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient
from app.services.llm_settings_service import LLMSettingsService
from app.ai.prompt_engine import PromptEngine
from app.ai.schemas import GradeDraftAI
from app.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.checkin import CheckinRecord
from app.models.grade import Grade
from app.models.manual import Manual
from app.models.scoring import ScoringStandard
from app.models.settings import PojuConfig
from app.models.student import Student
from app.poju.client import PojuClient
from app.schemas.volunteer import (
    GradeDraftOut,
    PendingGradeOut,
    SyncResult,
)

logger = logging.getLogger(__name__)

# 全局 PromptEngine 单例（与 RouteService / CheckinService 约定一致）
_prompt_engine: PromptEngine = PromptEngine()

# 提示词模板名
_GRADING_PROMPT_NAME = "grading"

# 手册片段最大字符数
_MANUAL_SNIPPET_MAX = 1500

# 历史档案条数
_HISTORY_LIMIT = 10

# 历史档案摘要截取长度
_HISTORY_CONTENT_SUMMARY_LEN = 100
_HISTORY_COMMENT_SUMMARY_LEN = 80

# AI 评改系统提示
_GRADING_SYSTEM_PROMPT = (
    "你是一名认真负责的「行动营作业评改志愿者」，"
    "请严格按 schema 返回 JSON，所有文案使用中文。"
)


class GradingService:
    """志愿者作业评改业务逻辑。

    使用方式：``GradingService(session, settings).xxx(...)``。
    LLMClient 通过 ``get_llm_client(settings)`` 取单例；PromptEngine 全局共享。
    所有写入由本服务 commit/refresh；session 由调用方管理生命周期。
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        # LLMClient 延迟获取：需异步读 DB 激活配置，故不在构造期取
        self.llm: Optional[LLMClient] = None
        self.prompt_engine: PromptEngine = _prompt_engine

    async def _ensure_llm(self) -> None:
        """按当前激活厂商取 LLMClient 单例（无激活回退 .env，见 LLMSettingsService）。"""
        if self.llm is None:
            self.llm = await LLMSettingsService(
                self.session, self.settings
            ).get_active_client()

    # ------------------------------------------------------------------
    # 待评改列表
    # ------------------------------------------------------------------
    async def list_pending(self, camp_id: int) -> list[PendingGradeOut]:
        """列出某行动营下 grade_status='pending' 的 CheckinRecord。

        学员昵称通过 left join Student 获取；若 Student 行不存在则用
        ``student_id``（转为字符串）作为回退。
        """
        # 校验 camp 存在（不区分角色，便于兜底）
        from app.models.camp import Camp

        camp_stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        if (await self.session.execute(camp_stmt)).scalar_one_or_none() is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")

        stmt = (
            select(CheckinRecord, Student.nickname)
            .outerjoin(Student, Student.id == CheckinRecord.student_id)
            .where(
                CheckinRecord.camp_id == camp_id,
                CheckinRecord.grade_status == "pending",
            )
            .order_by(CheckinRecord.id.asc())
        )
        rows = (await self.session.execute(stmt)).all()

        out: list[PendingGradeOut] = []
        for record, nickname in rows:
            nickname_value: str = (
                str(record.student_id) if nickname is None else nickname
            )
            out.append(
                PendingGradeOut(
                    checkin_id=record.id,
                    student_id=record.student_id,
                    student_nickname=nickname_value,
                    camp_id=record.camp_id,
                    day_number=record.day_number,
                    checkin_date=record.checkin_date,
                    content=record.content,
                    images=record.images,
                    submitted_at=record.submitted_at,
                )
            )
        return out

    # ------------------------------------------------------------------
    # 生成评改
    # ------------------------------------------------------------------
    async def generate_grade(self, checkin_id: int) -> GradeDraftOut:
        """调 LLM 生成评改草稿并存入 grades 表（source='ai'）。

        组装内容：
        - checkin_content: 本次打卡 content
        - history_archive: 同 student_id 下 grade_status='graded' 的近 10 条
          CheckinRecord，精简为 {date, stars, content_summary(前 100 字),
          comment_summary(前 80 字)} 列表
        - manual_snippet: 手册全文前 1500 字（无手册时回退提示）
        - scoring_standard: ScoringService.get_active() 的原始结构
        - current_day: 本次打卡的 day_number
        """
        await self._ensure_llm()
        record = await self._get_checkin(checkin_id)
        student = await self._get_student_or_none(record.student_id)

        history_archive = await self._build_history_archive(record.student_id, checkin_id)
        manual_snippet = await self._get_manual_snippet(record.camp_id)
        scoring_standard = await self._get_scoring_standard_text()

        checkin_content = record.content or "（学员本次打卡内容为空）"
        current_day = record.day_number

        prompt = self.prompt_engine.get_prompt(
            _GRADING_PROMPT_NAME,
            checkin_content=checkin_content,
            history_archive=history_archive,
            manual_snippet=manual_snippet,
            scoring_standard=scoring_standard,
            current_day=current_day,
        )

        try:
            result = await self.llm.chat(
                system=_GRADING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                response_schema=GradeDraftAI,
                temperature=0.4,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("评改草稿 LLM 调用失败: %s", exc)
            raise

        assert isinstance(result, GradeDraftAI)
        ai_raw = result.model_dump_json()

        # 写 grades 表新行
        dimension_payload: list[dict[str, Any]] = [
            {"key": d.key, "score": d.score, "reason": d.reason}
            for d in result.dimension_scores
        ]
        grade = Grade(
            checkin_record_id=checkin_id,
            stars=result.stars,
            comment=result.comment,
            dimension_scores=dimension_payload or None,
            ai_raw_output=ai_raw,
            source="ai",
        )
        self.session.add(grade)
        await self.session.commit()
        await self.session.refresh(grade)

        return GradeDraftOut(
            checkin_id=checkin_id,
            stars=grade.stars,
            comment=grade.comment,
            dimension_scores=grade.dimension_scores,
        )

    # ------------------------------------------------------------------
    # 确认并同步
    # ------------------------------------------------------------------
    async def confirm_and_sync(
        self,
        checkin_id: int,
        stars: int,
        comment: Optional[str],
    ) -> SyncResult:
        """写入最终评改并尝试同步破局。

        - 写入 Grade（source='confirmed' 若与最近一次 AI 草稿不一致，否则 'manual'）。
        - 更新 CheckinRecord(stars, comment, grade_status='graded', synced_to_poju=False)。
        - 调 PojuClient.submit_grade 同步：
          * 成功：synced_to_poju=True, synced_at=now → SyncResult(success=True)。
          * 失败：synced_to_poju 保持 False → SyncResult(success=False, message=...)。
        - 任何异常下本地评改已落库，绝不丢失。
        """
        if stars < 1 or stars > 3:
            raise ValidationError("stars 必须在 1-3 之间")

        record = await self._get_checkin(checkin_id)

        # 判断 source：与最近一次 ai 草稿对比
        last_ai_stmt = (
            select(Grade)
            .where(
                Grade.checkin_record_id == checkin_id,
                Grade.source == "ai",
            )
            .order_by(Grade.id.desc())
            .limit(1)
        )
        last_ai = (await self.session.execute(last_ai_stmt)).scalars().first()
        if last_ai is not None and last_ai.stars == stars and (last_ai.comment or "") == (comment or ""):
            source = "ai"  # 与 AI 草稿完全一致，沿用 ai 标记
        else:
            source = "manual" if last_ai is None else "confirmed"

        grade = Grade(
            checkin_record_id=checkin_id,
            stars=stars,
            comment=comment,
            dimension_scores=None,
            ai_raw_output=None,
            source=source,
        )
        self.session.add(grade)
        await self.session.flush()

        # 更新 CheckinRecord
        record.stars = stars
        # 不再写 CheckinRecord.comment（模型无此字段，评语仅存于 Grade 表）
        record.grade_status = "graded"
        record.synced_to_poju = False
        record.synced_at = None
        await self.session.flush()

        # 尝试同步破局
        synced = await self._sync_grade_to_poju(record)
        if synced:
            record.synced_to_poju = True
            record.synced_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(record)
            return SyncResult(
                success=True,
                message="ok",
                synced_at=record.synced_at,
            )

        # 同步失败：保留本地评改，不抛
        await self.session.commit()
        await self.session.refresh(record)
        return SyncResult(
            success=False,
            message="评改已保存本地；同步破局失败，可稍后重试",
            synced_at=None,
        )

    # ------------------------------------------------------------------
    # 仅保存（不同步破局）— BUG-VOL-006
    # ------------------------------------------------------------------
    async def save_draft_only(
        self,
        checkin_id: int,
        stars: int,
        comment: Optional[str],
    ) -> SyncResult:
        """仅保存评改到本地（不调破局同步）。

        - 写入 Grade（source 判定同 confirm_and_sync：与最近一次 ai 草稿一致
          沿用 'ai'，否则 'manual' 或 'confirmed'）。
        - 更新 CheckinRecord(stars, grade_status='graded', synced_to_poju=False)。
        - 不调 _sync_grade_to_poju。
        """
        if stars < 1 or stars > 3:
            raise ValidationError("stars 必须在 1-3 之间")

        record = await self._get_checkin(checkin_id)

        # 与 confirm_and_sync 一致：基于最近一次 ai 草稿判定 source
        last_ai_stmt = (
            select(Grade)
            .where(
                Grade.checkin_record_id == checkin_id,
                Grade.source == "ai",
            )
            .order_by(Grade.id.desc())
            .limit(1)
        )
        last_ai = (await self.session.execute(last_ai_stmt)).scalars().first()
        if last_ai is not None and last_ai.stars == stars and (last_ai.comment or "") == (comment or ""):
            source = "ai"
        else:
            source = "manual" if last_ai is None else "confirmed"

        grade = Grade(
            checkin_record_id=checkin_id,
            stars=stars,
            comment=comment,
            dimension_scores=None,
            ai_raw_output=None,
            source=source,
        )
        self.session.add(grade)
        await self.session.flush()

        # 更新 CheckinRecord（不调破局）
        record.stars = stars
        record.grade_status = "graded"
        record.synced_to_poju = False
        record.synced_at = None
        await self.session.commit()
        await self.session.refresh(record)

        return SyncResult(
            success=True,
            message="已保存本地（未同步破局）",
            synced_at=None,
        )

    # ------------------------------------------------------------------
    # 重试同步
    # ------------------------------------------------------------------
    async def retry_sync(self, checkin_id: int) -> SyncResult:
        """对已 graded 但未 synced 的记录重新尝试同步破局。"""
        record = await self._get_checkin(checkin_id)
        if record.grade_status != "graded":
            raise ValidationError("该记录尚未评改完成，无法重试同步")
        if record.synced_to_poju:
            return SyncResult(
                success=True,
                message="已同步，无需重试",
                synced_at=record.synced_at,
            )

        synced = await self._sync_grade_to_poju(record)
        if synced:
            record.synced_to_poju = True
            record.synced_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(record)
            return SyncResult(
                success=True,
                message="ok",
                synced_at=record.synced_at,
            )

        await self.session.commit()
        return SyncResult(
            success=False,
            message="同步破局失败，请稍后再试",
            synced_at=None,
        )

    # ------------------------------------------------------------------
    # 重新生成评改
    # ------------------------------------------------------------------
    async def regenerate_grade(self, checkin_id: int) -> GradeDraftOut:
        """重新生成评改（覆盖 grades 表最新一行）。"""
        # 确认打卡记录存在
        await self._get_checkin(checkin_id)
        return await self.generate_grade(checkin_id)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    async def _get_checkin(self, checkin_id: int) -> CheckinRecord:
        stmt = select(CheckinRecord).where(CheckinRecord.id == checkin_id)
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"打卡记录 {checkin_id} 不存在")
        return record

    async def _get_student_or_none(self, student_id: int) -> Optional[Student]:
        if student_id == 0:
            return None
        stmt = select(Student).where(Student.id == student_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _build_history_archive(
        self, student_id: int, current_checkin_id: int
    ) -> str:
        """组装历史档案：同 student_id + grade_status='graded' 近 10 条。

        格式化为 JSON 字符串，便于 LLM 直接解析。
        """
        if student_id == 0:
            return "[]"

        # join Grade 取最近一条评语（CheckinRecord 无 comment 字段）
        stmt = (
            select(CheckinRecord, Grade)
            .outerjoin(
                Grade,
                (Grade.checkin_record_id == CheckinRecord.id)
                & (Grade.source.in_(["ai", "confirmed", "manual"])),
            )
            .where(
                CheckinRecord.student_id == student_id,
                CheckinRecord.grade_status == "graded",
                CheckinRecord.id != current_checkin_id,
            )
            .order_by(CheckinRecord.id.desc())
            .limit(_HISTORY_LIMIT)
        )
        rows = (await self.session.execute(stmt)).all()

        if not rows:
            return "[]"

        items: list[dict[str, Any]] = []
        for r, grade in rows:
            content = r.content or ""
            # 评语从 Grade 表取（CheckinRecord 无该字段）
            comment = (grade.comment if grade is not None else None) or ""
            items.append(
                {
                    "date": r.checkin_date.isoformat(),
                    "stars": r.stars,
                    "content_summary": content[:_HISTORY_CONTENT_SUMMARY_LEN],
                    "comment_summary": comment[:_HISTORY_COMMENT_SUMMARY_LEN],
                }
            )
        return json.dumps(items, ensure_ascii=False)

    async def _get_manual_snippet(self, camp_id: int) -> str:
        """取手册全文前 1500 字。手册不存在时回退提示。"""
        stmt = select(Manual).where(Manual.camp_id == camp_id)
        manual = (await self.session.execute(stmt)).scalar_one_or_none()
        if manual is None or not manual.content:
            return "（手册未配置，请仅基于学员输入与评分标准评改。）"
        return manual.content[:_MANUAL_SNIPPET_MAX]

    async def _get_scoring_standard_text(self) -> str:
        """取当前生效评分标准，序列化为可读 JSON 字符串。"""
        stmt = select(ScoringStandard).where(ScoringStandard.is_active.is_(True))
        standard = (await self.session.execute(stmt)).scalar_one_or_none()
        if standard is None:
            return "（评分标准未配置，请按 1-3 星基本规则打分：1=需改进，2=合格，3=优秀。）"
        return json.dumps(
            {
                "dimensions": standard.dimensions or [],
                "star_rules": standard.star_rules or {},
            },
            ensure_ascii=False,
        )

    async def _sync_grade_to_poju(self, record: CheckinRecord) -> bool:
        """尝试调破局 submit_grade 同步评改。

        - PojuConfig 未配置 / 无 base_url / 无 token：返回 False（不抛）。
        - Student 缺失 / 无 poju_student_id：返回 False（不抛）。
        - 任何 Poju 异常：捕获后返回 False。
        - poju_checkin_id 缺失：返回 False（同步缺少目标 ID）。
        """
        if not record.poju_checkin_id:
            logger.warning(
                "checkin %s 缺少 poju_checkin_id，跳过破局同步", record.id
            )
            return False

        # 取 Student
        student = await self._get_student_or_none(record.student_id)
        if student is None or not student.poju_student_id:
            logger.warning(
                "checkin %s 缺少对应 Student 或 poju_student_id，跳过破局同步",
                record.id,
            )
            return False

        # 取 PojuConfig
        config_stmt = select(PojuConfig).order_by(PojuConfig.id.asc())
        config = (await self.session.execute(config_stmt)).scalars().first()
        if config is None or not config.base_url or not config.token:
            logger.warning("PojuConfig 未配置，无法同步评改")
            return False

        # 评语从最近一条 Grade 取（CheckinRecord 无 comment 字段）
        grade_stmt = (
            select(Grade)
            .where(Grade.checkin_record_id == record.id)
            .order_by(Grade.id.desc())
            .limit(1)
        )
        latest_grade = (await self.session.execute(grade_stmt)).scalars().first()
        comment_text = (latest_grade.comment if latest_grade is not None else "") or ""

        client = PojuClient(base_url=config.base_url, token=config.token)
        try:
            await client.submit_grade(
                student_id=student.poju_student_id,
                checkin_id=record.poju_checkin_id,
                stars=record.stars or 0,
                comment=comment_text,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "评改同步破局失败 checkin=%s: %s", record.id, exc
            )
            return False
        finally:
            await client.close()
