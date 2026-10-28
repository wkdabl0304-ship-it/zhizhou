"""权限全链路集成测试：真实随机库验证角色范围、管理状态、个人隔离及并发撤权。"""

import asyncio
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import delete, func, select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department, Permission, Role, RolePermission, User, UserRole
from app.schemas.auth import LoginRequest
from app.services.authorization import AuthorizationService, management_lock
from app.services.model_management import ModelManagementService
from app.services.users import UserManagementService
from tests.support.postgres import account, open_runtime, send

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def department(runtime, headers, name="研发部"):
    """通过正式接口创建本例部门，调用失败时保留响应用于诊断。"""
    response = await runtime.client.post("/api/departments", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def join(runtime, headers, department_id, user):
    """通过正式加入接口设置本例成员归属，不直接修改测试数据库。"""
    response = await runtime.client.post(f"/api/departments/{department_id}/members", headers=headers,
                                         json={"username": user.username})
    assert response.status_code == 200, response.text
    return response


async def administrator(runtime, headers, department_id, user):
    """准备一个合法部门管理员，所有身份授予均经过正式业务接口。"""
    await join(runtime, headers, department_id, user)
    response = await runtime.client.put(f"/api/departments/{department_id}/administrators/{user.id}", headers=headers)
    assert response.status_code == 200, response.text


async def actor(runtime, headers):
    """解析本例真实令牌取得服务调用身份，确保服务测试使用正式认证结果。"""
    return await runtime.auth.authenticate(headers["Authorization"].removeprefix("Bearer "))


async def test_department_lifecycle_scope_privacy_and_global_role_preservation(postgres_settings):
    """加入任免和删除部门立即改变权限，成员个人内容与全局超管身份始终保留。"""
    async with open_runtime(postgres_settings) as runtime:
        root, root_headers = await account(runtime.auth, "super_admin")
        manager, manager_headers = await account(runtime.auth)
        member, member_headers = await account(runtime.auth)
        free_user, free_headers = await account(runtime.auth)
        first = await department(runtime, root_headers)
        second = await department(runtime, root_headers, "市场部")
        await administrator(runtime, root_headers, first, manager)
        await administrator(runtime, root_headers, first, manager)
        me = (await runtime.client.get("/api/auth/me", headers=manager_headers)).json()["data"]
        assert me["roles"] == ["department_admin", "user"] and me["role"] == "user"
        assert me["department"] == {"id": first, "name": "研发部"}
        assert {"permission": "department_member:add", "scope_type": "department", "scope_id": first} in me["grants"]
        visible = (await runtime.client.get("/api/departments", headers=manager_headers)).json()["data"]
        assert [item["id"] for item in visible["items"]] == [first]
        for path in (f"/api/departments/{second}", f"/api/departments/{second}/members", f"/api/departments/{uuid4()}"):
            assert (await runtime.client.get(path, headers=manager_headers)).json()["code"] == 40405
        assert (await runtime.client.get("/api/users", headers=manager_headers)).status_code == 403
        assert (await runtime.client.get("/api/departments", headers=free_headers)).status_code == 403
        for method, path, body in (
            ("PATCH", f"/api/departments/{first}", {"name": "不允许改名"}),
            ("DELETE", f"/api/departments/{first}", None),
            ("PUT", f"/api/departments/{first}/administrators/{member.id}", None),
            ("PUT", f"/api/users/{member.id}/active", {"is_active": False}),
            ("PUT", f"/api/users/{member.id}/password", {"password": "not-allowed-password"}),
            ("PUT", f"/api/users/{member.id}/super-admin", None),
            ("POST", f"/api/departments/{second}/members", {"username": member.username}),
        ):
            response = await runtime.client.request(method, path, headers=manager_headers, json=body)
            assert response.status_code == 403, response.text
        await join(runtime, manager_headers, first, member)
        await join(runtime, manager_headers, first, member)
        conflict = await runtime.client.post(f"/api/departments/{second}/members", headers=root_headers, json={"username": member.username})
        assert conflict.status_code == 409 and conflict.json()["code"] == 40905
        missing = await runtime.client.post(f"/api/departments/{first}/members", headers=manager_headers, json={"username": "missing_account"})
        assert missing.json()["code"] == 40404
        cid, _ = await send(runtime.client, member_headers, "个人私密内容")
        for privileged in (root_headers, manager_headers, free_headers):
            for method, path, body in (("GET", f"/api/conversations/{cid}", None),
                ("PATCH", f"/api/conversations/{cid}/title", {"title": "不允许修改"}),
                ("DELETE", f"/api/conversations/{cid}", None)):
                assert (await runtime.client.request(method, path, headers=privileged, json=body)).json()["code"] == 40401
        listing = (await runtime.client.get(f"/api/departments/{first}/members", headers=manager_headers)).json()["data"]["items"]
        assert {row["id"] for row in listing} == {str(manager.id), str(member.id)}
        assert all(set(row) == {"id", "username", "is_active", "roles"} for row in listing)
        await join(runtime, root_headers, first, root)
        assert (await runtime.client.delete(f"/api/departments/{first}", headers=root_headers)).json()["code"] == 0
        for user_headers in (manager_headers, member_headers, root_headers):
            info = (await runtime.client.get("/api/auth/me", headers=user_headers)).json()["data"]
            assert info["department"] is None and "department_admin" not in info["roles"]
        assert "super_admin" in (await runtime.client.get("/api/auth/me", headers=root_headers)).json()["data"]["roles"]
        assert (await runtime.client.get(f"/api/conversations/{cid}", headers=member_headers)).status_code == 200
        assert (await runtime.client.post(f"/api/departments/{second}/members", headers=manager_headers, json={"username": free_user.username})).status_code == 403


async def test_remove_transfer_self_removal_and_disabled_members(postgres_settings):
    """移出部门撤销全部部门角色，转部门需显式重新加入，停用成员不能加入或被任命。"""
    async with open_runtime(postgres_settings) as runtime:
        _, root_headers = await account(runtime.auth, "super_admin")
        manager, manager_headers = await account(runtime.auth)
        member, member_headers = await account(runtime.auth)
        first = await department(runtime, root_headers)
        second = await department(runtime, root_headers, "另一个部门")
        await administrator(runtime, root_headers, first, manager)
        await administrator(runtime, root_headers, first, member)
        assert (await runtime.client.delete(f"/api/departments/{first}/members/{member.id}", headers=manager_headers)).json()["code"] == 0
        assert (await runtime.client.delete(f"/api/departments/{first}/members/{member.id}", headers=manager_headers)).json()["code"] == 0
        await join(runtime, root_headers, second, member)
        info = (await runtime.client.get("/api/auth/me", headers=member_headers)).json()["data"]
        assert info["roles"] == ["user"] and info["department"]["id"] == second
        assert (await runtime.client.delete(f"/api/departments/{first}/members/{member.id}", headers=manager_headers)).json()["code"] == 40907
        assert (await runtime.client.put(f"/api/users/{member.id}/active", headers=root_headers, json={"is_active": False})).status_code == 200
        assert (await runtime.client.put(f"/api/departments/{second}/administrators/{member.id}", headers=root_headers)).json()["code"] == 40907
        assert (await runtime.client.delete(f"/api/departments/{second}/members/{member.id}", headers=root_headers)).status_code == 200
        assert (await runtime.client.post(f"/api/departments/{first}/members", headers=manager_headers, json={"username": member.username})).json()["code"] == 40907
        assert (await runtime.client.delete(f"/api/departments/{first}/members/{manager.id}", headers=manager_headers)).status_code == 200
        assert (await runtime.client.get("/api/departments", headers=manager_headers)).status_code == 403


async def test_password_disable_enable_and_legacy_tokens(postgres_settings):
    """改密和停用撤销旧令牌，再启用不会复活旧凭据，旧版无版本 JWT 被拒绝。"""
    async with open_runtime(postgres_settings) as runtime:
        _, root_headers = await account(runtime.auth, "super_admin")
        user, headers = await account(runtime.auth)
        token = headers["Authorization"].removeprefix("Bearer ")
        claims = jwt.decode(token, postgres_settings.jwt_secret, algorithms=["HS256"], audience=postgres_settings.jwt_audience)
        assert claims["token_version"] == 1
        legacy = jwt.encode({key: value for key, value in claims.items() if key != "token_version"}, postgres_settings.jwt_secret, algorithm="HS256")
        assert (await runtime.client.get("/api/auth/me", headers={"Authorization": "Bearer " + legacy})).status_code == 401
        response = await runtime.client.put(f"/api/users/{user.id}/password", headers=root_headers, json={"password": "changed-password"})
        assert response.json() == {"code": 0, "message": "成功", "data": None}
        assert (await runtime.client.get("/api/auth/me", headers=headers)).status_code == 401
        assert (await runtime.client.post("/api/auth/login", json={"username": user.username, "password": "password-with-spaces "})).status_code == 401
        logged = await runtime.auth.login(LoginRequest(username=user.username, password="changed-password"))
        renewed = {"Authorization": "Bearer " + logged.access_token}
        assert (await runtime.client.put(f"/api/users/{user.id}/active", headers=root_headers, json={"is_active": False})).status_code == 200
        assert (await runtime.client.get("/api/auth/me", headers=renewed)).status_code == 401
        assert (await runtime.client.post("/api/auth/login", json={"username": user.username, "password": "changed-password"})).status_code == 401
        assert (await runtime.client.put(f"/api/users/{user.id}/active", headers=root_headers, json={"is_active": True})).status_code == 200
        assert (await runtime.client.get("/api/auth/me", headers=renewed)).status_code == 401
        latest = await runtime.auth.login(LoginRequest(username=user.username, password="changed-password"))
        assert jwt.decode(latest.access_token, postgres_settings.jwt_secret, algorithms=["HS256"], audience=postgres_settings.jwt_audience)["token_version"] == 3
        assert "password" not in (await runtime.client.get(f"/api/users/{user.id}", headers=root_headers)).text


@pytest.mark.parametrize("operation", ["disable", "revoke"])
async def test_last_active_superadmin_is_protected_under_concurrency(postgres_settings, operation):
    """两个管理员并发移除自身管理能力，必须恰好保留一名可用超管。"""
    async with open_runtime(postgres_settings) as runtime:
        first, first_headers = await account(runtime.auth, "super_admin")
        second, second_headers = await account(runtime.auth, "super_admin")

        async def remove_self(user, headers):
            """每个账号使用自己的真实令牌，竞争同一条最后管理员业务约束。"""
            if operation == "disable":
                return await runtime.client.put(f"/api/users/{user.id}/active", headers=headers, json={"is_active": False})
            return await runtime.client.delete(f"/api/users/{user.id}/super-admin", headers=headers)

        responses = await asyncio.wait_for(asyncio.gather(remove_self(first, first_headers), remove_self(second, second_headers)), 15)
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert [response.json()["code"] for response in responses if response.status_code == 409] == [40906]
        async with runtime.database.sessions() as session:
            count = await session.scalar(select(func.count()).select_from(UserRole).join(User, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id).where(User.is_active.is_(True), Role.code == "super_admin"))
            assert count == 1


async def test_concurrent_membership_has_one_winner_and_department_delete_is_atomic(postgres_settings):
    """跨部门并发加入只能成功一次，随后删除部门不会留下成员归属或部门授权。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        user, _ = await account(runtime.auth)
        ids = [await department(runtime, headers, name) for name in ("甲部门", "乙部门")]
        responses = await asyncio.wait_for(asyncio.gather(*[
            runtime.client.post(f"/api/departments/{did}/members", headers=headers, json={"username": user.username}) for did in ids]), 15)
        assert sorted(response.status_code for response in responses) == [200, 409]
        async with runtime.database.sessions() as session:
            winner = (await session.get(User, user.id)).department_id
        await runtime.client.put(f"/api/departments/{winner}/administrators/{user.id}", headers=headers)
        await runtime.client.delete(f"/api/departments/{winner}", headers=headers)
        async with runtime.database.sessions() as session:
            assert (await session.get(User, user.id)).department_id is None
            assert await session.scalar(select(func.count()).select_from(UserRole).where(UserRole.department_id == winner)) == 0


async def test_data_driven_grants_and_direct_service_entrypoints(postgres_settings):
    """角色名不决定权限，独立角色可按数据授权；直接服务调用也不能跳过检查。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        identity = await actor(runtime, headers)
        managed = ModelManagementService(runtime.model_config)
        with pytest.raises(RequestError) as rejected:
            await managed.execute(identity, runtime.model_config.list_models)
        assert rejected.value.error_code is ErrorCode.FORBIDDEN
        with pytest.raises(RequestError):
            await UserManagementService(runtime.database).get(identity, user.id)
        async with runtime.database.sessions.begin() as session:
            role = Role(code="model_operator", name="独立模型操作员", binding_scope="global")
            session.add(role)
            await session.flush()
            permission = await session.scalar(select(Permission).where(Permission.code == "model:manage"))
            session.add(RolePermission(role_id=role.id, permission_id=permission.id, scope_type="global"))
            session.add(UserRole(user_id=user.id, role_id=role.id))
        assert (await runtime.client.get("/api/model-config/models", headers=headers)).status_code == 200
        assert await managed.execute(identity, runtime.model_config.list_models)
        info = (await runtime.client.get("/api/auth/me", headers=headers)).json()["data"]
        assert info["role"] == "user" and info["roles"] == ["model_operator", "user"]
        with pytest.raises(RequestError):
            async with runtime.database.sessions() as session:
                await AuthorizationService(runtime.database).require(session, identity, "future:permission")
        async with runtime.database.sessions.begin() as session:
            await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        assert (await runtime.client.get("/api/model-config/models", headers=headers)).status_code == 403


async def test_pagination_filters_scope_and_stale_role_binding(postgres_settings):
    """分页不漏重，游标不能跨筛选或操作者复用，失配的旧部门绑定不生效。"""
    async with open_runtime(postgres_settings) as runtime:
        root, headers = await account(runtime.auth, "super_admin")
        other, other_headers = await account(runtime.auth, "super_admin")
        manager, manager_headers = await account(runtime.auth)
        ids = [await department(runtime, headers, name) for name in ("一部", "二部", "三部")]
        response = await runtime.client.get("/api/departments", headers=headers, params={"limit": 1})
        page = response.json()["data"]
        found = [page["items"][0]["id"]]
        cursor = page["next_cursor"]
        assert cursor
        assert (await runtime.client.get("/api/departments", headers=other_headers, params={"cursor": cursor})).status_code == 422
        while page["next_cursor"]:
            page = (await runtime.client.get("/api/departments", headers=headers, params={"limit": 1, "cursor": page["next_cursor"]})).json()["data"]
            found.extend(item["id"] for item in page["items"])
        assert len(found) == len(set(found)) == 3 and set(found) == set(ids)
        users_page = (await runtime.client.get("/api/users", headers=headers, params={"limit": 1})).json()["data"]
        assert (await runtime.client.get("/api/users", headers=headers, params={"cursor": users_page["next_cursor"], "is_active": False})).status_code == 422
        assert (await runtime.client.get("/api/users", headers=headers, params={"department_id": ids[0], "unassigned": True})).status_code == 422
        await administrator(runtime, headers, ids[0], manager)
        async with runtime.database.sessions.begin() as session:
            current = await session.get(User, manager.id)
            current.department_id = UUID(ids[1])
        assert (await runtime.client.get("/api/departments", headers=manager_headers)).status_code == 403
        assert (await runtime.client.get("/api/auth/me", headers=manager_headers)).json()["data"]["roles"] == ["user"]


async def test_waiting_management_write_rechecks_revoked_authority(postgres_settings, monkeypatch):
    """管理请求等待事务锁期间被撤权，取得锁后必须拒绝，不能改变目标账号。"""
    import app.services.authorization as authorization_module

    async with open_runtime(postgres_settings) as runtime:
        root, headers = await account(runtime.auth, "super_admin")
        target, _ = await account(runtime.auth)
        identity = await actor(runtime, headers)
        entered = asyncio.Event()
        original = authorization_module.management_lock

        async def observed_lock(session, *, shared=False):
            """标记待测写请求已进入锁等待，让撤权与继续执行之间的顺序可重复。"""
            entered.set()
            await original(session, shared=shared)

        task = None
        try:
            async with runtime.database.sessions.begin() as session:
                await management_lock(session)
                monkeypatch.setattr(authorization_module, "management_lock", observed_lock)
                task = asyncio.create_task(UserManagementService(runtime.database).set_active(identity, target.id, False))
                await asyncio.wait_for(entered.wait(), 5)
                role = await session.scalar(select(Role).where(Role.code == "super_admin"))
                await session.execute(delete(UserRole).where(UserRole.user_id == root.id, UserRole.role_id == role.id))
            with pytest.raises(RequestError) as rejected:
                await asyncio.wait_for(task, 10)
            assert rejected.value.error_code is ErrorCode.FORBIDDEN
            async with runtime.database.sessions() as session:
                assert (await session.get(User, target.id)).is_active
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
