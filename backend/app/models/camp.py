"""行动营模型（camps 表）。

对应技术方案 4.2.1。一个行动营有身份（学员/志愿者）、起止时间、总天数、
最低打卡完成天数等属性。状态按当前日期动态计算（不落库，见 camp_service.calc_status）。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.manual import Manual
    from app.models.student import Student
    from app.models.study_route import StudyRoute


class Camp(Base):
    """行动营。"""

    __tablename__ = "camps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="行动营名称")
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="身份：student / volunteer"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="简介")
    total_days: Mapped[int] = mapped_column(Integer, nullable=False, comment="总天数")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="开始日期")
    end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="结束日期")
    min_checkin_days: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="最低打卡完成天数（默认总天数×0.6，可改）"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="软删除标记"
    )

    created_at: Mapped[date] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间(UTC)"
    )
    updated_at: Mapped[date] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间(UTC)",
    )

    # 一对多关系
    manual: Mapped[Optional["Manual"]] = relationship(
        "Manual", back_populates="camp", uselist=False, cascade="all, delete-orphan"
    )
    study_route: Mapped[Optional["StudyRoute"]] = relationship(
        "StudyRoute", back_populates="camp", uselist=False, cascade="all, delete-orphan"
    )
    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="camp", cascade="all, delete-orphan"
    )
