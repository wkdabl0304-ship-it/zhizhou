"""文件真实 TCP 传输回归：逐块下载、断开资源释放以及原件锁与删除协作。"""

import asyncio
from contextlib import asynccontextmanager
import socket
import httpx
import pytest
import uvicorn

from app.core.settings import load_database_settings
from app.db.file_locks import FileLocks
from tests.support.apps import make_app
from tests.support.files import blob_for, space, upload
from tests.support.postgres import account, open_runtime, temporary_database

pytestmark = [pytest.mark.anyio, pytest.mark.transport, pytest.mark.postgres]


@asynccontextmanager
async def running(app):
    """在随机回环端口启动本例真实 Uvicorn，退出时等待服务器和套接字关闭。"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_config=None, access_log=False))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    serving.result()
                    raise AssertionError("文件测试服务启动失败")
                await asyncio.sleep(0.001)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, 5)
        finally:
            listener.close()


async def test_download_delivers_before_completion_and_disconnect_releases_file_lock(monkeypatch):
    """真实 TCP 首段先于完成到达，客户端断开后关闭原件并释放共享锁供清理。"""
    async with temporary_database(load_database_settings()) as settings, open_runtime(settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        content = b"a" * 131072
        node = await upload(runtime, headers, own["id"], "中文资料.bin", content)
        blob = await blob_for(runtime, node["id"])
        blocked, closed, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = runtime.files.storage.open_reader

        class PausedReader:
            """第二次读取暂停的磁盘包装，保留正式响应及文件锁的生命周期。"""

            def __init__(self, source):
                """保存真实磁盘句柄，记录是否已经发送首段。"""
                self.source = source
                self.calls = 0

            async def read(self, count):
                """首段直接交付，后续等待显式释放或请求取消。"""
                self.calls += 1
                if self.calls > 1:
                    blocked.set()
                    await release.wait()
                return await self.source.read(count)

            async def aclose(self):
                """关闭正式文件并通知用例可验证跨连接锁已经解除。"""
                await self.source.aclose()
                closed.set()

        async def controlled_reader(key):
            """只替换磁盘读取速度，不替换正式鉴权、数据库、锁或 ASGI 响应。"""
            return PausedReader(await original(key))

        monkeypatch.setattr(runtime.files.storage, "open_reader", controlled_reader)
        app = make_app(auth=runtime.auth, files=runtime.files)
        async with running(app) as base_url, httpx.AsyncClient(base_url=base_url, timeout=5) as client:
            async with asyncio.timeout(15):
                try:
                    async with client.stream("GET", f"/api/files/entries/{node['id']}/download", headers=headers) as response:
                        assert response.status_code == 200
                        assert response.headers["content-type"] == "application/octet-stream"
                        assert "filename*=UTF-8''" in response.headers["content-disposition"]
                        assert response.headers["cache-control"] == "private, no-store"
                        assert response.headers["x-content-type-options"] == "nosniff"
                        assert int(response.headers["content-length"]) == len(content)
                        # 保留迭代器，避免临时异步生成器回收时提前关闭 HTTPX 响应。
                        chunks = response.aiter_raw()
                        first = await anext(chunks)
                        assert first and content.startswith(first)
                        await blocked.wait()
                        assert not closed.is_set()
                        async with FileLocks(runtime.database.lock_engine).hold(blob.id, wait=False) as acquired:
                            assert not acquired
                    await closed.wait()
                    # 关闭句柄先于锁上下文退出，因此用独立连接等待该锁完成释放。
                    async with FileLocks(runtime.database.lock_engine).hold(blob.id):
                        pass
                    response = await runtime.client.delete(f"/api/files/entries/{node['id']}?version=1", headers=headers)
                    assert response.status_code == 200
                    await runtime.files.cleanup.run_once()
                    assert not runtime.files.storage.path(blob.storage_key).exists()
                finally:
                    release.set()
