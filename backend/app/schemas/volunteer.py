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
    """学员看板摘要。

    - 基础汇总字段：id / camp_id / nickname / wechat / current_day / valid_days /
      gap_to_min / last_stars / status / last_synced_at
    - 档案扩展字段（迁移 0004 起，从破局 query-people 拉取）：
      学员本人（full_name / wechat_id / phone / wechat_name / user_name /
      user_number）+ 组长（leader_*）+ 志愿者（volunteer_*）+ 数据官
      （data_officer_*）+ 打卡统计（clock_in_count / camp_days）。
    """

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

    # ====== 学员本人（破局 query-people）======
    full_name: Optional[str] = Field(default=None, description="姓名")
    wechat_id: Optional[str] = Field(default=None, description="微信号")
    phone: Optional[str] = Field(default=None, description="手机号")
    wechat_name: Optional[str] = Field(default=None, description="微信昵称")
    user_name: Optional[str] = Field(default=None, description="破局登录账号")
    user_number: Optional[str] = Field(default=None, description="破局编号")

    # ====== 组长 ======
    leader_name: Optional[str] = Field(default=None, description="组长姓名")
    leader_user_name: Optional[str] = Field(default=None, description="组长账号")
    leader_wechat_id: Optional[str] = Field(default=None, description="组长微信")

    # ====== 志愿者 ======
    volunteer_name: Optional[str] = Field(default=None, description="志愿者姓名")
    volunteer_user_name: Optional[str] = Field(default=None, description="志愿者账号")
    volunteer_wechat_id: Optional[str] = Field(default=None, description="志愿者微信")

    # ====== 数据官 ======
    data_officer_name: Optional[str] = Field(default=None, description="数据官姓名")
    data_officer_user_name: Optional[str] = Field(default=None, description="数据官账号")
    data_officer_wechat_id: Optional[str] = Field(default=None, description="数据官微信")

    # ====== 打卡统计 ======
    clock_in_count: Optional[int] = Field(default=None, description="已打卡次数（破局 clockInCount）")
    camp_days: Optional[int] = Field(default=None, description="行动营总天数（破局 campDays）")


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
    """同步破局结果。

    - success: 是否成功（业务异常时为 False，由 service 内部处理后返回）
    - message: 给前端展示的摘要文本
    - synced_at: 同步时间（成功时）
    - total_from_poju: 破局 total（本次同步从破局读到的总数）
    - synced_count: 本次处理/新增/覆盖的打卡记录条数
    - errors: 分页/附件失败明细（UI 可直接展示）
    """

    success: bool
    message: str
    synced_at: Optional[datetime] = Field(default=None, description="同步时间(成功时)")
    total_from_poju: int = Field(
        default=0,
        ge=0,
        description="破局 total（本次同步从破局读到的总记录数）",
    )
    synced_count: int = Field(
        default=0,
        ge=0,
        description="本次新增/更新的打卡记录条数",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="分页/附件失败明细（单页失败不阻断整体流程）",
    )


class InitResult(BaseModel):
    """初始化/刷新学员档案的结果。

    - imported：本次新增的 Student 行数
    - updated：本次更新已有 Student 的行数（按 (camp_id, poju_student_id) upsert）
    - total_from_poju：破局 query-people 接口返回的 total
    - pages_fetched：成功遍历的页数（含空页停页）
    - skipped：因 poju_student_id 缺失而跳过的条目数
    - errors：分页失败明细（UI 可直接展示）
    """

    success: bool
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    total_from_poju: int = 0
    pages_fetched: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str
    synced_at: Optional[datetime] = Field(default=None, description="同步时间(成功时)")


class ReminderItem(BaseModel):
    """单条待提醒学员信息（实时拉取破局，不落库）。

    数据来源：POST /server/volunteer/member-clock-in-status。
    remind_status 是状态机（NOT_REMINDED → REMINDING → REMINDED ...），
    这里透传字符串，由前端按需渲染，不锁枚举（前向兼容）。

    Attributes:
        user_number: 破局编号（userNumber），与 students.user_number 同义，
            用于反查本地 Student.id。
        student_id: 本地 Student.id（按 user_number 反查匹配），未匹配到为 None。
        wechat_name: 学员微信昵称。
        wechat_id: 微信号。
        clock_in_days: 当前打卡天数（破局 clockInDays）。
        rest_days: 可休息天数（破局 restDays）。
        remind_status: 提醒状态原始字符串（如 NOT_REMINDED）。
        is_done: 志愿者是否已提醒（isDone=true）。
    """

    user_number: str = Field(..., description="破局编号（userNumber）")
    student_id: Optional[int] = Field(
        default=None, description="本地 Student.id（按 user_number 匹配）"
    )
    wechat_name: Optional[str] = None
    wechat_id: Optional[str] = None
    clock_in_days: int = Field(default=0, ge=0, description="当前打卡天数")
    rest_days: int = Field(default=0, ge=0, description="可休息天数")
    remind_status: str = Field(
        default="UNKNOWN", description="破局原始状态字符串（透传，不锁枚举）"
    )
    is_done: bool = Field(default=False, description="志愿者是否已提醒")
