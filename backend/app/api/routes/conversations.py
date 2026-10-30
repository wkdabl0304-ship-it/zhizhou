"""用户会话目录、历史游标、标题与模型选择维护及软删除接口；会话由首条聊天创建。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_conversation_service, get_current_user
from app.models import User
from app.schemas.conversations import ConversationContent, ConversationList, ConversationInfo, ConversationTitleUpdate
from app.schemas.model_selection import ModelSelectionUpdate
from app.schemas.response import ApiResponse, success
from app.services.conversations import ConversationService

router = APIRouter(prefix="/conversations", tags=["会话"])


@router.patch("/{conversation_id}/title", response_model=ApiResponse[ConversationInfo])
async def update_title(
    conversation_id: UUID,
    body: ConversationTitleUpdate,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
):
    """修改自己的会话标题，允许生成期间保存，手动标题不再被自动生成覆盖。"""
    return success(await service.update_title(user.id, conversation_id, body))


@router.patch("/{conversation_id}/model-selection", response_model=ApiResponse[ConversationInfo])
async def update_model_selection(
    conversation_id: UUID,
    body: ModelSelectionUpdate,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
):
    """按版本保存模型选择；model_selection 为 null 时自动恢复，生成期间拒绝切换。"""
    return success(await service.update_model_selection(user.id, conversation_id, body))


@router.get("", response_model=ApiResponse[ConversationList])
async def recent(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
):
    """首次读取最近会话，携带游标继续向前读取；不接受页码或偏移量。"""
    return success(await service.list_recent(user.id, limit, cursor))


@router.get("/{conversation_id}", response_model=ApiResponse[ConversationContent])
async def content(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
):
    """返回最近的一批轮次及公开过程；每批按时间正序，游标指向更早轮次。"""
    return success(await service.content(user.id, conversation_id, limit, cursor))


@router.delete("/{conversation_id}", response_model=ApiResponse[None])
async def delete(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
):
    """幂等软删除自己的会话，生成期间返回冲突，保留轮次与 checkpoint。"""
    await service.delete(user.id, conversation_id)
    return success(None)
