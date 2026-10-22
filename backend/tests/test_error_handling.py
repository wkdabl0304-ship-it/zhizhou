"""验证错误码目录、异常分类、协议响应以及日志去重。

常规场景使用 TestClient；未知异常另外经过真实本地 Uvicorn 验证重抛行为。
"""

import logging
import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.api.exception_handlers import ERROR_RESPONSES, register_exception_handlers
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError, ServiceError, log_app_error
from app.schemas.chat import ChatResponse
from app.schemas.response import ApiResponse, success


def test_catalog_codes_are_unique_integers_with_explanations():
    """检查中央目录码值唯一、类型为整数，并为每个条目提供非空解释。"""
    codes = [error.code for error in ErrorCode]
    assert len(codes) == len(set(codes))
    assert all(type(code) is int for code in codes)
    assert all(error.message.strip() for error in ErrorCode)
    assert ErrorCode.SUCCESS.code == 0
    assert ErrorCode.BUSINESS_ERROR.is_business


@pytest.mark.parametrize("invalid", [20000, "20000", None])
def test_business_exception_rejects_unregistered_codes(invalid):
    """验证数字、字符串或空值不能绕过错误码目录构造业务异常。"""
    with pytest.raises(TypeError):
        BusinessError(invalid)


@pytest.mark.parametrize("invalid", [ErrorCode.SUCCESS, ErrorCode.INVALID_ARGUMENT, ErrorCode.INTERNAL_ERROR])
def test_business_exception_rejects_other_catalog_categories(invalid):
    """验证成功码、请求错误码和系统码均不能被当作业务失败。"""
    with pytest.raises(ValueError):
        BusinessError(invalid)


def test_service_exception_rejects_business_code():
    """验证系统异常不能携带会被解释为 HTTP 200 的业务码。"""
    with pytest.raises(ValueError):
        ServiceError(ErrorCode.BUSINESS_ERROR)


def test_application_error_logging_is_idempotent(caplog):
    """对同一异常重复调用日志函数，确认内部标识避免重复堆栈。"""
    logger = logging.getLogger("app.test.errors")
    error = ServiceError()
    with caplog.at_level(logging.ERROR):
        log_app_error(logger, exc=error)
        log_app_error(logger, exc=error)
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info


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
    ("/http/403", 403, 40000),
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


def test_real_uvicorn_fallback_response_and_single_traceback():
    # 用真实 HTTP 服务验证 Starlette 重抛后的日志行为，不依赖数据库或模型密钥。
    """在子进程运行真实本地 HTTP 服务，检查未知异常重抛和单次堆栈输出。

    测试结束会停止线程并关闭套接字，不依赖模型、数据库或外部服务。
    """
    script = """
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn
from fastapi import FastAPI
from app.api.exception_handlers import register_exception_handlers
from app.config.logging import build_logging_config
from app.config.settings import LoggingSettings
from app.errors.exceptions import BusinessError, ServiceError
from app.schemas.chat import ChatResponse
from app.schemas.response import ApiResponse

app = FastAPI()
register_exception_handlers(app)

@app.get('/unexpected')
def unexpected():
    '''制造未知异常，观察真实 ASGI 服务的兜底响应和重抛日志。'''
    raise RuntimeError('uvicorn-only-marker')

@app.get('/bad-response', response_model=ApiResponse[ChatResponse])
def bad_response():
    '''返回故意缺失字段的数据，触发服务端响应模型校验失败。'''
    return {'code': 0, 'message': 'ok', 'data': {}}

@app.get('/business')
def business():
    '''制造业务失败，验证真实服务返回 HTTP 200 且不打印堆栈。'''
    raise BusinessError()

@app.get('/service')
def service():
    '''制造已知系统失败，验证响应转换和边界层堆栈记录。'''
    raise ServiceError()

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, lifespan='off', log_config=build_logging_config(LoggingSettings()))
    server = uvicorn.Server(config)
    worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline and worker.is_alive(), 'server did not start'
            time.sleep(0.01)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path, status, code in (
            ('/unexpected', 500, 50000), ('/bad-response', 500, 50000),
            ('/business', 200, 20000), ('/service', 500, 50000),
        ):
            try:
                response = opener.open(f'http://127.0.0.1:{port}{path}', timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                assert response.status == status
                body = response.read().decode('utf-8')
                payload = json.loads(body)
            assert payload['code'] == code and payload['data'] is None
            assert 'uvicorn-only-marker' not in body
            assert 'ResponseValidationError' not in body
    finally:
        server.should_exit = True
        worker.join(10)
        assert not worker.is_alive(), 'server did not stop'
print('real-uvicorn-checked')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "real-uvicorn-checked"
    assert result.stderr.count("Exception in ASGI application") == 2
    assert result.stderr.splitlines().count("RuntimeError: uvicorn-only-marker") == 1
    # 两次未知失败由 Uvicorn 记录，一次已知系统失败由处理器记录；业务失败无堆栈。
    assert result.stderr.count("Traceback (most recent call last)") == 3
