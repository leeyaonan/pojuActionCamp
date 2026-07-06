"""加密与脱敏工具。

供 ``settings_service``（破局 Token）与 ``llm_settings_service``（大模型 API Key）
共用，避免加密/脱敏逻辑重复实现。

- Fernet 对称加密：密钥由 ``settings.secret_key`` 经 SHA-256 → urlsafe base64 派生，
  与破局 Token 同源（见技术方案 8.2）。
- 脱敏：仅保留末 4 位，其余以 ``****`` 代替。
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def ensure_fernet_key(secret_key: str) -> bytes:
    """将配置中的 secret_key 规整为 Fernet 接受的 32 字节 url-safe base64 密钥。

    Fernet 要求密钥为 32 字节的 url-safe base64 编码。配置中的 secret_key
    通常为任意字符串（开发期占位、生产期 32 字节随机串），这里统一做一次
    SHA-256 摘要后再做 base64，保证长度满足 Fernet 要求且稳定可复现。
    """
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def make_fernet(secret_key: str) -> Fernet:
    """根据 secret_key 构造 Fernet 实例。"""
    return Fernet(ensure_fernet_key(secret_key))


def encrypt(fernet: Fernet, plaintext: str) -> str:
    """明文 → Fernet 密文（url-safe base64 字符串）。"""
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(fernet: Fernet, ciphertext: str) -> str:
    """Fernet 密文 → 明文。

    解密失败抛 ``ValueError``（由调用方转换为业务 ``ValidationError``）。
    """
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("解密失败") from exc


def mask_token(token: str | None) -> str | None:
    """脱敏：仅展示末 4 位，其余以 ``****`` 代替。无值时返回 None。"""
    if not token:
        return None
    if len(token) <= 4:
        return "*" * len(token)
    return f"****{token[-4:]}"
