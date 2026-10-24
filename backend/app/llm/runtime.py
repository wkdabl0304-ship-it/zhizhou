"""模型执行装配：按轮次组合模型策略、供应商客户端与现有 Agent 图。"""

from contextlib import aclosing

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.llm.models.history import ModelHistoryMiddleware
from app.llm.providers.clients import open_model
from app.llm.types import ModelSnapshot
from app.schemas.chat import ChatResponse
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import ServiceError


class ConfiguredChatAgent:
    """按快照执行聊天，保存器和工具共享，模型与图资源属于当前轮次。"""

    def __init__(self, checkpointer, tools, *, model_opener=open_model):
        """保存公共执行依赖；model_opener 是协议测试替换网络的唯一入口。"""
        self.checkpointer, self.tools, self.model_opener = checkpointer, tools, model_opener

    async def astream(self, message: str, conversation_id: str, *, snapshot: ModelSnapshot):
        """执行固定模型的一轮对话，复用原事件转换和 checkpoint 终止语义。"""
        async with self.model_opener(snapshot) as model:
            graph = build_agent(model, self.tools, self.checkpointer, middleware=[ModelHistoryMiddleware(snapshot)])
            async with aclosing(ChatAgent(graph).astream(message, conversation_id)) as stream:
                async for event in stream:
                    yield event

    async def achat(self, message: str, conversation_id: str, *, snapshot: ModelSnapshot) -> str:
        """为命令行消费同一执行流并取得最终回答，取消时及时关闭内部迭代器。"""
        async with aclosing(self.astream(message, conversation_id, snapshot=snapshot)) as stream:
            async for event in stream:
                if isinstance(event, ChatResponse):
                    return event.reply
        raise ServiceError(ErrorCode.CHAT_FAILED)
