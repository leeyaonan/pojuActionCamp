"""迁移 0002：新增 llm_provider_configs 表 + 种入 4 家预置厂商。

revision: 0002
revises: 0001
create_date: 2026-07-04

对应 AI 模型配置技术方案 §3.2。表结构与 app/models/settings.py 的 LlmProviderConfig 对齐。

预置厂商（接入地址 / 模型名均来自各厂商官方文档，见 docs/api/）：
- DeepSeek  OpenAI 兼容  https://api.deepseek.com            deepseek-v4-flash
- 智谱 GLM  OpenAI 兼容  https://open.bigmodel.cn/api/paas/v4  glm-4.7-flash
- MiniMax   OpenAI 兼容  https://api.minimaxi.com/v1          MiniMax-M3
- LongCat   Anthropic    https://api.longcat.chat/anthropic   LongCat-2.0
  （LongCat 走 Anthropic Claude API 格式，端点 /anthropic/v1/messages，
   anthropic SDK 拼 /v1/messages，故 base_url 取 https://api.longcat.chat/anthropic）

4 条记录均为 is_preset=True, is_active=False, api_key=None, key_status='unknown'。
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.types import JSON

# revision 标识
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _create_llm_provider_configs() -> None:
    """创建 llm_provider_configs 表。"""
    op.create_table(
        "llm_provider_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False, comment="厂商显示名"),
        sa.Column(
            "protocol",
            sa.String(length=30),
            nullable=False,
            comment="接入协议：openai_compatible / anthropic",
        ),
        sa.Column(
            "base_url", sa.String(length=200), nullable=False, comment="接入地址(SDK base_url)"
        ),
        sa.Column(
            "api_key",
            sa.String(length=500),
            nullable=True,
            comment="API Key(加密存储)",
        ),
        sa.Column("model", sa.String(length=100), nullable=False, comment="默认模型名"),
        sa.Column(
            "models",
            JSON(),
            nullable=True,
            comment="可选模型列表(JSON数组,供前端下拉)",
        ),
        sa.Column(
            "is_preset",
            sa.Boolean(),
            nullable=False,
            comment="是否预置厂商(预置不可删除基础信息)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            comment="是否当前激活(全局仅一条True)",
        ),
        sa.Column(
            "key_status",
            sa.String(length=20),
            nullable=False,
            comment="Key 状态: valid/invalid/unknown",
        ),
        sa.Column(
            "last_checked_at", sa.DateTime(), nullable=True, comment="上次校验时间"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间(UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            comment="更新时间(UTC)",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


# ---------------------------------------------------------------------------
# 预置厂商种子数据（地址/模型来自官方文档 docs/api/）
# ---------------------------------------------------------------------------
_PRESET_PROVIDERS = [
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


def _insert_preset_providers() -> None:
    """插入 4 家预置厂商（is_preset=True, is_active=False, api_key=None, key_status='unknown'）。"""
    now = datetime.now(timezone.utc)
    rows = [
        {
            "name": p["name"],
            "protocol": p["protocol"],
            "base_url": p["base_url"],
            "api_key": None,
            "model": p["model"],
            "models": p["models"],
            "is_preset": True,
            "is_active": False,
            "key_status": "unknown",
            "last_checked_at": None,
            "created_at": now,
            "updated_at": now,
        }
        for p in _PRESET_PROVIDERS
    ]
    op.bulk_insert(
        sa.table(
            "llm_provider_configs",
            sa.column("name", sa.String),
            sa.column("protocol", sa.String),
            sa.column("base_url", sa.String),
            sa.column("api_key", sa.String),
            sa.column("model", sa.String),
            sa.column("models", JSON),
            sa.column("is_preset", sa.Boolean),
            sa.column("is_active", sa.Boolean),
            sa.column("key_status", sa.String),
            sa.column("last_checked_at", sa.DateTime),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        rows,
    )


def upgrade() -> None:
    """升级：建表 + 种入预置厂商。"""
    _create_llm_provider_configs()
    _insert_preset_providers()


def downgrade() -> None:
    """降级：删表。"""
    op.drop_table("llm_provider_configs")
