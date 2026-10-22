"""错误模型单元测试：验证目录约束、异常分类和日志去重。"""

import logging

import pytest

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError, ServiceError, log_app_error


def test_catalog_codes_are_unique_integers_with_explanations():
    """检查中央目录码值唯一、类型为整数，并为每个条目提供非空解释。"""
    codes = [error.code for error in ErrorCode]
    assert len(codes) == len(set(codes))
    assert all(type(code) is int for code in codes)
    assert all(error.message.strip() for error in ErrorCode)
    assert ErrorCode.SUCCESS.code == 0
    assert ErrorCode.BUSINESS_ERROR.is_business


@pytest.mark.parametrize("invalid", [20000, "20000", None])
def test_business_exception_rejects_unregistered_codes(invalid):
    """验证数字、字符串或空值不能绕过错误码目录构造业务异常。"""
    with pytest.raises(TypeError):
        BusinessError(invalid)


@pytest.mark.parametrize("invalid", [ErrorCode.SUCCESS, ErrorCode.INVALID_ARGUMENT, ErrorCode.INTERNAL_ERROR])
def test_business_exception_rejects_other_catalog_categories(invalid):
    """验证成功码、请求错误码和系统码均不能被当作业务失败。"""
    with pytest.raises(ValueError):
        BusinessError(invalid)


def test_service_exception_rejects_business_code():
    """验证系统异常不能携带会被解释为 HTTP 200 的业务码。"""
    with pytest.raises(ValueError):
        ServiceError(ErrorCode.BUSINESS_ERROR)


def test_application_error_logging_is_idempotent(caplog):
    """对同一异常重复调用日志函数，确认内部标识避免重复堆栈。"""
    logger = logging.getLogger("app.test.errors")
    error = ServiceError()
    with caplog.at_level(logging.ERROR):
        log_app_error(logger, exc=error)
        log_app_error(logger, exc=error)
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info
