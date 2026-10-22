"""认证模块的输入与公开用户信息；密码字段不出现在响应及对象 repr 中。"""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """用户名密码输入；用户名统一大小写，密码保留原始空格。"""

    model_config = ConfigDict(extra="forbid")
    username: str
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """将登录或注册账号标准化为数据库查询使用的用户名。

        对 value 去除首尾空白并转为小写，返回 3～32 位 ASCII 字母、数字
        或下划线组成的字符串；不符合格式时抛出 ValueError 交给模型校验。
        """
        value = value.strip().lower()
        if re.fullmatch(r"[a-z0-9_]{3,32}", value) is None:
            raise ValueError("用户名须为 3～32 位字母、数字或下划线")
        return value


class RegisterRequest(LoginRequest):
    """注册输入；角色仅作身份记录，超级管理员不拥有他人会话权限。"""

    role: Literal["user", "super_admin"] = "user"


class UserInfo(BaseModel):
    """当前用户的公开身份，不包含密码摘要或内部状态。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    role: Literal["user", "super_admin"]


class RegisteredUser(UserInfo):
    """注册成功返回账号及创建时间，客户端随后单独登录。"""

    created_at: datetime


class LoginResponse(BaseModel):
    """登录返回的短期访问令牌，不提供刷新或服务端撤销能力。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserInfo
