"""日志输出验证脚本：隔离全局 dictConfig，验证格式、级别、输出流与重复初始化。"""

import logging

from app.core.logging import configure_logging
from app.core.settings import LoggingSettings

# 先模拟 Uvicorn 已安装自己的 handler。
for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
    logging.getLogger(name).addHandler(logging.StreamHandler())
third = logging.getLogger('external.library')
third.setLevel(logging.DEBUG)
settings = LoggingSettings()
configure_logging(settings)
configure_logging(settings)
logging.getLogger('app.agents.agent').debug('hidden-app-debug')
logging.getLogger('app.agents.agent').info('visible-app-info')
logging.getLogger('uvicorn.error').info('visible-server-info')
logging.getLogger('uvicorn.access').info('visible-access-info')
third.info('hidden-third-party-info')
third.warning('visible-third-party-warning')
assert not third.disabled
assert len(logging.getLogger().handlers) == 1
configure_logging(LoggingSettings('DEBUG', 'DEBUG', False))
logging.getLogger('app.agents.agent').debug('visible-app-debug')
third.debug('visible-third-party-debug')
logging.getLogger('uvicorn.access').info('hidden-disabled-access')
print('stdout-reply')
