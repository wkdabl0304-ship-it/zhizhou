"""上传大小策略集成测试：范围授权、乐观并发、实际文件边界及已存文件兼容。"""

import asyncio

import pytest

from tests.support.files import department, space, upload
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


async def test_upload_limits_scopes_versions_and_existing_files(postgres_settings):
    """超管维护统一策略，部门管理员只维护本部门，降低上限不影响已有文件下载。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, rh = await account(runtime.auth, "super_admin")
        manager, mh = await account(runtime.auth)
        _, uh = await account(runtime.auth)
        first = await department(runtime, rh, manager=manager)
        second = await department(runtime, rh, "市场部")
        own = await space(runtime, uh, "personal")
        existing = await upload(runtime, uh, own["id"], content=b"12345")
        path = "/api/files/upload-limits/personal"
        initial = (await runtime.client.get(path, headers=uh)).json()["data"]
        assert initial["max_file_size_bytes"] == 104857600 and initial["version"] == 1 and initial["updated_by"] is None
        assert (await runtime.client.patch(path, headers=mh, json={"max_file_size_bytes": 2, "version": 1})).status_code == 403
        response = await runtime.client.patch(path, headers=rh, json={"max_file_size_bytes": 2, "version": 1})
        assert response.json()["data"]["version"] == 2
        assert response.json()["data"]["updated_by"] is not None
        assert (await runtime.client.patch(path, headers=rh, json={"max_file_size_bytes": 3, "version": 1})).json()["code"] == 40911
        await upload(runtime, uh, own["id"], content=b"12")
        await upload(runtime, uh, own["id"], name="empty", content=b"")
        response = await runtime.client.post(f"/api/files/spaces/{own['id']}/files", headers=uh, files={"file": ("large", b"123")})
        assert response.status_code == 413 and response.json()["code"] == 41301
        assert (await runtime.client.get(f"/api/files/entries/{existing['id']}/download", headers=uh)).content == b"12345"
        assert (await space(runtime, uh, "personal"))["max_file_size_bytes"] == 2
        for scope in ("global", "personal"):
            assert (await runtime.client.get(f"/api/files/upload-limits/{scope}", headers=uh)).status_code == 200
            assert (await runtime.client.patch(f"/api/files/upload-limits/{scope}", headers=mh,
                json={"max_file_size_bytes": 1, "version": 1})).status_code == 403
        department_path = f"/api/files/upload-limits/departments/{first}"
        assert (await runtime.client.get(department_path, headers=uh)).status_code == 404
        assert (await runtime.client.patch(department_path, headers=mh, json={"max_file_size_bytes": 5, "version": 1})).status_code == 200
        assert (await space(runtime, mh, "department"))["max_file_size_bytes"] == 5
        assert (await runtime.client.get(f"/api/files/upload-limits/departments/{second}", headers=mh)).status_code == 404
        assert (await runtime.client.patch(f"/api/files/upload-limits/departments/{second}", headers=rh,
            json={"max_file_size_bytes": 7, "version": 1})).status_code == 200


async def test_policy_concurrency_and_invalid_values_have_no_side_effect(postgres_settings):
    """并发修改必须有一个冲突，布尔和字符串等无效字节数不修改策略。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        path = "/api/files/upload-limits/global"
        for value in (True, "1024", 0, -1, 1099511627777):
            response = await runtime.client.patch(path, headers=headers, json={"max_file_size_bytes": value, "version": 1})
            assert response.status_code == 422
        assert (await runtime.client.get(path, headers=headers)).json()["data"]["version"] == 1
        responses = await asyncio.gather(*[runtime.client.patch(path, headers=headers,
            json={"max_file_size_bytes": value, "version": 1}) for value in (1000, 2000)])
        assert sorted(response.status_code for response in responses) == [200, 409]
