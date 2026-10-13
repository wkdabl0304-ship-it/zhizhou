"""后端配置：只在显式调用时读取环境变量和 .env。"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
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
    level: str = "INFO"
    third_party_level: str = "WARNING"
    access_enabled: bool = True


def _read_environment(env_path: Path | None = None) -> dict[str, str | None]:
    """读取仓库根目录 .env；系统环境变量优先，不修改进程环境。"""
    if env_path is None:
        env_path = Path(__file__).resolve().parents[3] / ".env"
    return {**dotenv_values(env_path), **os.environ}


def load_logging_settings(env_path: Path | None = None) -> LoggingSettings:
    """独立加载日志配置，不依赖模型或数据库配置。"""
    values = _read_environment(env_path)
    levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def level(name: str, default: str) -> str:
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
    """显式加载业务配置，沿用统一的环境读取规则。"""
    values = _read_environment(env_path)
    required = (
        "DEEPSEEK_API_KEY",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
    )
    missing = [name for name in required if not (values.get(name) or "").strip()]
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
