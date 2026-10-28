"""权限并发边界：部门生命周期竞争及停用期间既有流式请求的完成语义。"""

import asyncio
from uuid import UUID

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department, User, UserRole
from app.services.departments import DepartmentService
from tests.support.fakes.chat import StubChatModel
from tests.support.postgres import account, open_runtime
from tests.support.sse import parse_events

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


@pytest.mark.parametrize("operation", ["delete_join", "assign_remove"])
async def test_department_mutation_races_leave_no_orphan_authority(postgres_settings, operation):
    """删除与加入、任命与移除竞争后，最终成员归属及部门角色必须一致。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        user, _ = await account(runtime.auth)
        response = await runtime.client.post("/api/departments", headers=headers, json={"name": "并发测试部"})
        department_id = UUID(response.json()["data"]["id"])
        actor = await runtime.auth.authenticate(headers["Authorization"].removeprefix("Bearer "))
        service = DepartmentService(runtime.database)
        if operation == "assign_remove":
            await service.add_member(actor, department_id, user.username)
            actions = [service.set_administrator(actor, department_id, user.id, enabled=True),
                       service.remove_member(actor, department_id, user.id)]
        else:
            actions = [service.delete(actor, department_id), service.add_member(actor, department_id, user.username)]
        gate = asyncio.Event()

        async def competing(action):
            """同时释放真实服务操作，由数据库管理锁决定最终串行顺序。"""
            await gate.wait()
            return await action

        tasks = [asyncio.create_task(competing(action)) for action in actions]
        try:
            gate.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
            allowed = ErrorCode.DEPARTMENT_NOT_FOUND if operation == "delete_join" else ErrorCode.TARGET_STATE_CONFLICT
            for result in results:
                if isinstance(result, BaseException):
                    assert isinstance(result, RequestError) and result.error_code is allowed
            assert any(not isinstance(result, BaseException) for result in results)
            async with runtime.database.sessions() as session:
                assert (await session.get(User, user.id)).department_id is None
                assert await session.scalar(select(UserRole).where(UserRole.department_id == department_id)) is None
                if operation == "delete_join":
                    assert await session.get(Department, department_id) is None
        finally:
            gate.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def test_disabling_user_does_not_interrupt_existing_stream_but_blocks_next_request(postgres_settings):
    """账号停用立即约束后续请求，已经开始的 SSE 仍能完成并保存结果。"""
    entered, release = asyncio.Event(), asyncio.Event()

    class HeldModel(StubChatModel):
        """在真实图输出中间暂停，确认管理事务不会跨越模型等待。"""

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            """先发送增量再等待测试释放，退出时由外层图清理模型资源。"""
            yield ChatGenerationChunk(message=AIMessageChunk(content="开始", id="held"))
            entered.set()
            await release.wait()
            yield ChatGenerationChunk(message=AIMessageChunk(content="完成", id="held"))

    async with open_runtime(postgres_settings, HeldModel()) as runtime:
        _, root_headers = await account(runtime.auth, "super_admin")
        user, headers = await account(runtime.auth)
        task = asyncio.create_task(runtime.client.post("/api/chat", headers=headers, json={"message": "等待管理操作"}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            disabled = await asyncio.wait_for(runtime.client.put(f"/api/users/{user.id}/active", headers=root_headers,
                                                                json={"is_active": False}), 5)
            assert disabled.status_code == 200
            assert (await runtime.client.get("/api/auth/me", headers=headers)).status_code == 401
            release.set()
            response = await asyncio.wait_for(task, 10)
            assert parse_events(response)[-1].event == "done"
            assert (await runtime.client.post("/api/chat", headers=headers, json={"message": "后续应拒绝"})).status_code == 401
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
