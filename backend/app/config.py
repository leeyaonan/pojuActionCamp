"""应用配置模块。

基于 pydantic-settings 从 .env 加载配置，字段定义对齐技术方案 8.1。
破局 Token 不放 .env，运行时从 DB 读取（见 8.2）。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，字段对齐技术方案 8.1。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "破局行动营管理平台"
    debug: bool = True
    # 同步引擎用的 sqlite 路径；async 引擎在 database.py 中转为 sqlite+aiosqlite
    database_url: str = "sqlite:///./data/app.db"

    # 大模型
    llm_provider: str = "anthropic"  # anthropic | openai
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_timeout: int = 60

    # 破局接口（初始可空，运行时从 DB 读取覆盖）
    poju_base_url: str = ""

    # 定时任务
    scheduler_enabled: bool = True
    sync_cron_hour: int = 9  # 每日 9 点拉取
    sync_cron_minute: int = 0

    # 安全：Token 加密用密钥
    secret_key: str = "change-me-to-random-string"

    @property
    def async_database_url(self) -> str:
        """返回异步引擎可用的数据库 URL。

        将 sqlite:/// 转为 sqlite+aiosqlite:///，供 aiosqlite 异步驱动使用。
        """
        url = self.database_url
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("sqlite+aiosqlite:///"):
            return url
        return url


@lru_cache
def get_settings() -> Settings:
    """获取单例 Settings（lru_cache 保证全局唯一）。"""
    return Settings()
