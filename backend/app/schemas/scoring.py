"""评分标准 Schema。

对应技术方案 4.2.7、5.7、11.5。
维度与星级规则以结构化 JSON 存储，便于前端编辑与 AI 提示词渲染。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Dimension(BaseModel):
    """评分维度。"""

    key: str = Field(..., description="维度键(唯一)")
    name: str = Field(..., description="维度名称")
    desc: str = Field(..., description="维度描述")
    depends_archive: bool = Field(
        default=False,
        description="是否依赖学员历史档案(checkin_records)作为评分依据",
    )


class StarRules(BaseModel):
    """星级判定规则描述。"""

    three: str = Field(..., description="三星判定描述")
    two: str = Field(..., description="二星判定描述")
    one: str = Field(..., description="一星判定描述")


class ScoringOut(BaseModel):
    """评分标准输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dimensions: list[Dimension] = Field(default_factory=list, description="评分维度数组")
    star_rules: Optional[StarRules] = Field(default=None, description="星级判定规则")
    is_active: bool = Field(..., description="是否当前生效(全局一套)")
    created_at: datetime
    updated_at: datetime


class ScoringUpdate(BaseModel):
    """更新评分标准请求体。"""

    dimensions: list[Dimension] = Field(..., description="评分维度数组")
    star_rules: StarRules = Field(..., description="星级判定规则")
