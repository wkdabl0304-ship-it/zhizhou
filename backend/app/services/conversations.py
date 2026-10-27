"""会话业务服务：所有权、标题编排、游标读取、软删除、轮次快照及 SSE 生命周期。

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
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import AppError, RequestError
from app.models import Conversation
from app.repositories import conversations as repository
from app.schemas.chat import ChatAgentEvent, ChatDelta, ChatResponse, ChatStart
from app.schemas.conversations import (
    ConversationContent,
    ConversationInfo,
    ConversationList,
    ConversationTitleUpdate,
    TurnInfo,
    normalize_title,
)
from app.services.cursors import (
    ConversationCursor,
    TurnCursor,
    decode_cursor,
    encode_cursor,
)
from app.llm.types import ModelSnapshot
from app.llm.runtime import ConfiguredChatAgent
from app.services.model_config import ModelConfigService
from app.services.conversation_titles import ConversationTitleService
from app.schemas.model_selection import ModelSelection, ModelSelectionUpdate

logger = logging.getLogger(__name__)

# 整个标题阶段（读取、模型调用、保存）共用期限，避免首轮结束无界等待。
TITLE_TIMEOUT_SECONDS = 15


@dataclass
class PreparedChat:
    """已提交输入的执行上下文；正文缓冲只属于当前请求，不保存 ORM Session。"""

    conversation_id: UUID
    turn_id: UUID
    message: str
    is_new: bool
    public_events: list[dict] = field(default_factory=list)
    terminal: bool = False
    model_runtime: ModelSnapshot | None = field(default=None, repr=False)
    model_selection: ModelSelection | None = None
    model_selection_version: int = 1
    user_id: UUID | None = None


class ConversationService:
    """组织会话业务，所有访问都要求传入经过认证的用户 ID。"""

    def __init__(self, database: BusinessDatabase, *, model_config: ModelConfigService | None = None,
                 title_generator: ConversationTitleService | None = None) -> None:
        """初始化会话服务使用的数据库入口和执行锁管理器。

        服务对象可以跨请求复用，但不持有请求级 Session；每次读取或写入
        分别创建短事务，模型生成期间只保留专用连接上的跨进程会话锁。
        正式入口注入 model_config 和 title_generator；纯会话测试可省略模型依赖。
        """
        self.database = database
        self.model_config = model_config
        self.title_generator = title_generator
        self.locks = ConversationLocks(database.lock_engine)

    async def update_title(self, user_id: UUID, conversation_id: UUID, body: ConversationTitleUpdate) -> ConversationInfo:
        """立即保存自己的手动标题，允许生成期间修改并永久停止自动覆盖。"""
        async with self.database.sessions.begin() as session:
            row = await repository.update_title(session, user_id, conversation_id, body.title, source="manual")
            if row is None:
                raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
            return (await self._conversation_infos(session, [row]))[0]

    async def _generate_title(self, prepared: PreparedChat, response: ChatResponse) -> None:
        """为成功回答补齐正式标题，失败保留临时标题且不改变已完成的聊天结果。

        读取与保存各用短事务；模型等待期间不占用事务，保存条件再次检查来源。
        取消不被吞掉，供应商负责资源关闭；日志只包含标识与异常类型，避免泄露模型输入。
        """
        if prepared.model_runtime is None or prepared.user_id is None or self.title_generator is None:
            return
        try:
            async with asyncio.timeout(TITLE_TIMEOUT_SECONDS):
                async with self.database.sessions() as session:
                    question = await repository.title_question(session, prepared.user_id, prepared.conversation_id)
                if question is None:
                    return
                title = await self.title_generator.generate(prepared.model_runtime, question, response.reply)
                async with self.database.sessions.begin() as session:
                    await repository.update_title(session, prepared.user_id, prepared.conversation_id, title, source="auto")
        except Exception as error:
            logger.warning("生成会话标题失败 conversation_id=%s turn_id=%s error_type=%s",
                           prepared.conversation_id, prepared.turn_id, type(error).__name__)

    async def require_owned(self, user_id: UUID, conversation_id: UUID) -> None:
        """确认指定会话存在、未删除且属于当前用户。

        user_id 来自认证结果。会话不存在、已删除或属于他人时均抛出
        CONVERSATION_NOT_FOUND；在申请执行锁前调用，避免越权请求干扰他人。
        """
        async with self.database.sessions() as session:
            if await repository.owned(session, user_id, conversation_id) is None:
                raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)

    async def _conversation_infos(self, session, rows) -> list[ConversationInfo]:
        """批量补齐选择失效原因，使配置删除和停用不影响历史接口可读性。"""
        issues = await self.model_config.selections.issues(session, rows) if self.model_config is not None else {}
        return [ConversationInfo.model_validate(row).model_copy(update={"model_selection_issue": issues.get(row.id)}) for row in rows]

    async def update_model_selection(self, user_id: UUID, conversation_id: UUID, body: ModelSelectionUpdate) -> ConversationInfo:
        """立即保存自己的会话选择，复用执行锁和独立版本防止并发覆盖。

        配置验证和保存均在短事务内完成，失败不会改变旧选择；不更新最近消息时间，
        也不解密凭据或调用供应商。生成期间与删除、续聊竞争同一跨进程锁。
        """
        await self.require_owned(user_id, conversation_id)
        async with self.locks.hold(conversation_id) as acquired:
            if not acquired:
                raise RequestError(ErrorCode.CONVERSATION_BUSY)
            async with self.database.sessions.begin() as session:
                conversation = await repository.owned(session, user_id, conversation_id)
                if conversation is None:
                    raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
                if conversation.model_selection_version != body.model_selection_version:
                    raise RequestError(ErrorCode.MODEL_SELECTION_VERSION_CONFLICT)
                if self.model_config is None:
                    raise RuntimeError("模型选择服务尚未装配")
                await self.model_config.selections.validate(session, body.model_selection)
                conversation.model_selection = body.model_selection.model_dump(mode="json")
                conversation.model_selection_version += 1
                conversation.updated_at = datetime.now(UTC)
                await session.flush()
                return ConversationInfo.model_validate(conversation)

    async def list_recent(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> ConversationList:
        """分页返回当前用户最近使用的会话列表。

        limit 指定本批数量，cursor 为空时从最新会话开始，否则按其中的
        时间和 ID 继续读取更早记录。多取一条判断是否还有下一批，不执行
        COUNT 或 OFFSET 查询；游标属于其他用户时抛出 INVALID_ARGUMENT。
        """
        before = None
        if cursor is not None:
            parsed = decode_cursor(cursor, ConversationCursor)
            if parsed.user_id != user_id:
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            before = (parsed.at, parsed.id)
        async with self.database.sessions() as session:
            rows = await repository.recent(session, user_id, limit + 1, before)
            infos = await self._conversation_infos(session, rows[:limit])
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
            items=infos,
            next_cursor=next_cursor,
        )

    async def content(
        self, user_id: UUID, conversation_id: UUID, limit: int, cursor: str | None
    ) -> ConversationContent:
        """分页读取当前用户某个会话的公开聊天历史。

        先核验归属，再按 limit 和可选 cursor 读取较早轮次；每批结果按
        轮次正序展示，并返回会话信息及下一批游标。读取前尝试修复遗留的
        运行状态，但不等待或干扰活跃生成；跨用户或跨会话游标会被拒绝。
        """
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
                conversation=(await self._conversation_infos(session, [conversation]))[0],
                items=[TurnInfo.model_validate(row) for row in reversed(selected)],
                next_cursor=next_cursor,
            )

    async def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        """将当前用户的指定会话标记为已删除，使其不再出现在正常访问中。

        先核验归属，再取得与生成过程相同的执行锁；生成期间返回
        CONVERSATION_BUSY。重复删除不产生额外变化，轮次记录与 checkpoint
        均保留；不存在或不属于该用户的会话统一返回未找到。
        """
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
        """把指定会话已失去执行者的运行轮次修复为中断状态。

        非阻塞地尝试取得执行锁，只有取得后才更新遗留记录；活跃生成持锁
        时直接跳过，不等待它结束，也不自动重放模型或工具调用。
        """
        async with self.locks.hold(conversation_id) as acquired:
            if acquired:
                async with self.database.sessions.begin() as session:
                    await repository.interrupt_running(
                        session, conversation_id, datetime.now(UTC)
                    )

    async def recover(self) -> None:
        """在应用启动时清理上次退出后遗留的运行中轮次。

        先查询含运行轮次的会话，再逐个调用 recover_one；仍由其他进程
        持锁执行的会话保持原状，避免把正常任务误标为中断。
        """
        async with self.database.sessions() as session:
            ids = await repository.running_conversations(session)
        for conversation_id in ids:
            await self.recover_one(conversation_id)

    @asynccontextmanager
    async def prepare(
        self, user_id: UUID, message: str, conversation_id: UUID | None, *,
        model_selection: ModelSelection | None = None, model_selection_version: int | None = None,
    ) -> AsyncIterator[PreparedChat]:
        """为新一轮聊天创建可供 SSE 使用的业务执行上下文。

        user_id 为已认证用户，message 为本轮输入；conversation_id 为空时
        创建新会话，否则核验已有会话归属。持有执行锁后，在短事务中提交
        用户输入并 yield PreparedChat，路由随后才建立 SSE 响应。
        FastAPI request scope 在响应发送结束后退出本上下文；即使断开发生在首个
        事件之前，也会标记中断并释放锁。新会话与首轮输入在同一事务中创建。
        """
        is_new = conversation_id is None
        if (not is_new and model_selection is not None) or (is_new and model_selection_version is not None):
            raise RequestError(ErrorCode.INVALID_ARGUMENT)
        if not is_new:
            await self.require_owned(user_id, conversation_id)
        conversation_id = conversation_id or uuid4()
        async with self.locks.hold(conversation_id) as acquired:
            if not acquired:
                raise RequestError(ErrorCode.CONVERSATION_BUSY)
            async with self.database.sessions.begin() as session:
                if is_new:
                    conversation = Conversation(
                        id=conversation_id, user_id=user_id, title=normalize_title(message)[:24],
                        title_source="provisional", model_selection_version=1
                    )
                else:
                    conversation = await repository.owned(
                        session, user_id, conversation_id
                    )
                    if conversation is None:
                        raise RequestError(ErrorCode.CONVERSATION_NOT_FOUND)
                    if model_selection_version is not None and conversation.model_selection_version != model_selection_version:
                        raise RequestError(ErrorCode.MODEL_SELECTION_VERSION_CONFLICT)
                # 在创建会话或轮次前读取一致模型快照；无效选择不会留下消息或触发上游调用。
                selected = model_selection if is_new else (
                    ModelSelection.model_validate(conversation.model_selection) if conversation.model_selection is not None else None)
                snapshot = await self.model_config.selections.snapshot(session, selected) if self.model_config is not None else None
                if snapshot is not None:
                    selected = ModelSelection(model_configuration_id=snapshot.configuration_id, reasoning=snapshot.reasoning)
                    if conversation.model_selection is None:
                        conversation.model_selection = selected.model_dump(mode="json")
                        if not is_new:
                            conversation.model_selection_version += 1
                if is_new:
                    session.add(conversation)
                    await session.flush()
                # 取得执行锁后才能确认旧 running 轮次已失去执行者，不自动重放工具。
                await repository.interrupt_running(
                    session, conversation_id, datetime.now(UTC)
                )
                turn = await repository.add_turn(
                    session, conversation, message, datetime.now(UTC)
                )
                prepared = PreparedChat(conversation_id, turn.id, message, is_new)
                prepared.user_id = user_id
                prepared.model_runtime = snapshot
                prepared.model_selection = selected
                prepared.model_selection_version = conversation.model_selection_version
                if snapshot is not None:
                    turn.model_snapshot = snapshot.public_snapshot()
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
        """将本轮已公开的过程、回答和执行状态保存到业务历史中。

        prepared 提供当前轮次与过程缓冲，status 指定运行或终止状态；
        response 存在时保存最终回答，并移除过程里对应的临时正文。
        事务成功后才更新内存中的 terminal 标记；写入失败继续抛出异常，
        不能让调用方把尚未落库的结果当作已完成。
        """
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
        self, prepared: PreparedChat, agent: ChatAgent | ConfiguredChatAgent
    ) -> AsyncIterator[ChatStart | ChatAgentEvent]:
        """执行本轮聊天，并向路由逐个提供公开的进度和结果事件。

        prepared 必须来自仍有效的 prepare 上下文。先 yield 开始事件，
        再执行一次 Agent；相邻正文合并为历史快照，工具边界立即保存，
        正文按字节数或时间间隔保存。最终回答提交后尝试补齐标题，再 yield done。
        执行异常会尝试保存失败状态后继续传播；取消后的中断保存由 prepare 负责。
        """
        conversation_id = str(prepared.conversation_id)
        yield ChatStart(
            conversation_id=conversation_id,
            turn_id=prepared.turn_id,
            is_new=prepared.is_new,
            model_selection=prepared.model_selection,
            model_selection_version=prepared.model_selection_version,
        )
        saved_at = monotonic()
        buffered_bytes = 0
        try:
            options = {"snapshot": prepared.model_runtime} if prepared.model_runtime is not None else {}
            async with aclosing(
                agent.astream(prepared.message, conversation_id, **options)
            ) as stream:
                async for event in stream:
                    if event.conversation_id != conversation_id:
                        raise ValueError("Agent 事件归属与业务会话不一致")
                    if isinstance(event, ChatResponse):
                        await self.persist(prepared, status="completed", response=event)
                        await self._generate_title(prepared, event)
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
