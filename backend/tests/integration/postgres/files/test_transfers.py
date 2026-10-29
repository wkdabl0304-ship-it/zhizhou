"""原件生命周期与并发集成测试：可控分块暂停传输，验证撤权、删除、失败和清理边界。"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from app.core.errors.exceptions import RequestError
from app.db.file_locks import FileLocks
from app.models import FileBlob, FileEntry
from app.services.files.lifecycle import open_file_service
from tests.support.files import actor, blob_for, department, folder, space, upload
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


@pytest.mark.parametrize("change,code", [
    ("revoke", 40301), ("remove", 40406), ("disable", 40103), ("password", 40101),
    ("parent_delete", 40407), ("department_delete", 40406), ("limit", 41301),
])
async def test_upload_publication_rechecks_current_target_and_permissions(postgres_settings, change, code):
    """传输期间发生撤权、停用、改密、目录或部门删除和上限降低，发布失败且不留可见条目。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, rh = await account(runtime.auth, "super_admin")
        manager, headers = await account(runtime.auth)
        dep = await department(runtime, rh, manager=manager)
        shared = await space(runtime, headers, "department")
        parent = await folder(runtime, headers, shared["id"])
        identity = await actor(runtime, headers)
        entered, release = asyncio.Event(), asyncio.Event()

        async def chunks():
            """首段后暂停，允许另一个真实管理事务在文件发布前提交。"""
            yield b"first"
            entered.set()
            await release.wait()
            yield b"last"

        async with asyncio.timeout(15):
            task = asyncio.create_task(runtime.files.transfers.upload(identity, UUID(shared["id"]), UUID(parent["id"]), "race.bin", chunks()))
            try:
                await entered.wait()
                if change == "revoke":
                    response = await runtime.client.delete(f"/api/departments/{dep}/administrators/{manager.id}", headers=rh)
                elif change == "remove":
                    response = await runtime.client.delete(f"/api/departments/{dep}/members/{manager.id}", headers=rh)
                elif change == "disable":
                    response = await runtime.client.put(f"/api/users/{manager.id}/active", headers=rh, json={"is_active": False})
                elif change == "password":
                    response = await runtime.client.put(f"/api/users/{manager.id}/password", headers=rh, json={"password": "changed-password"})
                elif change == "parent_delete":
                    response = await runtime.client.delete(f"/api/files/entries/{parent['id']}?version=1", headers=rh)
                elif change == "department_delete":
                    response = await runtime.client.delete(f"/api/departments/{dep}", headers=rh)
                else:
                    response = await runtime.client.patch(f"/api/files/upload-limits/departments/{dep}", headers=rh,
                        json={"max_file_size_bytes": 1, "version": 1})
                assert response.status_code == 200, response.text
                release.set()
                with pytest.raises(RequestError) as error:
                    await task
                assert error.value.error_code.code == code
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        async with runtime.database.sessions() as session:
            assert not await session.scalar(select(FileEntry.id).where(FileEntry.kind == "file"))
            assert set((await session.scalars(select(FileBlob.state))).all()) == {"purged"}
        assert not list(runtime.files.storage.root.rglob("*.blob"))
        assert not list(runtime.files.storage.root.rglob("*.part"))


async def test_cleanup_skips_active_upload_and_cancel_releases_lock(postgres_settings):
    """清理不能删除正在上传的 staging，取消后关闭文件及锁且不发布原件。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        identity = await actor(runtime, headers)
        entered = asyncio.Event()

        async def chunks():
            """保持上传不结束，取消时让存储和原件锁执行各自 finally。"""
            yield b"first"
            entered.set()
            await asyncio.Event().wait()

        async with asyncio.timeout(15):
            task = asyncio.create_task(runtime.files.transfers.upload(identity, UUID(own["id"]), None, "cancel.bin", chunks()))
            try:
                await entered.wait()
                await runtime.files.cleanup.run_once()
                async with runtime.database.sessions() as session:
                    blob = (await session.scalars(select(FileBlob))).one()
                assert blob.state == "staging"
                assert runtime.files.storage.path(blob.storage_key, partial=True).exists()
            finally:
                task.cancel()
                result = await asyncio.gather(task, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)
            async with FileLocks(runtime.database.lock_engine).hold(blob.id, wait=False) as acquired:
                assert acquired
            await runtime.files.cleanup.run_once()
            async with runtime.database.sessions() as session:
                assert (await session.get(FileBlob, blob.id)).state == "purged"
                assert not await session.scalar(select(FileEntry.id))


async def test_download_holds_shared_lock_until_finished_then_cleanup_removes_file(postgres_settings):
    """已开始下载可在删除后读完，新的请求被拒绝，清理等待现有共享文件锁释放。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        content = b"\x00\xfforiginal"
        node = await upload(runtime, headers, own["id"], content=content)
        blob = await blob_for(runtime, node["id"])
        identity = await actor(runtime, headers)
        async with runtime.files.transfers.download(identity, UUID(node["id"])) as (info, reader):
            await runtime.files.delete(identity, UUID(node["id"]), 1)
            await runtime.files.cleanup.run_once()
            assert runtime.files.storage.path(blob.storage_key).exists()
            assert await reader.read() == content
            assert info.size_bytes == len(content)
            assert (await runtime.client.get(f"/api/files/entries/{node['id']}/download", headers=headers)).status_code == 404
            async with FileLocks(runtime.database.lock_engine).hold(blob.id, wait=False) as acquired:
                assert not acquired
        await runtime.files.cleanup.run_once()
        assert not runtime.files.storage.path(blob.storage_key).exists()
        assert (await blob_for(runtime, node["id"])).state == "purged"


async def test_storage_errors_are_safe_and_cleanup_retries(postgres_settings, monkeypatch):
    """磁盘写失败和缺失原件返回安全错误，清理失败保留状态并在恢复后成功回收。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        node = await upload(runtime, headers, own["id"])
        blob = await blob_for(runtime, node["id"])
        runtime.files.storage.path(blob.storage_key).unlink()
        response = await runtime.client.get(f"/api/files/entries/{node['id']}/download", headers=headers)
        assert response.status_code == 500 and response.json() == {"code": 50004, "message": "文件存储暂不可用，请稍后重试", "data": None}
        assert str(runtime.files.storage.root) not in response.text

        async def broken_write(*args):
            """模拟磁盘写入失败，不访问真实操作系统权限或开发文件。"""
            raise OSError("disk full /private/storage")

        monkeypatch.setattr(runtime.files.storage, "write", broken_write)
        response = await runtime.client.post(f"/api/files/spaces/{own['id']}/files", headers=headers, files={"file": ("failed.bin", b"content")})
        assert response.status_code == 500 and response.json()["code"] == 50004 and "/private" not in response.text
        await runtime.client.delete(f"/api/files/entries/{node['id']}?version=1", headers=headers)
        original_remove = runtime.files.storage.remove

        async def broken_remove(key):
            """模拟暂时无法清理，验证状态不被误报为已清理。"""
            raise PermissionError("temporary lock")

        monkeypatch.setattr(runtime.files.storage, "remove", broken_remove)
        await runtime.files.cleanup.run_once()
        assert (await blob_for(runtime, node["id"])).state == "delete_pending"
        monkeypatch.setattr(runtime.files.storage, "remove", original_remove)
        await runtime.files.cleanup.run_once()
        assert (await blob_for(runtime, node["id"])).state == "purged"


async def test_startup_cleanup_recovers_orphans_but_preserves_ready_files(postgres_settings):
    """重新打开正式文件生命周期时回收遗留 .part 和最终孤儿文件，保留可见原件。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        ready = await upload(runtime, headers, own["id"])
        ids = [uuid4(), uuid4()]
        async with runtime.database.sessions.begin() as session:
            for blob_id in ids:
                key = runtime.files.storage.key(blob_id)
                session.add(FileBlob(id=blob_id, storage_key=key))
                path = runtime.files.storage.path(key, partial=blob_id == ids[0])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"orphaned")
        async with open_file_service(runtime.database, runtime.files.storage.root) as restarted:
            async with runtime.database.sessions() as session:
                assert set((await session.scalars(select(FileBlob.state).where(FileBlob.id.in_(ids)))).all()) == {"purged"}
            assert (await blob_for(runtime, ready["id"])).state == "ready"
            assert (await runtime.client.get(f"/api/files/entries/{ready['id']}/download", headers=headers)).status_code == 200
        assert not any(task.get_name() == "file-cleanup" and not task.done() for task in asyncio.all_tasks())


async def test_published_metadata_rolls_back_when_final_transaction_fails(postgres_settings, monkeypatch):
    """最终事务抛错时目录及 ready 状态一起回滚，失败原件不能进入可见列表。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        identity = await actor(runtime, headers)
        original = runtime.files.entry_info

        async def mark_final_transaction(session, row):
            """标识已完成条目构造的最终事务，不改变正常业务返回。"""
            session.sync_session.info["reject_file_commit"] = True
            return await original(session, row)

        def reject_commit(session):
            """在真正提交阶段拒绝标记事务，其他准备及回收事务保持正常。"""
            if session.info.get("reject_file_commit"):
                raise RuntimeError("final transaction failed")

        async def chunks():
            """提供合法文件，使故障限定在最终数据库事务而非输入校验。"""
            yield b"content"

        monkeypatch.setattr(runtime.files, "entry_info", mark_final_transaction)
        sync_class = runtime.database.sessions.class_.sync_session_class
        event.listen(sync_class, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="final transaction failed"):
                await runtime.files.transfers.upload(identity, UUID(own["id"]), None, "failed", chunks())
        finally:
            event.remove(sync_class, "before_commit", reject_commit)
        async with runtime.database.sessions() as session:
            assert not await session.scalar(select(FileEntry.id))
            assert set((await session.scalars(select(FileBlob.state))).all()) == {"purged"}
