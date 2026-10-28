"""权限事务回归：单连接池下的配置读写和共享授权事务的回滚边界。"""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.schemas.model_config import ModelPatch
from app.services.authorization import AuthorizationService
from app.services.model_config import ModelConfigService
from app.services.model_management import ModelManagementService
from tests.support.postgres import account, open_runtime

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def test_model_authorization_and_storage_share_one_pool_connection(postgres_settings):
    """模型选项及管理读写在单连接池也能完成，并发请求不会因嵌套申请连接死锁。"""
    async with open_runtime(postgres_settings) as runtime:
        _, root_headers = await account(runtime.auth, "super_admin")
        _, user_headers = await account(runtime.auth)
        root = await runtime.auth.authenticate(root_headers["Authorization"].removeprefix("Bearer "))
        user = await runtime.auth.authenticate(user_headers["Authorization"].removeprefix("Bearer "))
        engine = create_async_engine(runtime.database.engine.url, pool_size=1, max_overflow=0, pool_timeout=5,
                                     hide_parameters=True)
        database = replace(runtime.database, engine=engine, sessions=async_sessionmaker(engine, expire_on_commit=False))
        configuration = ModelConfigService(database, postgres_settings.model_config_encryption_key,
                                           model_opener=runtime.model_config.model_opener)
        management = ModelManagementService(configuration)
        try:
            options = await asyncio.wait_for(asyncio.gather(*[management.options(user) for _ in range(4)]), 15)
            assert all(option.providers for option in options)
            rows = await asyncio.wait_for(asyncio.gather(*[
                management.execute(root, configuration.list_models) for _ in range(4)]), 15)
            model = rows[0][0]
            changed = await asyncio.wait_for(management.execute(root, configuration.patch_model, model.id,
                ModelPatch(version=model.version, name="共享事务中的配置")), 10)
            assert changed.name == "共享事务中的配置" and changed.version == model.version + 1
            assert (await configuration.get_model(model.id)).name == changed.name
        finally:
            await engine.dispose()


async def test_borrowed_configuration_transaction_does_not_commit_before_owner(postgres_settings):
    """底层配置借用授权事务后不能独立提交，外层失败必须撤销已经 flush 的修改。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, "super_admin")
        root = await runtime.auth.authenticate(headers["Authorization"].removeprefix("Bearer "))
        model = (await runtime.model_config.list_models())[0]
        authorization = AuthorizationService(runtime.database)
        with pytest.raises(RuntimeError, match="模拟业务提交前失败"):
            async with authorization.transaction(root, "model:manage") as session:
                changed = await runtime.model_config.patch_model(model.id, ModelPatch(version=model.version,
                    name="应该整体回滚"), session=session)
                assert changed.name == "应该整体回滚"
                raise RuntimeError("模拟业务提交前失败")
        current = await runtime.model_config.get_model(model.id)
        assert current.name == model.name and current.version == model.version
