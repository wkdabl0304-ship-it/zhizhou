"""循环配置单元测试：验证普通及 reload 启动使用兼容 Psycopg 的循环。"""

import asyncio
import sys

import pytest
import uvicorn


@pytest.mark.parametrize("reload", [False, True])
def test_uvicorn_loop_factory_for_normal_and_reload_startup(reload):
    """验证 Uvicorn 普通与 reload 配置都能导入工厂，在 Windows 创建 Selector 循环。"""
    config = uvicorn.Config("app.main:app", reload=reload, loop="app.core.event_loop:create_event_loop", log_config=None)
    factory = config.get_loop_factory()
    loop = factory()
    try:
        if sys.platform == "win32":
            assert isinstance(loop, asyncio.SelectorEventLoop)
        assert not loop.is_running()
    finally:
        loop.close()
