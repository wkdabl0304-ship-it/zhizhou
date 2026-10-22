"""用户会话目录、内容游标读取和软删除接口；不提供单独创建会话接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_conversation_service, get_current_user
from app.models import User
from app.schemas.conversations import ConversationContent, ConversationList
from app.schemas.response import ApiResponse, success
from app.services.conversations import ConversationService

router = APIRouter(prefix="/conversations", tags=["会话"])


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
