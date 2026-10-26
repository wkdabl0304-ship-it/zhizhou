"""受限选择迁移回归：真实临时库验证旧数据保留、降级往返和数据库基本约束。"""

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


async def test_upgrade_preserves_old_configuration_and_initializes_legacy_selection(postgres_settings):
    """旧配置升级默认启用且固定推理，选择为空；凭据、默认及轮次快照保持原值。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        cid, _ = await send(runtime.client, headers)
        async with runtime.database.sessions() as session:
            before = (await session.execute(text("""
                SELECT p.api_key_ciphertext, p.credential_revision, p.version, m.reasoning,
                       m.version, s.model_configuration_id, t.model_snapshot
                FROM provider_configurations p JOIN model_configurations m ON m.provider_configuration_id = p.id
                JOIN chat_model_settings s ON s.model_configuration_id = m.id
                JOIN chat_turns t ON t.conversation_id = :cid
            """), {"cid": cid})).one()
    downgrade = partial(run_python, "-m", "alembic", "downgrade", "0003_provider_configuration",
                        env_overrides=database_environment(postgres_settings))
    await anyio.to_thread.run_sync(downgrade)
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        cursor = await connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'")
        assert "model_selection" not in {row[0] for row in await cursor.fetchall()}
    await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    async with open_runtime(postgres_settings, configured=False) as runtime:
        async with runtime.database.sessions() as session:
            after = (await session.execute(text("""
                SELECT p.api_key_ciphertext, p.credential_revision, p.version, m.reasoning,
                       m.version, s.model_configuration_id, t.model_snapshot
                FROM provider_configurations p JOIN model_configurations m ON m.provider_configuration_id = p.id
                JOIN chat_model_settings s ON s.model_configuration_id = m.id
                JOIN chat_turns t ON t.conversation_id = :cid
            """), {"cid": cid})).one()
            defaults = (await session.execute(text("""
                SELECT p.enabled, m.enabled, m.reasoning_policy, c.model_selection,
                       c.model_selection_version, c.model_selection IS NULL
                FROM provider_configurations p CROSS JOIN model_configurations m CROSS JOIN conversations c
            """))).one()
        assert after == before
        assert tuple(defaults) == (True, True, {"mode": "fixed"}, None, 1, True)
        _, events = await send(runtime.client, headers, conversation_id=cid)
        assert events[0].payload["data"]["model_selection_version"] == 2
    await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")


async def test_database_rejects_invalid_json_and_nonpositive_versions(postgres_settings):
    """直接 SQL 也不能写入空策略模式、非对象 JSON 和无效选择版本。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        await send(runtime.client, headers)
        for statement in (
            "UPDATE model_configurations SET reasoning_policy = '{}'::jsonb",
            "UPDATE model_configurations SET reasoning_policy = jsonb_build_object('mode', NULL)",
            "UPDATE model_configurations SET reasoning_policy = '{\"mode\":\"unknown\"}'::jsonb",
            "UPDATE model_configurations SET reasoning_policy = '[]'::jsonb",
            "UPDATE conversations SET model_selection = 'null'::jsonb",
            "UPDATE conversations SET model_selection = '[]'::jsonb",
            "UPDATE conversations SET model_selection_version = 0",
        ):
            with pytest.raises(IntegrityError):
                async with runtime.database.sessions.begin() as session:
                    await session.execute(text(statement))
