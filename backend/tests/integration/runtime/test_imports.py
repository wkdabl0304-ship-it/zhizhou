"""导入集成测试：在独立解释器禁止入口导入时触发外部副作用。"""

import pytest

from tests.support.processes import run_script


@pytest.mark.subprocess
def test_imports_do_not_load_configuration_connect_or_invoke():
    """在独立进程禁止外部副作用，验证所有入口的导入保持惰性。"""
    result = run_script("import_safety.py")
    assert result.returncode == 0, result.stderr
