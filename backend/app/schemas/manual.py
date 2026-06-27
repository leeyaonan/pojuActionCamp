"""手册相关 Schema。

对应技术方案 4.2.2、5.6、11.4。
ManualPreview 用于列表/卡片预览，只取 content 头 N 字。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ManualOut(BaseModel):
    """手册元信息输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    camp_id: int
    filename: Optional[str] = Field(default=None, description="原始文件名")
    file_path: Optional[str] = Field(default=None, description="本地存储路径")
    content: Optional[str] = Field(default=None, description="手册全文")
    word_count: Optional[int] = Field(default=None, description="字数")
    uploaded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ManualPreview(BaseModel):
    """手册预览（content 头 N 字）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    camp_id: int
    filename: Optional[str] = None
    word_count: Optional[int] = None
    preview: str = Field(default="", description="手册全文前 N 字预览")
    uploaded_at: Optional[datetime] = None


class PasteIn(BaseModel):
    """粘贴手册文本请求体。"""

    content: str = Field(..., min_length=1, description="手册全文")
