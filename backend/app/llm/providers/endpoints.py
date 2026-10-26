"""官方端点约束：验证百炼粘贴地址，并兼容读取原有地域和业务空间配置。"""

import re
from urllib.parse import urlsplit

from app.schemas.model_config import ApiFormat, EndpointConfig, Provider

FORMATS: dict[Provider, tuple[ApiFormat, ...]] = {
    "openai": ("responses", "chat_completions"), "anthropic": ("messages",),
    "deepseek": ("chat_completions",), "bailian": ("chat_completions",),
}
REGIONS = {
    "cn-beijing": "北京", "ap-southeast-1": "新加坡", "cn-hongkong": "中国香港",
    "ap-northeast-1": "日本东京", "eu-central-1": "德国法兰克福", "us-east-1": "美国弗吉尼亚",
}
OFFICIAL_URLS = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com",
                 "deepseek": "https://api.deepseek.com"}


def validate_bailian_base_url(value: str) -> str:
    """返回规范的百炼 OpenAI 兼容地址，拒绝非官方主机、其他协议及附加凭据。"""
    value = value.strip().rstrip("/")
    if re.search(r"\s", value) or "?" in value or "#" in value:
        raise ValueError("百炼 Base URL 无效")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    official = host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"} or re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}\.[a-z][a-z0-9-]{0,62}\.maas\.aliyuncs\.com", host,
    )
    # netloc 必须只有主机，拒绝 user:password@host、额外端口及 IPv6 等其他目标。
    if (parsed.scheme != "https" or parsed.netloc.lower() != host or not official
            or parsed.path != "/compatible-mode/v1"):
        raise ValueError("请填写百炼官方 OpenAI 兼容 Base URL")
    return f"https://{host}/compatible-mode/v1"


def resolve_endpoint(provider: Provider, api_format: ApiFormat, endpoint: EndpointConfig) -> str:
    """验证官方端点配置并返回 SDK 所需地址，拒绝跨供应商格式与域名注入。"""
    if api_format not in FORMATS.get(provider, ()):
        raise ValueError("供应商不支持该接口格式")
    if provider != "bailian":
        if endpoint.endpoint_id != "official" or endpoint.workspace_id is not None or endpoint.base_url is not None:
            raise ValueError("供应商端点配置无效")
        return OFFICIAL_URLS[provider]
    if endpoint.base_url is not None:
        return validate_bailian_base_url(endpoint.base_url)
    if endpoint.endpoint_id not in REGIONS:
        raise ValueError("百炼地域无效")
    if endpoint.workspace_id:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", endpoint.workspace_id) is None:
            raise ValueError("百炼业务空间 ID 无效")
        return f"https://{endpoint.workspace_id}.{endpoint.endpoint_id}.maas.aliyuncs.com/compatible-mode/v1"
    # 北京、新加坡兼容官方旧域名；其他地域必须提供官方要求的业务空间。
    legacy = {"cn-beijing": "https://dashscope.aliyuncs.com/compatible-mode/v1",
              "ap-southeast-1": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"}
    if endpoint.endpoint_id not in legacy:
        raise ValueError("该地域需要业务空间 ID")
    return legacy[endpoint.endpoint_id]


def list_providers() -> list[dict]:
    """提供配置页面需要的四家供应商、格式和官方端点字段描述。"""
    result = []
    names = {"openai": "OpenAI", "anthropic": "Anthropic", "deepseek": "DeepSeek", "bailian": "阿里云百炼"}
    for provider, formats in FORMATS.items():
        endpoints = [{"endpoint_id": "official", "display_name": "官方服务", "workspace_id_required": False}]
        if provider == "bailian":
            endpoints = [{"endpoint_id": region, "display_name": name,
                          "workspace_id_required": region not in {"cn-beijing", "ap-southeast-1"}}
                         for region, name in REGIONS.items()]
        result.append({"provider": provider, "display_name": names[provider],
                       "api_formats": list(formats), "default_api_format": formats[0],
                       "endpoints": endpoints, "recommended": provider == "deepseek",
                       "provider_configuration_fields": ["name", "api_format", "endpoint_config", "api_key"]})
    return result
