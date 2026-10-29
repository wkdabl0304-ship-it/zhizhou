"""上传策略服务：全局和个人统一策略由全局授权维护，部门策略支持部门范围。"""

from sqlalchemy import select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department
from app.repositories import files as repository
from app.schemas.files import UploadLimitInfo
from app.services.authorization import management_lock


class UploadPolicies:
    """提供带版本的上传限制读写，不依赖文件原件存储资源。"""

    def __init__(self, access):
        """绑定文件访问服务以复用身份和当前有效授权。"""
        self.access = access

    async def get_or_update(self, actor, scope, department_id=None, body=None):
        """读取或更新可见策略，在同一短事务内复查授权并比较配置版本。"""
        async with self.access.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            user = await self.access.authorization.current(session, actor)
            grants = await self.access.authorization.grants(session, user)
            if scope == "department":
                visible = user.department_id == department_id or any(grant.permission == "file:read"
                    and grant.scope_type == "global" for grant in grants)
                if not visible or not await session.scalar(select(Department.id).where(Department.id == department_id)):
                    raise RequestError(ErrorCode.DEPARTMENT_NOT_FOUND)
            if body is not None:
                await self.access.authorization.require(session, user, "file_upload_limit:update", department_id=department_id)
            policy = await repository.policy(session, scope, department_id, lock=body is not None)
            if body is not None:
                if policy.version != body.version:
                    raise RequestError(ErrorCode.FILE_UPLOAD_LIMIT_VERSION_CONFLICT)
                if policy.max_file_size_bytes != body.max_file_size_bytes:
                    policy.max_file_size_bytes = body.max_file_size_bytes
                    policy.version += 1
                    policy.updated_by = user.id
                    await session.flush()
            return UploadLimitInfo.model_validate(policy)
