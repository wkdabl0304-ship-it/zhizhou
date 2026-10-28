"""权限输入单元测试：拒绝提权、未知字段和类型混淆，保留必要的账号兼容输入。"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.authorization import ActiveUpdate, DepartmentWrite, MemberAdd, PasswordReset


@pytest.mark.parametrize("role", ["super_admin", "department_admin", "unknown"])
def test_public_registration_cannot_select_management_role(role):
    """公开注册必须拒绝管理角色，而不是忽略角色后产生误导性成功。"""
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="password-123", role=role)


def test_management_inputs_normalize_names_and_reject_unsafe_fields():
    """部门和成员名标准化，启停严格布尔，密码不进入 repr，未知角色字段被拒绝。"""
    assert DepartmentWrite(name="  研发部  ").name == "研发部"
    assert MemberAdd(username=" ALIce ").username == "alice"
    assert "secret-password" not in repr(PasswordReset(password="secret-password"))
    for model, body in ((DepartmentWrite, {"name": "   "}), (ActiveUpdate, {"is_active": "false"}),
                        (MemberAdd, {"username": "alice", "role": "super_admin"}),
                        (PasswordReset, {"password": "short"})):
        with pytest.raises(ValidationError):
            model.model_validate(body)
