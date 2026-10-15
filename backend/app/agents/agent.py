"""执行一轮 Agent 对话，管理调用串行化、最终文本提取和异常分类。

本模块接收已组装的 LangChain 图，不负责 HTTP、环境读取或数据库连接。
Web 与命令行共用同一实现，通过 checkpoint 和 thread_id 延续历史。
"""

import logging
from threading import Lock
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from app.errors.codes import ErrorCode
from app.errors.exceptions import AppError, ServiceError, log_app_error

logger = logging.getLogger(__name__)


class ChatAgent:
    """包装可执行的 Agent 图，为调用方提供简单的 chat 接口。"""

    def __init__(self, agent: Runnable[dict[str, Any], dict[str, Any]]) -> None:
        """保存已组装的 agent，并创建覆盖完整对话轮次的进程内互斥锁。

        当前 MVP 的所有对话共用此锁，不同 thread_id 的调用也会排队；
        这只保证同一实例的串行化，不提供多进程间的并发控制。
        """
        self._agent = agent
        # MVP 串行执行完整对话轮次，避免同一 thread 的读写交错。
        self._lock = Lock()

    def chat(self, message: str, thread_id: str) -> str:
        """发送 message 到 thread_id 对应的对话，并返回最终助手文本。

        相同 thread_id 会由图的 checkpoint 读取历史。计时包含排队时间，
        日志只主动记录标识与耗时，不记录消息正文或回复。
        BusinessError 等已知应用异常保持原类型；其他调用失败或空回复
        包装为 ServiceError，并通过异常链保留底层错误供服务器排查。
        """
        # 从等待锁之前开始计时，包含排队和完整调用耗时。
        started = perf_counter()
        try:
            with self._lock:
                result = self._agent.invoke(
                    {"messages": [HumanMessage(content=message)]},
                    config={"configurable": {"thread_id": thread_id}},
                )
                # 只提取最后的助手消息，避免把中间工具调用或整段历史返回给客户端。
                messages = result.get("messages", [])
                if not messages or not isinstance(messages[-1], AIMessage):
                    raise ValueError("Agent 未返回最终助手消息")
                reply = str(messages[-1].text)
                if not reply.strip():
                    raise ValueError("Agent 未返回回复文本")
        except AppError as exc:
            # 保留业务码；内部 logged 标识让 HTTP 或命令行边界不再重复记录。
            duration_ms = round((perf_counter() - started) * 1000, 2)
            log_app_error(logger, exc, context={"thread_id": thread_id, "duration_ms": duration_ms})
            raise
        except Exception as exc:
            # 普通异常不能归入 HTTP 200 的业务失败；客户端只收到安全解释。
            duration_ms = (perf_counter() - started) * 1000
            error = ServiceError(ErrorCode.CHAT_FAILED)
            log_app_error(
                logger, error,
                context={"thread_id": thread_id, "duration_ms": round(duration_ms, 2)},
                cause=exc,
            )
            raise error from exc
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
