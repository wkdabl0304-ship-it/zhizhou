"""运行时集成资源：按需提供生命周期替身，不影响独立进程测试。"""

import pytest

from tests.support.fakes.runtime import make_runtime


@pytest.fixture
def runtime(monkeypatch):
    """为生命周期用例提供本例独享应用及可观察资源事件。"""
    return make_runtime(monkeypatch)
