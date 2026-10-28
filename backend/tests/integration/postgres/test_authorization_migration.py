"""权限迁移集成测试：真实旧结构回填、降级保留身份和个人内容，以及实际表约束。"""

from functools import partial
from uuid import uuid4

import anyio
import psycopg
import pytest

from app.db.checkpoint import build_conninfo
from tests.support.postgres import database_environment, migrate_database
from tests.support.processes import run_python

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def test_permission_migration_preserves_legacy_accounts_and_private_content(postgres_settings):
    """旧超管和普通账号正确回填，升级与降级不改密码、启停和已有会话正文。"""
    downgrade = partial(run_python, "-m", "alembic", "downgrade", "0005_conversation_titles",
                        env_overrides=database_environment(postgres_settings))
    result = await anyio.to_thread.run_sync(downgrade)
    assert result.returncode == 0, result.stdout + result.stderr
    admin, ordinary, conversation = uuid4(), uuid4(), uuid4()
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        await connection.execute("INSERT INTO users(id, username, password_hash, role, is_active) VALUES (%s,'legacy_admin','hash-a','super_admin',true),(%s,'legacy_user','hash-b','user',false)", (admin, ordinary))
        await connection.execute("INSERT INTO conversations(id,user_id,title) VALUES(%s,%s,'私人标题')", (conversation, ordinary))
        await connection.execute("INSERT INTO chat_turns(id,conversation_id,seq,user_content,status) VALUES(%s,%s,1,'私人正文','completed')", (uuid4(), conversation))
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        rows = await (await connection.execute("SELECT u.username,r.code FROM user_roles ur JOIN users u ON u.id=ur.user_id JOIN roles r ON r.id=ur.role_id ORDER BY u.username,r.code")).fetchall()
        assert rows == [("legacy_admin", "super_admin"), ("legacy_admin", "user"), ("legacy_user", "user")]
        assert await (await connection.execute("SELECT password_hash,is_active,department_id,token_version FROM users WHERE id=%s", (ordinary,))).fetchone() == ("hash-b", False, None, 1)
        assert await (await connection.execute("SELECT user_content FROM chat_turns WHERE conversation_id=%s", (conversation,))).fetchone() == ("私人正文",)
        for scope in ("global", "department", "self"):
            assert (await (await connection.execute("SELECT count(*) FROM role_permissions WHERE scope_type=%s", (scope,))).fetchone())[0] > 0
        assert (await (await connection.execute("SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id WHERE r.code='super_admin' AND p.code LIKE 'conversation:%%'")).fetchone())[0] == 0
    result = await anyio.to_thread.run_sync(downgrade)
    assert result.returncode == 0, result.stdout + result.stderr
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        assert await (await connection.execute("SELECT role FROM users WHERE id=%s", (admin,))).fetchone() == ("super_admin",)
        assert await (await connection.execute("SELECT title FROM conversations WHERE id=%s", (conversation,))).fetchone() == ("私人标题",)
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    assert result.returncode == 0, result.stdout + result.stderr
