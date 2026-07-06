"""大模型厂商配置路由。

对应 AI 模型配置技术方案 §7。挂在 /api/settings/llm 下：
- GET    /providers               列出所有厂商（Key 脱敏）
- POST   /providers               新增厂商
- PUT    /providers/{id}          更新厂商（含 Key / base_url / model）
- DELETE /providers/{id}          删除厂商（预置禁删）
- POST   /providers/{id}/test     测试连接
- POST   /providers/{id}/activate 激活该厂商
- GET    /active                  当前激活厂商（供前端「当前使用」卡）

路由独立成文件（而非并入 settings.py），避免与破局 /poju 路由的 prefix 叠加
污染。在 app/api/router.py 中以 /settings 前缀挂载 → /api/settings/llm/*。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.response import success
from app.deps import get_db, get_settings_dep
from app.schemas.settings import LlmProviderCreate, LlmProviderUpdate
from app.services.llm_settings_service import LLMSettingsService

router = APIRouter(prefix="/llm", tags=["llm-settings"])


def _service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> LLMSettingsService:
    """构造 LLMSettingsService 的 FastAPI 依赖。"""
    return LLMSettingsService(session, settings)


@router.get("/providers", response_model=None, summary="列出大模型厂商配置")
async def list_providers(
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """列出所有厂商配置（Key 脱敏）。表空时自动种入 4 家预置。"""
    out = await service.list_providers()
    return success([o.model_dump(mode="json") for o in out])


@router.post("/providers", response_model=None, summary="新增大模型厂商")
async def create_provider(
    payload: LlmProviderCreate,
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """新增自定义厂商（api_key 明文入参，密文入库）。"""
    out = await service.create_provider(payload)
    return success(out.model_dump(mode="json"))


@router.put("/providers/{provider_id}", response_model=None, summary="更新大模型厂商")
async def update_provider(
    provider_id: int,
    payload: LlmProviderUpdate,
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """更新厂商配置。api_key：None=不修改，空串=清除，非空=更新。"""
    out = await service.update_provider(provider_id, payload)
    return success(out.model_dump(mode="json"))


@router.delete("/providers/{provider_id}", response_model=None, summary="删除大模型厂商")
async def delete_provider(
    provider_id: int,
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """删除厂商。预置厂商禁删；删除激活厂商后回退 .env。"""
    await service.delete_provider(provider_id)
    return success(None)


@router.post(
    "/providers/{provider_id}/test", response_model=None, summary="测试厂商连接"
)
async def test_provider(
    provider_id: int,
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """用该厂商配置发轻量 ping，校验 Key 与地址，更新 key_status。

    成功返回 ``{valid: True}``；失败返回 ``{valid: False, message: 原因}``。
    """
    result = await service.test_provider(provider_id)
    return success(result.model_dump(mode="json"))


@router.post(
    "/providers/{provider_id}/activate", response_model=None, summary="激活厂商"
)
async def activate_provider(
    provider_id: int,
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """激活某厂商（全局仅一条 is_active=True）。仅 key_status=valid 可激活。"""
    out = await service.activate_provider(provider_id)
    return success(out.model_dump(mode="json"))


@router.get("/active", response_model=None, summary="当前激活厂商")
async def get_active(
    service: LLMSettingsService = Depends(_service),
) -> dict:
    """返回当前激活厂商脱敏信息（source: db / env / none）。"""
    out = await service.get_active_out()
    return success(out.model_dump(mode="json"))
