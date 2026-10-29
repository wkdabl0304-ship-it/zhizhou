"""文件模块的无提交仓储：空间初始化、目录查询及逻辑删除，事务由业务层拥有。"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileBlob, FileEntry, FileSpace, FileUploadPolicy


async def create_personal_space(session: AsyncSession, user_id: UUID) -> None:
    """在账号创建事务中初始化唯一的个人空间，不复制个人统一上传策略。"""
    session.add(FileSpace(kind="personal", owner_id=user_id))
    await session.flush()


async def create_department_space(session: AsyncSession, department_id: UUID) -> None:
    """在部门创建事务中初始化部门空间及独立的默认上传策略。"""
    session.add_all([FileSpace(kind="department", department_id=department_id),
                     FileUploadPolicy(scope_type="department", department_id=department_id)])
    await session.flush()


async def policy(session: AsyncSession, scope: str, department_id: UUID | None = None, *, lock=False):
    """读取指定范围策略，可在配置更新或上传发布时锁定策略行。"""
    statement = select(FileUploadPolicy).where(FileUploadPolicy.scope_type == scope,
                                               FileUploadPolicy.department_id == department_id)
    return (await session.scalars(statement.with_for_update() if lock else statement)).one()


async def entry(session: AsyncSession, entry_id: UUID):
    """读取尚未删除的条目，不在仓储层判断当前用户的空间权限。"""
    return await session.scalar(select(FileEntry).where(FileEntry.id == entry_id, FileEntry.deleted_at.is_(None)))


async def children(session: AsyncSession, space_id: UUID, parent_id: UUID | None):
    """返回同一层的有效名称键，供短写事务内的并发安全名称分配使用。"""
    return (await session.scalars(select(FileEntry.name_key).where(FileEntry.space_id == space_id,
                    FileEntry.parent_id == parent_id, FileEntry.deleted_at.is_(None)))).all()


async def mark_deleted(session: AsyncSession, statement) -> None:
    """逻辑删除选定条目并登记对应原文件清理，提交后立即拒绝新的访问。"""
    ids = statement.cte("deleted_targets")
    # 先更新原文件状态，再统一标记条目；二者仍处于调用方同一个事务。
    await session.execute(update(FileBlob).where(FileBlob.id.in_(select(FileEntry.blob_id).where(
        FileEntry.id.in_(select(ids.c.id)), FileEntry.blob_id.is_not(None))))
        .values(state="delete_pending", updated_at=func.now()))
    await session.execute(update(FileEntry).where(FileEntry.id.in_(select(ids.c.id)), FileEntry.deleted_at.is_(None))
        .values(deleted_at=func.now(), updated_at=func.now(), version=FileEntry.version + 1))


async def delete_tree(session: AsyncSession, row: FileEntry) -> None:
    """以递归查询原子选中整棵目录树，包括目标文件或目录自身。"""
    tree = select(FileEntry.id).where(FileEntry.id == row.id).cte("subtree", recursive=True)
    tree = tree.union_all(select(FileEntry.id).join(tree, FileEntry.parent_id == tree.c.id)
                          .where(FileEntry.space_id == row.space_id, FileEntry.deleted_at.is_(None)))
    await mark_deleted(session, select(tree.c.id))


async def close_department_space(session: AsyncSession, department_id: UUID) -> None:
    """在删除部门事务中关闭空间及全部资料，磁盘清理由持久化原文件状态驱动。"""
    space = await session.scalar(select(FileSpace).where(FileSpace.department_id == department_id,
                   FileSpace.kind == "department", FileSpace.deleted_at.is_(None)).with_for_update())
    if space is None:
        return
    await mark_deleted(session, select(FileEntry.id).where(FileEntry.space_id == space.id, FileEntry.deleted_at.is_(None)))
    space.deleted_at = func.now()
    await session.flush()
