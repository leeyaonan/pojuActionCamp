"""迁移 0003：camps 表新增 poju_action_id 列。

revision: 0003
revises: 0002
create_date: 2026-07-05

背景：
- 破局志愿者看板接口（POST /server/volunteer/query-people）以 actionId（破局
  UUID）作为行动营过滤条件。本地 camps 表当前仅有自增 id，需要新增字段记录
  对应的破局行动营 ID。
- 字段可空（nullable=True），允许用户在创建营时不填，后续通过编辑补填。
- 角色不限（学员身份也支持填写），但只有志愿者身份会在后续走"初始化学员档案"
  流程；学员身份即使填了也不影响现有业务。

与 app/models/camp.py 的 Camp.poju_action_id 字段严格对齐。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision 标识
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """升级：camps 表新增 poju_action_id（String 64，可空）。"""
    op.add_column(
        "camps",
        sa.Column(
            "poju_action_id",
            sa.String(length=64),
            nullable=True,
            comment="破局行动营 ID（actionId，UUID 字符串），可空，创建后可编辑",
        ),
    )


def downgrade() -> None:
    """降级：删除 poju_action_id 列。"""
    op.drop_column("camps", "poju_action_id")