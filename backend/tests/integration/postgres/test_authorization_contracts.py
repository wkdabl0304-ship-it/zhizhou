"""权限契约回归：全部模型入口、数据库约束、管理错误以及事务回滚和登录竞争。"""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department, Permission, Role, RolePermission, User, UserRole
from app.repositories import authorization as repository
from app.schemas.auth import LoginRequest
from app.schemas.authorization import PasswordReset
from app.services.authorization import AuthorizationService
from app.services.departments import DepartmentService
from app.services.users import UserManagementService
from tests.support.postgres import account, open_runtime, send

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def identity(runtime, headers):
    """用正式令牌取得服务身份，保持凭据版本与真实接口一致。"""
    return await runtime.auth.authenticate(headers["Authorization"].removeprefix("Bearer "))


async def test_all_model_management_routes_reject_ordinary_user_and_options_remain_available(postgres_settings):
    """普通用户不能借目录、详情、默认或主动测试绕过模型管理授权，模型使用保持可用。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        provider = (await runtime.model_config.list_provider_configurations())[0]
        model = (await runtime.model_config.list_models())[0]
        prefix = "/api/model-config"
        cases = [
            ("GET", "/catalog/providers", None), ("GET", "/catalog/models", None),
            ("GET", "/provider-configurations", None), ("GET", f"/provider-configurations/{provider.id}", None),
            ("POST", "/provider-configurations", {"name": "不允许创建", "provider": "deepseek", "api_format": "chat_completions", "endpoint_config": {"endpoint_id": "official"}, "api_key": "not-allowed-key"}),
            ("PATCH", f"/provider-configurations/{provider.id}", {"version": 1, "name": "不允许修改"}),
            ("DELETE", f"/provider-configurations/{provider.id}?version=1", None),
            ("GET", "/models", None), ("GET", f"/models/{model.id}", None),
            ("POST", "/models", {"name": "不允许创建", "provider_configuration_id": str(provider.id), "catalog_model_id": model.catalog_model_id}),
            ("PATCH", f"/models/{model.id}", {"version": 1, "name": "不允许修改"}),
            ("DELETE", f"/models/{model.id}?version=1", None), ("POST", f"/models/{model.id}/test", None),
            ("GET", "/default", None), ("PUT", "/default", {"version": 2, "model_configuration_id": None}),
        ]
        for method, path, body in cases:
            response = await runtime.client.request(method, prefix + path, headers=headers, json=body)
            assert response.status_code == 403 and response.json()["code"] == 40301, response.text
        options = await runtime.client.get(prefix + "/options", headers=headers)
        assert options.status_code == 200 and options.json()["data"]["providers"]
        await send(runtime.client, headers)
        assert (await runtime.model_config.get_model(model.id)).name == model.name


async def test_management_errors_role_lifecycle_and_database_constraints(postgres_settings):
    """名称冲突、缺失账号与非法任命返回约定错误；唯一、外键及范围约束实际生效。"""
    async with open_runtime(postgres_settings) as runtime:
        root, headers = await account(runtime.auth, "super_admin")
        user, user_headers = await account(runtime.auth)
        response = await runtime.client.post("/api/departments", headers=headers, json={"name": "  产品部  "})
        assert response.json()["data"]["name"] == "产品部"
        department_id = response.json()["data"]["id"]
        assert (await runtime.client.post("/api/departments", headers=headers, json={"name": "产品部"})).json()["code"] == 40908
        renamed = await runtime.client.patch(f"/api/departments/{department_id}", headers=headers, json={"name": "产品研发部"})
        assert renamed.json()["data"]["name"] == "产品研发部"
        for path in (f"/api/users/{uuid4()}", f"/api/departments/{uuid4()}"):
            assert (await runtime.client.get(path, headers=headers)).status_code == 404
        assert (await runtime.client.put(f"/api/departments/{department_id}/administrators/{user.id}", headers=headers)).json()["code"] == 40907
        await runtime.client.post(f"/api/departments/{department_id}/members", headers=headers, json={"username": user.username})
        for _ in range(2):
            assert (await runtime.client.put(f"/api/departments/{department_id}/administrators/{user.id}", headers=headers)).status_code == 200
        for _ in range(2):
            assert (await runtime.client.delete(f"/api/departments/{department_id}/administrators/{user.id}", headers=headers)).status_code == 200
        assert (await runtime.client.get("/api/auth/me", headers=user_headers)).json()["data"]["department"]["id"] == department_id
        for _ in range(2):
            assert (await runtime.client.put(f"/api/users/{user.id}/super-admin", headers=headers)).status_code == 200
        assert (await runtime.client.get("/api/users", headers=user_headers)).status_code == 200
        for _ in range(2):
            assert (await runtime.client.delete(f"/api/users/{user.id}/super-admin", headers=headers)).status_code == 200
        assert (await runtime.client.get("/api/users", headers=user_headers)).status_code == 403
        async with runtime.database.sessions() as session:
            role = await repository.role_by_code(session, "user")
            permission = await session.scalar(select(Permission).where(Permission.code == "model:use"))
        invalid = [
            UserRole(user_id=user.id, role_id=role.id),
            UserRole(user_id=uuid4(), role_id=role.id),
            Role(code="invalid", name="非法绑定", binding_scope="self"),
            RolePermission(role_id=role.id, permission_id=permission.id, scope_type="unknown"),
            Department(name="  "),
        ]
        for row in invalid:
            with pytest.raises(IntegrityError):
                async with runtime.database.sessions.begin() as session:
                    session.add(row)
        async with runtime.database.sessions.begin() as session:
            target = await session.get(User, user.id)
            with pytest.raises(RequestError):
                await AuthorizationService(runtime.database).bind(session, target, "department_admin", uuid4())


async def test_delete_department_rolls_back_all_members_and_roles_on_failure(postgres_settings):
    """删除最终 SQL 失败时，前面已执行的授权撤销和解除归属必须一起回滚。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        user, _ = await account(runtime.auth)
        created = await runtime.client.post("/api/departments", headers=headers, json={"name": "回滚测试部"})
        did = created.json()["data"]["id"]
        await runtime.client.post(f"/api/departments/{did}/members", headers=headers, json={"username": user.username})
        await runtime.client.put(f"/api/departments/{did}/administrators/{user.id}", headers=headers)
        actor = await identity(runtime, headers)

        def fail_final_delete(connection, cursor, statement, parameters, context, executemany):
            """只打断最后删除部门的 SQL，前面真实更新已经执行，退出后移除监听。"""
            if statement.startswith("DELETE FROM departments"):
                raise RuntimeError("模拟最终删除失败")

        engine = runtime.database.engine.sync_engine
        event.listen(engine, "before_cursor_execute", fail_final_delete)
        try:
            with pytest.raises(RuntimeError, match="模拟最终删除失败"):
                await DepartmentService(runtime.database).delete(actor, uuid_from(did))
        finally:
            event.remove(engine, "before_cursor_execute", fail_final_delete)
        async with runtime.database.sessions() as session:
            assert (await session.get(User, user.id)).department_id == uuid_from(did)
            assert await session.get(Department, uuid_from(did)) is not None
            assert await session.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.department_id == uuid_from(did))) is not None


def uuid_from(value):
    """将接口 UUID 文本转换为数据库主键，避免测试依赖驱动的隐式类型转换。"""
    from uuid import UUID
    return UUID(value)


@pytest.mark.parametrize("operation", ["disable", "password"])
async def test_login_cannot_issue_current_credentials_after_concurrent_change(postgres_settings, monkeypatch, operation):
    """密码校验完成前发生停用或改密，登录不能把旧密码验证结果签发成当前凭据。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        user, _ = await account(runtime.auth)
        actor = await identity(runtime, headers)
        service = UserManagementService(runtime.database)
        entered, release = asyncio.Event(), asyncio.Event()
        from app.services import auth as auth_module
        original_run = auth_module.to_thread.run_sync

        async def run_controlled(function, *args, **kwargs):
            """仅在登录校验之后暂停，其他密码哈希仍通过原线程工具运行。"""
            result = await original_run(function, *args, **kwargs)
            if function == runtime.auth.passwords.verify:
                entered.set()
                await release.wait()
            return result

        monkeypatch.setattr("app.services.auth.to_thread.run_sync", run_controlled)
        task = asyncio.create_task(runtime.auth.login(LoginRequest(username=user.username, password="password-with-spaces ")))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if operation == "disable":
                await service.set_active(actor, user.id, False)
            else:
                await service.reset_password(actor, user.id, PasswordReset(password="new-password-value"))
            release.set()
            with pytest.raises(RequestError) as rejected:
                await asyncio.wait_for(task, 10)
            assert rejected.value.error_code is ErrorCode.INVALID_CREDENTIALS
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
