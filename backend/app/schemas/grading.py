"""评改结果明细 Schema。

对应技术方案 4.2.6、5.4。
GradeRecordOut 用于展示评改历史（AI 草稿 + 人工修改均在 grades 表留痕）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

GradeSource = Literal["ai", "manual"]


class DimensionScoreOut(BaseModel):
    """单维度得分依据。"""

    model_config = ConfigDict(from_attributes=True)

    key: str = Field(..., description="维度键")
    score: float = Field(..., description="维度得分")
    reason: Optional[str] = Field(default=None, description="维度评分理由")


class GradeRecordOut(BaseModel):
    """评改结果明细（grades 表一行）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    checkin_record_id: int
    stars: int = Field(..., ge=1, le=3, description="星级 1-3")
    comment: Optional[str] = Field(default=None, description="评语")
    dimension_scores: Optional[list[dict[str, Any]]] = Field(
        default=None, description="维度得分依据 [{key,score,reason}]"
    )
    source: Optional[GradeSource] = Field(default=None, description="来源：ai / manual")
    created_at: datetime
