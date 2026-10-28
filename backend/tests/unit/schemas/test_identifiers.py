"""公共账号标识测试：验证各输入入口复用同一规则，规范化和拒绝边界保持一致。"""

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.authorization import MemberAdd
from app.schemas.identifiers import normalize_username


def input_for(model: type[BaseModel], username):
    """构造各入口所需的最小合法输入，让测试只观察用户名对外行为。"""
    body = {"username": username}
    if model is not MemberAdd:
        body["password"] = "password-123"
    return model.model_validate(body)


@pytest.mark.parametrize("model", [LoginRequest, RegisterRequest, MemberAdd])
@pytest.mark.parametrize("raw,expected", [("  ALIce_1  ", "alice_1"), ("ABC", "abc"),
                                        ("X" * 32, "x" * 32), ("\t alice \n", "alice")])
def test_account_inputs_share_normalization_and_length_boundaries(model, raw, expected):
    """登录、注册和添加成员均标准化用户名，允许长度上下界且不改变既有格式。"""
    assert input_for(model, raw).username == expected
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("model", [LoginRequest, RegisterRequest, MemberAdd])
@pytest.mark.parametrize("raw", ["", "   ", "ab", "x" * 33, "用户账号", "a-b", "a b", "abc!"])
def test_account_inputs_consistently_reject_invalid_names(model, raw):
    """所有账号输入均拒绝空值、越界长度、中文及非法字符，防止入口规则分歧。"""
    with pytest.raises(ValidationError):
        input_for(model, raw)
    with pytest.raises(ValueError, match="用户名须为"):
        normalize_username(raw)


@pytest.mark.parametrize("model", [LoginRequest, RegisterRequest, MemberAdd])
@pytest.mark.parametrize("raw", [None, 123, True, [], {}])
def test_account_inputs_reject_non_string_identifiers(model, raw):
    """HTTP 输入先拒绝非字符串用户名，不把其他 JSON 类型交给字符串处理函数。"""
    with pytest.raises(ValidationError):
        input_for(model, raw)
