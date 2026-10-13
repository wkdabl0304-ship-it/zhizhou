"""可直接编辑消息并运行的智能体示例。"""

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import create_model
from app.agents.tools.weather import get_weather
from app.config.settings import load_settings
from app.db.checkpoint import open_checkpointer

MESSAGE = "刚刚说什么了"
THREAD_ID = "conversation-002"


def main() -> None:
    settings = load_settings()
    model = create_model(settings)
    with open_checkpointer(settings) as checkpointer:
        agent = ChatAgent(build_agent(model, [get_weather], checkpointer))
        print(agent.chat(MESSAGE, THREAD_ID))


if __name__ == "__main__":
    main()
