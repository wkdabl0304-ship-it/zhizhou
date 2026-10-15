"""后端业务配置和日志配置的统一读取、校验入口。

两类配置共享环境读取规则，但可独立加载，使业务启动失败也能有日志。
仅在调用加载函数时读取仓库根目录 .env，模块导入不改变进程环境。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    """校验后的业务配置快照；冻结字段，避免运行中被随意修改。"""

    # repr=False 防止调试打印配置对象时直接暴露密钥或数据库密码。
    deepseek_api_key: str = field(repr=False)
    postgres_user: str
    postgres_password: str = field(repr=False)
    postgres_db: str
    postgres_port: int
    postgres_host: str = "127.0.0.1"
    model_name: str = "deepseek-flash"
    model_base_url: str = "https://api.deepseek.com"


@dataclass(frozen=True)
class LoggingSettings:
    """日志级别和访问日志开关；不依赖模型密钥或数据库连接。"""

    level: str = "INFO"
    third_party_level: str = "WARNING"
    access_enabled: bool = True


def _read_environment(env_path: Path | None = None) -> dict[str, str | None]:
    """合并文件与系统环境，返回配置键到原始字符串或 None 的映射。

    env_path 可在测试时指定；默认路径相对于本文件推导，不依赖工作目录。
    系统环境在合并时覆盖文件，即使覆盖值为空也保留，交由调用方校验。
    dotenv_values 只读取文件，不像 load_dotenv 那样写入 os.environ。
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parents[3] / ".env"
    return {**dotenv_values(env_path), **os.environ}


def load_logging_settings(env_path: Path | None = None) -> LoggingSettings:
    """读取并返回标准化的 LoggingSettings，无需完整的业务配置。

    日志级别转为大写，布尔开关接受 true/false 和 1/0。
    只有未提供的键使用默认值；显式空值或非法值抛出包含键名的 ValueError。
    env_path 的路径选择与环境优先级沿用统一读取函数。
    """
    values = _read_environment(env_path)
    levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def level(name: str, default: str) -> str:
        """读取 name 对应的日志级别；缺省用 default，非法时抛出 ValueError。"""
        value = (values.get(name, default) or "").strip().upper()
        if value not in levels:
            raise ValueError(f"{name} 必须是 DEBUG、INFO、WARNING、ERROR、CRITICAL 之一")
        return value

    enabled = (values.get("LOG_ACCESS_ENABLED", "true") or "").strip().lower()
    if enabled not in {"true", "false", "1", "0"}:
        raise ValueError("LOG_ACCESS_ENABLED 必须是 true、false、1 或 0")
    return LoggingSettings(
        level=level("LOG_LEVEL", "INFO"),
        third_party_level=level("LOG_THIRD_PARTY_LEVEL", "WARNING"),
        access_enabled=enabled in {"true", "1"},
    )


def load_settings(env_path: Path | None = None) -> Settings:
    """读取并校验业务配置，返回供模型和数据库工厂使用的 Settings。

    env_path 可覆盖默认环境文件。密钥、数据库用户、密码、库名和端口
    均须非空；端口须在 1–65535 范围内，否则抛出 ValueError。
    错误只指出配置项或约束，不把密钥等原始值拼接到错误消息中。
    """
    values = _read_environment(env_path)
    required = (
        "DEEPSEEK_API_KEY",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
    )
    missing = [name for name in required if not (values.get(name) or "").strip()]
    # 一次列出缺失项，方便开发者完整补齐配置后再尝试启动。
    if missing:
        raise ValueError(f"缺少配置项：{', '.join(missing)}")

    try:
        port = int(values["POSTGRES_PORT"])
    except ValueError:
        raise ValueError("POSTGRES_PORT 必须是 1–65535 之间的整数") from None
    if not 1 <= port <= 65535:
        raise ValueError("POSTGRES_PORT 必须是 1–65535 之间的整数")

    return Settings(
        deepseek_api_key=values["DEEPSEEK_API_KEY"],
        postgres_user=values["POSTGRES_USER"],
        postgres_password=values["POSTGRES_PASSWORD"],
        postgres_db=values["POSTGRES_DB"],
        postgres_port=port,
    )
