"""聊天回归测试共用替身：异步图与本地可流式模型，不访问网络或数据库。"""

import asyncio
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class GraphStub:
    """模拟 messages/updates 图流，记录调用并允许测试注入执行异常。"""

    def __init__(self, reply="你好"):
        """初始化可控图替身，供测试模拟一次成功或失败的 Agent 执行。

        reply 指定固定回复；调用记录、异常开关与关闭标记用于断言调用
        次数、传参、异常传播及异步资源清理，不访问外部模型。
        """
        self.reply = reply
        self.failure = None
        self.calls = []
        self.closed = False

    async def astream(self, inputs, **kwargs):
        """模拟 LangGraph 的消息增量和最终状态更新流。

        记录 inputs 与流选项，逐字符 yield 固定回复，再输出完整助手消息；
        注入 failure 时直接抛出，所有退出路径都在 finally 设置关闭标记。
        """
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
        """提供模型工厂要求的工具绑定入口，使本地替身可用于真实 Agent 图。

        不实际注册供应商工具，直接返回自身；工具选择由 _generate 模拟。
        """
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """生成可预测的模型结果，供测试验证历史延续和工具往返。

        根据 messages 返回工具结果、天气调用或拼接的历次用户输入；
        这是本地模拟逻辑，返回 ChatResult，同时满足模型的同步抽象契约。
        """
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
        """把本地生成结果转换为真实 Agent 可消费的异步模型流。

        普通回复逐字符 yield ChatGenerationChunk；工具选择只输出调用块，
        不抢先提供工具正文。每步让出事件循环，便于测试观察增量和取消。
        """
        reply = self._generate(messages).generations[0].message
        message_id = str(uuid4())
        if reply.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", id=message_id, tool_calls=reply.tool_calls))
        else:
            for text in reply.text:
                await asyncio.sleep(0)
                yield ChatGenerationChunk(message=AIMessageChunk(content=text, id=message_id))
