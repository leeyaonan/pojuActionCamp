"""业务异常体系与全局异常处理器。

异常体系对齐技术方案 7.3 与 8.4：
- 破局接口异常：PojuAuthError / PojuApiError / PojuNetworkError / PojuNotAvailable
- 大模型异常：LLMError
- 通用异常：NotFoundError / ValidationError / ManualNotFoundError

register_exception_handlers 将上述异常及 RequestValidationError 映射为
统一 JSON 响应 {code, message, data: null}，错误码见 8.4。

注意：app.ai.llm_client 另有同名的 LLMError（AI 层抛出）。
此处 LLMError 为基础设施层定义，二者模块路径不同，互不冲突；
若 AI 层需要复用全局错误码，可在 ai 模块内 from app.core.exceptions import LLMError。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 基础异常
# ---------------------------------------------------------------------------


class AppException(Exception):
    """所有业务异常基类。

    Attributes:
        code: 业务错误码（见技术方案 8.4）。
        message: 面向用户的错误信息。
        http_status: 对应 HTTP 状态码。
    """

    code: int = 5000
    message: str = "服务器内部错误"
    http_status: int = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        code: int | None = None,
        http_status: int | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# 通用业务异常
# ---------------------------------------------------------------------------


class ValidationError(AppException):
    """参数校验失败（业务侧）。"""

    code = 1001
    message = "参数校验失败"
    http_status = 400


class NotFoundError(AppException):
    """资源不存在。"""

    code = 1002
    message = "资源不存在"
    http_status = 404


class ManualNotFoundError(AppException):
    """手册未配置（降级提示，对应技术方案 8.4 错误码 3002）。"""

    code = 3002
    message = "手册未配置"
    http_status = 503


# ---------------------------------------------------------------------------
# 大模型异常
# ---------------------------------------------------------------------------


class LLMError(AppException):
    """大模型调用失败（对应技术方案 8.4 错误码 3001）。"""

    code = 3001
    message = "大模型调用失败"
    http_status = 502


# ---------------------------------------------------------------------------
# 破局接口异常（对齐技术方案 7.3）
# ---------------------------------------------------------------------------


class PojuException(AppException):
    """破局接口异常基类。"""

    code = 2002
    message = "破局接口不可用/网络错误"
    http_status = 502


class PojuAuthError(PojuException):
    """破局 Token 失效（401/403）。对应错误码 2001。"""

    code = 2001
    message = "破局 Token 失效"
    http_status = 401


class PojuApiError(PojuException):
    """破局接口业务错误。对应错误码 2002。"""

    code = 2002
    message = "破局接口业务错误"
    http_status = 502


class PojuNetworkError(PojuException):
    """破局接口网络超时。对应错误码 2002。"""

    code = 2002
    message = "破局接口网络错误"
    http_status = 502


class PojuNotAvailable(PojuException):
    """破局接口 pending/未开放（降级）。对应错误码 2003。"""

    code = 2003
    message = "破局接口待确认（pending）"
    http_status = 503


# ---------------------------------------------------------------------------
# 异常处理器
# ---------------------------------------------------------------------------


def _error_body(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造统一错误响应体。"""
    return {"code": code, "message": message, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，统一映射为 {code, message, data: null}。"""

    @app.exception_handler(AppException)
    async def _handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        # 内部错误记 ERROR，业务异常记 WARNING
        if exc.code == 5000:
            logger.exception("服务器内部错误: %s", exc.message)
        else:
            logger.warning("业务异常 code=%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, None),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """FastAPI 请求参数校验失败，映射为错误码 1001。"""
        logger.warning("请求参数校验失败: %s", exc.errors())
        return JSONResponse(
            status_code=400,
            content=_error_body(1001, "参数校验失败", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        """兜底：未捕获异常映射为 5000。"""
        logger.exception("未捕获异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body(5000, "服务器内部错误", None),
        )
