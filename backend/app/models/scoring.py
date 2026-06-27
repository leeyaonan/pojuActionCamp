"""评分标准模型（scoring_standards 表，全局）。

对应技术方案 4.2.7。全局一套生效标准，维度与星级规则以 JSON 存储，便于灵活增删。
修改对后续评改生效，已评改记录不回溯（PRD BR-F5-4）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class ScoringStandard(Base):
    """评分标准（全局一套生效）。"""

    __tablename__ = "scoring_standards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否当前生效(全局一套)"
    )
    dimensions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, comment="评分维度数组 [{key,name,desc,depends_archive}]"
    )
    star_rules: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="星级判定 {three,two,one} 描述"
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
