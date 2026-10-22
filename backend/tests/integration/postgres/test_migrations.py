"""PostgreSQL 集成测试：独立临时库验证迁移、索引及 ORM 约束。"""

from uuid import uuid4

import anyio
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db.business import check_schema
from app.models import ChatTurn, Conversation
from tests.support.postgres import open_runtime as runtime, account, send, migrate_database

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_real_migration_orm_constraints_and_checkpoint_exclusion(postgres_settings):
    """验证正式数据库迁移与 ORM 一致，并保留第三方 checkpoint 表。

    检查实际约束和索引，以及 Alembic check 不会误报应删除 checkpoint 表。
    """

    async with runtime(postgres_settings) as environment:
        database = environment.database
        auth = environment.auth
        client = environment.client
        await check_schema(database.engine)
        async with database.engine.connect() as connection:

            def indexes(sync_connection):
                """通过异步连接桥接 Inspector，仅用于检查数据库实际索引。"""
                return inspect(sync_connection).get_indexes("conversations")

            actual = await connection.run_sync(indexes)
            assert any(
                item["name"] == "idx_conversations_user_recent" for item in actual
            )
        _user, headers = await account(auth)
        conversation_id, _ = await send(client, headers)
        from uuid import UUID

        with pytest.raises(IntegrityError):
            async with database.sessions.begin() as session:
                session.add(
                    ChatTurn(
                        conversation_id=UUID(conversation_id),
                        seq=1,
                        user_content="重复轮次",
                    )
                )
        with pytest.raises(IntegrityError):
            async with database.sessions.begin() as session:
                session.add(Conversation(user_id=uuid4(), title="外键必须存在"))
    result = await anyio.to_thread.run_sync(migrate_database, postgres_settings, "check")
    assert result.returncode == 0, result.stdout + result.stderr
