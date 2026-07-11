"""迁移 0007：checkin_records 表扩展破局 clock-in 接口字段。

revision: 0007
revises: 0006
create_date: 2026-07-11

背景：
- 真实破局志愿者看板接口已确认：POST /server/clock-in/volunteer-query。
- 旧接口 GET /api/volunteer/checkins 的响应字段与志愿者实际拿到的数据
  不一致（无 today_action/today_achievement/good_things_share/next_action/
  poju_score/volunteer_name/attachments 等）。
- 本迁移在 checkin_records 表上加 15 列，全部 nullable=True：
  - sign_up_id / user_name / user_number / wechat_id / wechat_name /
    avatar / volunteer_name：学员身份/账号/头像/志愿者
  - today_action / today_achievement / good_things_share / next_action：
    打卡四板块（破局真实语义）
  - poju_score：破局原始 score（0=未评改/1-3=星级），与本地 stars 解耦
  - images_ref：附件 groupCode（破局原值，单 UUID）
  - images_json：附件列表 [{fileName,fileUrl,fileSize,fileMd5,suffix}]
  - submitted_at_ms：破局原始毫秒时间戳（排错用）

语义约定（与 archive_service 配合）：
- 同步时始终以破局为准：破局 score→本地 stars；破局 comment→本地 comment；
  破局 images_json→本地 images_json（联级调 attachment/list 拼装）。
- score=0/None → 本地 stars=null + grade_status='pending'；
  score=1/2/3 → 本地 stars=score + grade_status='graded'。
- 旧字段 content（仅一段文本）保留，作为兼容性兜底；新接口也带回 content 字段。

与 app/models/checkin.py 的 CheckinRecord 新增字段严格对齐。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision 标识
revision = "0007"
down_revision = "0004"
branch_labels = None
depends_on = None


# 集中定义新增列（升/降级复用，类型/注释保持一致）
_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, str]] = [
    ("sign_up_id", sa.String(length=64), "报名记录 ID（破局 signUpId）"),
    ("user_name", sa.String(length=64), "破局登录账号（userName）"),
    ("user_number", sa.String(length=64), "破局编号（userNumber）"),
    ("wechat_id", sa.String(length=100), "微信号（wechatId）"),
    ("wechat_name", sa.String(length=100), "微信昵称（wechatName）"),
    ("avatar", sa.String(length=500), "学员头像 URL"),
    ("today_action", sa.Text(), "今日实操（todayAction）"),
    ("today_achievement", sa.Text(), "今日成果（todayAchievement）"),
    ("good_things_share", sa.Text(), "好事分享（goodThingsShare）"),
    ("next_action", sa.Text(), "下一步行动（nextAction）"),
    ("poju_score", sa.Integer(), "破局原始 score：0=未评改/1-3=星级"),
    ("volunteer_name", sa.String(length=100), "志愿者姓名（volunteerName）"),
    ("images_ref", sa.String(length=64), "附件 groupCode（破局原值，单 UUID）"),
    ("images_json", sa.JSON(), "附件列表 [{fileName,fileUrl,fileSize,fileMd5,suffix}]"),
    ("submitted_at_ms", sa.BigInteger(), "提交时间原始毫秒时间戳（排错用）"),
]


def upgrade() -> None:
    """升级：checkin_records 表新增 15 个破局字段（全部可空）。"""
    for col_name, col_type, comment in _NEW_COLUMNS:
        op.add_column(
            "checkin_records",
            sa.Column(col_name, col_type, nullable=True, comment=comment),
        )


def downgrade() -> None:
    """降级：按反向顺序删除上述 15 列。"""
    for col_name, _col_type, _comment in reversed(_NEW_COLUMNS):
        op.drop_column("checkin_records", col_name)