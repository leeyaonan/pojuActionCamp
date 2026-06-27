"""通用响应模型。

对应技术方案 8.4 统一响应 {code,message,data}。
- ``ApiResponse[T]``：统一响应包装，data 为泛型。
- ``Paginated[T]``：分页响应。
- ``PageParams``：分页查询参数（供路由依赖注入）。
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装。"""

    code: int = Field(default=0, description="业务状态码：0 表示成功，非 0 见技术方案 8.4")
    message: str = Field(default="ok", description="提示信息")
    data: Optional[T] = Field(default=None, description="业务数据")


class Paginated(BaseModel, Generic[T]):
    """分页响应。"""

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(default=0, description="总条数")
    page: int = Field(default=1, description="当前页码(1 基)")
    page_size: int = Field(default=20, description="每页条数")
    total_pages: int = Field(default=0, description="总页数")


class PageParams(BaseModel):
    """分页查询参数。

    作为路由依赖项使用，从 query 参数解析。
    """

    model_config = ConfigDict(from_attributes=True)

    page: int = Field(default=1, ge=1, description="页码(1 基)")
    page_size: int = Field(default=20, ge=1, le=200, description="每页条数")

    @property
    def offset(self) -> int:
        """计算 SQL offset。"""
        return (self.page - 1) * self.page_size
