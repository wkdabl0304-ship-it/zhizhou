"""文件模块的空间、上传策略、原文件和目录树实体；磁盘内容不进入数据库。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (BigInteger, CHAR, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, Integer, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.entities import Base


class FileSpace(Base):
    """保存空间的权限归属；部门删除后保留关闭空间，供文件清理追踪。"""

    __tablename__ = "file_spaces"
    __table_args__ = (
        CheckConstraint("kind IN ('global', 'department', 'personal')", name="ck_file_spaces_kind"),
        CheckConstraint("(kind = 'global' AND department_id IS NULL AND owner_id IS NULL AND deleted_at IS NULL) OR "
                        "(kind = 'personal' AND department_id IS NULL AND owner_id IS NOT NULL AND deleted_at IS NULL) OR "
                        "(kind = 'department' AND owner_id IS NULL AND (department_id IS NOT NULL OR deleted_at IS NOT NULL))",
                        name="ck_file_spaces_ownership"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("uq_file_spaces_global", FileSpace.kind, unique=True,
      postgresql_where=text("kind = 'global' AND deleted_at IS NULL"))
Index("uq_file_spaces_department", FileSpace.department_id, unique=True,
      postgresql_where=text("kind = 'department' AND deleted_at IS NULL"))
Index("uq_file_spaces_personal", FileSpace.owner_id, unique=True,
      postgresql_where=text("kind = 'personal' AND deleted_at IS NULL"))


class FileUploadPolicy(Base):
    """保存全局、个人统一和部门独立的上传上限，不影响已保存文件。"""

    __tablename__ = "file_upload_policies"
    __table_args__ = (
        CheckConstraint("scope_type IN ('global', 'personal', 'department')", name="ck_file_upload_policies_scope"),
        CheckConstraint("(scope_type = 'department' AND department_id IS NOT NULL) OR "
                        "(scope_type IN ('global', 'personal') AND department_id IS NULL)",
                        name="ck_file_upload_policies_department"),
        CheckConstraint("max_file_size_bytes BETWEEN 1 AND 1099511627776", name="ck_file_upload_policies_size"),
        CheckConstraint("version > 0", name="ck_file_upload_policies_version"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scope_type: Mapped[str] = mapped_column(String(16))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    max_file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=104857600, server_default="104857600")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


Index("uq_file_upload_policies_scope", FileUploadPolicy.scope_type, unique=True,
      postgresql_where=text("department_id IS NULL"))
Index("uq_file_upload_policies_department", FileUploadPolicy.department_id, unique=True,
      postgresql_where=text("department_id IS NOT NULL"))


class FileBlob(Base):
    """记录原文件的发布与清理状态；purged 墓碑不提供恢复能力。"""

    __tablename__ = "file_blobs"
    __table_args__ = (
        CheckConstraint("state IN ('staging', 'ready', 'delete_pending', 'purged')", name="ck_file_blobs_state"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_file_blobs_size"),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="ck_file_blobs_sha256"),
        CheckConstraint("state <> 'ready' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL)", name="ck_file_blobs_ready"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    state: Mapped[str] = mapped_column(String(16), default="staging", server_default="staging", index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FileEntry(Base):
    """保存用户可见的文件和目录；复合父外键阻止跨空间目录关系。"""

    __tablename__ = "file_entries"
    __table_args__ = (
        UniqueConstraint("space_id", "id", name="uq_file_entries_space_id"),
        ForeignKeyConstraint(["space_id", "parent_id"], ["file_entries.space_id", "file_entries.id"],
                             name="fk_file_entries_parent", ondelete="RESTRICT"),
        CheckConstraint("kind IN ('file', 'folder')", name="ck_file_entries_kind"),
        CheckConstraint("(kind = 'file' AND blob_id IS NOT NULL) OR (kind = 'folder' AND blob_id IS NULL)",
                        name="ck_file_entries_blob"),
        CheckConstraint("length(name) BETWEEN 1 AND 255 AND name = btrim(name)", name="ck_file_entries_name"),
        CheckConstraint("version > 0", name="ck_file_entries_version"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_file_entries_parent"),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    space_id: Mapped[UUID] = mapped_column(ForeignKey("file_spaces.id", ondelete="RESTRICT"))
    parent_id: Mapped[UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(Text)
    blob_id: Mapped[UUID | None] = mapped_column(ForeignKey("file_blobs.id", ondelete="RESTRICT"), unique=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("uq_file_entries_name", FileEntry.space_id, FileEntry.parent_id, FileEntry.name_key, unique=True,
      postgresql_nulls_not_distinct=True, postgresql_where=text("deleted_at IS NULL"))
Index("idx_file_entries_directory", FileEntry.space_id, FileEntry.parent_id,
      FileEntry.created_at.desc(), FileEntry.id.desc(), postgresql_where=text("deleted_at IS NULL"))
Index("idx_file_entries_parent", FileEntry.space_id, FileEntry.parent_id)
