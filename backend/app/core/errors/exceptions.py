"""定义可预期的业务、系统异常，并管理跨层日志去重。

异常仅依赖中央错误码目录，既可用于 HTTP，也可用于命令行；HTTP 状态
转换留给 API 层。logged 是内部标识，不会出现在客户端响应中。
"""

import logging
from collections.abc import Mapping
from typing import ClassVar

from app.core.errors.codes import ErrorCode


class AppError(Exception):
    """保存错误目录条目与日志记录状态，供具体应用异常复用。"""

    def __init__(self, error_code: ErrorCode) -> None:
        """创建携带中央错误码及日志记录状态的应用异常。

        error_code 决定安全异常消息，logged 初始为 False，供跨层日志去重。
        传入数字或字符串而非目录成员时抛出 TypeError，防止绕过中央维护。
        """
        if not isinstance(error_code, ErrorCode):
            raise TypeError("应用异常必须使用 ErrorCode 中已定义的条目")
        self.error_code = error_code
        self.logged = False
        super().__init__(error_code.message)


class BusinessError(AppError):
    """可预期业务失败，JSON 或 SSE 边界返回非零业务码，HTTP 状态为 200。"""

    def __init__(self, error_code: ErrorCode = ErrorCode.BUSINESS_ERROR) -> None:
        """创建可预期业务失败，供协议边界返回对应业务码。

        error_code 必须是业务目录成员；不在 20000–29999 范围时抛出
        ValueError，避免把请求错误或系统异常当作普通业务失败。
        """
        super().__init__(error_code)
        if not error_code.is_business:
            raise ValueError("BusinessError 必须使用 20000–29999 范围内的业务码")


class RequestError(AppError):
    """已登记的认证及资源访问失败，HTTP 边界返回对应 4xx，SSE 内仍使用错误事件。"""

    _statuses: ClassVar[dict[ErrorCode, int]] = {
        ErrorCode.UNAUTHENTICATED: 401,
        ErrorCode.INVALID_CREDENTIALS: 401,
        ErrorCode.CONVERSATION_NOT_FOUND: 404,
        ErrorCode.CONVERSATION_BUSY: 409,
        ErrorCode.INVALID_ARGUMENT: 422,
        ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND: 404,
        ErrorCode.MODEL_CONFIGURATION_NOT_FOUND: 404,
        ErrorCode.MODEL_VERSION_CONFLICT: 409,
        ErrorCode.MODEL_CONFIG_IN_USE: 409,
    }

    def __init__(self, error_code: ErrorCode) -> None:
        """创建认证或资源访问失败，并附上预先约定的 HTTP 状态。

        error_code 必须位于 _statuses 映射中，否则抛出 ValueError；
        调用层不能自行改变该错误码对应的 HTTP 状态。
        """
        super().__init__(error_code)
        if error_code not in self._statuses:
            raise ValueError("RequestError 必须使用已登记的请求错误码")
        self.status_code = self._statuses[error_code]


class ServiceError(AppError):
    """可预期系统失败；默认返回 500，未配置模型返回 503，流内使用 error 事件。"""

    def __init__(self, error_code: ErrorCode = ErrorCode.INTERNAL_ERROR) -> None:
        """创建需要作为系统故障处理的应用异常。

        error_code 只能使用 50000–59999 范围内的系统目录成员，
        成功码、业务码或请求错误码会触发 ValueError。
        """
        super().__init__(error_code)
        if not 50000 <= error_code.code <= 59999:
            raise ValueError("ServiceError 必须使用系统错误码")
        self.status_code = 503 if error_code is ErrorCode.MODEL_NOT_CONFIGURED else 500


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
