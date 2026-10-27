"""标题模型替身：隔离真实供应商，支持可控等待、失败和资源关闭观察。"""

import asyncio
from contextlib import asynccontextmanager
import json

from langchain_core.messages import AIMessageChunk

from app.schemas.conversations import normalize_title


class TitleModelStub:
    """提供标题服务所需的模型流；不实现工具或 checkpoint，防止越过标题职责。"""

    def __init__(self, reply: str | None = "会话概览"):
        """准备本例独立门控和调用记录；reply 为空时返回规范化后的问题摘要。"""
        self.reply = reply
        self.failure = None
        self.release = None
        self.started = asyncio.Event()
        self.closed = False
        self.stream_closed = False
        self.snapshots = []
        self.messages = []

    @asynccontextmanager
    async def open(self, snapshot):
        """记录本次模型快照，并在正常、异常或取消退出时登记资源已关闭。"""
        self.snapshots.append(snapshot)
        try:
            yield self
        finally:
            self.closed = True

    async def astream(self, messages):
        """模拟推理与标题正文流，可由测试显式放行或注入供应商失败。"""
        self.messages.append(messages)
        self.started.set()
        try:
            if self.release is not None:
                await self.release.wait()
            if self.failure is not None:
                raise self.failure
            yield AIMessageChunk(content=[{"type": "reasoning", "reasoning": "不应进入标题的内部推理"}])
            reply = self.reply
            if reply is None:
                reply = normalize_title(json.loads(messages[-1].content)["question"])[:24]
            yield AIMessageChunk(content=reply)
        finally:
            self.stream_closed = True
