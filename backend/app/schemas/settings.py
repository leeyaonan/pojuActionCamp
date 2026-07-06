"""接口配置 Schema。

对应技术方案 4.2.8、5.8、8.2、11.5。
注意：token 在 PojuConfig ORM 中为密文，输出时由 settings_service 脱敏为 token_masked。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TokenStatus = Literal["valid", "invalid", "unknown"]


class PojuConfigOut(BaseModel):
    """破局接口配置输出（token 脱敏）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token_masked: Optional[str] = Field(
        default=None, description="脱敏后的 Token(仅保留首尾少量字符)"
    )
    base_url: Optional[str] = Field(default=None, description="接口基础地址")
    token_status: TokenStatus = Field(default="unknown", description="Token 状态")
    last_checked_at: Optional[datetime] = None
    has_token: bool = Field(default=False, description="是否已配置 Token")
    created_at: datetime
    updated_at: datetime


class TokenUpdate(BaseModel):
    """更新 Token 请求体。"""

    token: str = Field(..., min_length=1, description="破局 Authorization Token(明文,由 service 加密入库)")


class ConnectionResult(BaseModel):
    """测试连接结果。"""

    valid: bool = Field(..., description="连接/Token 是否有效")
    message: str = Field(..., description="结果说明")
    details: Optional[str] = Field(default=None, description="附加细节(如错误堆栈/响应摘要)")
    last_checked_at: Optional[datetime] = Field(default=None, description="本次校验时间")


# ---------------------------------------------------------------------------
# 大模型厂商配置（AI 模型配置功能）
# ---------------------------------------------------------------------------

Protocol = Literal["openai_compatible", "anthropic"]


class LlmProviderOut(BaseModel):
    """大模型厂商配置输出（api_key 脱敏）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    protocol: Protocol = Field(..., description="接入协议：openai_compatible / anthropic")
    base_url: str = Field(..., description="接入地址(SDK base_url)")
    model: str = Field(..., description="默认模型名")
    models: Optional[list[str]] = Field(default=None, description="可选模型列表")
    api_key_masked: Optional[str] = Field(
        default=None, description="脱敏后的 API Key(仅保留末 4 位)"
    )
    has_api_key: bool = Field(default=False, description="是否已配置 API Key")
    is_preset: bool = Field(default=False, description="是否预置厂商")
    is_active: bool = Field(default=False, description="是否当前激活")
    key_status: TokenStatus = Field(default="unknown", description="Key 状态")
    last_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class LlmProviderCreate(BaseModel):
    """新增厂商请求体。"""

    name: str = Field(..., min_length=1, max_length=50, description="厂商显示名")
    protocol: Protocol = Field(
        default="openai_compatible", description="接入协议：openai_compatible / anthropic"
    )
    base_url: str = Field(..., min_length=1, max_length=200, description="接入地址(SDK base_url)")
    model: str = Field(..., min_length=1, max_length=100, description="默认模型名")
    models: Optional[list[str]] = Field(default=None, description="可选模型列表")
    api_key: Optional[str] = Field(default=None, description="API Key(明文入参,不传则不设置)")


class LlmProviderUpdate(BaseModel):
    """更新厂商请求体。

    - ``api_key``：``None`` 或不传 = 不修改；空串 = 清除。
    - 其余字段 ``None`` 表示不修改。
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    protocol: Optional[Protocol] = None
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=200)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)
    models: Optional[list[str]] = None
    api_key: Optional[str] = Field(
        default=None, description="API Key(明文)。None=不修改,空串=清除"
    )


class LlmActiveOut(BaseModel):
    """当前激活厂商信息（供前端「当前使用」卡 + 调用方确认来源）。

    无激活厂商时各字段为 None，``source`` 标记配置来源。
    """

    source: Literal["db", "env", "none"] = Field(
        ..., description="配置来源：db=DB激活 / env=.env兜底 / none=无可用配置"
    )
    id: Optional[int] = None
    name: Optional[str] = None
    protocol: Optional[Protocol] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    is_active: bool = False
    key_status: TokenStatus = "unknown"
    last_checked_at: Optional[datetime] = None
    # .env 兜底时展示的 provider/model（脱敏，无 key 信息）
    env_provider: Optional[str] = None
    env_model: Optional[str] = None
    has_api_key: bool = False
