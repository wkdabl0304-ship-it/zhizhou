"""聊天回归测试共用替身：异步图与本地可流式模型，不访问网络或数据库。"""

import asyncio
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class GraphStub:
    """模拟 messages/updates 图流，记录调用并允许测试注入执行异常。"""

    def __init__(self, reply="你好"):
        """保存固定回复、调用记录、异常开关及底层流关闭状态。"""
        self.reply = reply
        self.failure = None
        self.calls = []
        self.closed = False

    async def astream(self, inputs, **kwargs):
        """记录传参，逐字符输出增量和最终更新，finally 标记资源已关闭。"""
        self.calls.append((inputs, kwargs))
        try:
            if self.failure:
                raise self.failure
            for text in self.reply:
                yield "messages", (AIMessageChunk(content=text, id="reply-1"), {"langgraph_node": "model"})
            yield "updates", {"model": {"messages": [AIMessage(content=self.reply, id="reply-1")]}}
        finally:
            self.closed = True


class StubChatModel(BaseChatModel):
    """供真实图执行的本地模型；支持原生异步增量、可观察历史及天气工具。"""

    @property
    def _llm_type(self):
        """返回替身类型标识，满足 BaseChatModel 抽象接口。"""
        return "test-model"

    def bind_tools(self, tools, **kwargs):
        """返回自身，工具选择由本地生成逻辑模拟。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """根据历史构造助手文本或天气调用；同步入口仅满足模型抽象契约。"""
        if isinstance(messages[-1], ToolMessage):
            reply = AIMessage(content=messages[-1].content)
        elif messages[-1].content == "天气":
            reply = AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "上海"}, "id": "weather-1",
            }])
        else:
            # 拼接历次用户输入，让多轮测试能够观察 checkpoint 是否延续。
            reply = AIMessage(content="|".join(
                message.content for message in messages if isinstance(message, HumanMessage)
            ))
        return ChatResult(generations=[ChatGeneration(message=reply)])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        """逐字符异步返回回复；工具选择只产生工具调用块，不发出工具正文。"""
        reply = self._generate(messages).generations[0].message
        message_id = str(uuid4())
        if reply.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", id=message_id, tool_calls=reply.tool_calls))
        else:
            for text in reply.text:
                await asyncio.sleep(0)
                yield ChatGenerationChunk(message=AIMessageChunk(content=text, id=message_id))
