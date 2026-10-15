"""天气工具演示：提供 LangChain 可识别的工具签名和固定天气结果。

当前不访问真实天气服务。函数 docstring 会成为提供给模型的工具说明，
实现细节通过普通注释解释，避免无意改变模型看到的工具描述。
"""

from langchain.tools import tool


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    # city 是模型按工具签名传入的城市名；返回值作为工具消息提供给 Agent。
    # 固定演示内容；未来接入天气服务时替换这里的实现。
    return f"{city}今天晴天，温度 25°C"
