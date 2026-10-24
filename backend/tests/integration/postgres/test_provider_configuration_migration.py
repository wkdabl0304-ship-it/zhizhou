"""供应商配置命名迁移回归：真实 PostgreSQL 验证升级、降级和已有数据保留。"""

from functools import partial

import anyio
import psycopg
import pytest
from sqlalchemy import select

from app.db.checkpoint import build_conninfo
from app.models import ChatTurn, ProviderConfiguration
from tests.support.postgres import account, database_environment, migrate_database, open_runtime, send
from tests.support.processes import run_python

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def test_rename_preserves_configuration_references_credentials_and_snapshots(postgres_settings):
    """更名前后配置、默认引用、密钥和历史来源一致，完整、部分和空快照均可往返迁移。"""
    async with open_runtime(postgres_settings) as runtime:
        before = await runtime.model_config.snapshot()
        _, headers = await account(runtime.auth)
        conversation_id, _ = await send(runtime.client, headers)
        for _ in range(2):
            await send(runtime.client, headers, conversation_id=conversation_id)
        async with runtime.database.sessions.begin() as session:
            turns = list(await session.scalars(select(ChatTurn).order_by(ChatTurn.seq)))
            turns[1].model_snapshot = {"provider_configuration_version": 7, "parameters": {"retained": True}}
            turns[2].model_snapshot = None
            expected_snapshots = [turn.model_snapshot for turn in turns]
            row = await session.get(ProviderConfiguration, before.provider_configuration_id)
            ciphertext = row.api_key_ciphertext

    # 先回到上一版结构，模拟已经部署旧版配置的数据库；不触及开发库。
    downgrade = partial(run_python, "-m", "alembic", "downgrade", "0002_model_configuration",
                        env_overrides=database_environment(postgres_settings))
    await anyio.to_thread.run_sync(downgrade)
    async with await psycopg.AsyncConnection.connect(build_conninfo(postgres_settings)) as connection:
        cursor = await connection.execute("""
            SELECT c.id, c.api_key_ciphertext, m.id, s.model_configuration_id
            FROM model_connections c
            JOIN model_configurations m ON m.connection_id = c.id
            JOIN chat_model_settings s ON s.model_configuration_id = m.id
        """)
        assert await cursor.fetchone() == (before.provider_configuration_id, ciphertext,
                                          before.configuration_id, before.configuration_id)
        cursor = await connection.execute("SELECT model_snapshot FROM chat_turns ORDER BY seq")
        old_snapshots = [row[0] for row in await cursor.fetchall()]
        assert old_snapshots[0] == {
            **{key: value for key, value in expected_snapshots[0].items()
               if key not in {"provider_configuration_id", "provider_configuration_version"}},
            "connection_id": str(before.provider_configuration_id),
            "connection_version": before.provider_configuration_version,
        }
        assert old_snapshots[1] == {"connection_version": 7, "parameters": {"retained": True}}
        assert old_snapshots[2] is None

    await anyio.to_thread.run_sync(migrate_database, postgres_settings)
    async with open_runtime(postgres_settings, configured=False) as runtime:
        after = await runtime.model_config.snapshot()
        assert after.public_snapshot() == before.public_snapshot()
        assert after.origin == before.origin
        assert after.api_key.get_secret_value() == before.api_key.get_secret_value()
        async with runtime.database.sessions() as session:
            row = await session.get(ProviderConfiguration, after.provider_configuration_id)
            assert row.api_key_ciphertext == ciphertext
            actual = list(await session.scalars(select(ChatTurn.model_snapshot).order_by(ChatTurn.seq)))
            assert actual == expected_snapshots
        # 迁移后的模型配置仍能经过正式聊天调用链续聊，checkpoint 来源无需重写。
        await send(runtime.client, headers, conversation_id=conversation_id)
    await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")
