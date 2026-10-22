"""模型工厂单元测试：替换客户端构造函数验证配置传递。"""

from app.agents.models import create_model
from app.core.settings import Settings


def test_model_factory_enables_thinking_and_preserves_existing_configuration(monkeypatch):
    """替换模型构造函数，确认配置原样传递并显式开启思考模式，不创建网络客户端。"""
    from app.agents import models

    observed = {}

    def model(**kwargs):
        """记录构造参数并返回占位，隔离真实模型客户端初始化。"""
        observed.update(kwargs)
        return "model"

    monkeypatch.setattr(models, "DeepSeekChatModel", model)
    settings = Settings("test-key", "postgres", "password", "zhizhou", 5432)
    assert create_model(settings) == "model"
    assert observed == {
        "model": settings.model_name, "api_key": "test-key",
        "base_url": settings.model_base_url, "extra_body": {"thinking": {"type": "enabled"}},
    }
