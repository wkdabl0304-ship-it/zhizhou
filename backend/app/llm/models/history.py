"""模型历史处理：保留同源内部上下文，跨模型只重放文本和完整工具调用对。"""

from copy import deepcopy

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.llm.types import ModelSnapshot

ORIGIN_KEY = "zhizhou_model_origin"


def project_history(messages: list[BaseMessage], snapshot: ModelSnapshot) -> list[BaseMessage]:
    """为目标模型生成历史副本，排除异源私有字段和没有完整结果的工具调用。

    原 checkpoint 始终保留，只有发送给模型的副本发生转换。工具调用必须
    与紧随其后的全部结果对应；中断留下的不完整调用只保留公开助手文字。
    """
    projected = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, ToolMessage):
            index += 1
            continue
        if not isinstance(message, AIMessage):
            projected.append(message.model_copy(deep=True))
            index += 1
            continue
        following = []
        after = index + 1
        while after < len(messages) and isinstance(messages[after], ToolMessage):
            following.append(messages[after])
            after += 1
        calls = message.tool_calls
        call_ids = {call["id"] for call in calls}
        results = {result.tool_call_id for result in following}
        complete = bool(calls) and call_ids == results and len(following) == len(calls)
        origin = message.response_metadata.get(ORIGIN_KEY)
        # 改造前仅运行固定 DeepSeek Flash；其普通推理文本不依赖账号签名。
        legacy = (origin is None and snapshot.catalog_model_id == "deepseek:deepseek-flash"
                  and isinstance(message.content, str)
                  and message.response_metadata.get("model_provider", "deepseek") == "deepseek"
                  and set(message.additional_kwargs) <= {"reasoning_content"})
        compatible = origin == snapshot.origin or legacy
        if compatible and (not calls or complete):
            projected.append(message.model_copy(deep=True))
        elif message.text or complete:
            projected.append(AIMessage(content=str(message.text), tool_calls=deepcopy(calls) if complete else []))
        if complete:
            for result in following:
                projected.append(ToolMessage(content=deepcopy(result.content), tool_call_id=result.tool_call_id,
                                             name=result.name, status=result.status))
        index = after
    return projected


class ModelHistoryMiddleware(AgentMiddleware):
    """在模型调用边界投影历史并标记新回复的来源，不改变公开 SSE 协议。"""

    def __init__(self, snapshot: ModelSnapshot):
        """固定本轮来源，整个工具循环保持同一模型、供应商配置和凭据版本。"""
        self.snapshot = snapshot

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        """用目标模型兼容的历史调用原处理器，并给最终消息加内部来源标记。"""
        response = await handler(request.override(messages=project_history(request.messages, self.snapshot)))
        result = []
        for message in response.result:
            if isinstance(message, AIMessage):
                metadata = {**message.response_metadata, ORIGIN_KEY: self.snapshot.origin}
                message = message.model_copy(update={"response_metadata": metadata}, deep=True)
            result.append(message)
        return ModelResponse(result=result, structured_response=response.structured_response)
