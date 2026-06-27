"""接口配置服务。

对应技术方案 4.2.8 / 5.8 / 8.2 / 11.5。
- 全局仅一条 PojuConfig 记录（首次访问自动创建，token_status='unknown'）。
- Token 以 Fernet 对称加密（密钥来自 settings.secret_key）后入库，
  对外仅暴露脱敏形式（末 4 位）。
- test_connection 使用解密后的 Token + 当前 base_url 构建 PojuClient
  调 verify_token() 探测，更新 token_status / last_checked_at。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import ValidationError
from app.models.settings import PojuConfig
from app.poju.client import PojuClient
from app.schemas.settings import ConnectionResult, PojuConfigOut

logger = logging.getLogger(__name__)


def _ensure_fernet_key(secret_key: str) -> bytes:
    """将配置中的 secret_key 规整为 Fernet 接受的 32 字节 url-safe base64 密钥。

    Fernet 要求密钥为 32 字节的 url-safe base64 编码。配置中的 secret_key
    通常为任意字符串（开发期占位、生产期 32 字节随机串），这里统一做一次
    SHA-256 摘要后再做 base64，保证长度满足 Fernet 要求且稳定可复现。
    """
    import base64
    import hashlib

    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _mask_token(token: str | None) -> str | None:
    """Token 脱敏：仅展示末 4 位，其余以 **** 代替。

    无 Token 时返回 None。
    """
    if not token:
        return None
    if len(token) <= 4:
        return "*" * len(token)
    return f"****{token[-4:]}"


class SettingsService:
    """破局接口配置业务逻辑。

    使用方式：``SettingsService(session, settings).get_config()`` 等。
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._fernet = Fernet(_ensure_fernet_key(settings.secret_key))

    # ------------------------------------------------------------------
    # 加解密
    # ------------------------------------------------------------------

    def _encrypt_token(self, token: str) -> str:
        """明文 Token → Fernet 密文（url-safe base64 字符串）。"""
        return self._fernet.encrypt(token.encode("utf-8")).decode("utf-8")

    def _decrypt_token(self, ciphertext: str) -> str:
        """Fernet 密文 → 明文 Token。解密失败抛 ValidationError。"""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            logger.error("Token 解密失败，secret_key 可能已变更: %s", exc)
            raise ValidationError("Token 解密失败，请重新配置") from exc

    # ------------------------------------------------------------------
    # 持久化辅助
    # ------------------------------------------------------------------

    async def _get_or_create_config(self) -> PojuConfig:
        """获取全局唯一 PojuConfig；不存在则创建一条占位行。"""
        stmt = select(PojuConfig).order_by(PojuConfig.id.asc())
        result = await self.session.execute(stmt)
        config = result.scalars().first()
        if config is None:
            config = PojuConfig(
                token=None,
                base_url=None,
                token_status="unknown",
                last_checked_at=None,
            )
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
        return config

    def _to_out(self, config: PojuConfig) -> PojuConfigOut:
        """将 ORM 模型映射为对外 PojuConfigOut（Token 脱敏）。"""
        plaintext: str | None = None
        if config.token:
            try:
                plaintext = self._decrypt_token(config.token)
            except ValidationError:
                # 解密失败时仅置空脱敏字段，不阻断整体查询
                plaintext = None
        return PojuConfigOut(
            id=config.id,
            token_masked=_mask_token(plaintext),
            base_url=config.base_url,
            token_status=config.token_status,
            last_checked_at=config.last_checked_at,
            has_token=bool(plaintext),
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------

    async def get_config(self) -> PojuConfigOut:
        """获取当前全局配置（脱敏后返回）。

        若表为空，自动创建一条 token_status='unknown' 的占位行。
        """
        config = await self._get_or_create_config()
        return self._to_out(config)

    async def update_token(self, token: str) -> PojuConfigOut:
        """更新 Token（明文入参，密文入库）。base_url 保持不变。"""
        config = await self._get_or_create_config()
        config.token = self._encrypt_token(token)
        # 更新 Token 后重置状态为 unknown，等待下次 test_connection 校验
        config.token_status = "unknown"
        config.last_checked_at = None
        await self.session.commit()
        await self.session.refresh(config)
        return self._to_out(config)

    async def update_base_url(self, base_url: str) -> PojuConfigOut:
        """更新 base_url（供后续 /test 校验使用，本任务不暴露 API）。"""
        config = await self._get_or_create_config()
        config.base_url = base_url
        await self.session.commit()
        await self.session.refresh(config)
        return self._to_out(config)

    async def test_connection(self) -> ConnectionResult:
        """使用当前 base_url + 解密 Token 调 PojuClient.verify_token()。

        Returns:
            ConnectionResult(valid, message, last_checked_at)
            - base_url 未配置：valid=False, message='未配置接口地址'
            - Token 未配置：valid=False, message='未配置 Token'
            - Token 解密失败：valid=False, message=错误说明
            - 调用成功：valid=True / False 由 verify_token() 决定
        """
        config = await self._get_or_create_config()
        base_url = (config.base_url or "").strip()
        if not base_url:
            config.token_status = "unknown"
            config.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            return ConnectionResult(
                valid=False,
                message="未配置接口地址",
                last_checked_at=config.last_checked_at,
            )

        if not config.token:
            config.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            return ConnectionResult(
                valid=False,
                message="未配置 Token",
                last_checked_at=config.last_checked_at,
            )

        # 解密 Token
        try:
            plaintext = self._decrypt_token(config.token)
        except ValidationError as exc:
            config.token_status = "invalid"
            config.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            return ConnectionResult(
                valid=False,
                message=exc.message,
                last_checked_at=config.last_checked_at,
            )

        # 调用 PojuClient 探测
        client = PojuClient(base_url=base_url, token=plaintext)
        try:
            valid = await client.verify_token()
        except Exception as exc:  # noqa: BLE001
            # 网络/业务异常统一视为 invalid，由 message 反映
            logger.warning("测试连接异常: %s", exc)
            config.token_status = "invalid"
            config.last_checked_at = datetime.now(timezone.utc)
            await self.session.commit()
            await client.close()
            return ConnectionResult(
                valid=False,
                message=f"测试连接失败：{exc}",
                details=str(exc)[:500],
                last_checked_at=config.last_checked_at,
            )

        config.token_status = "valid" if valid else "invalid"
        config.last_checked_at = datetime.now(timezone.utc)
        await self.session.commit()
        await client.close()
        return ConnectionResult(
            valid=valid,
            message="连接成功" if valid else "Token 无效或连接失败",
            last_checked_at=config.last_checked_at,
        )
