"""本地磁盘原文件适配：受控存储键、分块写入、原子发布和幂等清理。"""

from collections.abc import AsyncIterator
import hashlib
import os
from pathlib import Path
import re
from uuid import UUID

import anyio

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError


class LocalFileStorage:
    """将 UUID 原文件保存到私有目录，绝不把用户名称拼接进磁盘路径。"""

    def __init__(self, root: Path):
        """保存绝对存储根目录，目录准备留到显式初始化时执行。"""
        self.root = root.resolve()

    async def initialize(self) -> None:
        """准备并验证原文件目录可写，启动失败不留下临时探测文件。"""
        await anyio.to_thread.run_sync(self._initialize)

    def _initialize(self) -> None:
        """在线程内创建根目录并用临时文件验证实际读写能力。"""
        import tempfile
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=self.root) as probe:
            probe.write(b"zhizhou")
            probe.flush()

    @staticmethod
    def key(blob_id: UUID) -> str:
        """为原文件生成固定格式的内部存储键，不接受业务名称。"""
        return f"{blob_id.hex[:2]}/{blob_id.hex}.blob"

    def path(self, key: str, *, partial: bool = False) -> Path:
        """校验存储键并返回根目录内路径，拒绝越界及符号链接重定向。"""
        if not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{32}\.blob", key) or key[:2] != key[3:5]:
            raise ValueError("无效原文件存储键")
        candidate = self.root / (key + ".part" if partial else key)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or resolved != candidate:
            raise ValueError("原文件路径不可用")
        return candidate

    async def write(self, key: str, chunks: AsyncIterator[bytes], limit: int) -> tuple[int, str]:
        """分块保存原文件并返回大小和摘要，超过上限时不发布最终文件。

        调用方持有该原文件独占锁并登记 staging 记录；异常留下的 .part
        由调用方或重启后的清理任务处理，成功时先同步内容再原子改名。
        """
        partial = self.path(key, partial=True)
        target = self.path(key)
        await anyio.to_thread.run_sync(partial.parent.mkdir, 0o700, True, True)
        digest = hashlib.sha256()
        size = 0
        handle = await anyio.open_file(partial, "xb")
        try:
            async for chunk in chunks:
                size += len(chunk)
                if size > limit:
                    raise RequestError(ErrorCode.FILE_TOO_LARGE)
                digest.update(chunk)
                await handle.write(chunk)
            await handle.flush()
            await anyio.to_thread.run_sync(os.fsync, handle.wrapped.fileno())
        finally:
            with anyio.CancelScope(shield=True):
                await handle.aclose()
        await anyio.to_thread.run_sync(os.replace, partial, target)
        return size, digest.hexdigest()

    async def open_reader(self, key: str):
        """打开已有原文件供流式读取，调用方负责持锁和关闭文件句柄。"""
        return await anyio.open_file(self.path(key), "rb")

    async def remove(self, key: str) -> None:
        """幂等删除最终文件和未完成文件，磁盘异常保留给业务层安排重试。"""
        for partial in (False, True):
            path = self.path(key, partial=partial)
            await anyio.to_thread.run_sync(path.unlink, True)
