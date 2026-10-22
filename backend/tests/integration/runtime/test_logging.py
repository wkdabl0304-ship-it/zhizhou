"""日志进程集成测试：独立解释器隔离全局日志与 Windows spawn。"""

import pytest

from tests.support.processes import run_script


@pytest.mark.subprocess
def test_console_format_levels_access_switch_and_repeated_initialization():
    """验证统一格式、分类级别、访问日志开关、重复初始化和输出流分离。"""
    result = run_script("logging_console.py")
    assert result.stdout.strip() == "stdout-reply"
    lines = result.stderr.splitlines()
    assert len(lines) == 6
    for marker in (
        "visible-app-info", "visible-server-info", "visible-access-info",
        "visible-third-party-warning", "visible-app-debug", "visible-third-party-debug",
    ):
        assert result.stderr.count(marker) == 1
    assert "hidden-" not in result.stderr
    assert "INFO app.agents.agent visible-app-info" in result.stderr
    assert "WARNING external.library visible-third-party-warning" in result.stderr
    assert lines[0][4] == "-" and lines[0][7] == "-"


@pytest.mark.subprocess
def test_uvicorn_configuration_is_picklable_and_works_in_spawned_process():
    """验证日志配置可传给 Uvicorn，并能在 spawn 子进程中正常应用。"""
    result = run_script("logging_spawn.py")
    assert result.stderr.count("INFO uvicorn.error parent-marker") == 1
