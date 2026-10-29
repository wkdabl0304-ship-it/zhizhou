"""文件资源生命周期测试：启动失败不启动任务，正常或异常退出均回收周期任务。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.files import lifecycle

pytestmark = pytest.mark.anyio


async def test_cleanup_task_starts_and_is_stopped_on_body_failure(monkeypatch, tmp_path):
    """资源上下文先完成启动清理，退出异常时仍取消并等待周期任务。"""
    started, stopped = asyncio.Event(), asyncio.Event()

    async def run():
        """模拟周期任务并观察取消后的 finally，不使用真实等待时间。"""
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    cleanup = SimpleNamespace(run_once=AsyncMock(), run=run)
    service = SimpleNamespace(cleanup=cleanup)
    monkeypatch.setattr(lifecycle, "FileService", Mock(return_value=service))
    with pytest.raises(RuntimeError, match="body failure"):
        async with lifecycle.open_file_service(object(), tmp_path):
            cleanup.run_once.assert_awaited_once()
            await started.wait()
            raise RuntimeError("body failure")
    assert stopped.is_set()
    assert not any(task.get_name() == "file-cleanup" and not task.done() for task in asyncio.all_tasks())


async def test_startup_scan_failure_never_exposes_service_or_task(monkeypatch, tmp_path):
    """启动扫描失败时不接受请求，也不会残留周期清理任务。"""
    cleanup = SimpleNamespace(run_once=AsyncMock(side_effect=RuntimeError("scan failed")), run=AsyncMock())
    monkeypatch.setattr(lifecycle, "FileService", Mock(return_value=SimpleNamespace(cleanup=cleanup)))
    with pytest.raises(RuntimeError, match="scan failed"):
        async with lifecycle.open_file_service(object(), tmp_path):
            pytest.fail("启动失败不应提供文件服务")
    cleanup.run.assert_not_called()
