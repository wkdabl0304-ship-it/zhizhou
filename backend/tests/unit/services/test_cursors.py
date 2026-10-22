"""游标单元测试：验证编码往返、类型隔离和安全错误。"""

import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.services.cursors import ConversationCursor, TurnCursor, decode_cursor, encode_cursor


def test_scoped_cursor_roundtrip():
    """验证两类分页游标完整往返编码，并拒绝错误类型。

    核对版本、类型、用户归属、会话归属和排序键均保留，错误游标类型会被拒绝。
    """
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
    ids=["empty", "illegal-symbol", "over-limit", "invalid-base64", "invalid-shape"],
)
def test_invalid_cursor_has_only_safe_error(value):
    """验证非法分页游标统一转换为安全的参数错误。

    覆盖字符编码、长度和模型结构错误，确保不向接口泄露内部解析细节。
    """
    with pytest.raises(RequestError) as error:
        decode_cursor(value, TurnCursor)
    assert error.value.error_code is ErrorCode.INVALID_ARGUMENT
