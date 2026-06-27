"""API 路由聚合。

api_router 挂在 /api 前缀下，include 各子路由（camps/student/volunteer/
manual/scoring/settings）。每个 include 用 try/except 包裹，
子路由未实现或导入失败时不影响整体启动。
"""
from fastapi import APIRouter

api_router = APIRouter(prefix="/api")


def _safe_include(router: APIRouter, module: str, prefix: str) -> None:
    """安全挂载子路由：导入失败时仅记录，不阻断启动。"""
    try:
        import importlib

        mod = importlib.import_module(module)
        sub_router: APIRouter | None = getattr(mod, "router", None)
        if sub_router is None:
            return
        router.include_router(sub_router, prefix=prefix)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "子路由 %s 挂载失败（可能尚未实现）: %s", module, exc
        )


# 各子路由挂载，前缀对齐技术方案 11.x
_safe_include(api_router, "app.api.camps", "/camps")
_safe_include(api_router, "app.api.student", "/student")
_safe_include(api_router, "app.api.volunteer", "/volunteer")
_safe_include(api_router, "app.api.manual", "/manuals")
_safe_include(api_router, "app.api.scoring", "/scoring")
_safe_include(api_router, "app.api.settings", "/settings")
