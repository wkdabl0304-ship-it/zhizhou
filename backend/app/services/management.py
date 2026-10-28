"""管理模块共享的范围分页及账号展示，不承担部门和账号状态变更业务。"""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import tuple_

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department, User
from app.repositories.authorization import roles_for
from app.repositories import users
from app.schemas.authorization import DepartmentBrief, ManagedUser, MemberInfo
from app.services.authorization import AuthorizationService
from app.services.cursors import decode_cursor, encode_cursor


class ManagementCursor(BaseModel):
    """管理分页位置；指纹绑定操作者、操作、筛选及当前有效授权，但不授予权限。"""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    kind: Literal["users", "departments", "members"]
    fingerprint: str
    at: AwareDatetime
    id: UUID


async def paginate(session, authorization: AuthorizationService, actor: User, statement, entity, *,
                   kind: str, filters: dict, limit: int, cursor: str | None):
    """按稳定时间与 ID 分页，并拒绝跨用户、筛选或当前授权范围复用游标。"""
    if not 1 <= limit <= 100:
        raise RequestError(ErrorCode.INVALID_ARGUMENT)
    grants = [grant.model_dump(mode="json") for grant in await authorization.grants(session, actor)]
    raw = json.dumps({"actor": str(actor.id), "department": str(actor.department_id), "grants": grants,
                      "kind": kind, "filters": filters}, sort_keys=True, ensure_ascii=False, default=str)
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    if cursor is not None:
        position = decode_cursor(cursor, ManagementCursor)
        if position.kind != kind or position.fingerprint != fingerprint:
            raise RequestError(ErrorCode.INVALID_ARGUMENT)
        statement = statement.where(tuple_(entity.created_at, entity.id) < tuple_(position.at, position.id))
    rows = list((await session.scalars(statement.order_by(entity.created_at.desc(), entity.id.desc()).limit(limit + 1))).all())
    selected = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = selected[-1]
        next_cursor = encode_cursor(ManagementCursor(kind=kind, fingerprint=fingerprint, at=last.created_at, id=last.id))
    return selected, next_cursor


async def managed_user(session, user: User) -> ManagedUser:
    """构造管理账号白名单，角色只展示当前有效绑定，不读取任何个人内容。"""
    department = await session.get(Department, user.department_id) if user.department_id else None
    return ManagedUser(id=user.id, username=user.username, is_active=user.is_active,
        department=DepartmentBrief.model_validate(department) if department else None,
        roles=sorted({row.code for row in await roles_for(session, user.id)}),
        created_at=user.created_at, updated_at=user.updated_at)


async def target_user(session, user_id: UUID) -> User:
    """锁定管理操作的目标账号，不存在时返回统一账号错误，供用户和部门服务复用。"""
    user = await users.by_id(session, user_id, lock=True)
    if user is None:
        raise RequestError(ErrorCode.USER_NOT_FOUND)
    return user


async def member_info(session, user: User) -> MemberInfo:
    """构造部门成员最小资料，仅展示当前部门角色，不公开全局管理员身份和凭据。"""
    return MemberInfo(id=user.id, username=user.username, is_active=user.is_active,
        roles=sorted({row.code for row in await roles_for(session, user.id) if row.department_id is not None}))
