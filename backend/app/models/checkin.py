"""打卡评改记录模型（checkin_records 表）。

对应技术方案 4.2.5。此表既是学员档案数据来源，也记录每次打卡与评改状态。
`is_valid`（是否有效打卡 = stars>=2）为计算字段，不落库，由 @property 动态计算。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

if TYPE_CHECKING:
    from app.models.camp import Camp
    from app.models.grade import Grade
    from app.models.student import Student


class CheckinRecord(Base):
    """打卡评改记录（即学员档案条目）。"""

    __tablename__ = "checkin_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False, comment="所属学员"
    )
    camp_id: Mapped[int] = mapped_column(
        ForeignKey("camps.id"), nullable=False, comment="所属行动营(冗余,便于按营查询)"
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="第几天打卡")
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False, comment="打卡日期")
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="学员打卡内容"
    )
    images: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, comment="图片信息(URL/路径,来自破局接口)"
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="学员提交时间(破局接口返回)"
    )
    poju_checkin_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="破局打卡记录唯一标识"
    )
    grade_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, comment="评改状态：pending/graded"
    )
    stars: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="评改星级 1-3"
    )
    synced_to_poju: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="评改是否已同步破局"
    )
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="同步时间"
    )

    # ====== 迁移 0007：破局 clock-in 接口扩展字段 ======
    sign_up_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="报名记录 ID（破局 signUpId）"
    )
    user_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="破局登录账号（userName）"
    )
    user_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="破局编号（userNumber）"
    )
    wechat_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信号（wechatId）"
    )
    wechat_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="微信昵称（wechatName）"
    )
    avatar: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="学员头像 URL"
    )
    today_action: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="今日实操（todayAction）"
    )
    today_achievement: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="今日成果（todayAchievement）"
    )
    good_things_share: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="好事分享（goodThingsShare）"
    )
    next_action: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="下一步行动（nextAction）"
    )
    poju_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="破局原始 score：0=未评改/1-3=星级"
    )
    volunteer_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="志愿者姓名（volunteerName）"
    )
    images_ref: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="附件 groupCode（破局原值，单 UUID）"
    )
    images_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, comment="附件列表 [{fileName,fileUrl,fileSize,fileMd5,suffix}]"
    )
    submitted_at_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="提交时间原始毫秒时间戳（排错用）"
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

    # 关系
    student: Mapped["Student"] = relationship("Student", back_populates="checkin_records")
    camp: Mapped["Camp"] = relationship("Camp")
    grades: Mapped[list["Grade"]] = relationship(
        "Grade", back_populates="checkin_record", cascade="all, delete-orphan"
    )

    @property
    def is_valid(self) -> bool:
        """是否有效打卡：评改星级 >= 2（PRD BR-G-2）。计算字段，不落库。"""
        return self.stars is not None and self.stars >= 2
