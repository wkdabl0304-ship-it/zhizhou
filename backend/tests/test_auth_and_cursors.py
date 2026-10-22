"""无需数据库的认证输入、业务会话协议、游标和公开快照边界回归。"""

import asyncio
import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from chat_fakes import GraphStub
from pydantic import ValidationError
from service_fakes import MemoryConversationService

from app.agents.agent import ChatAgent
from app.errors.codes import ErrorCode
from app.errors.exceptions import RequestError
from app.schemas.auth import RegisterRequest
from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse
from app.services.conversations import PreparedChat
from app.services.cursors import (
    ConversationCursor,
    TurnCursor,
    decode_cursor,
    encode_cursor,
)


def test_registration_normalizes_username_but_preserves_password():
    """账号去空格并转小写，密码空格保留，默认普通用户且不泄露密码 repr。"""
    body = RegisterRequest(username="  ALIce_1 ", password=" secret with spaces ")
    assert body.username == "alice_1" and body.password == " secret with spaces "
    assert body.role == "user" and body.password not in repr(body)
    for username in ["ab", "x" * 33, "用户账号", "a-b", "a b"]:
        with pytest.raises(ValidationError):
            RegisterRequest(username=username, password="password-123")
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="password-123", role="admin")


@pytest.mark.parametrize(
    "body",
    [
        {"message": "hi", "thread_id": str(uuid4())},
        {"message": "hi", "conversation_id": ""},
        {"message": "hi", "conversation_id": "unknown"},
        {"message": " \n"},
    ],
)
def test_chat_rejects_legacy_names_and_invalid_business_id(body):
    """旧字段不能被静默忽略并意外创建新会话，非法业务标识和空正文必须拒绝。"""
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(body)


def test_new_chat_optional_id_and_scoped_cursor_roundtrip():
    """首次聊天允许缺省 ID，目录及历史游标保留版本、类型、归属和排序键。"""
    assert ChatRequest(message="你好").conversation_id is None
    assert ChatRequest(message="你好", conversation_id=None).conversation_id is None
    user_id, conversation_id = uuid4(), uuid4()
    cursor = ConversationCursor(
        version=1,
        kind="conversations",
        user_id=user_id,
        at=datetime.now(UTC),
        id=conversation_id,
    )
    assert decode_cursor(encode_cursor(cursor), ConversationCursor) == cursor
    history = TurnCursor(
        version=1, kind="turns", user_id=user_id, conversation_id=conversation_id, seq=5
    )
    assert decode_cursor(encode_cursor(history), TurnCursor) == history
    with pytest.raises(RequestError):
        decode_cursor(encode_cursor(history), ConversationCursor)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "!",
        "a" * 2049,
        "not_base64_",
        base64.urlsafe_b64encode(b"{}").decode().rstrip("="),
    ],
)
def test_invalid_cursor_has_only_safe_error(value):
    """编码、长度及结构错误均转成中央参数错误，不把解析细节返回接口。"""
    with pytest.raises(RequestError) as error:
        decode_cursor(value, TurnCursor)
    assert error.value.error_code is ErrorCode.INVALID_ARGUMENT


def test_stream_waits_for_final_business_commit_and_coalesces_text():
    """done 必须等待业务提交；相邻正文合并，不能逐 token 形成历史记录。"""

    async def scenario():
        """阻塞最终提交，验证已看到增量但看不到完成事件，随后放行。"""
        service = MemoryConversationService()
        real_persist = service.persist
        entered, release = asyncio.Event(), asyncio.Event()

        async def persist(prepared, **kwargs):
            """在成功提交前暂停，模拟数据库提交尚未确认。"""
            if kwargs.get("status") == "completed":
                entered.set()
                await release.wait()
            await real_persist(prepared, **kwargs)

        service.persist = persist
        prepared = PreparedChat(uuid4(), uuid4(), "你好", True)
        observed = []

        async def consume():
            """保存流事件，观察完成时序而不依赖真实时间长短。"""
            async for event in service.stream(
                prepared, ChatAgent(GraphStub("你好世界"))
            ):
                observed.append(event)

        task = asyncio.create_task(consume())
        await entered.wait()
        assert any(isinstance(event, ChatDelta) for event in observed)
        assert not any(isinstance(event, ChatResponse) for event in observed)
        assert (
            len(prepared.public_events) == 1
            and prepared.public_events[0]["data"]["text"] == "你好世界"
        )
        release.set()
        await task
        assert isinstance(observed[-1], ChatResponse) and prepared.terminal

    asyncio.run(asyncio.wait_for(scenario(), 5))


def test_openapi_exposes_only_business_conversation_ids_and_bearer_auth():
    """正式 OpenAPI 不再承诺旧字段，首次聊天不要求 ID，也不暴露创建会话接口。"""
    from app.main import app

    schema = app.openapi()
    assert "thread_id" not in json.dumps(schema)
    assert schema["components"]["schemas"]["ChatRequest"]["required"] == ["message"]
    assert "conversation_id" in schema["components"]["schemas"]["ConversationInfo"]["properties"]
    assert "post" not in schema["paths"]["/api/conversations"]
    assert schema["paths"]["/api/chat"]["post"]["security"] == [{"HTTPBearer": []}]
