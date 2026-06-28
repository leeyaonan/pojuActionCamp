"""学员端 Schema：学习路线、每日任务、今日任务、打卡生成/提交/记录。

对应技术方案 4.2.3、4.2.5、5.2、5.3、11.2。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# 提交方式：自动调破局接口 / 手动复制
SubmitMethod = Literal["auto", "manual"]
# 同步状态：未同步 / 已同步 / 同步失败 / 手动模式不适用
SyncStatus = Literal["pending", "synced", "failed", "manual"]
# 评改状态
GradeStatus = Literal["pending", "graded"]


# ---------------- 学习路线与每日任务 ----------------

class DayTaskOut(BaseModel):
    """每日任务输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    day_number: int = Field(..., ge=1, description="第几天(1~N)")
    title: str
    description: Optional[str] = None
    tags: Optional[list[str]] = Field(
        default=None, description="标签(章节名/类型/时长等，字符串列表)"
    )
    is_completed: bool = False
    edited: bool = Field(default=False, description="是否被人工编辑过")
    created_at: datetime
    updated_at: datetime


class RouteOut(BaseModel):
    """学习路线输出（含每日任务列表）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    camp_id: int
    generated_at: Optional[datetime] = None
    source: Optional[str] = Field(default=None, description="来源：ai / manual")
    tasks: list[DayTaskOut] = Field(default_factory=list, description="每日任务列表(按 day_number 排序)")
    created_at: datetime
    updated_at: datetime


class DayTaskUpdate(BaseModel):
    """编辑每日任务请求体（部分更新）。"""

    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class RouteRegenerateIn(BaseModel):
    """重新规划学习路线请求体。"""

    keep_edits: bool = Field(
        default=True,
        description="true: 保留人工编辑过的任务(edited=true)，仅重生成未编辑部分；false: 全量覆盖",
    )


class TodayOut(BaseModel):
    """今日任务+进度。"""

    day_number: Optional[int] = Field(
        default=None, ge=1, description="今日第几天(营未开始/已结束为 None)"
    )
    task: Optional[DayTaskOut] = Field(default=None, description="今日任务(无则为 None)")
    progress: float = Field(
        default=0.0, ge=0.0, le=1.0, description="整体进度 current_day/total_days"
    )


# ---------------- 打卡生成与提交 ----------------

class CheckinGenerateIn(BaseModel):
    """生成打卡内容请求体。"""

    text: str = Field(..., min_length=1, description="学员所做/输入文字")
    images: Optional[list[str]] = Field(
        default=None, description="图片信息列表(URL/路径,来自破局接口)"
    )


class CheckinDraftOut(BaseModel):
    """AI 生成的打卡草稿（四板块）。

    不入库，由前端展示并可编辑后提交。
    """

    today_action: str = Field(..., description="今日行动")
    today_gain: str = Field(..., description="今日收获")
    good_thing: str = Field(..., description="今日好事")
    next_step: str = Field(..., description="下一步")


class CheckinSubmitIn(BaseModel):
    """提交打卡请求体。"""

    content: str = Field(..., min_length=1, description="最终打卡内容(四板块拼装)")
    auto: bool = Field(default=False, description="是否自动调用破局接口提交")


class CheckinSubmitResult(BaseModel):
    """打卡提交结果。"""

    submitted: bool = Field(..., description="是否已记录入库")
    method: SubmitMethod = Field(..., description="提交方式：auto / manual")
    sync_status: SyncStatus = Field(..., description="同步状态")
    poju_checkin_id: Optional[str] = Field(
        default=None, description="破局打卡记录唯一标识(自动提交成功时返回)"
    )
    degraded: bool = Field(
        default=False,
        description="True 表示 auto=true 但破局同步降级为 manual（修复 BUG-STU-008）",
    )


class CheckinRecordOut(BaseModel):
    """打卡评改记录输出（即学员档案条目）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    camp_id: int
    day_number: int
    checkin_date: date
    content: Optional[str] = None
    images: Optional[list[dict[str, Any]]] = None
    submitted_at: Optional[datetime] = None
    poju_checkin_id: Optional[str] = None
    grade_status: GradeStatus
    stars: Optional[int] = Field(default=None, ge=1, le=3, description="评改星级 1-3")
    is_valid: bool = Field(default=False, description="是否有效打卡(stars>=2)")
    synced_to_poju: bool = False
    synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
