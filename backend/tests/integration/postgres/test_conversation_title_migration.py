"""标题迁移集成测试：验证旧标题保护、往返保留及数据库来源约束。"""

from functools import partial

import anyio
import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.checkpoint import build_conninfo
from tests.support.postgres import account, database_environment, migrate_database, open_runtime, send
from tests.support.processes import run_python

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def test_upgrade_protects_legacy_titles_and_roundtrip_preserves_content(postgres_settings):
    """降级保留现有标题，重新升级将所有旧会话保护为 manual，不改历史或模型选择。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        cid, _ = await send(runtime.client, headers, "自动来源")
        manual, _ = await send(runtime.client, headers, "手动来源")
        await runtime.client.patch(f"/api/conversations/{manual}/title", headers=headers, json={"title": "保留的手动标题"})
        async with runtime.conversations.prepare(user.id, "临时来源", None):
            pass
        async with runtime.database.sessions() as session:
            statement = text("""
                SELECT c.id, c.title, c.user_id, c.created_at, c.updated_at, c.last_message_at,
                       c.deleted_at, c.model_selection, c.model_selection_version,
                       t.seq, t.user_content, t.assistant_content, t.status, t.public_events, t.model_snapshot
                FROM conversations c JOIN chat_turns t ON c.id = t.conversation_id ORDER BY c.id, t.seq
            """)
            before = (await session.execute(statement)).all()
            assert set((await session.execute(text("SELECT title_source FROM conversations"))).scalars()) == {"auto", "manual", "provisional"}
    downgrade = partial(run_python, "-m", "alembic", "downgrade", "0004_model_selection",
                        env_overrides=database_environment(postgres_settings))
    await anyio.to_thread.run_sync(downgrade)
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        cursor = await connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'")
        assert "title_source" not in {row[0] for row in await cursor.fetchall()}
        # 验证升级前真实旧结构已有的标题不会被迁移改写。
        await connection.execute("UPDATE conversations SET title = '升级前已有标题' WHERE id = %s", (cid,))
    await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    async with open_runtime(postgres_settings, configured=False) as runtime:
        async with runtime.database.sessions() as session:
            after = (await session.execute(statement)).all()
            expected = [tuple(row[:1]) + ("升级前已有标题",) + tuple(row[2:]) if str(row[0]) == cid else tuple(row) for row in before]
            assert [tuple(row) for row in after] == expected
            assert set((await session.execute(text("SELECT title_source FROM conversations"))).scalars()) == {"manual"}
        await send(runtime.client, headers, "迁移后继续", cid)
        assert not runtime.title_model.snapshots
        detail = (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        assert detail["conversation"]["title"] == "升级前已有标题"
    await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")


async def test_source_constraint_and_default_protect_direct_database_writes(postgres_settings):
    """直接 SQL 写入也受来源枚举和非空约束限制，未指定来源时默认 manual。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        await send(runtime.client, headers)
        for value in ("unknown", "", None):
            with pytest.raises(IntegrityError):
                async with runtime.database.sessions.begin() as session:
                    await session.execute(text("UPDATE conversations SET title_source = :source"), {"source": value})
        async with runtime.database.sessions.begin() as session:
            source = await session.scalar(text("""
                INSERT INTO conversations (id, user_id, title)
                VALUES (gen_random_uuid(), :uid, '未指定来源') RETURNING title_source
            """), {"uid": user.id})
            assert source == "manual"
