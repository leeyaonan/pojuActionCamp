"""接口配置模型。

- ``PojuConfig``：破局接口配置（poju_configs 表，全局唯一一条）。
  对应技术方案 4.2.8。存储破局平台 Token 与接口地址。
  Token 字段以密文存储，加解密由 service 层（app/core/crypto + poju/auth）处理，
  模型层不感知加密细节，仅提供原始 String 列。

- ``LlmProviderConfig``：大模型厂商配置（llm_provider_configs 表，多条）。
  对应 AI 模型配置技术方案 §3。支持多家厂商，全局仅一条 ``is_active=True``。
  ``api_key`` 以密文存储；``protocol`` 区分 openai_compatible / anthropic 两种接入协议。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func
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


class LlmProviderConfig(Base):
    """大模型厂商配置（多条，全局仅一条 is_active=True）。

    对应 AI 模型配置技术方案 §3.1。预置 4 家国内厂商 + 支持自定义新增。
    protocol 取值：
    - ``openai_compatible``：走 openai SDK + 自定义 base_url（DeepSeek / GLM / MiniMax）。
    - ``anthropic``：走 anthropic SDK + 自定义 base_url（LongCat）。
    api_key 加密存储，加解密由 LLMSettingsService 处理（复用 app/core/crypto）。
    """

    __tablename__ = "llm_provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="厂商显示名")
    # 协议：openai_compatible（openai SDK + base_url）/ anthropic（anthropic SDK + base_url）
    protocol: Mapped[str] = mapped_column(
        String(30),
        default="openai_compatible",
        nullable=False,
        comment="接入协议：openai_compatible / anthropic",
    )
    base_url: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="接入地址(SDK base_url)"
    )
    # api_key 加密存储，加解密由 service 层处理
    api_key: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="API Key(加密存储)"
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="默认模型名")
    # 该厂商支持的模型列表（JSON 数组），供前端下拉选择
    models: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="可选模型列表(JSON数组,供前端下拉)"
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否预置厂商(预置不可删除基础信息)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否当前激活(全局仅一条True)"
    )
    key_status: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
        comment="Key 状态: valid/invalid/unknown",
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
