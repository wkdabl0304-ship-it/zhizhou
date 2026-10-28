"""部门 API：资料管理、成员直接加入移除及管理员任免，不提供消息或邀请确认流程。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_department_service
from app.models import User
from app.schemas.authorization import DepartmentInfo, DepartmentWrite, MemberAdd, MemberInfo, Page
from app.schemas.response import ApiResponse, success
from app.services.departments import DepartmentService

router = APIRouter(prefix="/departments", tags=["部门管理"])
type Actor = Annotated[User, Depends(get_current_user)]
type Service = Annotated[DepartmentService, Depends(get_department_service)]
type Limit = Annotated[int, Query(ge=1, le=100)]
type Cursor = Annotated[str | None, Query(max_length=2048)]


@router.get("", response_model=ApiResponse[Page[DepartmentInfo]])
async def departments(actor: Actor, service: Service, limit: Limit = 20, cursor: Cursor = None):
    """分页列出授权范围覆盖的部门。"""
    return success(await service.list(actor, limit=limit, cursor=cursor))


@router.post("", response_model=ApiResponse[DepartmentInfo])
async def create(body: DepartmentWrite, actor: Actor, service: Service):
    """创建名称唯一的部门，不隐式加入成员或任命管理员。"""
    return success(await service.save(actor, body))


@router.get("/{department_id}", response_model=ApiResponse[DepartmentInfo])
async def department(department_id: UUID, actor: Actor, service: Service):
    """读取可见部门资料，其他部门与不存在的部门使用相同错误。"""
    return success(await service.get(actor, department_id))


@router.patch("/{department_id}", response_model=ApiResponse[DepartmentInfo])
async def rename(department_id: UUID, body: DepartmentWrite, actor: Actor, service: Service):
    """修改部门名称，不修改成员归属或角色。"""
    return success(await service.save(actor, body, department_id))


@router.delete("/{department_id}", response_model=ApiResponse[None])
async def delete(department_id: UUID, actor: Actor, service: Service):
    """解除全部成员归属和部门授权后删除部门，保留账号和个人内容。"""
    await service.delete(actor, department_id)
    return success(None)


@router.get("/{department_id}/members", response_model=ApiResponse[Page[MemberInfo]])
async def members(department_id: UUID, actor: Actor, service: Service,
                  search: Annotated[str | None, Query(max_length=32)] = None, limit: Limit = 20, cursor: Cursor = None):
    """分页读取指定部门成员的最小账号资料，可在部门内搜索用户名。"""
    return success(await service.members(actor, department_id, search=search, limit=limit, cursor=cursor))


@router.post("/{department_id}/members", response_model=ApiResponse[MemberInfo])
async def add_member(department_id: UUID, body: MemberAdd, actor: Actor, service: Service):
    """按完整用户名立即加入已有启用账号，无需确认和通知。"""
    return success(await service.add_member(actor, department_id, body.username))


@router.delete("/{department_id}/members/{user_id}", response_model=ApiResponse[None])
async def remove_member(department_id: UUID, user_id: UUID, actor: Actor, service: Service):
    """移除成员及该部门授权，保留基础与全局角色。"""
    await service.remove_member(actor, department_id, user_id)
    return success(None)


@router.put("/{department_id}/administrators/{user_id}", response_model=ApiResponse[None])
async def assign_administrator(department_id: UUID, user_id: UUID, actor: Actor, service: Service):
    """幂等任命本部门启用成员为部门管理员。"""
    await service.set_administrator(actor, department_id, user_id, enabled=True)
    return success(None)


@router.delete("/{department_id}/administrators/{user_id}", response_model=ApiResponse[None])
async def revoke_administrator(department_id: UUID, user_id: UUID, actor: Actor, service: Service):
    """幂等撤销该部门管理员角色，允许部门暂时没有管理员。"""
    await service.set_administrator(actor, department_id, user_id, enabled=False)
    return success(None)
