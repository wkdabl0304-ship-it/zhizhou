"""有版本及归属范围的 Base64URL 游标；查询条件仍独立强制限定当前用户。"""

import base64
import binascii
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.errors.codes import ErrorCode
from app.errors.exceptions import RequestError


class ConversationCursor(BaseModel):
    """目录游标包含稳定的复合排序键及用户范围，不支持跨用户读取。"""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    kind: Literal["conversations"]
    user_id: UUID
    at: AwareDatetime
    id: UUID


class TurnCursor(BaseModel):
    """历史游标只允许在当前用户的指定会话中继续读取更小的轮次序号。"""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    kind: Literal["turns"]
    user_id: UUID
    conversation_id: UUID
    seq: int = Field(gt=0, strict=True)


def encode_cursor(cursor: BaseModel) -> str:
    """将已校验的游标编码为无填充的 URL 安全文本，不把编码当作访问授权。"""
    return (
        base64.urlsafe_b64encode(cursor.model_dump_json().encode()).decode().rstrip("=")
    )


def decode_cursor[T: BaseModel](value: str, schema: type[T]) -> T:
    """严格校验长度、Base64URL 和字段结构，失败统一返回参数错误而非内部解析细节。"""
    try:
        if (
            not value
            or len(value) > 2048
            or any(
                char
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for char in value
            )
        ):
            raise ValueError("无效游标编码")
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        return schema.model_validate_json(raw)
    except ValueError, ValidationError, binascii.Error:
        raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
