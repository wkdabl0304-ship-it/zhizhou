"""先配置日志，再启动 Web 服务：python -m app。"""

import argparse
from collections.abc import Sequence

import uvicorn

from app.config.logging import build_logging_config
from app.config.settings import load_logging_settings


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="启动知舟聊天 API")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="开发时自动重载代码")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须是 1–65535 之间的整数")

    settings = load_logging_settings()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=build_logging_config(settings),
        access_log=settings.access_enabled,
    )


if __name__ == "__main__":
    main()
