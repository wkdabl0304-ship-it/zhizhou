"""智能体命令行演示入口，复用 Web 服务相同的配置、模型和持久化实现。

编辑 MESSAGE、THREAD_ID 后执行 python -m app.agents；成功回复写入
stdout，日志写入 stderr。导入本模块不会自动执行对话。
"""

import logging

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import create_model
from app.agents.tools.weather import get_weather
from app.config.logging import configure_logging
from app.config.settings import load_logging_settings, load_settings
from app.db.checkpoint import open_checkpointer
from app.errors.exceptions import AppError, log_app_error

logger = logging.getLogger("app.agents.cli")

# 保持标识可延续历史；改为新的标识即可创建独立对话。
MESSAGE = "刚刚说什么了"
THREAD_ID = "conversation-002"


def main() -> None:
    """初始化运行依赖，执行一轮示例对话，并打印最终文本。

    数据库连接在 with 内保持有效，离开时关闭。已知应用失败记录一次
    日志后以退出码 1 结束，避免解释器再次输出相同堆栈；启动配置或
    数据库初始化失败仍直接抛出，使调用者及时发现环境问题。
    """
    configure_logging(load_logging_settings())
    settings = load_settings()
    model = create_model(settings)
    with open_checkpointer(settings) as checkpointer:
        agent = ChatAgent(build_agent(model, [get_weather], checkpointer))
        try:
            reply = agent.chat(MESSAGE, THREAD_ID)
        except AppError as exc:
            # Agent 通常已经记录失败；帮助函数会依据 logged 标识自动跳过。
            log_app_error(logger, exc)
            raise SystemExit(1) from None
        print(reply)


if __name__ == "__main__":
    main()
