"""账号仓储，只执行 ORM 查询及 flush；事务提交由认证服务负责。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def by_username(session: AsyncSession, username: str) -> User | None:
    """按已经标准化的用户名查找账号，返回值可能包含密码摘要，仅供服务内部使用。"""
    return await session.scalar(select(User).where(User.username == username))


async def by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """按令牌中的用户 ID 查找最新账号状态。"""
    return await session.get(User, user_id)


async def add_user(
    session: AsyncSession, username: str, password_hash: str, role: str
) -> User:
    """写入账号并获取数据库默认时间；唯一约束冲突交由服务层统一转换。"""
    user = User(username=username, password_hash=password_hash, role=role)
    session.add(user)
    await session.flush()
    return user
