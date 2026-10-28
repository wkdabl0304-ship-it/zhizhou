"""模型配置 E2E 支撑回归：验证边界替身、控制授权与按引用顺序重置，禁止真实模型调用。"""
from types import SimpleNamespace
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
from pydantic import SecretStr
import pytest

from app.core.errors.codes import ErrorCode
from app.llm.providers.failures import ProviderFailure
from app.services.conversation_titles import ConversationTitleService
from tests.support.e2e import ControlledModel, build_test_app, open_test_model, reset_model_configuration


@pytest.mark.anyio
async def test_e2e_lifespan_replaces_and_restores_title_model_boundary(monkeypatch):
    """浏览器测试使用本地标题模型，退出恢复原工厂，不让假凭据触发真实网络。"""
    import app.main as main

    titles = ConversationTitleService()
    original = titles.model_opener
    configuration = SimpleNamespace(model_opener=object())
    original_configuration = configuration.model_opener

    @asynccontextmanager
    async def lifespan(app):
        """只提供所需服务占位，隔离数据库并检查包装器确实恢复注入点。"""
        app.state.model_config_service = configuration
        app.state.conversation_service = SimpleNamespace(title_generator=titles)
        yield

    monkeypatch.setattr(main, "lifespan", lifespan)
    app = build_test_app(None, ControlledModel(), "token")
    async with app.router.lifespan_context(app):
        assert titles.model_opener is not original
        assert await titles.generate(object(), "  测试\n标题  ", "回答") == "测试 标题"
    assert titles.model_opener is original
    assert configuration.model_opener is original_configuration


@pytest.mark.anyio
async def test_local_model_boundary_success_and_safe_auth_failure():
    """正常假密钥返回本地模型，拒绝密钥只产生安全业务错误，不访问外部供应商。"""
    model = ControlledModel()
    async with open_test_model(SimpleNamespace(api_key=SecretStr("test")), model=model) as opened:
        assert opened is model
    with pytest.raises(ProviderFailure) as error:
        async with open_test_model(SimpleNamespace(api_key=SecretStr("e2e-rejected-key")), model=model):
            pytest.fail("拒绝密钥不应进入模型调用")
    assert error.value.error_code is ErrorCode.MODEL_AUTH_FAILED
    assert "e2e-rejected-key" not in str(error.value)


@pytest.mark.anyio
async def test_reset_uses_versions_and_clears_references_before_providers():
    """重置先清除默认再逐项删除，始终使用读取的当前版本而不是固定迁移版本。"""
    events = []
    service = AsyncMock()
    service.get_default.return_value = SimpleNamespace(version=8)
    service.list_models.return_value = [SimpleNamespace(id="model", version=3)]
    service.list_provider_configurations.return_value = [SimpleNamespace(id="provider", version=2)]

    async def setting(body):
        """记录清除默认的真实输入，以断言写入版本与引用解除顺序。"""
        assert body.version == 8 and body.model_configuration_id is None
        events.append("default")

    async def delete_model(identity, version):
        """登记模型删除必须先于关联供应商。"""
        assert (identity, version) == ("model", 3)
        events.append("model")

    async def delete_provider(identity, version):
        """登记供应商删除使用真实读到的版本。"""
        assert (identity, version) == ("provider", 2)
        events.append("provider")

    service.set_default.side_effect = setting
    service.delete_model.side_effect = delete_model
    service.delete_provider_configuration.side_effect = delete_provider
    await reset_model_configuration(service, seeded=False)
    assert events == ["default", "model", "provider"]


@pytest.mark.anyio
async def test_reset_control_requires_token_and_validates_mode(monkeypatch):
    """没有控制令牌或模式不合法时不能重置全局配置；成功路径只操作注入的测试服务。"""
    reset = AsyncMock()
    monkeypatch.setattr("tests.support.e2e.reset_model_configuration", reset)
    app = build_test_app(None, ControlledModel(), "control")
    app.state.model_config_service = object()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/__e2e__/model-configuration", json={"mode": "empty"})).status_code == 403
        headers = {"Authorization": "Bearer control"}
        assert (await client.post("/__e2e__/model-configuration", headers=headers, json={"mode": "other"})).status_code == 422
        reset.assert_not_awaited()
        assert (await client.post("/__e2e__/model-configuration", headers=headers, json={"mode": "empty"})).status_code == 200
        reset.assert_awaited_once_with(app.state.model_config_service, seeded=False)


@pytest.mark.anyio
async def test_admin_control_only_allows_authenticated_test_fixture(monkeypatch):
    """测试管理身份必须经本次控制令牌授予，公开注册不会自动获得管理权限。"""
    grant = AsyncMock()
    monkeypatch.setattr("tests.support.e2e.grant_super_admin", grant)
    app = build_test_app(None, ControlledModel(), "control")
    app.state.auth_service = SimpleNamespace(database=object())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/__e2e__/super-admin", json={"username": "alice"})).status_code == 403
        grant.assert_not_awaited()
        response = await client.post("/__e2e__/super-admin", headers={"Authorization": "Bearer control"}, json={"username": " ALIce "})
        assert response.json() == {"granted": True}
        grant.assert_awaited_once_with(app.state.auth_service.database, "alice")
