"""组装 Agent，不创建模型或数据库资源。"""

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
    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
