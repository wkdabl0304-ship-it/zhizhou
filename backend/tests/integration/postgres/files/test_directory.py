"""文件目录与权限集成测试；使用真实账号、随机临时库及独立原件目录。"""

import asyncio
import pytest
from tests.support.files import blob_for, department, folder, join, space, spaces, upload
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


async def test_space_permissions_and_private_content_are_isolated(postgres_settings):
    """三类空间按当前成员和授权隔离，所有管理员均不能读取他人个人资料。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        root, rh = await account(runtime.auth, "super_admin")
        manager, mh = await account(runtime.auth)
        member, uh = await account(runtime.auth)
        outsider, oh = await account(runtime.auth)
        dep = await department(runtime, rh, manager=manager)
        other_dep = await department(runtime, rh, "市场部")
        await join(runtime, rh, dep, member)
        public = await space(runtime, uh, "global")
        own = await space(runtime, uh, "personal")
        shared = await space(runtime, mh, "department")
        other = await space(runtime, rh, "department", other_dep)
        assert public["capabilities"] == shared["capabilities"][:1] == ["read"]
        assert own["capabilities"] == shared["capabilities"] == ["read", "upload", "update", "delete"]
        assert len(await spaces(runtime, uh)) == 3
        assert len(await spaces(runtime, oh)) == 2
        assert len(await spaces(runtime, rh)) == 4
        private_file = await upload(runtime, uh, own["id"])
        for headers in (rh, mh, oh):
            for suffix in ("", "/download"):
                response = await runtime.client.get(f"/api/files/entries/{private_file['id']}{suffix}", headers=headers)
                assert response.status_code == 404 and response.json()["code"] == 40407
            assert (await runtime.client.get(f"/api/files/spaces/{own['id']}", headers=headers)).json()["code"] == 40406
        for headers, target in ((uh, public), (uh, shared), (mh, public)):
            response = await runtime.client.post(f"/api/files/spaces/{target['id']}/folders", headers=headers, json={"name": "禁止"})
            assert response.status_code == 403, response.text
        assert (await runtime.client.get(f"/api/files/spaces/{other['id']}", headers=mh)).status_code == 404
        shared_file = await upload(runtime, mh, shared["id"])
        assert (await runtime.client.get(f"/api/files/entries/{shared_file['id']}/download", headers=uh)).content == b"\x00\xfforiginal"
        assert (await runtime.client.patch(f"/api/files/entries/{shared_file['id']}", headers=uh, json={"name": "改名", "version": 1})).status_code == 403
        assert (await runtime.client.delete(f"/api/files/entries/{shared_file['id']}?version=1", headers=uh)).status_code == 403
        assert (await runtime.client.get("/api/files/spaces")).status_code == 401


async def test_directory_breadcrumbs_duplicates_rename_and_recursive_delete(postgres_settings):
    """目录浏览与详情正确，重名自动另存，递归删除立即阻止读取并可复用名称。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        first = await folder(runtime, headers, own["id"], "合同")
        nested = await folder(runtime, headers, own["id"], "年度", first["id"])
        original = await upload(runtime, headers, own["id"], "方案.pdf", parent_id=nested["id"])
        duplicate = await upload(runtime, headers, own["id"], "方案.PDF", parent_id=nested["id"])
        empty = await upload(runtime, headers, own["id"], "空文件", b"", nested["id"])
        assert duplicate["name"] == "方案 (1).PDF" and empty["size_bytes"] == 0
        response = await runtime.client.get(f"/api/files/spaces/{own['id']}/entries", headers=headers, params={"parent_id": nested["id"]})
        data = response.json()["data"]
        assert [row["name"] for row in data["breadcrumbs"]] == ["合同", "年度"]
        assert {row["id"] for row in data["items"]} == {original["id"], duplicate["id"], empty["id"]}
        detail = (await runtime.client.get(f"/api/files/entries/{original['id']}", headers=headers)).json()["data"]
        assert detail["entry"]["name"] == "方案.pdf" and detail["breadcrumbs"] == data["breadcrumbs"]
        response = await runtime.client.patch(f"/api/files/entries/{original['id']}", headers=headers, json={"name": "方案.PDF", "version": 1})
        assert response.json()["data"]["version"] == 2
        assert (await runtime.client.patch(f"/api/files/entries/{original['id']}", headers=headers, json={"name": "过期", "version": 1})).json()["code"] == 40910
        assert (await runtime.client.patch(f"/api/files/entries/{duplicate['id']}", headers=headers, json={"name": "方案.pdf", "version": 1})).json()["code"] == 40909
        assert (await runtime.client.post(f"/api/files/spaces/{own['id']}/folders", headers=headers, json={"name": "方案.pdf", "parent_id": nested["id"]})).json()["code"] == 40909
        assert (await runtime.client.get(f"/api/files/entries/{first['id']}/download", headers=headers)).status_code == 422
        response = await runtime.client.delete(f"/api/files/entries/{first['id']}?version=1", headers=headers)
        assert response.json() == {"code": 0, "message": "成功", "data": None}
        for row in (first, nested, original, duplicate, empty):
            assert (await runtime.client.get(f"/api/files/entries/{row['id']}", headers=headers)).status_code == 404
        assert (await runtime.client.get(f"/api/files/entries/{original['id']}/download", headers=headers)).status_code == 404
        blob = await blob_for(runtime, original["id"])
        assert blob.state == "delete_pending" and runtime.files.storage.path(blob.storage_key).exists()
        await runtime.files.cleanup.run_once()
        blob = await blob_for(runtime, original["id"])
        assert blob.state == "purged" and not runtime.files.storage.path(blob.storage_key).exists()
        assert (await folder(runtime, headers, own["id"], "合同"))["id"] != first["id"]


async def test_pagination_is_bound_to_actor_directory_and_current_authorization(postgres_settings):
    """分页不会重复读取或跨空间复用，部门变化使旧游标失效。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        root, rh = await account(runtime.auth, "super_admin")
        member, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        for index in range(3):
            await folder(runtime, headers, own["id"], f"目录{index}")
        path = f"/api/files/spaces/{own['id']}/entries"
        first = (await runtime.client.get(path, headers=headers, params={"limit": 1})).json()["data"]
        second = (await runtime.client.get(path, headers=headers, params={"limit": 2, "cursor": first["next_cursor"]})).json()["data"]
        assert len(first["items"]) == 1 and len(second["items"]) == 2 and second["next_cursor"] is None
        assert len({row["id"] for row in first["items"] + second["items"]}) == 3
        assert (await runtime.client.get(path, headers=headers, params={"parent_id": first["items"][0]["id"], "cursor": first["next_cursor"]})).status_code == 422
        public = await space(runtime, headers, "global")
        assert (await runtime.client.get(f"/api/files/spaces/{public['id']}/entries", headers=headers, params={"cursor": first["next_cursor"]})).status_code == 422
        dep = await department(runtime, rh)
        await join(runtime, rh, dep, member)
        assert (await runtime.client.get(path, headers=headers, params={"cursor": first["next_cursor"]})).status_code == 422
        assert (await runtime.client.get(path, headers=headers, params={"limit": 101})).status_code == 422


async def test_concurrent_uploads_allocate_unique_names_and_versions_serialize(postgres_settings):
    """同空间并发上传获得最小可用序号，并发改名只能由一个版本请求成功。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        results = await asyncio.wait_for(asyncio.gather(*[upload(runtime, headers, own["id"]) for _ in range(3)]), 15)
        assert {row["name"] for row in results} == {"方案.pdf", "方案 (1).pdf", "方案 (2).pdf"}
        row = results[0]
        responses = await asyncio.gather(*[runtime.client.patch(f"/api/files/entries/{row['id']}", headers=headers,
            json={"name": f"新名{index}", "version": 1}) for index in range(2)])
        assert sorted(response.status_code for response in responses) == [200, 409]


async def test_department_delete_closes_shared_files_but_preserves_private_files(postgres_settings):
    """删除部门同时关闭所有共享资料并清理策略，成员个人原件和全局资料仍存在。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, rh = await account(runtime.auth, "super_admin")
        member, headers = await account(runtime.auth)
        dep = await department(runtime, rh)
        await join(runtime, rh, dep, member)
        shared = await space(runtime, rh, "department", dep)
        own = await space(runtime, headers, "personal")
        node = await folder(runtime, rh, shared["id"])
        shared_file = await upload(runtime, rh, shared["id"], parent_id=node["id"])
        personal_file = await upload(runtime, headers, own["id"])
        response = await runtime.client.delete(f"/api/departments/{dep}", headers=rh)
        assert response.status_code == 200, response.text
        assert (await runtime.client.get(f"/api/files/spaces/{shared['id']}", headers=rh)).status_code == 404
        assert (await runtime.client.get(f"/api/files/entries/{shared_file['id']}/download", headers=rh)).status_code == 404
        assert (await runtime.client.get(f"/api/files/entries/{personal_file['id']}/download", headers=headers)).status_code == 200
        await runtime.files.cleanup.run_once()
        assert (await blob_for(runtime, shared_file["id"])).state == "purged"
        assert (await blob_for(runtime, personal_file["id"])).state == "ready"
