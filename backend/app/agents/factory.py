"""将模型、工具、提示词和状态保存器组合成可运行的 LangChain Agent。

依赖由启动入口传入，可在测试中替换模型和存储，本模块不管理外部连接。
"""

from collections.abc import Sequence

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agents.prompts import SYSTEM_PROMPT


def build_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    checkpointer: BaseCheckpointSaver,
):
    """组装执行聊天与工具调用的 Agent 图，供 Web 和命令行共用。

    返回支持 astream 的图，不在此执行对话。
    model 负责生成和工具选择，tools 定义可调用能力，checkpointer
    负责按 Agent 适配的内部状态键保存消息。调用方须在整个图执行期间保持存储可用。
    统一系统提示词从 prompts 模块读取；组装本身不会发起模型请求。
    """
    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
