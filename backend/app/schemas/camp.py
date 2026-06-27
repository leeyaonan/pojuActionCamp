"""行动营相关 Schema。

对应技术方案 4.2.1、5.1、11.1。
状态(status)、当前天数(current_day)、有效天数(valid_days)等为运行期计算字段，不落库，
由 camp_service 在构造 CampSummary/CampOut 时填入。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["student", "volunteer"]
CampStatus = Literal["not_started", "ongoing", "ended"]


class CampBase(BaseModel):
    """行动营公共字段。"""

    name: str = Field(..., max_length=100, description="行动营名称")
    role: Role = Field(..., description="身份：student / volunteer")
    description: Optional[str] = Field(default=None, description="简介")
    total_days: int = Field(..., gt=0, description="总天数")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    min_checkin_days: int = Field(..., gt=0, description="最低打卡完成天数")

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date 不能早于 start_date")
        return v


class CampCreate(CampBase):
    """创建行动营请求体。"""

    @field_validator("min_checkin_days")
    @classmethod
    def _min_days_le_total(cls, v: int, info) -> int:
        total = info.data.get("total_days")
        if total and v > total:
            raise ValueError("min_checkin_days 不能大于 total_days")
        return v


class CampUpdate(BaseModel):
    """更新行动营请求体（部分更新，字段可选）。

    注意：role 创建后一般不可改；此处保留可选字段以兼容描述/天数等调整。
    """

    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    total_days: Optional[int] = Field(default=None, gt=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    min_checkin_days: Optional[int] = Field(default=None, gt=0)


class CampOut(CampBase):
    """行动营详情/完整输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: CampStatus = Field(..., description="运行期计算状态：not_started/ongoing/ended")
    current_day: Optional[int] = Field(
        default=None, description="当前第几天(未开始为 None)"
    )
    valid_days: int = Field(default=0, description="已有效打卡天数(stars>=2)")
    has_manual: bool = Field(default=False, description="是否已上传手册")
    has_route: bool = Field(default=False, description="是否已生成学习路线")
    created_at: datetime
    updated_at: datetime


class CampSummary(BaseModel):
    """行动营列表摘要（含状态/进度）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: Role
    total_days: int
    start_date: date
    end_date: date
    min_checkin_days: int
    status: CampStatus
    current_day: Optional[int] = None
    valid_days: int = 0
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度比例 current_day/total_days")
    created_at: datetime
