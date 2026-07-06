"""大模型厂商配置服务。

对应 AI 模型配置技术方案 §5。复用破局 settings 的加密/脱敏基础设施
（``app/core/crypto.py``），仅数据模型不同：破局是「全局单条」，LLM 是
「多条 + 激活标记」。

职责：
- ``list_providers``：列出所有厂商（Key 脱敏）；表空时自动种入 4 家预置（自愈）。
- ``create_provider`` / ``update_provider`` / ``delete_provider``：CRUD；
  预置厂商禁删；Key 明文入参、密文入库；配置变更重置 key_status 与单例。
- ``test_provider``：解密 Key → LLMClient 发轻量 ping → 更新 key_status。
- ``activate_provider``：仅 key_status=valid 可激活；全局仅一条 is_active=True；
  激活后 reset 单例，确保下次 AI 调用按新配置重建。
- ``get_active_provider``：取当前激活的 ORM（含加密 Key），供调用方判断。
- ``get_active_client``：取激活配置 → 解密 → get_llm_client 单例；无激活回退 .env；
  .env 也无 Key 时抛 LLMError（提示到 AI 模型配置激活）。
- ``get_active_out``：返回激活厂商脱敏信息（供前端「当前使用」卡）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import (
    LLMClient,
    get_llm_client,
    reset_llm_client_singleton,
)
from app.config import Settings
from app.core.crypto import decrypt, encrypt, make_fernet, mask_token
from app.core.exceptions import LLMError, NotFoundError, ValidationError
from app.models.settings import LlmProviderConfig
from app.schemas.settings import (
    LlmActiveOut,
    LlmProviderCreate,
    LlmProviderOut,
    LlmProviderUpdate,
)
from app.schemas.settings import ConnectionResult

logger = logging.getLogger(__name__)


# 预置厂商（地址/模型来自官方文档 docs/api/，与迁移 0002 种子一致）
_PRESET_PROVIDERS: list[dict] = [
    {
        "name": "DeepSeek",
        "protocol": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    },
    {
        "name": "智谱 GLM",
        "protocol": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7-flash",
        "models": ["glm-4.7-flash", "glm-4.7", "glm-5.2", "glm-5-turbo"],
    },
    {
        "name": "MiniMax",
        "protocol": "openai_compatible",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M3",
        "models": ["MiniMax-M3", "MiniMax-M2.7"],
    },
    {
        "name": "LongCat",
        "protocol": "anthropic",
        "base_url": "https://api.longcat.chat/anthropic",
        "model": "LongCat-2.0",
        "models": ["LongCat-2.0"],
    },
]


class LLMSettingsService:
    """大模型厂商配置业务逻辑。

    使用方式：``LLMSettingsService(session, settings).list_providers()`` 等。
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._fernet = make_fernet(settings.secret_key)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _encrypt(self, plaintext: str) -> str:
        """明文 Key → Fernet 密文。"""
        return encrypt(self._fernet, plaintext)

    def _decrypt(self, ciphertext: str) -> str:
        """密文 → 明文 Key。失败抛 ValidationError。"""
        try:
            return decrypt(self._fernet, ciphertext)
        except ValueError as exc:
            logger.error("API Key 解密失败，secret_key 可能已变更: %s", exc)
            raise ValidationError("API Key 解密失败，请重新配置") from exc

    async def _get(self, provider_id: int) -> LlmProviderConfig:
        """按 id 取厂商配置；不存在 raise NotFoundError。"""
        cfg = await self.session.get(LlmProviderConfig, provider_id)
        if cfg is None:
            raise NotFoundError(f"厂商配置 {provider_id} 不存在")
        return cfg

    def _to_out(self, cfg: LlmProviderConfig) -> LlmProviderOut:
        """ORM → 脱敏输出。解密失败时仅置空脱敏字段，不阻断查询。"""
        plaintext: str | None = None
        if cfg.api_key:
            try:
                plaintext = decrypt(self._fernet, cfg.api_key)
            except ValueError:
                plaintext = None
        return LlmProviderOut(
            id=cfg.id,
            name=cfg.name,
            protocol=cfg.protocol,  # type: ignore[arg-type]
            base_url=cfg.base_url,
            model=cfg.model,
            models=cfg.models,
            api_key_masked=mask_token(plaintext),
            has_api_key=bool(plaintext),
            is_preset=cfg.is_preset,
            is_active=cfg.is_active,
            key_status=cfg.key_status,  # type: ignore[arg-type]
            last_checked_at=cfg.last_checked_at,
            created_at=cfg.created_at,
            updated_at=cfg.updated_at,
        )

    async def _ensure_presets(self) -> None:
        """表空时种入 4 家预置厂商（兜底，即使迁移种子未执行也能自愈）。"""
        stmt = select(LlmProviderConfig).limit(1)
        if (await self.session.execute(stmt)).scalars().first() is not None:
            return
        logger.info("llm_provider_configs 表为空，种入 4 家预置厂商")
        for p in _PRESET_PROVIDERS:
            self.session.add(
                LlmProviderConfig(
                    name=p["name"],
                    protocol=p["protocol"],
                    base_url=p["base_url"],
                    model=p["model"],
                    models=p["models"],
                    api_key=None,
                    is_preset=True,
                    is_active=False,
                    key_status="unknown",
                    last_checked_at=None,
                )
            )
        await self.session.commit()

    # ------------------------------------------------------------------
    # 列表 / CRUD
    # ------------------------------------------------------------------

    async def list_providers(self) -> list[LlmProviderOut]:
        """列出所有厂商（Key 脱敏），按 id 升序。表空自动种入预置。"""
        await self._ensure_presets()
        stmt = select(LlmProviderConfig).order_by(LlmProviderConfig.id.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_out(r) for r in rows]

    async def create_provider(self, payload: LlmProviderCreate) -> LlmProviderOut:
        """新增自定义厂商。api_key 明文入参、密文入库。"""
        cfg = LlmProviderConfig(
            name=payload.name,
            protocol=payload.protocol,
            base_url=payload.base_url,
            model=payload.model,
            models=payload.models,
            api_key=self._encrypt(payload.api_key) if payload.api_key else None,
            is_preset=False,
            is_active=False,
            key_status="unknown",
        )
        self.session.add(cfg)
        await self.session.commit()
        await self.session.refresh(cfg)
        return self._to_out(cfg)

    async def update_provider(
        self, provider_id: int, payload: LlmProviderUpdate
    ) -> LlmProviderOut:
        """更新厂商配置。

        - api_key：None=不修改，空串=清除，非空=更新。
        - 改动 protocol/base_url/model/api_key 任一都会重置 key_status='unknown'
          （配置变更需重新测试连接）。
        - 若该厂商已激活，配置变更后 reset 单例，下次 AI 调用按新配置重建。
        """
        cfg = await self._get(provider_id)
        config_changed = False
        if payload.name is not None:
            cfg.name = payload.name
        if payload.protocol is not None:
            cfg.protocol = payload.protocol
            config_changed = True
        if payload.base_url is not None:
            cfg.base_url = payload.base_url
            config_changed = True
        if payload.model is not None:
            cfg.model = payload.model
            config_changed = True
        if payload.models is not None:
            cfg.models = payload.models
        # api_key 处理：None=不动，空串=清除，非空=更新
        if payload.api_key is not None:
            if payload.api_key == "":
                cfg.api_key = None
            else:
                cfg.api_key = self._encrypt(payload.api_key)
            config_changed = True

        if config_changed:
            cfg.key_status = "unknown"
            cfg.last_checked_at = None

        await self.session.commit()
        await self.session.refresh(cfg)

        if cfg.is_active and config_changed:
            reset_llm_client_singleton()
        return self._to_out(cfg)

    async def delete_provider(self, provider_id: int) -> None:
        """删除厂商。预置厂商禁删；删除激活厂商后回退 .env（reset 单例）。"""
        cfg = await self._get(provider_id)
        if cfg.is_preset:
            raise ValidationError("预置厂商不可删除")
        was_active = cfg.is_active
        await self.session.delete(cfg)
        await self.session.commit()
        if was_active:
            reset_llm_client_singleton()

    # ------------------------------------------------------------------
    # 测试连接
    # ------------------------------------------------------------------

    async def test_provider(self, provider_id: int) -> ConnectionResult:
        """用该厂商配置发轻量 ping，校验 Key 与地址，更新 key_status。

        成功返回 ``ConnectionResult(valid=True)``；失败返回
        ``ConnectionResult(valid=False, message=具体原因)``（不抛异常，
        便于前端展示具体错误）。Key 缺失 / 解密失败抛 ValidationError。
        """
        cfg = await self._get(provider_id)
        if not cfg.api_key:
            raise ValidationError("请先填写该厂商的 API Key")

        plaintext = self._decrypt(cfg.api_key)

        client = LLMClient(
            provider=cfg.protocol,
            api_key=plaintext,
            model=cfg.model,
            timeout=30,
            base_url=cfg.base_url,
        )
        try:
            await client.chat(
                system="你是测试助手。",
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
            )
            cfg.key_status = "valid"
            cfg.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            return ConnectionResult(
                valid=True,
                message="连接成功",
                last_checked_at=cfg.last_checked_at,
            )
        except Exception as exc:  # noqa: BLE001
            cfg.key_status = "invalid"
            cfg.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            logger.warning(
                "厂商 %s(id=%s) 测试连接失败: %s", cfg.name, cfg.id, exc
            )
            return ConnectionResult(
                valid=False,
                message=f"连接失败：{exc}",
                details=str(exc),
                last_checked_at=cfg.last_checked_at,
            )

    # ------------------------------------------------------------------
    # 激活 / 切换
    # ------------------------------------------------------------------

    async def activate_provider(self, provider_id: int) -> LlmProviderOut:
        """激活某厂商：全局仅一条 is_active=True；仅 key_status=valid 可激活。

        激活后 reset_llm_client_singleton，确保下次 AI 调用按新配置重建客户端。
        """
        cfg = await self._get(provider_id)
        if cfg.key_status != "valid":
            raise ValidationError("仅可激活已通过测试连接的厂商")
        if not cfg.api_key:
            raise ValidationError("该厂商未配置 API Key，无法激活")

        # 其余全部置 False（全局唯一激活）
        await self.session.execute(
            update(LlmProviderConfig)
            .where(LlmProviderConfig.id != provider_id)
            .values(is_active=False)
        )
        cfg.is_active = True
        await self.session.commit()
        await self.session.refresh(cfg)

        # 单例失效，下次 get_llm_client 按新激活配置重建
        reset_llm_client_singleton()
        return self._to_out(cfg)

    # ------------------------------------------------------------------
    # 供调用方使用
    # ------------------------------------------------------------------

    async def get_active_provider(self) -> Optional[LlmProviderConfig]:
        """取当前激活的厂商 ORM（含加密 Key）。无激活返回 None。"""
        stmt = (
            select(LlmProviderConfig)
            .where(LlmProviderConfig.is_active.is_(True))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_active_client(
        self, timeout: Optional[int] = None
    ) -> LLMClient:
        """取当前激活厂商的 LLMClient 单例。

        - 有激活且已配置 Key：解密 → get_llm_client(provider, key, model, timeout, base_url)。
        - 无激活：回退 .env 的 LLM_* 配置（无 base_url，走官方 anthropic/openai）。
        - 无激活且 .env 也无 LLM_API_KEY：抛 LLMError（3001），提示到 AI 模型配置激活。

        供 RouteService / GradingService / CheckinService 等 AI 调用方使用。
        """
        active = await self.get_active_provider()
        t = timeout or self.settings.llm_timeout

        if active is not None and active.api_key:
            plaintext = self._decrypt(active.api_key)
            return get_llm_client(
                provider=active.protocol,
                api_key=plaintext,
                model=active.model,
                timeout=t,
                base_url=active.base_url,
            )

        # 回退 .env
        if not self.settings.llm_api_key:
            raise LLMError(
                "尚未激活任何大模型厂商，且 .env 未配置 LLM_API_KEY，"
                "请到「AI 模型配置」激活一家厂商"
            )
        return get_llm_client(
            provider=self.settings.llm_provider,
            api_key=self.settings.llm_api_key,
            model=self.settings.llm_model,
            timeout=t,
            base_url=None,
        )

    async def get_active_out(self) -> LlmActiveOut:
        """返回当前激活厂商脱敏信息（供前端「当前使用」卡 + /active 端点）。

        - source='db'：有激活厂商。
        - source='env'：无激活但 .env 有 LLM_API_KEY（兜底）。
        - source='none'：无激活且 .env 无 Key。
        """
        active = await self.get_active_provider()
        if active is not None:
            has_key = False
            if active.api_key:
                try:
                    decrypt(self._fernet, active.api_key)
                    has_key = True
                except ValueError:
                    has_key = False
            return LlmActiveOut(
                source="db",
                id=active.id,
                name=active.name,
                protocol=active.protocol,  # type: ignore[arg-type]
                base_url=active.base_url,
                model=active.model,
                is_active=True,
                key_status=active.key_status,  # type: ignore[arg-type]
                last_checked_at=active.last_checked_at,
                has_api_key=has_key,
            )

        if self.settings.llm_api_key:
            return LlmActiveOut(
                source="env",
                env_provider=self.settings.llm_provider,
                env_model=self.settings.llm_model,
                has_api_key=True,
            )
        return LlmActiveOut(source="none", has_api_key=False)
