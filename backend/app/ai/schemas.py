"""AI 输出结构的 Pydantic 模型。

供 LLMClient 的 response_schema 参数使用：当传入这些模型时，
LLMClient 会强制结构化输出并用这些模型做 Pydantic 校验。
"""

from typing import List

from pydantic import BaseModel, Field


class DayTaskAI(BaseModel):
    """学习路线中单日任务的 AI 输出结构。"""

    day_number: int = Field(..., description="天数序号，从 1 开始", ge=1)
    title: str = Field(..., description="当日任务标题，简洁概括")
    description: str = Field(..., description="当日任务详细描述，可执行、有递进")
    tags: List[str] = Field(
        default_factory=list, description="当日任务标签列表，可为空"
    )


class RoutePlanAI(BaseModel):
    """学习路线规划的整体 AI 输出结构。

    注意：route_plan.txt 提示词要求 AI 输出 JSON 数组
    ``[{day_number, title, description, tags}]``。LLMClient 在结构化输出时
    会将该数组包装为本模型（即 ``{"tasks": [...]}``）以适配 Pydantic 校验，
    因此提示词中亦要求最终输出 ``{"tasks": [...]}`` 形态。
    """

    tasks: List[DayTaskAI] = Field(..., description="按天拆分的任务列表")


class CheckinDraftAI(BaseModel):
    """打卡内容生成的 AI 输出结构（四板块）。"""

    today_action: str = Field(..., description="今日行动：学员实际做了什么")
    today_gain: str = Field(..., description="今日收获：学员的感悟与所得")
    good_thing: str = Field(..., description="好事分享：值得记录的好事")
    next_step: str = Field(..., description="下一步行动：明日或后续计划")


class DimensionScore(BaseModel):
    """作业评改中单个维度的评分结构。"""

    key: str = Field(..., description="维度标识，与评分标准中的 key 对应")
    score: str = Field(..., description="该维度得分（可为星级或分值，字符串形式）")
    reason: str = Field(..., description="该维度得分理由")


class GradeDraftAI(BaseModel):
    """作业评改的 AI 输出结构。"""

    stars: int = Field(..., description="总体星级，1-3 星", ge=1, le=3)
    comment: str = Field(..., description="总体评语")
    dimension_scores: List[DimensionScore] = Field(
        ..., description="各维度评分明细"
    )
