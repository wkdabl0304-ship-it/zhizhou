"""Web 命令行入口：解析监听参数，将日志配置传给 Uvicorn 后启动服务。

在 backend 目录执行 python -m app；导入本模块不会自动启动服务器。
"""

import argparse
from collections.abc import Sequence

import uvicorn

from app.config.logging import build_logging_config
from app.config.settings import load_logging_settings


def main(argv: Sequence[str] | None = None) -> None:
    """解析启动参数并运行 Web 服务，阻塞直到服务退出。

    Args:
        argv: 参数序列；None 表示读取终端参数，测试可传列表避免依赖终端。

    Raises:
        SystemExit: 请求帮助或提供非法端口等参数时由 argparse 结束进程。
        ValueError: 日志环境变量无效时直接停止启动。
    """
    parser = argparse.ArgumentParser(description="启动知舟聊天 API")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="开发时自动重载代码")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须是 1–65535 之间的整数")

    settings = load_logging_settings()
    # 使用导入字符串而非 app 对象，使 reload 子进程能够重新加载应用。
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="app.config.event_loop:create_event_loop",
        log_config=build_logging_config(settings),
        access_log=settings.access_enabled,
    )


if __name__ == "__main__":
    main()
