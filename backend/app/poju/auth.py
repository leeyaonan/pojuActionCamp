"""破局 Token 管理。

MVP 不做自动登录，Token 由用户手动登录破局平台后获取并在界面配置。
Token 的加密存储/解密由 service 层（settings_service + cryptography）负责，
TokenManager 仅持有解密后的明文 Token 并生成请求头。
"""
from __future__ import annotations


class TokenManager:
    """持有破局 Token 并生成鉴权请求头。"""

    def __init__(self, token: str | None = None) -> None:
        self._token: str | None = token

    def update_token(self, token: str) -> None:
        """更新 Token（用户在界面重新配置时调用）。"""
        self._token = token

    def get_token(self) -> str | None:
        return self._token

    def get_headers(self) -> dict[str, str]:
        """生成鉴权请求头。

        Returns:
            包含 Authorization 与 Content-Type 的请求头字典。
            若 Token 未配置，Authorization 为空字符串（调用方应先校验）。
        """
        token = self._token or ""
        return {
            "Authorization": token,
            "Content-Type": "application/json",
        }
