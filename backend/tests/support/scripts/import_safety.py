"""入口导入验证脚本：禁止配置加载、数据库连接、模型调用和日志初始化。"""

import importlib
import logging
import os
from unittest.mock import patch

before = dict(os.environ)
handlers = list(logging.getLogger().handlers)
level = logging.getLogger().level
def forbidden(*args, **kwargs):
    '''禁止导入期间触发配置读取、连接或调用，以立即暴露外部副作用。'''
    raise AssertionError('external side effect during import')

with patch('dotenv.dotenv_values', forbidden), \
     patch('dotenv.load_dotenv', forbidden), \
     patch('app.agents.models.DeepSeekChatModel.__init__', forbidden), \
     patch('langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.from_conn_string', forbidden), \
     patch('logging.config.dictConfig', forbidden), \
     patch('uvicorn.run', forbidden):
    for name in (
        'app.core.settings', 'app.core.logging', 'app.db.checkpoint', 'app.agents.models',
        'app.core.errors.codes', 'app.core.errors.exceptions', 'app.schemas.response', 'app.api.exception_handlers',
        'app.api.dependencies', 'app.api.routes.chat', 'app.api.router',
        'app.agents.factory', 'app.agents.agent', 'app.agents.__main__', 'app.main', 'app.__main__'
    ):
        importlib.import_module(name)
assert dict(os.environ) == before
assert logging.getLogger().handlers == handlers
assert logging.getLogger().level == level
