"""迁移 0004：students 表扩展档案字段（query-people 全字段）。

revision: 0004
revises: 0003
create_date: 2026-07-05

背景：
- 破局志愿者看板端点 POST /server/volunteer/query-people 返回的 records[]
  含十余个身份/统计字段（fullName/wechatId/phone/clockInCount 等），
  但当前 students 表只有最小同步字段（nickname/wechat），无法支持完整的
  "初始化学员档案" / "刷新学员档案"两条业务流。
- 字段全部 nullable=True：旧数据不破、可空字段缺失不阻断；覆盖式更新由
  服务端 ArchiveService.init_volunteer_archive / refresh_volunteer_archive
  负责按 (camp_id, poju_student_id) upsert。
- nickname 与 wechat 保留为最小同步字段，与新增 full_name / wechat_id 双向
  同步（以 query-people 为准），保留向后兼容。
- 学员档案与 checkin_records 互不干扰：本迁移不动打卡相关表。

与 app/models/student.py 的 Student 新增字段严格对齐。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision 标识
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


# 集中定义新增列（升/降级复用，类型/注释保持一致）
_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, str]] = [
    ("full_name", sa.String(length=100), "姓名（破局 fullName）"),
    ("wechat_id", sa.String(length=100), "微信号（破局 wechatId）"),
    ("phone", sa.String(length=32), "手机号"),
    ("wechat_name", sa.String(length=100), "微信昵称（破局 wechatName）"),
    ("user_name", sa.String(length=64), "破局登录账号"),
    ("user_number", sa.String(length=64), "破局编号"),
    ("leader_name", sa.String(length=100), "组长姓名"),
    ("leader_user_name", sa.String(length=64), "组长账号"),
    ("leader_wechat_id", sa.String(length=100), "组长微信"),
    ("volunteer_name", sa.String(length=100), "志愿者姓名"),
    ("volunteer_user_name", sa.String(length=64), "志愿者账号"),
    ("volunteer_wechat_id", sa.String(length=100), "志愿者微信"),
    ("data_officer_name", sa.String(length=100), "数据官姓名"),
    ("data_officer_user_name", sa.String(length=64), "数据官账号"),
    ("data_officer_wechat_id", sa.String(length=100), "数据官微信"),
    ("clock_in_count", sa.Integer(), "已打卡次数（破局 clockInCount）"),
    ("camp_days", sa.Integer(), "行动营总天数（破局 campDays）"),
]


def upgrade() -> None:
    """升级：students 表新增 17 个档案字段（全部可空）。"""
    for col_name, col_type, comment in _NEW_COLUMNS:
        op.add_column(
            "students",
            sa.Column(col_name, col_type, nullable=True, comment=comment),
        )


def downgrade() -> None:
    """降级：按反向顺序删除上述 17 列。"""
    for col_name, _col_type, _comment in reversed(_NEW_COLUMNS):
        op.drop_column("students", col_name)
