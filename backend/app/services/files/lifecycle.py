"""文件服务生命周期：启动校验磁盘、回收遗留暂存并管理周期清理任务。"""

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

import anyio

from app.services.files.service import FileService
from app.storage.local import LocalFileStorage


@asynccontextmanager
async def open_file_service(database, root):
    """提供初始化完成的文件服务，退出时先停止清理任务再由外层关闭数据库。"""
    storage = LocalFileStorage(root)
    await storage.initialize()
    service = FileService(database, storage)
    await service.cleanup.run_once()
    task = asyncio.create_task(service.cleanup.run(), name="file-cleanup")
    try:
        yield service
    finally:
        with anyio.CancelScope(shield=True):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
