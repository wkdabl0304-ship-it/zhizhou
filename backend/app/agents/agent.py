"""异步执行 Agent 对话，输出助手文本并按会话隔离完整轮次。

Web 与命令行共用本模块；图负责 checkpoint，HTTP 协议由 API 层编码。
锁仅协调同一事件循环中的单个 Agent 实例，不提供多进程互斥。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from app.errors.codes import ErrorCode
from app.errors.exceptions import AppError, ServiceError, log_app_error
from app.schemas.chat import ChatDelta, ChatResponse

logger = logging.getLogger(__name__)


@dataclass
class _ConversationLock:
    """单个会话的锁与引用计数；users 包括持有者和等待者。"""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class ChatAgent:
    """包装异步 Agent 图，提供文本增量和最终回复，不暴露内部工具消息。"""

    def __init__(self, agent: Runnable[dict[str, Any], dict[str, Any]]) -> None:
        """保存图并初始化会话锁表；实例须在一个事件循环内使用。"""
        self._agent = agent
        self._locks: dict[str, _ConversationLock] = {} # 全局会话锁列表

    @asynccontextmanager
    async def _conversation(self, thread_id: str) -> AsyncIterator[None]:
        """按进入顺序取得会话锁，取消等待或离开后回收最后一个引用。

        注册及注销引用之间没有 await，因此事件循环内不需要额外注册表锁。
        等待者先登记引用，避免持有者释放时移除仍被其他请求使用的锁。
        """
        entry = self._locks.setdefault(thread_id, _ConversationLock())
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._locks[thread_id]

    async def astream(self, message: str, thread_id: str) -> AsyncIterator[ChatDelta | ChatResponse]:
        """发送一轮消息，yield 文本增量，持久化完成后 yield 最终回复。

        同会话排队，不同会话并发；计时包含排队时间。调用方提前结束时
        必须关闭迭代器，才能立即释放图与会话锁。取消不转换为业务失败，
        也不回滚已有 checkpoint；已知应用异常保留，其他失败包装为
        CHAT_FAILED，日志只主动记录标识及耗时，不记录对话正文。
        """
        started = perf_counter()
        try:
            async with self._conversation(thread_id):
                final_message = None
                final_id = ""
                current_id = str(uuid4())
                # 使用稳定的 v1 多模式格式；sync 只要求每步落库后推进，数据库 I/O 仍是异步。
                stream = self._agent.astream(
                    {"messages": [HumanMessage(content=message)]},
                    config={"configurable": {"thread_id": thread_id}},
                    stream_mode=["messages", "updates"],
                    version="v1",
                    durability="sync", # 保存时等待持久化完成，再继续
                )
                async with aclosing(stream):
                    async for mode, payload in stream:
                        if mode == "messages":
                            chunk, metadata = payload
                            # text 仅提取文本块；reasoning、工具参数和 ToolMessage 均不外发。
                            if isinstance(chunk, AIMessage) and metadata.get("langgraph_node") == "model":
                                current_id = chunk.id or current_id
                                if chunk.text:
                                    yield ChatDelta(thread_id=thread_id, message_id=current_id, text=str(chunk.text))
                        elif mode == "updates":
                            for update in payload.values():
                                if isinstance(update, dict) and update.get("messages"):
                                    final_message = update["messages"][-1]
                                    final_id = final_message.id or current_id
                                    # 下个模型步骤拥有独立标识；不能把工具前的文字合并进最终回答。
                                    current_id = str(uuid4())
                if (
                    not isinstance(final_message, AIMessage)
                    or final_message.tool_calls
                    or not final_message.text.strip()
                ):
                    raise ValueError("Agent 未返回最终助手文本")
                result = ChatResponse(reply=str(final_message.text), thread_id=thread_id, message_id=final_id)
                # 图迭代结束已经等待 checkpoint 写入，记录成功后才交付 done。
                duration_ms = round((perf_counter() - started) * 1000, 2)
                logger.info(
                    "对话完成 thread_id=%r duration_ms=%.2f", thread_id, duration_ms,
                    extra={"thread_id": thread_id, "duration_ms": duration_ms},
                )
                yield result
        except AppError as exc:
            log_app_error(logger, exc, context={
                "thread_id": thread_id, "duration_ms": round((perf_counter() - started) * 1000, 2),
            })
            raise
        except Exception as exc:
            error = ServiceError(ErrorCode.CHAT_FAILED)
            log_app_error(logger, error, context={
                "thread_id": thread_id, "duration_ms": round((perf_counter() - started) * 1000, 2),
            }, cause=exc)
            raise error from exc

    async def achat(self, message: str, thread_id: str) -> str:
        """消费同一个异步流并返回最终文本，供命令行使用，不重复执行图。"""
        async with aclosing(self.astream(message, thread_id)) as stream:
            async for event in stream:
                if isinstance(event, ChatResponse):
                    return event.reply
        raise ServiceError(ErrorCode.CHAT_FAILED)


if __name__ == "__main__":
    # 兼容原运行命令；示例配置统一维护在包入口。
    from app.agents.__main__ import main

    main()
