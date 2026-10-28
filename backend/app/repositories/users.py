"""账号仓储，只执行 ORM 查询及 flush；事务提交由认证服务负责。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def by_username(session: AsyncSession, username: str) -> User | None:
    """按用户名查询账号，供登录时验证身份。

    username 应已经标准化；未找到时返回 None。返回的 ORM 对象包含密码
    摘要，仅供服务内部使用，不应直接序列化为接口响应。
    """
    return await session.scalar(select(User).where(User.username == username))


async def by_id(session: AsyncSession, user_id: UUID, *, lock: bool = False) -> User | None:
    """按 ID 读取最新账号，管理写入可锁定行；未找到返回 None，不复用过期 ORM 状态。"""
    statement = select(User).where(User.id == user_id).execution_options(populate_existing=True)
    return await session.scalar(statement.with_for_update() if lock else statement)


async def add_user(
    session: AsyncSession, username: str, password_hash: str
) -> User:
    """创建账号记录并返回包含数据库默认字段的 ORM 对象。

    password_hash 必须是服务层已计算的密码摘要；这里只执行 flush，
    事务提交和用户名唯一约束冲突的转换由认证服务负责。
    """
    user = User(username=username, password_hash=password_hash)
    session.add(user)
    await session.flush()
    return user
