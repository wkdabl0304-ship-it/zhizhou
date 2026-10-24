"""凭据与端点单元回归：验证认证加密、固定官方域名及严格参数形状。"""

from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError
import pytest

from app.llm.providers.endpoints import list_providers, resolve_endpoint
from app.llm.secrets import SecretBox
from app.schemas.model_config import ProviderConfigurationCreate, EndpointConfig


def test_authenticated_encryption_and_wrong_master_key():
    """同一凭据每次加密不同，损坏密文或错误主密钥均不能恢复明文。"""
    box = SecretBox(Fernet.generate_key().decode())
    secret = SecretStr("private-model-key")
    a, b = box.encrypt(secret), box.encrypt(secret)
    assert a != b and "private-model-key" not in a
    assert box.decrypt(a).get_secret_value() == "private-model-key"
    assert "private-model-key" not in repr(box.decrypt(a))
    for cipher in (SecretBox(Fernet.generate_key().decode()), box):
        with pytest.raises(ValueError) as error:
            cipher.decrypt(a if cipher is not box else "damaged")
        assert "private-model-key" not in str(error.value)


def test_official_endpoints_and_workspace_injection_rejection():
    """固定端点生成官方域名；业务空间不能注入其他主机或路径。"""
    assert len(list_providers()) == 4
    assert resolve_endpoint("deepseek", "chat_completions", EndpointConfig(endpoint_id="official")) == "https://api.deepseek.com"
    assert resolve_endpoint("bailian", "chat_completions", EndpointConfig(endpoint_id="cn-beijing", workspace_id="work_123")) == "https://work_123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    for provider, fmt, endpoint in [
        ("deepseek", "messages", EndpointConfig(endpoint_id="official")),
        ("openai", "responses", EndpointConfig(endpoint_id="https://evil.invalid")),
        ("bailian", "chat_completions", EndpointConfig(endpoint_id="cn-beijing", workspace_id="foo.evil/path")),
        ("bailian", "chat_completions", EndpointConfig(endpoint_id="us-east-1")),
    ]:
        with pytest.raises(ValueError):
            resolve_endpoint(provider, fmt, endpoint)


def test_credentials_are_write_only_and_unknown_parameters_forbidden():
    """输入对象隐藏密钥并拒绝空值、自定义地址和未声明端点字段。"""
    body = dict(name="正式供应商配置", provider="deepseek", api_format="chat_completions", endpoint_config={"endpoint_id": "official"}, api_key="private-model-key")
    assert "private-model-key" not in repr(ProviderConfigurationCreate(**body))
    for changes in ({"api_key": "  "}, {"base_url": "https://evil.invalid"}, {"endpoint_config": {"endpoint_id": "official", "extra": 1}}):
        with pytest.raises(ValidationError):
            ProviderConfigurationCreate(**(body | changes))
