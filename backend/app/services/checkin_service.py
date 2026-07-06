"""打卡业务服务。

对应技术方案 5.3 / 11.2。

职责：
- ``generate_checkin``：取今日 DayTask + 手册片段，组装提示词调 LLM 生成四板块草稿，
  **不落库**（前端展示后允许编辑再走 submit）。
- ``submit_checkin``：MVP 单用户学员身份下，写入 CheckinRecord 并按需调破局接口同步。
- ``list_checkins``：按 camp_id 倒序返回打卡记录。

MVP 简化决策：
- 学员身份（camp.role='student'）下打卡写入 CheckinRecord 时，``student_id`` 用 ``0``
  作为占位（本期无 students 表行），``camp_id`` 记录当前行动营。该简化方案避免引入
  虚拟学员行；后续多用户学员档案上线时，可改为真实 ``Student.id`` 并补齐拉取同步。
- ``auto=True`` 时从 ``PojuConfig`` 取 token + base_url 构建 PojuClient 调
  ``submit_checkin``；遇到 ``PojuNotAvailable``（接口 pending）则降级为
  ``method='manual'``、``sync_status='manual'``；其它破局异常上抛由统一响应处理器
  接管。
- ``sync_status`` 实际未落表（CheckinRecord ORM 无该字段），按业务约定映射到
  CheckinSubmitResult 返回给前端，便于后续接 scheduler 时的状态机对齐。
"""
from __future__ import annotations

import logging
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient
from app.services.llm_settings_service import LLMSettingsService
from app.ai.prompt_engine import PromptEngine
from app.ai.schemas import CheckinDraftAI
from app.config import Settings
from app.core.exceptions import ManualNotFoundError, NotFoundError, ValidationError
from app.models.camp import Camp
from app.models.checkin import CheckinRecord
from app.models.manual import Manual
from app.models.settings import PojuConfig
from app.models.study_route import DayTask, StudyRoute
from app.poju.client import PojuClient
from app.poju.exceptions import PojuNotAvailable
from app.schemas.student import (
    CheckinDraftOut,
    CheckinRecordOut,
    CheckinSubmitResult,
)

logger = logging.getLogger(__name__)

# 学员身份下 CheckinRecord.student_id 占位值（MVP 单用户）
MVP_STUDENT_ID_PLACEHOLDER = 0

# 提示词模板名
_CHECKIN_PROMPT_NAME = "checkin_gen"

# 手册片段最大字符数
_MANUAL_SNIPPET_MAX = 2000

# MVP 单用户学员身份标识
_STUDENT_ROLE = "student"


class CheckinService:
    """打卡业务逻辑。

    使用方式：``CheckinService(session, settings, llm, prompt_engine).xxx(...)``。
    所有写入由本服务负责 commit/refresh；session 由调用方管理生命周期。
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        prompt_engine: PromptEngine,
    ) -> None:
        self.session = session
        self.settings = settings
        # LLMClient 延迟获取：需异步读 DB 激活配置，故不在构造期取
        self.llm: Optional[LLMClient] = None
        self.prompt_engine = prompt_engine

    async def _ensure_llm(self) -> None:
        """按当前激活厂商取 LLMClient 单例（无激活回退 .env，见 LLMSettingsService）。"""
        if self.llm is None:
            self.llm = await LLMSettingsService(
                self.session, self.settings
            ).get_active_client()

    # ------------------------------------------------------------------
    # 生成打卡草稿
    # ------------------------------------------------------------------

    async def generate_checkin(
        self,
        camp_id: int,
        text: str,
        images: Optional[list[str]] = None,
    ) -> CheckinDraftOut:
        """调 LLM 生成四板块打卡草稿（不入库）。

        - 校验 camp 存在且 role='student'。
        - 取今日 DayTask（按 camp.start_date 推算 day_number，无路线/无任务时回退提示）。
        - 取手册全文前 2000 字作为 manual_snippet。
        - 组装 checkin_gen.txt 提示词，response_schema=CheckinDraftAI。
        """
        await self._ensure_llm()
        if not text or not text.strip():
            raise ValidationError("text 不能为空")

        camp = await self._get_active_camp(camp_id)
        if camp.role != _STUDENT_ROLE:
            raise ValidationError(f"camp {camp_id} 不是学员行动营，无法生成打卡草稿")

        today = _date_cls.today()
        # 计算今日 day_number（ongoing 才有意义；非 ongoing 给空串让 LLM 自由发挥）
        day_number: Optional[int] = None
        if camp.start_date <= today <= camp.end_date:
            day_number = (today - camp.start_date).days + 1

        today_task_text = await self._get_today_task_text(camp_id, day_number)
        manual_snippet = await self._get_manual_snippet(camp_id)

        # 组装 today_input：text + 可选 images
        images_section = ""
        if images:
            images_section = "\n\n【图片】\n" + "\n".join(images)
        today_input = text.strip() + images_section

        try:
            system_prompt = self.prompt_engine.load(_CHECKIN_PROMPT_NAME)
        except FileNotFoundError as exc:
            logger.error("打卡提示词模板缺失: %s", exc)
            raise ValidationError("打卡提示词模板不存在，请检查 app/ai/prompts/ 目录") from exc

        user_message = self.prompt_engine.render(
            system_prompt,
            today_input=today_input,
            today_task=today_task_text,
            manual_snippet=manual_snippet,
        )

        try:
            result = await self.llm.chat(
                system="你是一名「每日打卡整理助手」，请严格按 schema 返回 JSON。",
                messages=[{"role": "user", "content": user_message}],
                response_schema=CheckinDraftAI,
                temperature=0.7,
            )
        except Exception as exc:  # noqa: BLE001
            # LLMClient 内部已重试；这里统一抛业务异常便于上层响应
            logger.exception("打卡草稿 LLM 调用失败: %s", exc)
            raise

        # result 是 CheckinDraftAI 实例（response_schema 已校验）
        assert isinstance(result, CheckinDraftAI)
        return CheckinDraftOut(
            today_action=result.today_action,
            today_gain=result.today_gain,
            good_thing=result.good_thing,
            next_step=result.next_step,
        )

    # ------------------------------------------------------------------
    # 提交打卡
    # ------------------------------------------------------------------

    async def submit_checkin(
        self,
        camp_id: int,
        content: str,
        auto: bool = False,
    ) -> CheckinSubmitResult:
        """提交打卡：落本地 CheckinRecord（student_id=0 占位），按需调破局同步。

        - camp 必须是 student 角色。
        - day_number / checkin_date 按 camp.start_date 与 today 计算。
        - auto=True：尝试调 PojuClient.submit_checkin；PojuNotAvailable 降级 manual。
        - 其它破局异常（auth / network / api）由调用方/异常处理器接管。
        """
        if not content or not content.strip():
            raise ValidationError("content 不能为空")

        camp = await self._get_active_camp(camp_id)
        if camp.role != _STUDENT_ROLE:
            raise ValidationError(f"camp {camp_id} 不是学员行动营，无法提交打卡")

        today = _date_cls.today()
        if today < camp.start_date:
            raise ValidationError("营期未开始，无法提交打卡")
        if today > camp.end_date:
            raise ValidationError("营期已结束，无法提交打卡")
        day_number = (today - camp.start_date).days + 1

        # 同日去重（P0-BUG-PJU-002）：同一 camp + 同一 day_number 仅允许 1 条
        dup_stmt = (
            select(CheckinRecord.id)
            .where(
                CheckinRecord.camp_id == camp_id,
                CheckinRecord.day_number == day_number,
            )
            .limit(1)
        )
        if (await self.session.execute(dup_stmt)).scalar_one_or_none() is not None:
            raise ValidationError(
                f"今日（Day {day_number}）已打卡，每位学员每天仅 1 条记录"
            )

        # 默认：手动模式
        method: str = "manual"
        sync_status: str = "manual"
        poju_checkin_id: Optional[str] = None
        degraded = False

        if auto:
            prev_method = "auto"  # 用户意图是 auto
            method, sync_status, poju_checkin_id = await self._sync_to_poju(content)
            # auto 失败降级为 manual（BUG-STU-008：标识 degraded 让前端可区分）
            if method != prev_method:
                degraded = True

        record = CheckinRecord(
            student_id=MVP_STUDENT_ID_PLACEHOLDER,
            camp_id=camp_id,
            day_number=day_number,
            checkin_date=today,
            content=content,
            images=None,
            submitted_at=datetime.now(timezone.utc) if auto else None,
            poju_checkin_id=poju_checkin_id,
            grade_status="pending",
            stars=None,
            synced_to_poju=(sync_status == "synced"),
            synced_at=datetime.now(timezone.utc) if sync_status == "synced" else None,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)

        return CheckinSubmitResult(
            submitted=True,
            method=method,  # type: ignore[arg-type]
            sync_status=sync_status,  # type: ignore[arg-type]
            poju_checkin_id=poju_checkin_id,
            degraded=degraded,
        )

    # ------------------------------------------------------------------
    # 列出打卡记录
    # ------------------------------------------------------------------

    async def list_checkins(self, camp_id: int) -> list[CheckinRecordOut]:
        """按 camp_id 取所有打卡记录，按 id 倒序（最新在前）。"""
        # 校验 camp 存在（存在性校验，不区分角色，便于前端兜底）
        await self._get_active_camp(camp_id)

        stmt = (
            select(CheckinRecord)
            .where(CheckinRecord.camp_id == camp_id)
            .order_by(CheckinRecord.id.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [CheckinRecordOut.model_validate(r) for r in rows]

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

    async def _get_today_task_text(
        self, camp_id: int, day_number: Optional[int]
    ) -> str:
        """组装今日任务文本。

        - 无 day_number：返回兜底提示。
        - 有 day_number 但无路线/无对应日任务：返回兜底说明。
        - 否则：``【第N天】标题\\n描述\\n标签``。
        """
        if day_number is None:
            return "今日不在营期内，仅根据学员输入整理。"

        # 找 camp 的 study_route
        route_stmt = select(StudyRoute).where(StudyRoute.camp_id == camp_id)
        route = (await self.session.execute(route_stmt)).scalar_one_or_none()
        if route is None:
            return f"（第 {day_number} 天）尚未生成学习路线。"

        task_stmt = select(DayTask).where(
            DayTask.route_id == route.id,
            DayTask.day_number == day_number,
        )
        task = (await self.session.execute(task_stmt)).scalar_one_or_none()
        if task is None:
            return f"（第 {day_number} 天）未找到对应的每日任务。"

        lines = [f"【第 {task.day_number} 天】{task.title}"]
        if task.description:
            lines.append(task.description)
        if task.tags:
            tag_str = "、".join(
                str(t.get("name") or t.get("label") or t)
                if isinstance(t, dict)
                else str(t)
                for t in task.tags
            )
            if tag_str:
                lines.append(f"标签：{tag_str}")
        return "\n".join(lines)

    async def _get_manual_snippet(self, camp_id: int) -> str:
        """取手册全文前 2000 字。

        - 手册缺失时 raise ManualNotFoundError（BUG-STU-009：对齐 route generate 行为）。
        """
        manual_stmt = select(Manual).where(Manual.camp_id == camp_id)
        manual = (await self.session.execute(manual_stmt)).scalar_one_or_none()
        if manual is None or not manual.content:
            raise ManualNotFoundError(f"camp {camp_id} 未配置手册或手册内容为空")
        return manual.content[:_MANUAL_SNIPPET_MAX]

    async def _sync_to_poju(self, content: str) -> tuple[str, str, Optional[str]]:
        """调破局 submit_checkin；返回 (method, sync_status, poju_checkin_id)。

        - PojuNotAvailable：降级为 ('manual', 'manual', None)。
        - PojuConfig 未配置 token / base_url：降级为 ('manual', 'manual', None)。
        - 其它破局异常上抛，由统一异常处理器接管。
        """
        config_stmt = select(PojuConfig).order_by(PojuConfig.id.asc())
        config = (await self.session.execute(config_stmt)).scalars().first()
        if config is None or not config.base_url or not config.token:
            logger.warning("PojuConfig 未配置，无法自动同步打卡，降级为手动")
            return ("manual", "manual", None)

        # 简化处理：MVP 阶段 PojuConfig.token 字段虽为密文存储，但本服务
        # 暂不引入解密（与 SettingsService 行为解耦），直接以明文尝试调用，
        # 由 PojuClient 401/403 时抛 PojuAuthError 走统一处理路径。
        # 真实生产应复用 SettingsService 的解密逻辑。
        plaintext_token: str = config.token

        client = PojuClient(base_url=config.base_url, token=plaintext_token)
        try:
            try:
                await client.submit_checkin(content=content)
            except PojuNotAvailable as exc:
                # 接口 pending/未开放 → 降级为手动
                logger.info("破局打卡接口暂不可用，降级为手动: %s", exc)
                return ("manual", "manual", None)
        finally:
            await client.close()

        # submit_checkin 当前不返回 poju_checkin_id，留扩展位
        return ("auto", "synced", None)
