"""智能体命令行演示入口，复用 Web 服务相同的配置、模型和持久化实现。

编辑 MESSAGE、CONVERSATION_ID 后执行 python -m app.agents；成功回复写入
stdout，日志写入 stderr。导入本模块不会自动执行对话。
"""

import asyncio
import logging

from app.llm.runtime import ConfiguredChatAgent
from app.agents.tools.weather import get_weather
from app.core.event_loop import create_event_loop
from app.core.logging import configure_logging
from app.core.settings import load_logging_settings, load_settings
from app.db.checkpoint import open_checkpointer
from app.db.business import open_business_database
from app.services.model_config import ModelConfigService
from app.core.errors.exceptions import AppError, log_app_error

logger = logging.getLogger("app.agents.cli")

# 保持标识可延续历史；改为新的标识即可创建独立对话。
MESSAGE = "刚刚说什么了"
CONVERSATION_ID = "conversation-002"


async def run_chat() -> None:
    """执行命令行示例对话，并将最终助手文本输出到标准输出。

    读取数据库默认模型和 checkpoint 后调用共享执行器；连接与 Agent
    始终在同一事件循环内使用，MESSAGE 与 CONVERSATION_ID 指定本次输入。
    数据库连接在 async with 内保持有效，离开时关闭。已知应用失败记录一次
    日志后以退出码 1 结束，避免解释器再次输出相同堆栈；启动配置或
    数据库初始化失败仍直接抛出，使调用者及时发现环境问题。
    """
    settings = load_settings()
    async with open_business_database(settings) as database, open_checkpointer(settings) as checkpointer:
        service = ModelConfigService(database, settings.model_config_encryption_key)
        agent = ConfiguredChatAgent(checkpointer, [get_weather])
        try:
            snapshot = await service.snapshot()
            reply = await agent.achat(MESSAGE, CONVERSATION_ID, snapshot=snapshot)
        except AppError as exc:
            # Agent 通常已经记录失败；帮助函数会依据 logged 标识自动跳过。
            log_app_error(logger, exc)
            raise SystemExit(1) from None
        print(reply)


def main() -> None:
    """启动智能体命令行演示，供 python -m app.agents 调用。

    先配置日志，再用兼容 psycopg 的事件循环运行 run_chat；退出上下文时
    关闭循环，对话执行与异常退出规则由 run_chat 处理。
    """
    configure_logging(load_logging_settings())
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(run_chat())


if __name__ == "__main__":
    main()
