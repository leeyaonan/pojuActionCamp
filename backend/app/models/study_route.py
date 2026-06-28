"""学习路线与每日任务模型（study_routes + day_tasks 表）。

对应技术方案 4.2.3。一个学员行动营一份学习路线（camp_id 唯一），
路线下含多天每日任务。支持 AI 生成与人工编辑（edited 标记）。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

if TYPE_CHECKING:
    from app.models.camp import Camp


class StudyRoute(Base):
    """学习路线（一个学员行动营一份）。"""

    __tablename__ = "study_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camp_id: Mapped[int] = mapped_column(
        ForeignKey("camps.id"), unique=True, nullable=False, comment="所属行动营(唯一)"
    )
    generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="生成时间"
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="来源：ai / manual"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间(UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间(UTC)",
    )

    camp: Mapped["Camp"] = relationship("Camp", back_populates="study_route")
    day_tasks: Mapped[list["DayTask"]] = relationship(
        "DayTask",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="DayTask.day_number",
    )


class DayTask(Base):
    """每日任务。"""

    __tablename__ = "day_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("study_routes.id"), nullable=False, comment="所属学习路线"
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="第几天(1~N)")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="任务标题")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="任务描述")
    tags: Mapped[Optional[list[Any]]] = mapped_column(
        JSON, nullable=True, comment="标签（字符串列表或任意结构，schema 由 Pydantic 校验）"
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否完成"
    )
    edited: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否被人工编辑过"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间(UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间(UTC)",
    )

    route: Mapped["StudyRoute"] = relationship("StudyRoute", back_populates="day_tasks")
