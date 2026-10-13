"""应用、Uvicorn 和第三方库共用的标准 logging 配置。"""

import logging
from logging.config import dictConfig
from typing import Any

from app.config.settings import LoggingSettings


class NamespaceLevelFilter(logging.Filter):
    """也约束已自行设置级别的 logger，避免第三方 DEBUG 日志淹没输出。"""

    def __init__(self, app_level: str, third_party_level: str) -> None:
        super().__init__()
        levels = logging.getLevelNamesMapping() # 获取日志级别到数字的映射
        self.app_level = levels[app_level]
        self.third_party_level = levels[third_party_level]

    # 根据命名空间选择不同的过滤级别
    def filter(self, record: logging.LogRecord) -> bool:
        application = any(
            record.name == name or record.name.startswith(f"{name}.")
            for name in ("app", "uvicorn")
        )
        minimum = self.app_level if application else self.third_party_level
        return record.levelno >= minimum


def build_logging_config(settings: LoggingSettings) -> dict[str, Any]:
    """构建配置而不修改全局 logging；字典可直接交给 Uvicorn 子进程。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            "namespace_level": {
                "()": "app.config.logging.NamespaceLevelFilter",
                "app_level": settings.level,
                "third_party_level": settings.third_party_level,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler", # 终端打印
                "formatter": "default",
                "filters": ["namespace_level"],
                "stream": "ext://sys.stderr", #  终端打印
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.third_party_level,
        },
        "loggers": {
            # propagate: 是否传递给父级 logger
            "app": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn.error": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn.access": {
                "handlers": [],
                "level": settings.level,
                "propagate": settings.access_enabled,
            },
        },
    }


def configure_logging(settings: LoggingSettings) -> None:
    """只由启动入口调用；重复配置替换 handler，不叠加输出。"""
    dictConfig(build_logging_config(settings))
