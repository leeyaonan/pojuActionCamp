"""学习路线服务。

对应技术方案 4.2.3 / 5.2 / 11.2。
- generate_route：基于手册内容调 LLM 生成按天拆分的每日任务。
- get_route：按 camp_id 取学习路线（含按 day_number 排序的任务）。
- update_day_task：编辑单个任务（标记 edited=True）。
- regenerate_route：重生成；keep_edits=True 保留已编辑任务，其余重生成。
- get_today_task：按 today 推算 Day N 并返回当日任务。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.llm_client import LLMClient, get_llm_client
from app.ai.prompt_engine import PromptEngine
from app.ai.schemas import RoutePlanAI
from app.config import Settings
from app.core.exceptions import ManualNotFoundError, NotFoundError
from app.models.camp import Camp
from app.models.manual import Manual
from app.models.study_route import DayTask, StudyRoute
from app.schemas.student import DayTaskOut, RouteOut, TodayOut


# 全局 PromptEngine 单例（与现有约定保持一致：模板按需 load/cache）
_prompt_engine: PromptEngine = PromptEngine()


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------


class RouteService:
    """学习路线业务逻辑。

    使用方式：``RouteService(session, settings).generate_route(camp_id)``。
    LLMClient 通过 ``get_llm_client(settings)`` 取单例；PromptEngine 全局共享。
    所有方法按需 commit/refresh；session 由调用方管理生命周期。
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.llm: LLMClient = get_llm_client(settings)
        self.prompt_engine: PromptEngine = _prompt_engine

    # ------------------------------------------------------------------
    # 写：生成
    # ------------------------------------------------------------------
    async def generate_route(self, camp_id: int) -> RouteOut:
        """生成学习路线（AI）。

        - 取 camp + manual(无 content 时 raise ManualNotFoundError)。
        - 渲染 route_plan.txt 提示词，调 LLMClient.chat(response_schema=RoutePlanAI)。
        - 若该 camp 已存在路线：删除原路线（级联删除 day_tasks）后重建。
        - 插入 StudyRoute(source='ai') 与对应 DayTask；返回 RouteOut。
        """
        camp, manual = await self._load_camp_and_manual(camp_id)

        prompt = self.prompt_engine.get_prompt(
            "route_plan",
            camp_name=camp.name,
            total_days=camp.total_days,
            start_date=camp.start_date.isoformat(),
            end_date=camp.end_date.isoformat(),
            manual_content=manual.content or "",
        )

        result = await self.llm.chat(
            system=prompt,
            messages=[{"role": "user", "content": "请根据上述手册与行动营信息生成学习路线。"}],
            response_schema=RoutePlanAI,
        )
        # LLMClient 在传入 response_schema 时返回的是已校验的 Pydantic 实例
        plan: RoutePlanAI = result  # type: ignore[assignment]

        # 删除原路线（如有），cascade 清掉 day_tasks
        existing_stmt = select(StudyRoute).where(StudyRoute.camp_id == camp_id)
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()

        now = datetime.now(timezone.utc)
        route = StudyRoute(
            camp_id=camp_id,
            generated_at=now,
            source="ai",
        )
        self.session.add(route)
        await self.session.flush()  # 取到 route.id

        for t in plan.tasks:
            self.session.add(
                DayTask(
                    route_id=route.id,
                    day_number=t.day_number,
                    title=t.title,
                    description=t.description,
                    tags=list(t.tags) if t.tags else None,
                    is_completed=False,
                    edited=False,
                )
            )

        await self.session.commit()
        await self.session.refresh(route)

        return await self._to_route_out(route)

    # ------------------------------------------------------------------
    # 读：取路线
    # ------------------------------------------------------------------
    async def get_route(self, camp_id: int) -> Optional[RouteOut]:
        """按 camp_id 取学习路线（含按 day_number 排序的任务）。

        - 营不存在/已软删 → 抛 NotFoundError（修复 BUG-MAN-004 孤儿数据）。
        - 路线不存在 → 返回 None（前端识别"待生成"状态）。
        """
        # 校验 camp 存在（不区分角色）
        camp_stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        if (await self.session.execute(camp_stmt)).scalar_one_or_none() is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")

        stmt = (
            select(StudyRoute)
            .where(StudyRoute.camp_id == camp_id)
            .options(selectinload(StudyRoute.day_tasks))
        )
        route = (await self.session.execute(stmt)).scalar_one_or_none()
        if route is None:
            return None
        return await self._to_route_out(route)

    # ------------------------------------------------------------------
    # 写：编辑任务
    # ------------------------------------------------------------------
    async def update_day_task(self, task_id: int, patch: dict) -> DayTaskOut:
        """更新单个 DayTask；任意字段被修改即标记 edited=True。

        - patch: 允许 title / description / tags 三个字段（其它忽略）。
        - 不存在时 raise NotFoundError。
        """
        task = await self.session.get(DayTask, task_id)
        if task is None:
            raise NotFoundError(f"DayTask {task_id} 不存在")

        changed = False
        if "title" in patch and patch["title"] is not None:
            if task.title != patch["title"]:
                task.title = patch["title"]
                changed = True
        if "description" in patch and patch["description"] is not None:
            new_desc = patch["description"]
            if (task.description or "") != new_desc:
                task.description = new_desc
                changed = True
        if "tags" in patch and patch["tags"] is not None:
            # tags 为 list[dict]；不同即视为修改
            if task.tags != patch["tags"]:
                task.tags = patch["tags"]
                changed = True

        if changed:
            task.edited = True

        await self.session.commit()
        await self.session.refresh(task)
        return DayTaskOut.model_validate(task)

    # ------------------------------------------------------------------
    # 写：重新规划
    # ------------------------------------------------------------------
    async def regenerate_route(self, camp_id: int, keep_edits: bool = True) -> RouteOut:
        """重生成学习路线。

        - keep_edits=True：保留 edited=True 的 DayTask，其余删除并按 AI 重生成。
          若 AI 返回的任务数与原 edited 任务数之和不等于 total_days，按现有池子保留。
        - keep_edits=False：全量删除已有路线并按 AI 重建（等同 generate_route）。
        """
        camp, manual = await self._load_camp_and_manual(camp_id)

        if not keep_edits:
            return await self.generate_route(camp_id)

        # 保留 edited 任务的模式
        existing_route_stmt = (
            select(StudyRoute)
            .where(StudyRoute.camp_id == camp_id)
            .options(selectinload(StudyRoute.day_tasks))
        )
        existing = (await self.session.execute(existing_route_stmt)).scalar_one_or_none()
        if existing is None:
            # 没有旧路线，直接生成
            return await self.generate_route(camp_id)

        kept_tasks = [t for t in existing.day_tasks if t.edited]
        kept_day_numbers = {t.day_number for t in kept_tasks}

        # 渲染 prompt + 调 LLM
        prompt = self.prompt_engine.get_prompt(
            "route_plan",
            camp_name=camp.name,
            total_days=camp.total_days,
            start_date=camp.start_date.isoformat(),
            end_date=camp.end_date.isoformat(),
            manual_content=manual.content or "",
        )
        result = await self.llm.chat(
            system=prompt,
            messages=[{"role": "user", "content": "请根据上述手册与行动营信息生成学习路线。"}],
            response_schema=RoutePlanAI,
        )
        plan: RoutePlanAI = result  # type: ignore[assignment]

        # 删除未编辑的 DayTask（edited=False）
        for t in existing.day_tasks:
            if not t.edited:
                await self.session.delete(t)
        await self.session.flush()

        # 补齐 AI 返回的、且不在 kept_day_numbers 中的任务
        existing_day_numbers = set(kept_day_numbers)
        for ai_task in plan.tasks:
            if ai_task.day_number in existing_day_numbers:
                # 已被人工编辑过 → 跳过，不覆盖
                continue
            self.session.add(
                DayTask(
                    route_id=existing.id,
                    day_number=ai_task.day_number,
                    title=ai_task.title,
                    description=ai_task.description,
                    tags=list(ai_task.tags) if ai_task.tags else None,
                    is_completed=False,
                    edited=False,
                )
            )

        existing.generated_at = datetime.now(timezone.utc)
        existing.source = "ai"
        await self.session.commit()
        await self.session.refresh(existing)

        return await self._to_route_out(existing)

    # ------------------------------------------------------------------
    # 读：今日任务
    # ------------------------------------------------------------------
    async def get_today_task(self, camp_id: int, today: date) -> TodayOut:
        """按 today 推算 Day N 并返回当日任务。

        - 营未开始 / 已结束：day_number=None, task=None, progress=0.0/1.0。
        - 无学习路线：day_number=None, task=None, progress=0.0。
        """
        camp_stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        camp = (await self.session.execute(camp_stmt)).scalar_one_or_none()
        if camp is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")

        if today < camp.start_date:
            return TodayOut(day_number=None, task=None, progress=0.0)
        if today > camp.end_date:
            return TodayOut(day_number=None, task=None, progress=1.0)

        day_number = (today - camp.start_date).days + 1

        # 取学习路线 + 当日任务
        route_stmt = (
            select(StudyRoute)
            .where(StudyRoute.camp_id == camp_id)
            .options(selectinload(StudyRoute.day_tasks))
        )
        route = (await self.session.execute(route_stmt)).scalar_one_or_none()
        if route is None:
            return TodayOut(day_number=day_number, task=None, progress=0.0)

        task = next((t for t in route.day_tasks if t.day_number == day_number), None)
        task_out: Optional[DayTaskOut] = (
            DayTaskOut.model_validate(task) if task is not None else None
        )

        # progress：current_day / total_days（当前 day 已存在则计数到该天，否则按已生成任务数估算）
        if task_out is not None:
            completed = sum(1 for t in route.day_tasks if t.is_completed)
            current = day_number
        else:
            completed = 0
            current = day_number - 1
        progress = (current / camp.total_days) if camp.total_days else 0.0
        # 避免因 completed > current 出现 >1（仅在任务存在且完成数更多时）
        if task_out is not None and completed > current:
            progress = (completed / camp.total_days) if camp.total_days else 0.0

        return TodayOut(day_number=day_number, task=task_out, progress=progress)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    async def _load_camp_and_manual(self, camp_id: int) -> tuple[Camp, Manual]:
        """取未软删的 camp + 手册；手册不存在 raise ManualNotFoundError。"""
        camp_stmt = select(Camp).where(Camp.id == camp_id, Camp.is_deleted.is_(False))
        camp = (await self.session.execute(camp_stmt)).scalar_one_or_none()
        if camp is None:
            raise NotFoundError(f"行动营 {camp_id} 不存在")

        manual_stmt = select(Manual).where(Manual.camp_id == camp_id)
        manual = (await self.session.execute(manual_stmt)).scalar_one_or_none()
        if manual is None or not (manual.content or "").strip():
            raise ManualNotFoundError(f"camp {camp_id} 未配置手册或手册内容为空")

        return camp, manual

    async def _to_route_out(self, route: StudyRoute) -> RouteOut:
        """把 StudyRoute ORM 转 RouteOut，确保 day_tasks 已加载并按 day_number 排序。

        - BUG-NEW-001：兼容旧数据（dict 形式）转字符串列表，避免 Pydantic 校验失败。
        """
        # 关系已通过 selectinload 加载；若未加载则显式查询一次
        if "day_tasks" not in route.__dict__ or route.day_tasks is None:
            await self.session.refresh(route, attribute_names=["day_tasks"])

        tasks_sorted = sorted(route.day_tasks, key=lambda t: t.day_number)

        normalized_tasks: list[DayTaskOut] = []
        for t in tasks_sorted:
            tags_str: list[str] = []
            for tag in (t.tags or []):
                if isinstance(tag, str):
                    tags_str.append(tag)
                elif isinstance(tag, dict):
                    # 旧结构：{"name": "...", "label": "...", "key": "...", "title": "..."}
                    picked: Optional[str] = None
                    for key in ("name", "label", "key", "title"):
                        if key in tag and tag[key]:
                            picked = str(tag[key])
                            break
                    tags_str.append(picked if picked is not None else str(tag))
                else:
                    tags_str.append(str(tag))

            normalized_tasks.append(
                DayTaskOut(
                    id=t.id,
                    route_id=t.route_id,
                    day_number=t.day_number,
                    title=t.title,
                    description=t.description,
                    tags=tags_str or None,
                    is_completed=t.is_completed,
                    edited=t.edited,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
            )

        return RouteOut(
            id=route.id,
            camp_id=route.camp_id,
            generated_at=route.generated_at,
            source=route.source,
            tasks=normalized_tasks,
            created_at=route.created_at,
            updated_at=route.updated_at,
        )
