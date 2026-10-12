import os

from dotenv import load_dotenv
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.postgres import PostgresSaver

env_path = Path(__file__).resolve().parents[3] / ".env"

load_dotenv(env_path)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

DB_URI = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:{POSTGRES_PORT}/{POSTGRES_DB}"


# 1. 创建 DeepSeek 模型
model = ChatOpenAI(
    model="deepseek-flash",
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


# 2. 创建工具
@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    # 这里只是演示，实际项目可以调用天气 API
    return f"{city}今天晴天，温度 25°C"


# 3. 创建 Agent
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

    # 第一次运行时需要调用，用于创建 checkpoint 相关表
    checkpointer.setup()

    agent = create_agent(
        model=model,
        tools=[get_weather],
        system_prompt="你是一个智能助手。需要外部信息时请使用提供的工具。",
        checkpointer=checkpointer,
    )

    # 同一个 thread_id = 同一段对话
    config = {
        "configurable": {
            "thread_id": "conversation-001"
        }
    }

    # 第一轮
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content="刚刚聊了什么"
                )
            ]
        },
        config=config,
    )

    print(result["messages"][-1].content)
