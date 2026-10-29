"""文件模块的严格输入、公开响应及文件名规则；不暴露磁盘和清理状态。"""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal
import unicodedata
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def normalize_name(value):
    """规范化文件和目录的显示名称，拒绝路径、控制字符及不可用名称。"""
    if not isinstance(value, str):
        raise ValueError("名称必须是字符串")
    value = unicodedata.normalize("NFC", value.strip())
    if (not 1 <= len(value) <= 255 or value in {".", ".."}
        or any(char in "/\\" or unicodedata.category(char).startswith("C") for char in value)):
        raise ValueError("文件名称不可用")
    return value


def name_key(value: str) -> str:
    """生成忽略大小写并消除规范等价差异的名称比较键。"""
    return unicodedata.normalize("NFC", value.casefold())


def numbered_name(name: str, number: int) -> str:
    """为重复上传生成受长度约束的序号名称，尽量保留最后一个扩展名。"""
    suffix = f" ({number})"
    extension = PurePosixPath(name).suffix
    stem = name[:-len(extension)] if extension else name
    room = 255 - len(suffix) - len(extension)
    if room < 1:
        return name[:255 - len(suffix)] + suffix
    return stem[:room] + suffix + extension


type FileName = Annotated[str, BeforeValidator(normalize_name), Field(min_length=1, max_length=255)]
type SpaceKind = Literal["global", "department", "personal"]
type Capability = Literal["read", "upload", "update", "delete"]


class FileInput(BaseModel):
    """拒绝未知字段，防止客户端注入空间归属、原文件键或内部状态。"""

    model_config = ConfigDict(extra="forbid")


class FolderCreate(FileInput):
    """指定空间内创建目录，parent_id 为空时使用空间根目录。"""

    parent_id: UUID | None = None
    name: FileName


class EntryRename(FileInput):
    """以已读取版本重命名条目，防止覆盖其他请求的修改。"""

    name: FileName
    version: int = Field(strict=True, gt=0)


class UploadLimitUpdate(FileInput):
    """设置字节单位的上传上限，并携带乐观并发版本。"""

    max_file_size_bytes: int = Field(strict=True, ge=1, le=1099511627776)
    version: int = Field(strict=True, gt=0)


class UploadLimitInfo(BaseModel):
    """返回可见上传策略及最后修改信息，不包含数据库内部主键。"""

    model_config = ConfigDict(from_attributes=True)
    scope_type: SpaceKind
    department_id: UUID | None
    max_file_size_bytes: int
    version: int
    updated_by: UUID | None
    updated_at: datetime


class SpaceInfo(BaseModel):
    """返回空间归属、有效上限和当前账号可执行的操作。"""

    id: UUID
    kind: SpaceKind
    name: str
    department_id: UUID | None
    owner_id: UUID | None
    max_file_size_bytes: int
    capabilities: list[Capability]


class EntryInfo(BaseModel):
    """返回有效条目元数据；目录大小为空，空文件大小为零。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    space_id: UUID
    parent_id: UUID | None
    kind: Literal["file", "folder"]
    name: str
    size_bytes: int | None
    created_by: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class Breadcrumb(BaseModel):
    """标识一层可读目录，根目录由空间信息表达。"""

    id: UUID
    name: str


class EntryDetail(BaseModel):
    """返回条目及其所在目录链，目录详情的链包含自身。"""

    entry: EntryInfo
    breadcrumbs: list[Breadcrumb]


class DirectoryPage(BaseModel):
    """返回一层目录的稳定分页、面包屑及空间能力。"""

    space: SpaceInfo
    parent_id: UUID | None
    breadcrumbs: list[Breadcrumb]
    items: list[EntryInfo]
    next_cursor: str | None
