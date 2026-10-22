"""会话与轮次 ORM 仓储；所有目录访问包含用户归属，提交和执行锁由服务管理。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatTurn, Conversation


async def owned(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
    *,
    include_deleted: bool = False,
) -> Conversation | None:
    """同时校验会话 ID 与用户，默认排除软删除记录；删除幂等检查可包含已删除项。"""
    statement = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if not include_deleted:
        statement = statement.where(Conversation.deleted_at.is_(None))
    return await session.scalar(statement)


async def recent(
    session: AsyncSession,
    user_id: UUID,
    limit: int,
    before: tuple[datetime, UUID] | None,
) -> list[Conversation]:
    """按复合键读取最近会话，用严格小于边界避免同时间记录重复。"""
    statement = select(Conversation).where(
        Conversation.user_id == user_id, Conversation.deleted_at.is_(None)
    )
    if before is not None:
        statement = statement.where(
            tuple_(Conversation.last_message_at, Conversation.id) < tuple_(*before)
        )
    result = await session.scalars(
        statement.order_by(
            Conversation.last_message_at.desc(), Conversation.id.desc()
        ).limit(limit)
    )
    return list(result)


async def turns(
    session: AsyncSession, conversation_id: UUID, limit: int, before_seq: int | None
) -> list[ChatTurn]:
    """在服务已核验归属后读取最近轮次，结果暂为倒序，响应层再反转展示。"""
    statement = select(ChatTurn).where(ChatTurn.conversation_id == conversation_id)
    if before_seq is not None:
        statement = statement.where(ChatTurn.seq < before_seq)
    return list(
        await session.scalars(statement.order_by(ChatTurn.seq.desc()).limit(limit))
    )


async def add_turn(
    session: AsyncSession, conversation: Conversation, message: str, now: datetime
) -> ChatTurn:
    """持会话执行锁时分配下一个序号，并更新会话的最近用户消息时间。"""
    seq = await session.scalar(
        select(func.coalesce(func.max(ChatTurn.seq), 0)).where(
            ChatTurn.conversation_id == conversation.id
        )
    )
    turn = ChatTurn(
        conversation_id=conversation.id,
        seq=seq + 1,
        user_content=message,
        status="running",
    )
    conversation.last_message_at = now
    conversation.updated_at = now
    session.add(turn)
    await session.flush()
    return turn


async def save_turn(session: AsyncSession, turn_id: UUID, **values: Any) -> None:
    """仅更新尚未终止的轮次，防止断开清理覆盖已提交的成功或失败状态。"""
    await session.execute(
        update(ChatTurn)
        .where(ChatTurn.id == turn_id, ChatTurn.status == "running")
        .values(**values)
    )


async def interrupt_running(
    session: AsyncSession, conversation_id: UUID, now: datetime
) -> None:
    """确认没有活跃执行锁后，将该会话遗留运行轮次标记中断，不自动重放工具。"""
    await session.execute(
        update(ChatTurn)
        .where(
            ChatTurn.conversation_id == conversation_id, ChatTurn.status == "running"
        )
        .values(status="interrupted", updated_at=now, finished_at=now)
    )


async def running_conversations(session: AsyncSession) -> list[UUID]:
    """枚举待恢复会话标识，调用层仍需逐个取得执行锁后才能修改状态。"""
    return list(
        await session.scalars(
            select(ChatTurn.conversation_id)
            .where(ChatTurn.status == "running")
            .distinct()
        )
    )
