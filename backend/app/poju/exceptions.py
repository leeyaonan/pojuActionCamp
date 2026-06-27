"""破局接口异常 re-export。

异常统一定义在 app.core.exceptions（对齐技术方案 8.4 错误码），此处
re-export 便于 poju 模块内部与调用方就近导入，保持单一来源。
"""
from app.core.exceptions import (
    PojuApiError,
    PojuAuthError,
    PojuNetworkError,
    PojuNotAvailable,
    PojuException,
)

__all__ = [
    "PojuException",
    "PojuAuthError",
    "PojuApiError",
    "PojuNetworkError",
    "PojuNotAvailable",
]
