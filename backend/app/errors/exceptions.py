"""定义可预期的业务、系统异常，并管理跨层日志去重。

异常仅依赖中央错误码目录，既可用于 HTTP，也可用于命令行；HTTP 状态
转换留给 API 层。logged 是内部标识，不会出现在客户端响应中。
"""

import logging
from collections.abc import Mapping

from app.errors.codes import ErrorCode


class AppError(Exception):
    """保存错误目录条目与日志记录状态，供具体应用异常复用。"""

    def __init__(self, error_code: ErrorCode) -> None:
        """接收已登记的 error_code，初始化安全异常消息和未记录状态。

        传入数字或字符串而非目录成员时抛出 TypeError，防止绕过中央维护。
        """
        if not isinstance(error_code, ErrorCode):
            raise TypeError("应用异常必须使用 ErrorCode 中已定义的条目")
        self.error_code = error_code
        self.logged = False
        super().__init__(error_code.message)


class BusinessError(AppError):
    """可预期业务失败，HTTP 边界返回 200，客户端通过非零 code 判断。"""

    def __init__(self, error_code: ErrorCode = ErrorCode.BUSINESS_ERROR) -> None:
        """接收业务目录成员；码值不在 20000–29999 范围时抛出 ValueError。"""
        super().__init__(error_code)
        if not error_code.is_business:
            raise ValueError("BusinessError 必须使用 20000–29999 范围内的业务码")


class ServiceError(AppError):
    """可预期系统失败，由 HTTP 边界转换为安全的 500 响应。"""

    def __init__(self, error_code: ErrorCode = ErrorCode.INTERNAL_ERROR) -> None:
        """接收系统目录成员；成功码、业务码或请求错误码均不允许使用。"""
        super().__init__(error_code)
        if not 50000 <= error_code.code <= 59999:
            raise ValueError("ServiceError 必须使用系统错误码")


def log_app_error(
    logger: logging.Logger,
    exc: AppError,
    *,
    context: Mapping[str, object] | None = None,
    cause: Exception | None = None,
) -> None:
    """通过 logger 记录 exc，并标记已记录；重复调用直接返回。

    Args:
        logger: 当前层的标准 logger，沿用全局输出配置。
        exc: 需要记录的应用异常；业务失败为 WARNING，系统失败为 ERROR。
        context: 主动允许记录的上下文，如对话标识和耗时，不应包含聊天正文。
        cause: 包装异常尚未抛出时可传入原始异常，以记录真正的失败堆栈。

    业务异常不附加堆栈；系统异常优先记录 cause，否则记录 exc 本身。
    本函数不抛出或转换 exc，调用方仍负责传播异常或构建响应。
    """
    if exc.logged:
        return
    fields = dict(context or {})
    details = " ".join(f"{key}={value!r}" for key, value in fields.items())
    business = isinstance(exc, BusinessError)
    source = cause if cause is not None else exc
    logger.log(
        # 使用标准 exc_info 元组，保留 traceback，同时避免打印局部变量值。
        logging.WARNING if business else logging.ERROR,
        "%s code=%d%s",
        exc.error_code.message,
        exc.error_code.code,
        f" {details}" if details else "",
        extra=fields,
        exc_info=None if business else (type(source), source, source.__traceback__),
    )
    exc.logged = True
