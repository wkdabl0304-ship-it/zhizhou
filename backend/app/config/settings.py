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


def load_settings(env_path: Path | None = None) -> Settings:
    """读取 backend/.env；系统环境变量优先，不修改进程环境。"""
    if env_path is None:
        env_path = Path(__file__).resolve().parents[3] / ".env"
    values = {**dotenv_values(env_path), **os.environ}
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
