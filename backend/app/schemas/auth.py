"""认证模块的输入与公开用户信息；密码字段不出现在响应及对象 repr 中。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.authorization import DepartmentBrief, Grant
from app.schemas.identifiers import Username


class LoginRequest(BaseModel):
    """用户名密码输入；用户名统一大小写，密码保留原始空格。"""

    model_config = ConfigDict(extra="forbid")
    username: Username
    password: str = Field(min_length=8, max_length=128, repr=False)


class RegisterRequest(LoginRequest):
    """只注册普通用户；兼容旧客户端显式提交 user，拒绝注册管理身份。"""

    role: Literal["user"] = "user"


class UserInfo(BaseModel):
    """当前用户的公开身份，不包含密码摘要或内部状态。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    role: Literal["user", "super_admin"]
    department: DepartmentBrief | None = None
    roles: list[str] = Field(default_factory=list)
    grants: list[Grant] = Field(default_factory=list)


class RegisteredUser(UserInfo):
    """注册成功返回账号及创建时间，客户端随后单独登录。"""

    created_at: datetime


class LoginResponse(BaseModel):
    """登录返回的短期访问令牌；凭据版本支持停用、改密后撤销旧令牌，不提供刷新令牌。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserInfo
