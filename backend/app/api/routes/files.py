"""共享文件 API：空间和目录管理、受限单文件上传、附件下载及范围上传策略。"""

from typing import Annotated, Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import get_current_user, get_file_service
from app.api.file_streaming import FileDownloadResponse, upload_form
from app.models import User
from app.schemas.authorization import Page
from app.schemas.files import (DirectoryPage, EntryDetail, EntryInfo, EntryRename, FolderCreate,
                               SpaceInfo, UploadLimitInfo, UploadLimitUpdate)
from app.schemas.response import ApiResponse, success
from app.services.files import FileService

router = APIRouter(prefix="/files", tags=["共享文件"])
type Actor = Annotated[User, Depends(get_current_user)]
type Service = Annotated[FileService, Depends(get_file_service)]
type Limit = Annotated[int, Query(ge=1, le=100)]
type Cursor = Annotated[str | None, Query(max_length=2048)]


@router.get("/spaces", response_model=ApiResponse[Page[SpaceInfo]])
async def spaces(actor: Actor, service: Service, limit: Limit = 20, cursor: Cursor = None):
    """分页列出当前可见的全局、部门和本人个人空间。"""
    return success(await service.spaces(actor, limit=limit, cursor=cursor))


@router.get("/spaces/{space_id}", response_model=ApiResponse[SpaceInfo])
async def space(space_id: UUID, actor: Actor, service: Service):
    """读取空间及其有效上传限制和操作能力。"""
    return success(await service.space(actor, space_id))


@router.get("/spaces/{space_id}/entries", response_model=ApiResponse[DirectoryPage])
async def directory(space_id: UUID, actor: Actor, service: Service, parent_id: UUID | None = None,
                    limit: Limit = 20, cursor: Cursor = None):
    """分页浏览一层目录，省略 parent_id 时浏览空间根目录。"""
    return success(await service.directory(actor, space_id, parent_id=parent_id, limit=limit, cursor=cursor))


@router.post("/spaces/{space_id}/folders", response_model=ApiResponse[EntryInfo])
async def folder(space_id: UUID, body: FolderCreate, actor: Actor, service: Service):
    """创建目录；同一层存在同名文件或目录时返回名称冲突。"""
    return success(await service.folder(actor, space_id, body))


@router.post("/spaces/{space_id}/files", response_model=ApiResponse[EntryInfo], openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "additionalProperties": False,
        "properties": {"file": {"type": "string", "format": "binary"}},
    }}}},
})
async def upload(space_id: UUID, request: Request, actor: Actor, service: Service, parent_id: UUID | None = None):
    """先验证可写目标再读取单文件表单，完成后返回自动分配的最终名称。"""
    limit = await service.transfers.target(actor, space_id, parent_id)
    form = await upload_form(request, limit)
    try:
        uploaded = form["file"]

        async def chunks():
            """分块读取已受限的临时文件，原件发布与权限复查由业务服务执行。"""
            while chunk := await uploaded.read(1024 * 1024):
                yield chunk

        return success(await service.transfers.upload(actor, space_id, parent_id, uploaded.filename, chunks()))
    finally:
        with anyio.CancelScope(shield=True):
            await form.close()


@router.get("/entries/{entry_id}", response_model=ApiResponse[EntryDetail])
async def entry(entry_id: UUID, actor: Actor, service: Service):
    """读取有效条目详情及其目录面包屑。"""
    return success(await service.detail(actor, entry_id))


@router.patch("/entries/{entry_id}", response_model=ApiResponse[EntryInfo])
async def rename(entry_id: UUID, body: EntryRename, actor: Actor, service: Service):
    """按已读取版本重命名文件或目录，不覆盖其他请求的修改。"""
    return success(await service.rename(actor, entry_id, body))


@router.delete("/entries/{entry_id}", response_model=ApiResponse[None])
async def delete(entry_id: UUID, actor: Actor, service: Service, version: Annotated[int, Query(gt=0)]):
    """按版本删除文件或递归删除目录，立即隐藏条目并可靠清理原件。"""
    await service.delete(actor, entry_id, version)
    return success(None)


@router.get("/entries/{entry_id}/download", response_class=FileDownloadResponse, status_code=200,
            responses={200: {"description": "完整原文件附件", "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def download(entry_id: UUID, actor: Actor, service: Service):
    """通过当前权限检查下载完整文件，原件不通过静态地址暴露。"""
    return FileDownloadResponse(service, actor, entry_id)


@router.get("/upload-limits/departments/{department_id}", response_model=ApiResponse[UploadLimitInfo])
async def department_limit(department_id: UUID, actor: Actor, service: Service):
    """读取本人部门或全局授权覆盖的部门上传限制。"""
    return success(await service.policies.get_or_update(actor, "department", department_id))


@router.patch("/upload-limits/departments/{department_id}", response_model=ApiResponse[UploadLimitInfo])
async def update_department_limit(department_id: UUID, body: UploadLimitUpdate, actor: Actor, service: Service):
    """按版本修改部门上传限制，允许相应部门及全局管理授权。"""
    return success(await service.policies.get_or_update(actor, "department", department_id, body))


@router.get("/upload-limits/{scope}", response_model=ApiResponse[UploadLimitInfo])
async def limit(scope: Literal["global", "personal"], actor: Actor, service: Service):
    """读取全局空间或个人空间统一上传限制。"""
    return success(await service.policies.get_or_update(actor, scope))


@router.patch("/upload-limits/{scope}", response_model=ApiResponse[UploadLimitInfo])
async def update_limit(scope: Literal["global", "personal"], body: UploadLimitUpdate, actor: Actor, service: Service):
    """按版本修改全局或个人统一上限，仅接受全局管理授权。"""
    return success(await service.policies.get_or_update(actor, scope, body=body))
