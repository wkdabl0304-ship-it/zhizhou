"""Agent 对话逻辑，与 HTTP、环境配置和数据库连接管理无关。"""

import logging
from threading import Lock
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


class ChatAgent:
    def __init__(self, agent: Runnable[dict[str, Any], dict[str, Any]]) -> None:
        self._agent = agent
        # MVP 串行执行完整对话轮次，避免同一 thread 的读写交错。
        self._lock = Lock()

    def chat(self, message: str, thread_id: str) -> str:
        # 从等待锁之前开始计时，包含排队和完整调用耗时。
        started = perf_counter()
        try:
            with self._lock:
                result = self._agent.invoke(
                    {"messages": [HumanMessage(content=message)]},
                    config={"configurable": {"thread_id": thread_id}},
                )
                messages = result.get("messages", [])
                if not messages or not isinstance(messages[-1], AIMessage):
                    raise ValueError("Agent 未返回最终助手消息")
                reply = str(messages[-1].text)
                if not reply.strip():
                    raise ValueError("Agent 未返回回复文本")
        except Exception:
            duration_ms = (perf_counter() - started) * 1000
            logger.exception(
                "对话失败 thread_id=%r duration_ms=%.2f",
                thread_id,
                duration_ms,
                extra={"thread_id": thread_id, "duration_ms": duration_ms},
            )
            raise
        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "对话完成 thread_id=%r duration_ms=%.2f",
            thread_id,
            duration_ms,
            extra={"thread_id": thread_id, "duration_ms": duration_ms},
        )
        return reply


if __name__ == "__main__":
    # 兼容原运行命令；示例配置统一维护在包入口。
    from app.agents.__main__ import main

    main()
