"""权限模块公开数据与管理输入；所有响应均排除凭据，分页使用受范围约束的游标。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.identifiers import Username


class StrictInput(BaseModel):
    """拒绝未知管理字段，避免客户端提交未支持的角色、归属或内部状态。"""

    model_config = ConfigDict(extra="forbid")


class DepartmentBrief(BaseModel):
    """身份与用户资料中使用的最小部门信息。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class DepartmentInfo(DepartmentBrief):
    """部门接口返回的资料及资料更新时间，不混入成员变动时间。"""

    created_at: datetime
    updated_at: datetime


class Grant(BaseModel):
    """已解析的操作授权；全局无范围 ID，部门和本人分别使用部门或用户 ID。"""

    permission: str
    scope_type: Literal["global", "department", "self"]
    scope_id: UUID | None


class DepartmentWrite(StrictInput):
    """创建或改名部门的输入，名称按去除首尾空白后的完整值判重。"""

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        """标准化部门显示名称，空白名称由长度约束拒绝。"""
        return value.strip() if isinstance(value, str) else value


class MemberAdd(StrictInput):
    """按完整用户名加入既有账号，不接受模糊查询或指定成员角色。"""

    username: Username


class ActiveUpdate(StrictInput):
    """显式设置账号启停状态，不把数字或字符串当作布尔值。"""

    is_active: bool = Field(strict=True)


class PasswordReset(StrictInput):
    """管理员设置的新密码，只在当前请求中传递，不进入对象 repr。"""

    password: str = Field(min_length=8, max_length=128, repr=False)


class ManagedUser(BaseModel):
    """账号管理白名单；不包含个人会话、密码哈希、令牌版本或有效令牌。"""

    id: UUID
    username: str
    is_active: bool
    department: DepartmentBrief | None
    roles: list[str]
    created_at: datetime
    updated_at: datetime


class MemberInfo(BaseModel):
    """部门成员白名单，只展示身份、启停及当前部门的角色。"""

    id: UUID
    username: str
    is_active: bool
    roles: list[str]


class Page[T](BaseModel):
    """稳定游标分页的当前记录及下一页位置，无下一页时返回 null。"""

    items: list[T]
    next_cursor: str | None = None
