"""文件正式迁移集成测试：存量回填、降级保护及数据库约束与 ORM 一致性。"""

from functools import partial
from uuid import uuid4

import anyio
import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.checkpoint import build_conninfo
from app.models import FileBlob, FileEntry, FileSpace, FileUploadPolicy
from tests.support.files import folder, space, upload
from tests.support.postgres import account, database_environment, migrate_database, open_runtime
from tests.support.processes import run_python

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


async def downgrade(settings, *, expected_returncode=0):
    """仅在本例随机库回退到文件模块之前的版本，保留命令输出供断言。"""
    return await anyio.to_thread.run_sync(partial(run_python, "-m", "alembic", "downgrade", "0006_authorization",
        env_overrides=database_environment(settings), expected_returncode=expected_returncode))


async def test_migration_backfills_existing_users_departments_and_role_grants(postgres_settings):
    """真实旧结构升级后每个账号部门均有空间，默认上限和文件范围授权完整。"""
    result = await downgrade(postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr
    first, second, dep = uuid4(), uuid4(), uuid4()
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        await connection.execute("INSERT INTO departments(id,name) VALUES(%s,'旧部门')", (dep,))
        await connection.execute("INSERT INTO users(id,username,password_hash,department_id,is_active) VALUES(%s,'legacy_one','hash',%s,true),(%s,'legacy_two','hash',NULL,false)", (first, dep, second))
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr
    async with open_runtime(postgres_settings, configured=False) as runtime:
        async with runtime.database.sessions() as session:
            rows = (await session.scalars(select(FileSpace))).all()
            assert len(rows) == 4
            assert {row.owner_id for row in rows if row.kind == "personal"} == {first, second}
            assert {row.department_id for row in rows if row.kind == "department"} == {dep}
            policies = (await session.scalars(select(FileUploadPolicy))).all()
            assert len(policies) == 3 and {row.max_file_size_bytes for row in policies} == {104857600}
            assert all(row.version == 1 and row.updated_by is None for row in policies)
            grants = (await session.execute(text("""SELECT r.code,p.code,rp.scope_type FROM role_permissions rp
                JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id WHERE p.code LIKE 'file%%'"""))).all()
            assert ("user", "file:upload", "self") in grants
            assert ("super_admin", "file:read", "global") in grants
            assert ("department_admin", "file_upload_limit:update", "department") in grants
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")
    assert result.returncode == 0, result.stdout + result.stderr
    result = await downgrade(postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr


async def test_downgrade_refuses_business_data_and_does_not_touch_original_file(postgres_settings):
    """存在目录或文件记录时迁移拒绝降级，磁盘原件和全部表均保留。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, headers = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        node = await upload(runtime, headers, own["id"])
        before = list(runtime.files.storage.root.rglob("*.blob"))
    result = await downgrade(postgres_settings, expected_returncode=1)
    assert result.returncode == 1 and "存在文件业务数据" in result.stdout + result.stderr
    assert all(path.exists() for path in before)
    async with open_runtime(postgres_settings, configured=False) as runtime:
        response = await runtime.client.get(f"/api/files/entries/{node['id']}/download", headers=headers)
        assert response.status_code == 200 and response.content == b"\x00\xfforiginal"


async def test_database_enforces_root_names_parent_space_and_blob_state(postgres_settings):
    """绕过服务的直接写入仍不能破坏根目录判重、跨空间父外键及原件约束。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        first, headers = await account(runtime.auth)
        second, sh = await account(runtime.auth)
        own = await space(runtime, headers, "personal")
        other = await space(runtime, sh, "personal")
        parent = await folder(runtime, headers, own["id"], "Root")
        from uuid import UUID
        for values in (
            {"space_id": UUID(own["id"]), "name": "ROOT", "name_key": "root"},
            {"space_id": UUID(other["id"]), "name": "cross", "name_key": "cross", "parent_id": UUID(parent["id"])},
        ):
            with pytest.raises(IntegrityError):
                async with runtime.database.sessions.begin() as session:
                    session.add(FileEntry(kind="folder", created_by=first.id, **values))
        with pytest.raises(IntegrityError):
            async with runtime.database.sessions.begin() as session:
                session.add(FileBlob(storage_key="unused", state="ready"))
        with pytest.raises(IntegrityError):
            async with runtime.database.sessions.begin() as session:
                session.add(FileSpace(kind="personal", owner_id=first.id))
        result = await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")
        assert result.returncode == 0, result.stdout + result.stderr
