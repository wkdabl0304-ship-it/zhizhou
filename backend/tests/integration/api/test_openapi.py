"""OpenAPI 集成测试：核对正式应用的认证与会话公开协议。"""

import json

from fastapi.testclient import TestClient

from tests.support.apps import make_app


def test_openapi_exposes_only_business_conversation_ids_and_bearer_auth():
    """验证公开接口文档采用业务会话标识和 Bearer 认证约定。

    检查旧 thread_id 不再暴露、首次聊天只要求正文，且没有独立创建会话接口。
    """
    from app.main import app

    schema = app.openapi()
    assert "thread_id" not in json.dumps(schema)
    assert schema["components"]["schemas"]["ChatRequest"]["required"] == ["message"]
    assert "conversation_id" in schema["components"]["schemas"]["ConversationInfo"]["properties"]
    assert "post" not in schema["paths"]["/api/conversations"]
    assert schema["paths"]["/api/chat"]["post"]["security"] == [{"HTTPBearer": []}]


def test_test_application_matches_production_openapi():
    """验证共享测试应用的路由、响应约定和文档元数据与正式入口一致。"""
    from app.main import app

    assert make_app().openapi() == app.openapi()


def test_openapi_uses_provider_configuration_names():
    """公开接口、引用字段及模型测试结果采用供应商配置命名，便于配置页面对接。"""
    schema = make_app().openapi()
    paths = schema["paths"]
    base = "/api/model-config/provider-configurations"
    assert set(paths[base]) == {"get", "post"}
    assert set(paths[base + "/{provider_configuration_id}"]) == {"get", "patch", "delete"}
    assert "/api/model-config/connections" not in paths
    assert paths[base]["post"]["security"] == [{"HTTPBearer": []}]
    schemas = schema["components"]["schemas"]
    assert "provider_configuration_id" in schemas["ModelCreate"]["required"]
    assert "connection_id" not in schemas["ModelCreate"]["properties"]
    assert "provider_configuration_fields" in schemas["ProviderInfo"]["properties"]
    assert "provider_configuration_version" in schemas["ModelTestResult"]["properties"]
    parameters = paths["/api/model-config/models"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {"provider_configuration_id"}


def test_openapi_documents_sse_and_uniform_pre_stream_errors(runtime):
    """OpenAPI 成功类型仅为 SSE，示例涵盖终止事件；参数及框架错误仍为 JSON。"""
    with TestClient(runtime.app) as client:
        schema = client.get("/openapi.json").json()
    assert "openapi" in schema and "code" not in schema
    assert "/chat" not in schema["paths"]
    assert "/api/api/chat" not in schema["paths"]
    operation = schema["paths"]["/api/chat"]["post"]
    assert operation["tags"] == ["聊天"]
    responses = operation["responses"]
    assert set(responses["200"]["content"]) == {"text/event-stream"}
    content = responses["200"]["content"]["text/event-stream"]
    assert "event: done" in content["examples"]["success"]["value"]
    for name in ("delta", "tool_call", "tool_start", "tool_end"):
        assert f"event: {name}" in content["examples"]["success"]["value"]
    assert "reasoning_delta" not in str(operation)
    assert "event: tool_error" in content["examples"]["tool_error"]["value"]
    assert "event: error" in content["examples"]["error"]["value"]
    for status in ("404", "405", "422", "500"):
        reference = responses[status]["content"]["application/json"]["schema"]["$ref"]
        error_schema = schema["components"]["schemas"][reference.split("/")[-1]]
        assert set(error_schema["properties"]) == {"code", "message", "data"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]
