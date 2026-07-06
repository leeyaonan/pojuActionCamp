"""学员模型（students 表）。

对应技术方案 4.2.4。志愿者身份下，从破局平台拉取的学员对齐到本地，
通过 (camp_id, poju_student_id) 唯一约束跨多次拉取对齐同一学员。

档案字段（迁移 0004 起扩展）：
- 现有最小字段：camp_id / poju_student_id / nickname / wechat / last_synced_at
  （保留最小同步语义，向后兼容）
- 档案全字段（query-people 接口）：full_name / wechat_id / phone / wechat_name /
  user_name / user_number / leader_name / leader_user_name / leader_wechat_id /
  volunteer_name / volunteer_user_name / volunteer_wechat_id / data_officer_*
  / clock_in_count / camp_days
- 唯一约束不变：``(camp_id, poju_student_id)``（poju_student_id 实为破局 user UUID）
- 学员档案数据与 checkin_records 表解耦：本表写入不影响打卡记录。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.camp import Camp
    from app.models.checkin import CheckinRecord


class Student(Base):
    """学员（志愿者带教场景下从破局平台拉取）。"""

    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("camp_id", "poju_student_id", name="uq_student_camp_poju"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camp_id: Mapped[int] = mapped_column(
        ForeignKey("camps.id"), nullable=False, comment="所属行动营"
    )
    # poju_student_id 在本表中实际存放破局 user UUID（query-people records[].id），
    # 字段名保留历史命名以避免改动下游 SQL；长度提到 64 与 Camp.poju_action_id 对齐。
    poju_student_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="破局平台学员唯一标识（query-people records[].id，UUID 字符串）"
    )
    # 最小字段（历史同步路径仍使用）
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, comment="昵称（与 full_name 同步）")
    wechat: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信（与 wechat_id 同步）"
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近同步时间"
    )

    # ====== 迁移 0004 起新增档案字段（query-people 全字段）======
    # 学员本人
    full_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="姓名（破局 fullName）"
    )
    wechat_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信号（破局 wechatId）"
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="手机号"
    )
    wechat_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信昵称（破局 wechatName）"
    )
    user_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="破局登录账号（数字字符串）"
    )
    user_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="破局编号"
    )
    # 组长
    leader_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="组长姓名"
    )
    leader_user_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="组长账号"
    )
    leader_wechat_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="组长微信"
    )
    # 志愿者
    volunteer_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="志愿者姓名"
    )
    volunteer_user_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="志愿者账号"
    )
    volunteer_wechat_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="志愿者微信"
    )
    # 数据官
    data_officer_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="数据官姓名"
    )
    data_officer_user_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="数据官账号"
    )
    data_officer_wechat_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="数据官微信"
    )
    # 打卡统计
    clock_in_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="已打卡次数（破局 clockInCount）"
    )
    camp_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="行动营总天数（破局 campDays）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间(UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间(UTC)",
    )

    camp: Mapped["Camp"] = relationship("Camp", back_populates="students")
    checkin_records: Mapped[list["CheckinRecord"]] = relationship(
        "CheckinRecord", back_populates="student", cascade="all, delete-orphan"
    )
