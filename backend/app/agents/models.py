"""旧模型适配导入入口：保留 DeepSeek 客户端导出，运行装配已迁移到 app.llm。"""

from app.llm.providers.deepseek import DeepSeekChatModel

__all__ = ["DeepSeekChatModel"]
