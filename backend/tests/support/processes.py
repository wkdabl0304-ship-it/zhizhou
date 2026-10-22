"""测试子进程支撑：固定解释器、后端工作目录、编码和有限等待。"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent / "scripts"


def run_python(*arguments: str, env_overrides=None, timeout: float = 30, expected_returncode: int = 0):
    """运行当前虚拟环境的 Python 并返回捕获结果，意外退出时报告双输出流。

    arguments 为模块或脚本参数；env_overrides 显式覆盖子进程配置而不改变
    当前进程环境。expected_returncode 用于验证故意失败的命令，默认要求成功；
    超时由 subprocess 抛出并终止子进程，不忽略失败。
    """
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=BACKEND_ROOT,
        env={**os.environ, **(env_overrides or {}), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    assert result.returncode == expected_returncode, result.stdout + result.stderr
    return result


def run_script(name: str):
    """在独立解释器执行支撑脚本，隔离日志、模块导入及服务器进程状态。"""
    return run_python(str(SCRIPTS / name))
