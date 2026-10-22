"""应用、Uvicorn 和第三方库共用的标准 logging 配置。

构建配置与应用配置分离：Web 入口可将字典交给 Uvicorn，命令行和
应用生命周期可显式初始化。业务模块只获取 logger，不自行添加 handler。
"""

import logging
from logging.config import dictConfig
from typing import Any

from app.core.settings import LoggingSettings


class NamespaceLevelFilter(logging.Filter):
    """也约束已自行设置级别的 logger，避免第三方 DEBUG 日志淹没输出。"""

    def __init__(self, app_level: str, third_party_level: str) -> None:
        """初始化应用日志与第三方日志各自的最低输出级别。

        app_level 和 third_party_level 须已通过配置校验；将级别名转换为
        数值缓存，供 filter 判断每条记录是否允许输出。
        """
        super().__init__()
        levels = logging.getLevelNamesMapping() # 获取日志级别到数字的映射
        self.app_level = levels[app_level]
        self.third_party_level = levels[third_party_level]

    # 根据命名空间选择不同的过滤级别
    def filter(self, record: logging.LogRecord) -> bool:
        """判断一条日志是否达到所属类别的输出级别。

        返回 True 时允许 handler 输出 record，否则过滤该条记录。
        app、uvicorn 及其子 logger 使用应用级别，其余使用第三方级别。
        handler 上的过滤还能约束自行设置过级别的子 logger。
        """
        application = any(
            record.name == name or record.name.startswith(f"{name}.")
            for name in ("app", "uvicorn")
        )
        minimum = self.app_level if application else self.third_party_level
        return record.levelno >= minimum


def build_logging_config(settings: LoggingSettings) -> dict[str, Any]:
    """生成应用、Uvicorn 和第三方库共用的日志配置。

    根据 settings 返回可供 dictConfig 使用的字典，不修改全局日志状态；
    字典使用可导入的类路径，能够传给 Windows spawn/reload 子进程。
    所有受管日志传播到根 logger 的单个 stderr handler，避免重复输出。
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        # 文本格式不读取聊天内容或密钥，只显示主动传给 logger 的消息。
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            "namespace_level": {
                "()": "app.core.logging.NamespaceLevelFilter",
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
            # 未显式配置的库默认继承第三方级别。
            "handlers": ["console"],
            "level": settings.third_party_level,
        },
        "loggers": {
            # propagate: 是否传递给父级 logger
            "app": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn.error": {"handlers": [], "level": settings.level, "propagate": True},
            "uvicorn.access": {
                # 自身没有 handler；关闭传播即可关闭访问日志。
                "handlers": [],
                "level": settings.level,
                "propagate": settings.access_enabled,
            },
        },
    }


def configure_logging(settings: LoggingSettings) -> None:
    """启用当前进程统一的日志格式、输出级别和访问日志开关。

    使用 settings 构造并应用 dictConfig，会修改进程全局的 logging 配置。
    只由启动入口或 lifespan 调用；dictConfig 替换受管 handler，
    因此为兼容启动方式而重复初始化时，不会叠加同一日志的输出次数。
    """
    dictConfig(build_logging_config(settings))
