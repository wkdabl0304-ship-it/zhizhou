from langchain.tools import tool


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    # 固定演示内容；未来接入天气服务时替换这里的实现。
    return f"{city}今天晴天，温度 25°C"
