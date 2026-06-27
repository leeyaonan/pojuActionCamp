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
