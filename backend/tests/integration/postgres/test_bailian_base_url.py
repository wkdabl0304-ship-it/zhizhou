"""百炼地址配置集成：验证粘贴保存、密钥保留、运行快照及旧 JSON 配置的兼容读取。"""

from uuid import UUID

import pytest
from pydantic import SecretStr

from app.models import ProviderConfiguration
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
PREFIX = "/api/model-config"


async def test_pasted_address_crud_snapshot_and_key_retention(postgres_settings):
    """完整地址经正式 API 保存并进入模型快照；更换地址保留原密钥且拒绝过期或错误写入。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        client, service = runtime.client, runtime.model_config
        address = "https://ws-paste.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        result = await client.post(f"{PREFIX}/provider-configurations", headers=headers, json={
            "name": "粘贴百炼地址", "provider": "bailian", "api_format": "chat_completions",
            "endpoint_config": {"base_url": f"  {address}/  "}, "api_key": "fake-bailian-key"})
        assert result.status_code == 200 and result.json()["code"] == 0, result.text
        provider = result.json()["data"]
        path = f"{PREFIX}/provider-configurations/{provider['id']}"
        assert provider["endpoint_config"]["base_url"] == address
        assert "fake-bailian-key" not in result.text
        assert (await client.get(path, headers=headers)).json()["data"]["endpoint_config"]["base_url"] == address
        result = await client.post(f"{PREFIX}/models", headers=headers, json={
            "name": "百炼对话", "provider_configuration_id": provider["id"], "catalog_model_id": "bailian:qwen3.8-flash"})
        assert result.status_code == 200 and result.json()["code"] == 0, result.text
        model_id = UUID(result.json()["data"]["id"])
        before = await service.snapshot(model_id)
        assert before.base_url == address
        changed = "https://ws-other.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        result = await client.patch(path, headers=headers, json={"version": 1, "endpoint_config": {"base_url": changed}})
        assert result.status_code == 200 and result.json()["data"]["version"] == 2, result.text
        after = await service.snapshot(model_id)
        assert before.base_url == address and after.base_url == changed
        assert after.api_key.get_secret_value() == "fake-bailian-key" and after.credential_revision == 1
        assert (await client.patch(path, headers=headers, json={"version": 1, "name": "过期修改"})).status_code == 409
        invalid = await client.patch(path, headers=headers, json={"version": 2, "endpoint_config": {"base_url": "https://evil.invalid/compatible-mode/v1"}})
        assert invalid.status_code == 422
        assert (await service.get_provider_configuration(provider["id"])).version == 2
        async with runtime.database.sessions() as session:
            row = await session.get(ProviderConfiguration, provider["id"])
            assert row.endpoint_config == {"base_url": changed}
            assert row.credential_revision == 1


@pytest.mark.parametrize(("legacy", "address"), [
    ({"endpoint_id": "cn-beijing", "workspace_id": "ws-existing"}, "https://ws-existing.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"),
    ({"endpoint_id": "ap-southeast-1"}, "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
])
async def test_legacy_rows_display_equivalent_url_without_resetting_key(postgres_settings, legacy, address):
    """旧地域配置读取为等价 URL，读取不改版本，后续保存自然转换 JSON 而不重置密钥。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        service, client = runtime.model_config, runtime.client
        # 直接写入旧版 JSON 形状模拟已部署数据；新版本创建接口会主动保存规范地址。
        async with runtime.database.sessions.begin() as session:
            row = ProviderConfiguration(name="已有百炼", provider="bailian", api_format="chat_completions",
                endpoint_config=legacy, api_key_ciphertext=service.secrets.encrypt(SecretStr("legacy-fake-key")))
            session.add(row)
            await session.flush()
            provider_id = row.id
        listed = (await client.get(f"{PREFIX}/provider-configurations", headers=headers)).json()["data"]
        assert listed[0]["endpoint_config"]["base_url"] == address and listed[0]["version"] == 1
        async with runtime.database.sessions() as session:
            assert (await session.get(ProviderConfiguration, provider_id)).endpoint_config == legacy
        created = await client.post(f"{PREFIX}/models", headers=headers, json={
            "name": "已有连接新方案", "provider_configuration_id": str(provider_id), "catalog_model_id": "bailian:qwen3.8-flash"})
        assert created.status_code == 200 and created.json()["code"] == 0, created.text
        model_id = UUID(created.json()["data"]["id"])
        assert (await service.snapshot(model_id)).base_url == address
        updated = await client.patch(f"{PREFIX}/provider-configurations/{provider_id}", headers=headers, json={"version": 1, "name": "仅修改名称"})
        assert updated.status_code == 200 and updated.json()["data"]["version"] == 2, updated.text
        snapshot = await service.snapshot(model_id)
        assert snapshot.base_url == address and snapshot.api_key.get_secret_value() == "legacy-fake-key"
        assert snapshot.credential_revision == 1
        async with runtime.database.sessions() as session:
            assert (await session.get(ProviderConfiguration, provider_id)).endpoint_config == {"base_url": address}
        # 旧版客户端仍可提交地域字段，写入与返回值均转换为规范地址，便于平滑更新。
        old_request = await client.post(f"{PREFIX}/provider-configurations", headers=headers, json={
            "name": "旧客户端新建", "provider": "bailian", "api_format": "chat_completions",
            "endpoint_config": legacy, "api_key": "legacy-client-fake-key"})
        assert old_request.status_code == 200 and old_request.json()["code"] == 0, old_request.text
        assert old_request.json()["data"]["endpoint_config"]["base_url"] == address
        async with runtime.database.sessions() as session:
            created_row = await session.get(ProviderConfiguration, old_request.json()["data"]["id"])
            assert created_row.endpoint_config == {"base_url": address}
