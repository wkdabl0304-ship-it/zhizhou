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
    """查询属于指定用户的会话，未匹配时返回 None。

    查询同时限定 conversation_id 与 user_id，默认排除软删除记录；
    include_deleted 仅在需要识别重复删除等场景时启用。本函数不提交事务。
    """
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
    """读取指定用户最近使用的一批未删除会话。

    按最近消息时间、会话 ID 倒序返回至多 limit 条；before 不为空时
    继续读取该复合排序键之前的记录，避免同时间记录跨批重复。
    """
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
    """读取指定会话最近的一批问答轮次。

    返回至多 limit 条、按 seq 倒序排列的记录；before_seq 用于继续向前
    翻阅。调用前服务层必须核验会话归属，返回结果由服务层反转为展示顺序。
    """
    statement = select(ChatTurn).where(ChatTurn.conversation_id == conversation_id)
    if before_seq is not None:
        statement = statement.where(ChatTurn.seq < before_seq)
    return list(
        await session.scalars(statement.order_by(ChatTurn.seq.desc()).limit(limit))
    )


async def add_turn(
    session: AsyncSession, conversation: Conversation, message: str, now: datetime
) -> ChatTurn:
    """为会话新增一轮运行中的问答记录，并返回该记录。

    调用方须持有会话执行锁；在当前最大 seq 后分配序号，保存 message，
    并用 now 更新会话活跃时间。这里只 flush 以取得默认值，事务由服务提交。
    """
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
    """将给定字段写入指定的运行中轮次。

    values 由服务层构造；更新条件要求原状态仍为 running，防止断开清理
    覆盖已经提交的终止结果。本函数执行更新，不提交事务，也不返回更新数量。
    """
    await session.execute(
        update(ChatTurn)
        .where(ChatTurn.id == turn_id, ChatTurn.status == "running")
        .values(**values)
    )


async def interrupt_running(
    session: AsyncSession, conversation_id: UUID, now: datetime
) -> None:
    """将指定会话尚未结束的轮次批量标记为中断。

    调用方须持有执行锁，确认没有其他执行者后再调用；now 同时写入更新和
    结束时间，不自动重放模型或工具。事务提交仍由服务层负责。
    """
    await session.execute(
        update(ChatTurn)
        .where(
            ChatTurn.conversation_id == conversation_id, ChatTurn.status == "running"
        )
        .values(status="interrupted", updated_at=now, finished_at=now)
    )


async def running_conversations(session: AsyncSession) -> list[UUID]:
    """查询仍含运行中轮次的会话 ID，供启动恢复流程使用。

    结果按会话去重，但不代表这些会话已经失去执行者；调用层须逐个取得
    执行锁后才能修改状态。
    """
    return list(
        await session.scalars(
            select(ChatTurn.conversation_id)
            .where(ChatTurn.status == "running")
            .distinct()
        )
    )
