"""账号标识的公共校验规则，供认证输入、部门成员输入和本地运维共同复用。"""

import re
from typing import Annotated

from pydantic import AfterValidator


def normalize_username(value: str) -> str:
    """将用户名转换为统一账号标识，并拒绝不符合现有格式的输入。

    去除首尾空白并转小写后，必须为 3～32 位 ASCII 字母、数字或下划线；
    返回规范化字符串，格式错误抛出 ValueError，不查询或修改账号数据。
    """
    value = value.strip().lower()
    if re.fullmatch(r"[a-z0-9_]{3,32}", value) is None:
        raise ValueError("用户名须为 3～32 位字母、数字或下划线")
    return value


# Pydantic 先验证字符串类型，再应用与命令行完全相同的规范化及格式校验。
type Username = Annotated[str, AfterValidator(normalize_username)]
