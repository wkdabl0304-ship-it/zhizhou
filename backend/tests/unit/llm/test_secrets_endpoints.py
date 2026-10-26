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


@pytest.mark.parametrize("address", [
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "https://llm-demo.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    "https://ws-demo.cn-hongkong.maas.aliyuncs.com/compatible-mode/v1",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
])
def test_pasted_bailian_base_url_normalization(address):
    """可直接粘贴业务空间或原公共地址，首尾空白及末尾斜杠不影响最终调用。"""
    config = EndpointConfig(base_url=f"  {address}/ \n")
    assert config.base_url == address
    assert resolve_endpoint("bailian", "chat_completions", config) == address


@pytest.mark.parametrize("address", [
    "http://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "https://127.0.0.1/compatible-mode/v1", "https://evil.invalid/compatible-mode/v1",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com.evil.invalid/compatible-mode/v1",
    "https://user:secret@ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com:443/compatible-mode/v1",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/api/v1",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1?key=secret",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1#fragment",
    "https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/\nv1",
])
def test_invalid_pasted_bailian_base_url_rejected(address):
    """错误协议、伪装域名、凭据、原生接口和请求参数不能成为密钥发送目标。"""
    with pytest.raises(ValueError):
        resolve_endpoint("bailian", "chat_completions", EndpointConfig(base_url=address))


def test_direct_address_cannot_mix_legacy_fields_or_change_other_providers():
    """直接地址与旧地域参数互斥，其他供应商继续使用自身既定官方端点。"""
    address = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    for fields in ({}, {"base_url": " "}, {"base_url": address, "endpoint_id": "cn-beijing"},
                   {"base_url": address, "workspace_id": "ws-demo"}):
        with pytest.raises(ValidationError):
            EndpointConfig(**fields)
    with pytest.raises(ValueError):
        resolve_endpoint("deepseek", "chat_completions", EndpointConfig(base_url=address))


def test_credentials_are_write_only_and_unknown_parameters_forbidden():
    """输入对象隐藏密钥并拒绝空值、自定义地址和未声明端点字段。"""
    body = dict(name="正式供应商配置", provider="deepseek", api_format="chat_completions", endpoint_config={"endpoint_id": "official"}, api_key="private-model-key")
    assert "private-model-key" not in repr(ProviderConfigurationCreate(**body))
    for changes in ({"api_key": "  "}, {"base_url": "https://evil.invalid"}, {"endpoint_config": {"endpoint_id": "official", "extra": 1}}):
        with pytest.raises(ValidationError):
            ProviderConfigurationCreate(**(body | changes))
