"""HTTP 错误验证脚本：短暂启动回环 Uvicorn，核对兜底响应和实际堆栈次数。"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn
from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.core.errors.exceptions import BusinessError, ServiceError
from app.core.logging import build_logging_config
from app.core.settings import LoggingSettings
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
