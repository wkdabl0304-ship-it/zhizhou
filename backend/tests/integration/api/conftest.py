"""API 测试资源：每例独立应用执行正式生命周期，外部资源由替身隔离。"""

import pytest

from tests.support.fakes.runtime import make_runtime


@pytest.fixture
def runtime(monkeypatch):
    """为 API 用例提供独立运行环境，退出时自动撤销入口模块替换。"""
    return make_runtime(monkeypatch)
