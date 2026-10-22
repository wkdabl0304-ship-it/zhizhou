"""请求模型单元测试：验证账号标准化和聊天输入协议。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.chat import ChatRequest


def test_registration_normalizes_username_but_preserves_password():
    """验证注册输入能正确标准化账号，同时保留密码原文并隐藏敏感字段。

    检查账号去空格和转小写、默认普通用户，以及密码不会出现在模型 repr 中。
    """
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
    """验证聊天输入会拒绝旧协议字段、非法会话标识和空白正文。

    防止旧字段被静默忽略后意外按首次聊天创建新会话。
    """
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(body)


def test_new_chat_allows_omitted_or_null_conversation_id():
    """验证首次聊天可以省略或显式传入空会话 ID。"""
    assert ChatRequest(message="你好").conversation_id is None
    assert ChatRequest(message="你好", conversation_id=None).conversation_id is None
