"""志愿者端 Schema：学员看板摘要、学员档案、待评改、评改生成/确认、同步结果。

对应技术方案 5.4、5.5、11.3。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.grading import GradeRecordOut
from app.schemas.student import CheckinRecordOut

# 学员状态：进行中 / 已达标 / 未达标
StudentStatus = Literal["ongoing", "qualified", "unqualified"]


class StudentSummary(BaseModel):
    """学员看板摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    camp_id: int
    nickname: str
    wechat: Optional[str] = None
    current_day: Optional[int] = Field(default=None, description="当前第几天")
    valid_days: int = Field(default=0, description="已有效打卡天数")
    gap_to_min: int = Field(
        ..., description="距最低完成天数差额(min_checkin_days - valid_days)，负值表示已超额"
    )
    last_stars: Optional[int] = Field(
        default=None, ge=1, le=3, description="最近一次评改星级"
    )
    status: StudentStatus
    last_synced_at: Optional[datetime] = None


class ArchiveTimelineItem(BaseModel):
    """档案时间线条目（单条打卡记录）。"""

    model_config = ConfigDict(from_attributes=True)

    checkin_id: int
    day_number: int
    checkin_date: date
    content: Optional[str] = None
    stars: Optional[int] = Field(default=None, ge=1, le=3)
    is_valid: bool = False
    grade_status: str
    synced_to_poju: bool = False


class ArchiveStats(BaseModel):
    """档案统计。"""

    total_checkins: int = Field(default=0, description="总打卡数")
    valid_days: int = Field(default=0, description="有效打卡天数")
    gap_to_min: int = Field(..., description="距最低完成天数差额")
    avg_stars: Optional[float] = Field(default=None, description="平均星级")
    status: StudentStatus


class StudentArchive(BaseModel):
    """学员档案（含统计+时间线）。"""

    model_config = ConfigDict(from_attributes=True)

    student: StudentSummary
    stats: ArchiveStats
    timeline: list[ArchiveTimelineItem] = Field(default_factory=list)


class PendingGradeOut(BaseModel):
    """待评改条目。"""

    model_config = ConfigDict(from_attributes=True)

    checkin_id: int
    student_id: int
    student_nickname: str
    camp_id: int
    day_number: int
    checkin_date: date
    content: Optional[str] = None
    images: Optional[list[dict[str, Any]]] = None
    submitted_at: Optional[datetime] = None


class GradeGenerateIn(BaseModel):
    """生成评改请求体。"""

    checkin_id: int


class GradeConfirmIn(BaseModel):
    """确认并同步评改请求体。"""

    checkin_id: int
    stars: int = Field(..., ge=1, le=3, description="最终星级 1-3")
    comment: Optional[str] = Field(default=None, description="评语(可由 AI 草稿修改)")


class GradeDraftOut(BaseModel):
    """AI 生成的评改草稿（含维度依据）。"""

    model_config = ConfigDict(from_attributes=True)

    checkin_id: int
    stars: int = Field(..., ge=1, le=3)
    comment: Optional[str] = None
    dimension_scores: Optional[list[dict[str, Any]]] = Field(
        default=None, description="维度得分依据 [{key,score,reason}]"
    )


class SyncResult(BaseModel):
    """同步破局结果。"""

    success: bool
    message: str
    synced_at: Optional[datetime] = Field(default=None, description="同步时间(成功时)")
