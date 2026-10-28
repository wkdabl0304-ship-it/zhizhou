"""用户管理 API：只接受服务端认证身份，账号资料采用白名单，业务权限由服务复查。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_user_management_service
from app.models import User
from app.schemas.authorization import ActiveUpdate, ManagedUser, Page, PasswordReset
from app.schemas.response import ApiResponse, success
from app.services.users import UserManagementService

router = APIRouter(prefix="/users", tags=["用户管理"])
type Actor = Annotated[User, Depends(get_current_user)]
type Service = Annotated[UserManagementService, Depends(get_user_management_service)]


@router.get("", response_model=ApiResponse[Page[ManagedUser]])
async def users(actor: Actor, service: Service, search: Annotated[str | None, Query(max_length=32)] = None,
                is_active: bool | None = None, department_id: UUID | None = None, unassigned: bool = False,
                limit: Annotated[int, Query(ge=1, le=100)] = 20,
                cursor: Annotated[str | None, Query(max_length=2048)] = None):
    """分页搜索账号资料，支持启停、部门及无部门筛选，不读取个人内容。"""
    return success(await service.list(actor, search=search, is_active=is_active, department_id=department_id,
                                      unassigned=unassigned, limit=limit, cursor=cursor))


@router.get("/{user_id}", response_model=ApiResponse[ManagedUser])
async def user(user_id: UUID, actor: Actor, service: Service):
    """读取单个账号的管理资料。"""
    return success(await service.get(actor, user_id))


@router.put("/{user_id}/active", response_model=ApiResponse[ManagedUser])
async def active(user_id: UUID, body: ActiveUpdate, actor: Actor, service: Service):
    """启用或停用账号，停用同时撤销既有令牌。"""
    return success(await service.set_active(actor, user_id, body.is_active))


@router.put("/{user_id}/password", response_model=ApiResponse[None])
async def password(user_id: UUID, body: PasswordReset, actor: Actor, service: Service):
    """直接设置新密码并撤销旧令牌，不改变账号启停状态。"""
    await service.reset_password(actor, user_id, body)
    return success(None)


@router.put("/{user_id}/super-admin", response_model=ApiResponse[None])
async def assign_super_admin(user_id: UUID, actor: Actor, service: Service):
    """幂等授予启用账号全局超级管理员角色。"""
    await service.set_super_admin(actor, user_id, enabled=True)
    return success(None)


@router.delete("/{user_id}/super-admin", response_model=ApiResponse[None])
async def revoke_super_admin(user_id: UUID, actor: Actor, service: Service):
    """撤销全局超级管理员角色，并保护最后一名可用管理员。"""
    await service.set_super_admin(actor, user_id, enabled=False)
    return success(None)
