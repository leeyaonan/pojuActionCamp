"""手册模型（manuals 表）。

对应技术方案 4.2.2。一个行动营一份手册（camp_id 唯一）。
手册内容既存文件系统（file_path），也存 DB（content），AI 读取走 DB 字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.camp import Camp


class Manual(Base):
    """行动营手册。"""

    __tablename__ = "manuals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camp_id: Mapped[int] = mapped_column(
        ForeignKey("camps.id"), unique=True, nullable=False, comment="所属行动营(唯一)"
    )
    filename: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="原始文件名"
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="本地存储路径 data/manuals/{camp_id}/"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="手册全文（提取后存库，供 AI 读取）"
    )
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="字数")
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="上传时间"
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

    camp: Mapped["Camp"] = relationship("Camp", back_populates="manual")
