"""模型工厂回归：验证四家使用专用客户端且生命周期属于本轮。"""

from uuid import uuid4

from pydantic import SecretStr
import pytest

from app.llm.models.policy import resolve_parameters
from app.llm.providers.clients import open_model, AnthropicChatModel, OpenAIChatModel, QwenChatModel
from app.llm.providers.deepseek import DeepSeekChatModel
from app.llm.types import ModelSnapshot
from app.schemas.model_config import DefaultReasoning


@pytest.mark.anyio
@pytest.mark.parametrize("provider,api_format,model_id,client_type", [
    ("deepseek", "chat_completions", "deepseek-flash", DeepSeekChatModel),
    ("openai", "responses", "gpt-6.1-sol", OpenAIChatModel),
    ("anthropic", "messages", "claude-sonnet-5", AnthropicChatModel),
    ("bailian", "chat_completions", "qwen3.8-max", QwenChatModel),
])
async def test_specialized_client_and_owned_resources(provider, api_format, model_id, client_type):
    """四家客户端来自对应专用集成，退出上下文后 HTTP 客户端全部关闭。"""
    catalog_id = f"{provider}:{model_id}"
    _, params = resolve_parameters(provider, api_format, catalog_id, DefaultReasoning(), 16384)
    snapshot = ModelSnapshot(uuid4(), uuid4(), 1, 1, 1, provider, api_format, catalog_id,
                             "https://test.invalid", params, SecretStr("private-test-key"))
    async with open_model(snapshot) as model:
        assert isinstance(model, client_type)
        if provider == "anthropic":
            sync, asynchronous = model._owned_sync, model._owned_async
        else:
            sync, asynchronous = model.http_client, model.http_async_client
        assert not sync.is_closed and not asynchronous.is_closed
        assert "private-test-key" not in str(snapshot.public_snapshot())
    assert sync.is_closed and asynchronous.is_closed
