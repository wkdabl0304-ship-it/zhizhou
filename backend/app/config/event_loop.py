"""Web 与命令行的事件循环工厂，兼容 Windows 上的异步 psycopg。

通过可导入函数传给 Uvicorn，确保 reload 子进程也使用同一策略；
不修改已弃用的全局事件循环 policy，导入时不创建循环。
"""

import asyncio
import sys


def create_event_loop() -> asyncio.AbstractEventLoop:
    """创建当前平台可供 psycopg 使用的循环，由 Runner 或 Uvicorn 负责关闭。"""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
