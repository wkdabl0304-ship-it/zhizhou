"""会话业务服务：所有权、游标读取、软删除、轮次快照及 SSE 生命周期。

公开历史只由白名单事件构造，与模型 checkpoint 分开提交；短事务不跨越模型等待。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID, uuid4

import anyio

from app.agents.agent import ChatAgent
from app.db.business import BusinessDatabase
from app.db.locks import ConversationLocks
from app.errors.codes import ErrorCode
from app.errors.exceptions import AppError, RequestError
from app.models import Conversation
from app.repositories import conversations as repository
from app.schemas.chat import ChatAgentEvent, ChatDelta, ChatResponse, ChatStart
from app.schemas.conversations import (
    ConversationContent,
    ConversationInfo,
    ConversationList,
    TurnInfo,
)
from app.services.cursors import (
    ConversationCursor,
    TurnCursor,
    decode_cursor,
    encode_cursor,
)

logger = logging.getLogger(__name__)


@dataclass
class PreparedChat:
    """已提交输入的执行上下文；正文缓冲只属于当前请求，不保存 ORM Session。"""

    conversation_id: UUID
    turn_id: UUID
    message: str
    is_new: bool
    public_events: list[dict] = field(default_factory=list)
    terminal: bool = False


class ConversationService:
    """组织会话业务，所有访问都要求传入经过认证的用户 ID。"""

    def __init__(self, database: BusinessDatabase) -> None:
        """保存 Session 工厂与跨进程锁，不在实例中持有请求级数据库事务。"""
        self.database = database
        self.locks = ConversationLocks(database.lock_engine)

    async def require_owned(self, user_id: UUID, conversation_id: UUID) -> None:
        """在取得执行锁前核验所有权，防止陌生用户用猜测 ID 干扰他人的执行锁。"""
        async with self.database.sessions() as session:
            if await repository.owned(session, user_id, conversation_id) is None:
                raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)

    async def list_recent(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> ConversationList:
        """返回最近会话及继续向前读取的游标，不进行 COUNT 或 OFFSET 查询。"""
        before = None
        if cursor is not None:
            parsed = decode_cursor(cursor, ConversationCursor)
            if parsed.user_id != user_id:
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            before = (parsed.at, parsed.id)
        async with self.database.sessions() as session:
            rows = await repository.recent(session, user_id, limit + 1, before)
        selected = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = selected[-1]
            next_cursor = encode_cursor(
                ConversationCursor(
                    version=1,
                    kind="conversations",
                    user_id=user_id,
                    at=last.last_message_at,
                    id=last.id,
                )
            )
        return ConversationList(
            items=[ConversationInfo.model_validate(row) for row in selected],
            next_cursor=next_cursor,
        )

    async def content(
        self, user_id: UUID, conversation_id: UUID, limit: int, cursor: str | None
    ) -> ConversationContent:
        """读取最近轮次；仅在取得非阻塞执行锁时修复遗留运行状态。"""
        await self.require_owned(user_id, conversation_id)
        before_seq = None
        if cursor is not None:
            parsed = decode_cursor(cursor, TurnCursor)
            if parsed.user_id != user_id or parsed.conversation_id != conversation_id:
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            before_seq = parsed.seq
        await self.recover_one(conversation_id)
        async with self.database.sessions() as session:
            conversation = await repository.owned(session, user_id, conversation_id)
            if conversation is None:
                raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
            rows = await repository.turns(
                session, conversation_id, limit + 1, before_seq
            )
            selected = rows[:limit]
            next_cursor = None
            if len(rows) > limit:
                next_cursor = encode_cursor(
                    TurnCursor(
                        version=1,
                        kind="turns",
                        user_id=user_id,
                        conversation_id=conversation_id,
                        seq=selected[-1].seq,
                    )
                )
            return ConversationContent(
                conversation=ConversationInfo.model_validate(conversation),
                items=[TurnInfo.model_validate(row) for row in reversed(selected)],
                next_cursor=next_cursor,
            )

    async def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        """取得同一执行锁后幂等软删除；生成期间拒绝删除，也不移除 checkpoint。"""
        async with self.database.sessions() as session:
            if (
                await repository.owned(
                    session, user_id, conversation_id, include_deleted=True
                )
                is None
            ):
                raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
        async with self.locks.hold(conversation_id) as acquired:
            if not acquired:
                raise RequestError(ErrorCode.CONVERSATION_BUSY)
            async with self.database.sessions.begin() as session:
                conversation = await repository.owned(
                    session, user_id, conversation_id, include_deleted=True
                )
                if conversation is None:
                    raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
                if conversation.deleted_at is None:
                    conversation.deleted_at = datetime.now(UTC)

    async def recover_one(self, conversation_id: UUID) -> None:
        """不会等待活跃生成；只有确实没有执行者时才中断遗留轮次。"""
        async with self.locks.hold(conversation_id) as acquired:
            if acquired:
                async with self.database.sessions.begin() as session:
                    await repository.interrupt_running(
                        session, conversation_id, datetime.now(UTC)
                    )

    async def recover(self) -> None:
        """启动时检查遗留运行轮次；其他进程正在处理的会话不会被修改。"""
        async with self.database.sessions() as session:
            ids = await repository.running_conversations(session)
        for conversation_id in ids:
            await self.recover_one(conversation_id)

    @asynccontextmanager
    async def prepare(
        self, user_id: UUID, message: str, conversation_id: UUID | None
    ) -> AsyncIterator[PreparedChat]:
        """建立请求级执行上下文，先提交用户输入，再让路由建立 SSE。

        FastAPI request scope 在响应发送结束后退出本上下文；即使断开发生在首个
        事件之前，也会标记中断并释放锁。新会话与首轮输入在同一事务中创建。
        """
        is_new = conversation_id is None
        if not is_new:
            await self.require_owned(user_id, conversation_id)
        conversation_id = conversation_id or uuid4()
        async with self.locks.hold(conversation_id) as acquired:
            if not acquired:
                raise RequestError(ErrorCode.CONVERSATION_BUSY)
            async with self.database.sessions.begin() as session:
                if is_new:
                    conversation = Conversation(
                        id=conversation_id, user_id=user_id, title=message.strip()[:24]
                    )
                    session.add(conversation)
                    await session.flush()
                else:
                    conversation = await repository.owned(
                        session, user_id, conversation_id
                    )
                    if conversation is None:
                        raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
                await repository.interrupt_running(
                    session, conversation_id, datetime.now(UTC)
                )
                turn = await repository.add_turn(
                    session, conversation, message, datetime.now(UTC)
                )
                prepared = PreparedChat(conversation_id, turn.id, message, is_new)
            try:
                yield prepared
            finally:
                if not prepared.terminal:
                    # 清理失败交给下次访问时的恢复，不覆盖原始取消或执行异常。
                    with anyio.CancelScope(shield=True):
                        try:
                            async with asyncio.timeout(5):
                                await self.persist(prepared, status="interrupted")
                        except Exception:
                            logger.exception(
                                "保存中断轮次失败 conversation_id=%s turn_id=%s",
                                conversation_id,
                                prepared.turn_id,
                            )

    async def persist(
        self,
        prepared: PreparedChat,
        *,
        status: str = "running",
        response: ChatResponse | None = None,
        error_code: int | None = None,
    ) -> None:
        """提交公开快照；成功提交终止状态后才改变内存标记，失败不能假称已完成。"""
        now = datetime.now(UTC)
        values = {
            "public_events": deepcopy(prepared.public_events),
            "status": status,
            "updated_at": now,
            "error_code": error_code,
        }
        if status != "running":
            values["finished_at"] = now
        if response is not None:
            values["assistant_content"] = response.reply
            values["assistant_message_id"] = response.message_id
            values["public_events"] = [
                item
                for item in values["public_events"]
                if not (
                    item["event"] == "delta"
                    and item["data"]["message_id"] == response.message_id
                )
            ]
        async with self.database.sessions.begin() as session:
            await repository.save_turn(session, prepared.turn_id, **values)
        prepared.terminal = status != "running"

    async def stream(
        self, prepared: PreparedChat, agent: ChatAgent
    ) -> AsyncIterator[ChatStart | ChatAgentEvent]:
        """执行一次 Agent，合并正文快照；工具边界立即保存，done 在业务落库后输出。"""
        conversation_id = str(prepared.conversation_id)
        yield ChatStart(
            conversation_id=conversation_id,
            turn_id=prepared.turn_id,
            is_new=prepared.is_new,
        )
        saved_at = monotonic()
        buffered_bytes = 0
        try:
            async with aclosing(
                agent.astream(prepared.message, conversation_id)
            ) as stream:
                async for event in stream:
                    if event.conversation_id != conversation_id:
                        raise ValueError("Agent 事件归属与业务会话不一致")
                    if isinstance(event, ChatResponse):
                        await self.persist(prepared, status="completed", response=event)
                        yield event
                        return
                    data = event.model_dump(mode="json")
                    events = prepared.public_events
                    if (
                        isinstance(event, ChatDelta)
                        and events
                        and events[-1]["event"] == "delta"
                        and events[-1]["data"]["message_id"] == event.message_id
                    ):
                        events[-1]["data"]["text"] += event.text
                    else:
                        events.append({"event": event.event, "data": data})
                    if isinstance(event, ChatDelta):
                        buffered_bytes += len(event.text.encode("utf-8"))
                    if (
                        not isinstance(event, ChatDelta)
                        or buffered_bytes >= 16384
                        or monotonic() - saved_at >= 1
                    ):
                        await self.persist(prepared)
                        buffered_bytes = 0
                        saved_at = monotonic()
                    yield event
            raise ValueError("Agent 没有交付最终回答")
        except Exception as exc:
            code = (
                exc.error_code.code
                if isinstance(exc, AppError)
                else ErrorCode.CHAT_FAILED.code
            )
            try:
                await self.persist(prepared, status="failed", error_code=code)
            except Exception:
                logger.exception(
                    "保存失败轮次异常 conversation_id=%s turn_id=%s",
                    conversation_id,
                    prepared.turn_id,
                )
            raise
