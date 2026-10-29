"""文件 HTTP 行为集成测试：鉴权先于请求体、父目录隔离及异常下载的资源回收。"""

import hashlib
from uuid import UUID

import pytest
from starlette.requests import ClientDisconnect

from app.api.file_streaming import FileDownloadResponse
from app.db.file_locks import FileLocks
from tests.support.files import actor, blob_for, folder, space, upload
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


async def test_authentication_and_upload_authorization_precede_body_consumption(postgres_settings):
    """未登录或只有读取权的请求不读取上传正文，也不创建暂存或条目。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        public = await space(runtime, headers, "global")
        consumed = []

        async def content():
            """一旦应用读取上传正文即登记，验证权限失败发生在网络读取之前。"""
            consumed.append(True)
            yield b"must not be consumed"

        for auth_headers, status in (({}, 401), (headers, 403)):
            response = await runtime.client.post(f"/api/files/spaces/{public['id']}/files", headers=auth_headers, content=content())
            assert response.status_code == status
        assert consumed == []
        assert not list(runtime.files.storage.root.rglob("*.blob"))
        assert not list(runtime.files.storage.root.rglob("*.part"))


async def test_cross_space_parent_and_invalid_multipart_are_rejected(postgres_settings):
    """跨空间父节点、文件父节点及多文件或额外字段不能改变目标目录或绕过单文件协议。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        personal = await space(runtime, headers, "personal")
        public = await space(runtime, headers, "global")
        parent = await folder(runtime, headers, personal["id"])
        original = await upload(runtime, headers, personal["id"], "unsafe.html", b"<script>example</script>")
        blob = await blob_for(runtime, original["id"])
        assert blob.sha256 == hashlib.sha256(b"<script>example</script>").hexdigest()
        response = await runtime.client.get(f"/api/files/entries/{original['id']}/download", headers=headers)
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")
        response = await runtime.client.post(f"/api/files/spaces/{public['id']}/files", headers=headers,
            params={"parent_id": parent["id"]}, files={"file": ("cross", b"cross")})
        assert response.status_code == 404 and response.json()["code"] == 40407
        response = await runtime.client.post(f"/api/files/spaces/{personal['id']}/folders", headers=headers,
            json={"name": "not-child", "parent_id": original["id"]})
        assert response.status_code == 422
        path = f"/api/files/spaces/{personal['id']}/files"
        for files, data in (([("file", ("one", b"a")), ("file", ("two", b"b"))], None),
                            ({"wrong": ("one", b"a")}, None), ({"file": ("one", b"a")}, {"owner_id": "injected"})):
            assert (await runtime.client.post(path, headers=headers, files=files, data=data)).status_code == 422
        assert len(list(runtime.files.storage.root.rglob("*.blob"))) == 1


@pytest.mark.parametrize("spec", ["2.0", "2.4"])
async def test_asgi_send_failure_releases_open_file_and_shared_lock(postgres_settings, spec):
    """发送失败在旧新版 ASGI 协议下都回收正式下载上下文，不残留共享锁。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        node = await upload(runtime, headers, own["id"])
        identity = await actor(runtime, headers)
        blob = await blob_for(runtime, node["id"])
        response = FileDownloadResponse(runtime.files, identity, UUID(node["id"]))

        async def receive():
            """保持旧 ASGI 的断开监听等待，让测试故障仅来自发送边界。"""
            import asyncio
            await asyncio.Event().wait()

        async def send(message):
            """在响应头之后模拟网络写失败，验证发送异常也会退出文件上下文。"""
            if message["type"] == "http.response.body":
                raise OSError("client disconnected")

        with pytest.raises((OSError, ClientDisconnect, ExceptionGroup)) as error:
            await response({"type": "http", "asgi": {"spec_version": spec}}, receive, send)
        if spec == "2.4":
            assert isinstance(error.value, ClientDisconnect)
        else:
            def leaves(exception):
                """展开旧协议任务组的异常，只接受本例刻意触发的网络发送故障。"""
                if isinstance(exception, BaseExceptionGroup):
                    for nested in exception.exceptions:
                        yield from leaves(nested)
                else:
                    yield exception

            assert all(isinstance(leaf, OSError) and str(leaf) == "client disconnected" for leaf in leaves(error.value))
        async with FileLocks(runtime.database.lock_engine).hold(blob.id, wait=False) as acquired:
            assert acquired
        await runtime.files.delete(identity, UUID(node["id"]), 1)
        await runtime.files.cleanup.run_once()
        assert not runtime.files.storage.path(blob.storage_key).exists()
