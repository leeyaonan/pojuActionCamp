"""学员模型（students 表）。

对应技术方案 4.2.4。志愿者身份下，从破局平台拉取的学员对齐到本地，
通过 (camp_id, poju_student_id) 唯一约束跨多次拉取对齐同一学员。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.camp import Camp
    from app.models.checkin import CheckinRecord


class Student(Base):
    """学员（志愿者带教场景下从破局平台拉取）。"""

    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("camp_id", "poju_student_id", name="uq_student_camp_poju"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camp_id: Mapped[int] = mapped_column(
        ForeignKey("camps.id"), nullable=False, comment="所属行动营"
    )
    poju_student_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="破局平台学员唯一标识(接口返回)"
    )
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, comment="昵称")
    wechat: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信(拉群用)"
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近同步时间"
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

    camp: Mapped["Camp"] = relationship("Camp", back_populates="students")
    checkin_records: Mapped[list["CheckinRecord"]] = relationship(
        "CheckinRecord", back_populates="student", cascade="all, delete-orphan"
    )
