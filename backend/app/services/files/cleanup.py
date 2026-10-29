"""文件清理服务：以数据库状态为队列，跨进程跳过正在传输的原文件。"""

import asyncio
import logging

from sqlalchemy import select

from app.models import FileBlob

logger = logging.getLogger(__name__)


class FileCleanup:
    """回收失去上传锁的暂存原件和逻辑删除原件，失败保留状态以便重试。"""

    def __init__(self, database, storage, locks):
        """绑定数据库、磁盘及锁，不在构造时启动任务。"""
        self.database = database
        self.storage = storage
        self.locks = locks

    async def run_once(self):
        """扫描当前待清理记录并幂等清理，持锁后重新确认状态以避免误删已发布文件。"""
        async with self.database.sessions() as session:
            ids = (await session.scalars(select(FileBlob.id).where(FileBlob.state.in_(["staging", "delete_pending"])))).all()
        for blob_id in ids:
            try:
                async with self.locks.hold(blob_id, wait=False) as acquired:
                    if not acquired:
                        continue
                    async with self.database.sessions.begin() as session:
                        blob = await session.get(FileBlob, blob_id)
                        if blob is None or blob.state not in {"staging", "delete_pending"}:
                            continue
                        await self.storage.remove(blob.storage_key)
                        blob.state = "purged"
            except Exception:
                logger.exception("原文件清理失败 blob_id=%s", blob_id)

    async def run(self):
        """每 60 秒重试一次清理，扫描故障不会终止后续扫描，取消由应用生命周期负责。"""
        while True:
            await asyncio.sleep(60)
            try:
                await self.run_once()
            except Exception:
                logger.exception("文件清理扫描失败")
