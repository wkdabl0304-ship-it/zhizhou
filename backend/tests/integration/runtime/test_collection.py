"""测试发现集成回归：独立进程在无业务配置和禁止数据库连接时收集全量测试。"""

import pytest

from tests.support.processes import SCRIPTS, run_python


@pytest.mark.subprocess
def test_collection_does_not_initialize_external_resources():
    """验证收集阶段不读取有效数据库配置、不建库且不需要模型与 JWT 密钥。"""
    run_python(
        str(SCRIPTS / "collection_safety.py"),
        env_overrides={"POSTGRES_PORT": "invalid", "DEEPSEEK_API_KEY": "", "JWT_SECRET": ""},
    )
