"""HTTP 传输集成测试：真实服务验证兜底响应和单次堆栈记录。"""

import pytest

from tests.support.processes import run_script

pytestmark = pytest.mark.transport


@pytest.mark.subprocess
def test_real_uvicorn_fallback_response_and_single_traceback():
    # 用真实 HTTP 服务验证 Starlette 重抛后的日志行为，不依赖数据库或模型密钥。
    """在子进程运行真实本地 HTTP 服务，检查未知异常重抛和单次堆栈输出。

    测试结束会停止线程并关闭套接字，不依赖模型、数据库或外部服务。
    """
    result = run_script("http_errors.py")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "real-uvicorn-checked"
    assert result.stderr.count("Exception in ASGI application") == 2
    assert result.stderr.splitlines().count("RuntimeError: uvicorn-only-marker") == 1
    # 两次未知失败由 Uvicorn 记录，一次已知系统失败由处理器记录；业务失败无堆栈。
    assert result.stderr.count("Traceback (most recent call last)") == 3
