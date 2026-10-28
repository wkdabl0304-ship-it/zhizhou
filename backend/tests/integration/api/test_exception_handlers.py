"""异常处理集成测试：通过独立 FastAPI 应用验证协议、响应头与脱敏。"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.api.exception_handlers import ERROR_RESPONSES, register_exception_handlers
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError, ServiceError
from app.schemas.chat import ChatResponse
from app.schemas.response import ApiResponse, success


@pytest.fixture
def app():
    """创建只用于测试的 FastAPI 应用，注册统一处理器与各类失败路由。"""
    app = FastAPI(responses=ERROR_RESPONSES)
    register_exception_handlers(app)

    @app.get("/business")
    def business():
        """直接抛出业务异常，用于验证 HTTP 200 与业务码的对应关系。"""
        raise BusinessError()

    @app.get("/service")
    def service():
        """抛出尚未记录日志的系统异常，验证边界处理器补记堆栈。"""
        raise ServiceError(ErrorCode.CHAT_FAILED)

    @app.get("/http/{status}")
    def http_error(status: int):
        """按路径参数抛出 HTTP 异常，携带内部解释与协议头供保留、脱敏测试。"""
        raise HTTPException(
            status,
            detail="private-http-detail",
            headers={"WWW-Authenticate": "Bearer", "Retry-After": "3"},
        )

    @app.get("/unexpected")
    def unexpected():
        """模拟未分类的编程错误，验证未知异常不会返回业务成功状态。"""
        raise ValueError("private-programming-error")

    @app.get("/bad-response", response_model=ApiResponse[ChatResponse])
    def bad_response():
        """故意返回不符合声明模型的数据，触发响应模型校验失败。"""
        return {"code": 0, "message": "成功", "data": {"reply": 123}}

    @app.get("/success", response_model=ApiResponse[dict[str, int]])
    def success_response():
        """用统一构建函数返回带具体字典类型的业务数据。"""
        return success({"count": 1})

    return app


def test_response_construction_preserves_data_type(app):
    """验证通用响应外壳不丢失成功数据的字段和整数类型。"""
    with TestClient(app) as client:
        response = client.get("/success")
    assert response.json() == {"code": 0, "message": "成功", "data": {"count": 1}}


@pytest.mark.parametrize("path,status,code", [
    ("/does-not-exist", 404, 40400),
    ("/http/400", 400, 40000),
    ("/http/401", 401, 40101),
    ("/http/403", 403, 40301),
    ("/http/404", 404, 40400),
    ("/http/405", 405, 40500),
    ("/http/422", 422, 42200),
    ("/http/429", 429, 40000),
    ("/http/500", 500, 50000),
    ("/http/503", 503, 50000),
])
def test_http_errors_keep_status_and_hide_internal_detail(app, path, status, code):
    """检查各类 HTTP 错误保留状态和必要头，响应不包含内部 detail。"""
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["data"] is None
    assert set(response.json()) == {"code", "message", "data"}
    assert "private-http-detail" not in response.text
    if path.startswith("/http/"):
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["retry-after"] == "3"


def test_method_not_allowed_keeps_allow_header(app):
    """验证框架 405 使用统一格式，同时保留客户端需要的 Allow 头。"""
    with TestClient(app) as client:
        response = client.post("/success")
    assert response.status_code == 405
    assert response.json() == {"code": 40500, "message": "请求方法不允许", "data": None}
    assert "GET" in response.headers["allow"]


@pytest.mark.parametrize("path,status,code,level", [
    ("/business", 200, 20000, logging.WARNING),
    ("/service", 500, 50001, logging.ERROR),
])
def test_application_errors_are_logged_at_the_boundary_once(app, caplog, path, status, code, level):
    """验证未记录的应用异常在边界仅记录一次，业务警告无堆栈。"""
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["data"] is None
    records = [record for record in caplog.records if record.name == "app.api.exception_handlers"]
    assert len(records) == 1
    assert records[0].levelno == level
    assert bool(records[0].exc_info) is (status == 500)


@pytest.mark.parametrize("path", ["/unexpected", "/bad-response"])
def test_unknown_and_outbound_validation_errors_are_safe_500(app, caplog, path):
    """验证未知异常与返回值校验失败都使用安全的 500 兜底响应。"""
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(path)
    assert response.status_code == 500
    assert response.json() == {"code": 50000, "message": "服务器内部错误，请稍后重试", "data": None}
    # TestClient 不包含 Uvicorn；兜底处理器不额外打印将由服务器记录的堆栈。
    assert not [record for record in caplog.records if record.name.startswith("app.")]
