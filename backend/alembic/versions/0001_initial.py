"""初始迁移：创建全部表 + 种子数据。

revision: 0001
revises:
create_date: 2026-06-27

基于 app/models 下的 ORM 模型手写 upgrade/downgrade（非 autogenerate），
确保 __tablename__ 与列定义与模型完全一致。

包含表：
- camps              行动营
- manuals            手册（camp_id 唯一）
- study_routes       学习路线（camp_id 唯一）
- day_tasks          每日任务
- students           学员（camp_id+poju_student_id 唯一）
- checkin_records    打卡评改记录
- grades             评改结果明细
- scoring_standards  评分标准（全局一套）
- poju_configs       破局接口配置（全局）

upgrade 末尾插入种子数据：
- scoring_standards：默认评分标准（PRD F5 / 技术方案 5.1 初版），is_active=True。
- poju_configs：空配置行，token_status='unknown'。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.types import JSON

# revision 标识
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 表结构定义（与模型 __tablename__ / 列严格对齐）
# ---------------------------------------------------------------------------

def _create_camps() -> None:
    """创建 camps 表。"""
    op.create_table(
        "camps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, comment="行动营名称"),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            comment="身份：student / volunteer",
        ),
        sa.Column("description", sa.Text(), nullable=True, comment="简介"),
        sa.Column("total_days", sa.Integer(), nullable=False, comment="总天数"),
        sa.Column("start_date", sa.Date(), nullable=False, comment="开始日期"),
        sa.Column("end_date", sa.Date(), nullable=False, comment="结束日期"),
        sa.Column(
            "min_checkin_days",
            sa.Integer(),
            nullable=False,
            comment="最低打卡完成天数（默认总天数×0.6，可改）",
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, comment="软删除标记"
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


def _create_manuals() -> None:
    """创建 manuals 表。"""
    op.create_table(
        "manuals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "camp_id",
            sa.Integer(),
            nullable=False,
            comment="所属行动营(唯一)",
        ),
        sa.Column("filename", sa.String(length=200), nullable=True, comment="原始文件名"),
        sa.Column(
            "file_path",
            sa.String(length=500),
            nullable=True,
            comment="本地存储路径 data/manuals/{camp_id}/",
        ),
        sa.Column(
            "content", sa.Text(), nullable=True, comment="手册全文（提取后存库，供 AI 读取）"
        ),
        sa.Column("word_count", sa.Integer(), nullable=True, comment="字数"),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True, comment="上传时间"),
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
        sa.UniqueConstraint("camp_id", name="uq_manuals_camp_id"),
        sa.ForeignKeyConstraint(["camp_id"], ["camps.id"]),
    )


def _create_study_routes() -> None:
    """创建 study_routes 表。"""
    op.create_table(
        "study_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "camp_id",
            sa.Integer(),
            nullable=False,
            comment="所属行动营(唯一)",
        ),
        sa.Column("generated_at", sa.DateTime(), nullable=True, comment="生成时间"),
        sa.Column(
            "source", sa.String(length=20), nullable=True, comment="来源：ai / manual"
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
        sa.UniqueConstraint("camp_id", name="uq_study_routes_camp_id"),
        sa.ForeignKeyConstraint(["camp_id"], ["camps.id"]),
    )


def _create_day_tasks() -> None:
    """创建 day_tasks 表。"""
    op.create_table(
        "day_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "route_id",
            sa.Integer(),
            nullable=False,
            comment="所属学习路线",
        ),
        sa.Column("day_number", sa.Integer(), nullable=False, comment="第几天(1~N)"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="任务标题"),
        sa.Column("description", sa.Text(), nullable=True, comment="任务描述"),
        sa.Column("tags", JSON(), nullable=True, comment="标签（手册章节/类型/时长）"),
        sa.Column(
            "is_completed", sa.Boolean(), nullable=False, comment="是否完成"
        ),
        sa.Column(
            "edited", sa.Boolean(), nullable=False, comment="是否被人工编辑过"
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
        sa.ForeignKeyConstraint(["route_id"], ["study_routes.id"]),
    )


def _create_students() -> None:
    """创建 students 表（含 (camp_id, poju_student_id) 唯一约束）。"""
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camp_id", sa.Integer(), nullable=False, comment="所属行动营"),
        sa.Column(
            "poju_student_id",
            sa.String(length=64),
            nullable=False,
            comment="破局平台学员唯一标识(接口返回)",
        ),
        sa.Column("nickname", sa.String(length=100), nullable=False, comment="昵称"),
        sa.Column("wechat", sa.String(length=100), nullable=True, comment="微信(拉群用)"),
        sa.Column(
            "last_synced_at", sa.DateTime(), nullable=True, comment="最近同步时间"
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
        sa.ForeignKeyConstraint(["camp_id"], ["camps.id"]),
        sa.UniqueConstraint(
            "camp_id", "poju_student_id", name="uq_student_camp_poju"
        ),
    )


def _create_checkin_records() -> None:
    """创建 checkin_records 表。"""
    op.create_table(
        "checkin_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False, comment="所属学员"),
        sa.Column(
            "camp_id",
            sa.Integer(),
            nullable=False,
            comment="所属行动营(冗余,便于按营查询)",
        ),
        sa.Column("day_number", sa.Integer(), nullable=False, comment="第几天打卡"),
        sa.Column("checkin_date", sa.Date(), nullable=False, comment="打卡日期"),
        sa.Column("content", sa.Text(), nullable=True, comment="学员打卡内容"),
        sa.Column(
            "images", JSON(), nullable=True, comment="图片信息(URL/路径,来自破局接口)"
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            nullable=True,
            comment="学员提交时间(破局接口返回)",
        ),
        sa.Column(
            "poju_checkin_id",
            sa.String(length=64),
            nullable=True,
            comment="破局打卡记录唯一标识",
        ),
        sa.Column(
            "grade_status",
            sa.String(length=20),
            nullable=False,
            comment="评改状态：pending/graded",
        ),
        sa.Column("stars", sa.Integer(), nullable=True, comment="评改星级 1-3"),
        sa.Column(
            "synced_to_poju",
            sa.Boolean(),
            nullable=False,
            comment="评改是否已同步破局",
        ),
        sa.Column("synced_at", sa.DateTime(), nullable=True, comment="同步时间"),
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
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["camp_id"], ["camps.id"]),
    )


def _create_grades() -> None:
    """创建 grades 表。"""
    op.create_table(
        "grades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "checkin_record_id",
            sa.Integer(),
            nullable=False,
            comment="关联打卡记录",
        ),
        sa.Column("stars", sa.Integer(), nullable=False, comment="星级 1-3"),
        sa.Column("comment", sa.Text(), nullable=True, comment="评语"),
        sa.Column(
            "dimension_scores",
            JSON(),
            nullable=True,
            comment="维度得分依据 [{key,score,reason}]",
        ),
        sa.Column(
            "ai_raw_output", sa.Text(), nullable=True, comment="AI 原始返回(调试用)"
        ),
        sa.Column(
            "source", sa.String(length=20), nullable=True, comment="来源：ai / manual"
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
        sa.ForeignKeyConstraint(["checkin_record_id"], ["checkin_records.id"]),
    )


def _create_scoring_standards() -> None:
    """创建 scoring_standards 表。"""
    op.create_table(
        "scoring_standards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            comment="是否当前生效(全局一套)",
        ),
        sa.Column(
            "dimensions",
            JSON(),
            nullable=True,
            comment="评分维度数组 [{key,name,desc,depends_archive}]",
        ),
        sa.Column(
            "star_rules",
            JSON(),
            nullable=True,
            comment="星级判定 {three,two,one} 描述",
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


def _create_poju_configs() -> None:
    """创建 poju_configs 表。"""
    op.create_table(
        "poju_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "token",
            sa.String(length=500),
            nullable=True,
            comment="Authorization Token(加密存储,加解密由service层处理)",
        ),
        sa.Column(
            "base_url", sa.String(length=200), nullable=True, comment="接口基础地址"
        ),
        sa.Column(
            "token_status",
            sa.String(length=20),
            nullable=False,
            comment="Token状态：valid/invalid/unknown",
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
# 种子数据
# ---------------------------------------------------------------------------

# 默认评分标准（PRD F5 / 技术方案 5.1 初版）
_DEFAULT_DIMENSIONS = [
    {
        "key": "completeness",
        "name": "完整度",
        "desc": "四个板块是否均填写、内容是否完整",
        "depends_archive": False,
    },
    {
        "key": "authenticity",
        "name": "行动真实性",
        "desc": "今日行动是否真实完成的具体行动，而非空泛套话",
        "depends_archive": False,
    },
    {
        "key": "depth",
        "name": "收获深度",
        "desc": "今日收获是否有具体感悟/思考，而非流水账",
        "depends_archive": False,
    },
    {
        "key": "progress",
        "name": "进步性",
        "desc": "相比该学员历史作业是否有进步/变化",
        "depends_archive": True,
    },
    {
        "key": "originality",
        "name": "原创性",
        "desc": "是否抄袭/重复本人之前作业或他人作业",
        "depends_archive": True,
    },
]

_DEFAULT_STAR_RULES = {
    "three": "优秀：各维度均达标，收获有深度，且有明显进步/亮点",
    "two": "良好：基本达标，内容完整真实，无抄袭",
    "one": "待改进：内容敷衍、不完整、套话、抄袭或重复之前作业",
}


def _insert_seed_data() -> None:
    """插入种子数据：默认评分标准 + 空 PojuConfig。"""
    now = datetime.now(timezone.utc)

    # 默认评分标准（全局唯一生效）
    op.bulk_insert(
        sa.table(
            "scoring_standards",
            sa.column("is_active", sa.Boolean),
            sa.column("dimensions", JSON),
            sa.column("star_rules", JSON),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "is_active": True,
                "dimensions": _DEFAULT_DIMENSIONS,
                "star_rules": _DEFAULT_STAR_RULES,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    # 空破局接口配置行：token_status='unknown'
    op.bulk_insert(
        sa.table(
            "poju_configs",
            sa.column("token", sa.String),
            sa.column("base_url", sa.String),
            sa.column("token_status", sa.String),
            sa.column("last_checked_at", sa.DateTime),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "token": None,
                "base_url": None,
                "token_status": "unknown",
                "last_checked_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """升级：创建全部表并插入种子数据。"""
    # 按外键依赖顺序建表（被依赖者先建）
    _create_camps()
    _create_manuals()
    _create_study_routes()
    _create_day_tasks()
    _create_students()
    _create_checkin_records()
    _create_grades()
    _create_scoring_standards()
    _create_poju_configs()

    # 种子数据
    _insert_seed_data()


def downgrade() -> None:
    """降级：按依赖逆序删表。"""
    op.drop_table("poju_configs")
    op.drop_table("scoring_standards")
    op.drop_table("grades")
    op.drop_table("checkin_records")
    op.drop_table("students")
    op.drop_table("day_tasks")
    op.drop_table("study_routes")
    op.drop_table("manuals")
    op.drop_table("camps")
