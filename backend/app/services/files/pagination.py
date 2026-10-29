"""文件目录游标分页；游标只标识位置，不能替代每次请求的授权过滤。"""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import tuple_

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.services.cursors import decode_cursor, encode_cursor


class FileCursor(BaseModel):
    """绑定操作者、当前范围和查询条件的稳定时间游标。"""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    kind: Literal["spaces", "entries"]
    fingerprint: str
    at: AwareDatetime
    id: UUID


async def page(session, statement, entity, user, grants, *, kind, filters, limit, cursor):
    """按创建时间和 UUID 降序分页，拒绝跨用户、目录或授权范围复用游标。"""
    if not 1 <= limit <= 100:
        raise RequestError(ErrorCode.INVALID_ARGUMENT)
    raw = json.dumps({"actor": str(user.id), "department": str(user.department_id),
        "grants": [grant.model_dump(mode="json") for grant in grants], "kind": kind, "filters": filters},
        sort_keys=True, default=str)
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    if cursor is not None:
        position = decode_cursor(cursor, FileCursor)
        if position.kind != kind or position.fingerprint != fingerprint:
            raise RequestError(ErrorCode.INVALID_ARGUMENT)
        statement = statement.where(tuple_(entity.created_at, entity.id) < tuple_(position.at, position.id))
    rows = list((await session.scalars(statement.order_by(entity.created_at.desc(), entity.id.desc()).limit(limit + 1))).all())
    selected = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = selected[-1]
        next_cursor = encode_cursor(FileCursor(kind=kind, fingerprint=fingerprint, at=last.created_at, id=last.id))
    return selected, next_cursor
