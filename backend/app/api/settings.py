"""接口配置路由。

对应技术方案 11.5：接口配置管理。
- GET  /settings/poju       获取接口配置（Token 脱敏）
- PUT  /settings/poju/token 更新 Token（明文入参，service 加密入库）
- PUT  /settings/poju/base-url 更新 base_url（支持置空）
- POST /settings/poju/test  触发一次连接探测

所有路由统一返回 ``success()`` 包裹的 dict，由 response 中间件 / 异常处理器负责
序列化。注意：早期版本使用 ``response_model=PojuConfigOut`` 会让 FastAPI 走
StreamingResponse 分支，导致中间件无法补包 ``{code, message, data}``，故此处
改用 ``response_model=None`` + ``success()``，与其它模块保持一致。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_settings_dep
from app.config import Settings
from app.core.response import success
from app.schemas.settings import ConnectionResult, PojuConfigOut, TokenUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/poju", tags=["settings"])


class BaseUrlUpdate(BaseModel):
    """更新 base_url 请求体。

    - ``base_url`` 为空字符串或 ``None`` 时表示清除当前 base_url。
    """

    base_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="破局接口 base URL（http(s)://...），置空表示清除",
    )


def _service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> SettingsService:
    """构造 SettingsService 的 FastAPI 依赖。"""
    return SettingsService(session, settings)


@router.get("", response_model=None, summary="获取破局接口配置")
async def get_poju_config(
    service: SettingsService = Depends(_service),
) -> dict:
    """获取全局破局接口配置，Token 以脱敏形式返回。"""
    config: PojuConfigOut = await service.get_config()
    return success(config.model_dump(mode="json"))


@router.put("/token", response_model=None, summary="更新破局 Token")
async def update_poju_token(
    payload: TokenUpdate,
    service: SettingsService = Depends(_service),
) -> dict:
    """更新破局平台 Authorization Token（明文入参，内部 Fernet 加密入库）。"""
    config: PojuConfigOut = await service.update_token(payload.token)
    return success(config.model_dump(mode="json"))


@router.put("/base-url", response_model=None, summary="更新破局 base URL")
async def update_poju_base_url(
    payload: BaseUrlUpdate,
    service: SettingsService = Depends(_service),
) -> dict:
    """更新破局平台 base_url。``base_url`` 为空字符串或 ``None`` 时清除。"""
    config: PojuConfigOut = await service.update_base_url(payload.base_url)
    return success(config.model_dump(mode="json"))


@router.post("/test", response_model=None, summary="测试破局连接")
async def test_poju_connection(
    service: SettingsService = Depends(_service),
) -> dict:
    """用当前 base_url + 解密 Token 探测破局接口，更新状态字段。

    业务失败时（base_url/Token 缺失、Token 失效、网络错、接口 pending）
    由全局异常处理器返回 ``{code != 0, message, data: null}``，调用方
    在响应拦截器即可识别；仅在成功时返回 ``{code: 0, data: ConnectionResult}``。
    """
    result: ConnectionResult = await service.test_connection()
    return success(result.model_dump(mode="json"))
