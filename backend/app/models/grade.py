"""评改结果明细模型（grades 表）。

对应技术方案 4.2.6。记录 AI 生成与人工修改的评改历史，便于追溯与重评。
checkin_records 只存"最终生效"的星级评语，grades 保留每次生成明细。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

if TYPE_CHECKING:
    from app.models.checkin import CheckinRecord


class Grade(Base):
    """评改结果明细（AI/人工生成历史）。"""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkin_record_id: Mapped[int] = mapped_column(
        ForeignKey("checkin_records.id"), nullable=False, comment="关联打卡记录"
    )
    stars: Mapped[int] = mapped_column(Integer, nullable=False, comment="星级 1-3")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="评语")
    dimension_scores: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, comment="维度得分依据 [{key,score,reason}]"
    )
    ai_raw_output: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="AI 原始返回(调试用)"
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

    checkin_record: Mapped["CheckinRecord"] = relationship(
        "CheckinRecord", back_populates="grades"
    )
