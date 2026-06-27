"""统一响应封装。

统一响应格式 {code, message, data}（对齐技术方案 8.4）：
- success(data, message="ok"): 构造成功响应。
- error(code, message, http_status): 构造错误响应（通常由异常处理器调用）。
- ApiResponse[T]: 泛型响应模型，供路由层声明返回类型与 OpenAPI 文档使用。

另提供响应中间件，将未包裹的 dict/列表统一包成成功响应。
"""
from __future__ import annotations

import json
from typing import Any, Generic, TypeVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应模型。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """构造成功响应体（code=0）。"""
    return {"code": 0, "message": message, "data": data}


def error(code: int, message: str, http_status: int = 400) -> JSONResponse:
    """构造错误响应（HTTP 状态码与业务错误码分离）。"""
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": None},
    )


async def response_wrap_middleware(request: Request, call_next: Any) -> Response:
    """响应包裹中间件。

    将业务路由直接返回的 dict / list 自动包成统一成功响应 {code:0, message:'ok', data}。
    - 已经是统一格式（含 code 字段）的 dict 不再二次包裹。
    - JSONResponse / 非 2xx 响应原样透传（异常处理器已构造好统一格式）。
    - 非字典/列表的 JSON 响应也包裹一层。
    """
    response: Response = await call_next(request)

    # 仅处理 2xx 且为 JSON 的响应；其它（异常/重定向等）原样返回
    if not (200 <= response.status_code < 300):
        return response

    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

    # 仅处理普通 JSONResponse（含 .body）；StreamingResponse 等无 .body 属性，直接透传
    if not hasattr(response, "body"):
        return response

    # 复用底层 body
    try:
        body = response.body
        if not body:
            return response
        parsed = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return response

    # 已是统一格式则透传
    if isinstance(parsed, dict) and "code" in parsed and "message" in parsed:
        return response

    # 包裹为统一成功响应
    wrapped = {"code": 0, "message": "ok", "data": parsed}
    return JSONResponse(status_code=200, content=wrapped)
