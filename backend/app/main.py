"""FastAPI 应用入口。

职责：
- 创建 FastAPI 应用。
- 配置 CORS（允许 localhost:5173）。
- 注册全局异常处理器、统一响应中间件。
- 挂载 /api 路由。
- lifespan 启动时尝试初始化调度器（失败仅告警，不阻断启动）。
- 提供 GET /api/health 健康检查。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.response import response_wrap_middleware, success


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化日志与调度器，关闭时清理。"""
    settings: Settings = get_settings()
    setup_logging(debug=settings.debug)
    logger = logging.getLogger("app.main")
    logger.info("应用启动: %s", settings.app_name)

    # 尝试初始化调度器；失败仅告警，不阻断后端启动
    try:
        from app.scheduler.scheduler import init_scheduler

        init_scheduler(settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("调度器初始化失败（忽略，后端继续运行）: %s", exc)

    yield

    # 关闭调度器（若已启动）
    try:
        import app.scheduler.scheduler as _sched_mod

        if _sched_mod.scheduler is not None and _sched_mod.scheduler.running:
            _sched_mod.scheduler.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("调度器关闭失败（忽略）: %s", exc)

    logger.info("应用关闭")


def create_app() -> FastAPI:
    """构造 FastAPI 应用。"""
    settings = get_settings()
    app = FastAPI(
        title="破局行动营管理平台",
        description="AI破局行动营自动化管理平台 MVP",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS：允许前端开发地址 localhost:5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 统一响应包裹中间件：dict/list 自动包成 {code,message,data}
    app.middleware("http")(response_wrap_middleware)

    # 全局异常处理器
    register_exception_handlers(app)

    # 路由
    app.include_router(api_router)

    # 健康检查
    @app.get("/api/health", tags=["system"])
    async def health() -> dict:
        """健康检查，返回统一成功响应。"""
        return success({"status": "ok"})

    return app


app = create_app()
