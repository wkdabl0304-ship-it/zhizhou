"""模型运行快照：分离每轮私有凭据、历史兼容标识与可持久化的公开参数。"""

from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import SecretStr

from app.schemas.model_config import ApiFormat, Provider


@dataclass(frozen=True)
class ModelSnapshot:
    """固定本轮使用的供应商配置及模型参数，数据库变更不会修改已创建的快照。"""

    provider_configuration_id: UUID
    configuration_id: UUID
    provider_configuration_version: int
    model_version: int
    credential_revision: int
    provider: Provider
    api_format: ApiFormat
    catalog_model_id: str
    base_url: str
    parameters: dict[str, Any]
    api_key: SecretStr = field(repr=False)
    # 正式快照始终写入具体推理值；默认空值保留独立客户端测试的构造兼容。
    reasoning: dict[str, Any] | None = None

    @property
    def origin(self) -> str:
        """生成绑定供应商配置、凭据版本、模型和格式的非秘密历史兼容标识。"""
        scope = [str(self.provider_configuration_id), self.credential_revision, self.provider,
                 self.api_format, self.catalog_model_id, self.base_url]
        return hashlib.sha256(json.dumps(scope).encode()).hexdigest()

    def public_snapshot(self) -> dict[str, Any]:
        """返回轮次可持久化的实际执行参数，不包含明文、密文或加密主密钥。"""
        value = {"provider_configuration_id": str(self.provider_configuration_id), "model_configuration_id": str(self.configuration_id),
                "provider_configuration_version": self.provider_configuration_version, "model_version": self.model_version,
                "provider": self.provider, "api_format": self.api_format,
                "catalog_model_id": self.catalog_model_id, "parameters": deepcopy(self.parameters)}
        if self.reasoning is not None:
            value["reasoning"] = deepcopy(self.reasoning)
        return value
