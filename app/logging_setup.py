"""日志配置。

此前项目完全没有日志：行情三级降级的失败、备份恢复前的自动备份失败等异常
都被 `except Exception: pass` 静默吞掉，用户反馈"行情不准 / 备份失败"时
没有任何可排查的痕迹。这里统一配置一个滚动文件日志，写到 数据目录/logs/app.log。

用法::

    from app.logging_setup import setup_logging, get_logger

    setup_logging()                      # 程序启动时调用一次
    logger = get_logger(__name__)        # 各模块取自己的 logger
    logger.warning("降级到备用接口: %s", err, exc_info=True)
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.database import get_data_dir

_ROOT_LOGGER_NAME = "family_asset"
_MAX_BYTES = 1 * 1024 * 1024     # 单个日志文件上限 1MB
_BACKUP_COUNT = 3                # 保留最近 3 个滚动文件

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """配置日志（重复调用安全，只初始化一次）。

    - 始终写滚动文件：数据目录/logs/app.log；
    - 开发环境（非 frozen）额外输出到控制台，便于调试；
    - 日志目录不可写时静默跳过，绝不影响主程序启动。
    """
    global _configured
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    if _configured:
        return root

    root.setLevel(level)
    root.propagate = False       # 不向根 logger 冒泡，避免重复输出

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        log_dir = get_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "app.log", maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass                     # 日志不可用不应影响主程序

    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    """取模块级 logger（传 __name__ 即可）。"""
    return logging.getLogger(_ROOT_LOGGER_NAME).getChild(name)
