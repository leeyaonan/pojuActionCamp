"""破局接口配置模型（poju_configs 表，全局）。

对应技术方案 4.2.8。存储破局平台 Token 与接口地址。
Token 字段以密文存储，加解密由 service 层（poju/auth + cryptography）处理，
模型层不感知加密细节，仅提供原始 String 列。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PojuConfig(Base):
    """破局接口配置（全局）。"""

    __tablename__ = "poju_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 注意：token 在此处为加密后的密文字符串，加解密由 service 层处理（见技术方案 8.2）。
    token: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Authorization Token(加密存储,加解密由service层处理)"
    )
    base_url: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="接口基础地址"
    )
    token_status: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False, comment="Token状态：valid/invalid/unknown"
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="上次校验时间"
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
