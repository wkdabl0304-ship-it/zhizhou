"""模型身份投影回归：历史快照只公开展示所需字段，损坏旧数据不阻断历史读取。"""
from uuid import uuid4

import pytest

from app.services.model_selection import model_identity


def test_public_identity_excludes_runtime_parameters_and_handles_removed_catalog():
    """投影排除凭据与 SDK 参数，目录移除后保留快照中的原生模型标识。"""
    model_id = uuid4()
    identity = model_identity({"model_configuration_id": str(model_id), "catalog_model_id": "removed:original-model", "parameters": {"api_key": "private-key"}})
    assert identity.model_dump(mode="json") == {"model_configuration_id": str(model_id), "catalog_model_id": "removed:original-model", "display_name": "original-model"}


@pytest.mark.parametrize("snapshot", [None, {}, [], {"catalog_model_id": "x"}, {"catalog_model_id": "", "model_configuration_id": str(uuid4())}])
def test_missing_or_invalid_snapshot_is_optional(snapshot):
    """旧数据没有完整模型身份时返回空值，不伪造或阻止原聊天显示。"""
    assert model_identity(snapshot) is None
