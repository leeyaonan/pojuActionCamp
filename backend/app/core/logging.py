"""日志配置模块。

结构化日志，按模块分 logger，输出到控制台 + data/logs/<启动日期>/<启动时间>.log。
关键操作（接口调用、AI 调用、定时任务）记录 INFO；异常记录 ERROR + 堆栈。
对齐技术方案 8.3。
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志根目录
LOG_DIR = Path("data/logs")

# 日志格式
_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(debug: bool = True) -> None:
    """初始化全局日志配置。

    - 控制台输出：INFO（debug=True 时为 DEBUG）。
    - 文件输出：data/logs/<启动日期 YYYY-MM-DD>/app-<启动时间 HH-MM-SS>.log，
      按大小轮转，保留备份；不同启动之间按日期分目录、按启动时间分文件。
    - 第三方库日志级别下调，避免噪声。
    """
    global _configured
    if _configured:
        return

    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    # 清理已有 handler，避免重复添加
    root.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # 文件 handler：以启动日期为子目录、启动时间为文件名，每次启动新建一个文件
    try:
        from datetime import datetime
        start_ts = datetime.now()
        day_dir = LOG_DIR / start_ts.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        log_file = day_dir / f"app-{start_ts.strftime('%H-%M-%S')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # 目录不可创建（如只读环境）时仅用控制台，不阻断启动
        root.warning("无法创建日志文件目录 %s，仅使用控制台日志", LOG_DIR)

    # 第三方库降噪
    for noisy in ("uvicorn", "uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not debug else logging.INFO)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取按模块命名的 logger。"""
    if not _configured:
        # 兜底：未显式调用 setup_logging 时也保证可用
        setup_logging(debug=os.getenv("DEBUG", "true").lower() in ("1", "true", "yes"))
    return logging.getLogger(name)
