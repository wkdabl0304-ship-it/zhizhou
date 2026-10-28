"""本地账号运维入口测试：规范化参数、错误退出与安全输出，不连接数据库。"""

from unittest.mock import AsyncMock

import pytest

from app import manage
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError


@pytest.mark.parametrize("raw,expected", [(" ALIce ", "alice"), ("ABC", "abc"), ("X" * 32, "x" * 32)])
def test_management_command_normalizes_account_and_reports_success(monkeypatch, capsys, raw, expected):
    """运维命令只对明确指定的标准用户名授权，成功输出不包含凭据。"""
    grant = AsyncMock()
    monkeypatch.setattr(manage, "grant", grant)
    manage.main(["grant-super-admin", raw])
    grant.assert_awaited_once_with(expected)
    assert capsys.readouterr().out == f"已授予超级管理员：{expected}\n"


def test_management_command_returns_nonzero_for_disabled_account(monkeypatch, capsys):
    """目标状态不满足条件时退出失败，不误报已授权或回显内部异常。"""
    monkeypatch.setattr(manage, "grant", AsyncMock(side_effect=RequestError(ErrorCode.TARGET_STATE_CONFLICT)))
    with pytest.raises(SystemExit) as failure:
        manage.main(["grant-super-admin", "alice"])
    assert failure.value.code == 1
    captured = capsys.readouterr()
    assert not captured.out and "目标状态或归属已变化" in captured.err


@pytest.mark.parametrize("username", ["", "  ", "ab", "x" * 33, "invalid-user", "a b", "用户账号"])
def test_management_command_rejects_invalid_account_without_side_effects(monkeypatch, username):
    """非法用户名在打开数据库前被拒绝。"""
    grant = AsyncMock()
    monkeypatch.setattr(manage, "grant", grant)
    with pytest.raises(SystemExit) as failure:
        manage.main(["grant-super-admin", username])
    assert failure.value.code == 2
    grant.assert_not_called()
