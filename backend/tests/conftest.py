"""后端测试公共配置：只提供路径和兼容 Psycopg 的 function scope 事件循环。"""

from pathlib import Path

import pytest

from app.core.event_loop import create_event_loop


@pytest.fixture
def backend_root(pytestconfig) -> Path:
    """返回 pytest 配置所在的后端目录，避免迁移影响子进程工作路径。"""
    return Path(pytestconfig.rootpath)


@pytest.fixture
def anyio_backend():
    """让异步用例及 fixture 共用本例独享的 asyncio 循环并在退出时关闭。"""
    return "asyncio", {"loop_factory": create_event_loop}
