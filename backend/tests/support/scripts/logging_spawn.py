"""日志 spawn 验证脚本：验证 Uvicorn 日志字典可在 Windows 子进程中应用。"""

import multiprocessing

from uvicorn import Config

from app.core.logging import build_logging_config
from app.core.settings import LoggingSettings

if __name__ == '__main__':
    # 使用标准库函数作为 spawn 目标，以模拟 Windows reload 子进程配置日志。
    config = build_logging_config(LoggingSettings())
    Config('app.main:app', log_config=config)
    import logging
    logging.getLogger('uvicorn.error').info('parent-marker')
    process = multiprocessing.get_context('spawn').Process(
        target=logging.config.dictConfig, args=(config,)
    )
    process.start()
    process.join(10)
    if process.is_alive():
        process.terminate()
        process.join()
        raise AssertionError('spawn did not finish')
    assert process.exitcode == 0
