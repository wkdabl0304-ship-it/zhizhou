"""集中转换 HTTP 错误响应；不重写成功响应、下载或流式响应。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import (
    BusinessError,
    RequestError,
    ServiceError,
    log_app_error,
)
from app.schemas.response import ApiResponse, failure

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    422: ErrorCode.INVALID_ARGUMENT,
}


async def request_error_handler(request: Request, exc: RequestError) -> JSONResponse:
    """返回认证或会话访问的安全请求错误，401 保留标准 Bearer 认证头。"""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return _error_response(exc.error_code, exc.status_code, headers)


def _error_response(
    error_code: ErrorCode, status_code: int, headers: dict[str, str] | None = None
) -> JSONResponse:
    """将目录 error_code 转为使用 status_code 的统一 JSONResponse。

    headers 用于保留 Allow、WWW-Authenticate 等协议头；响应体只序列化
    安全的中央解释与空 data，不直接序列化异常对象或 HTTP detail。
    """
    return JSONResponse(
        status_code=status_code,
        content=failure(error_code).model_dump(mode="json"),
        headers=headers,
    )


async def business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:
    """对 exc 补记尚未记录的业务警告，返回 HTTP 200 和对应业务码。"""
    log_app_error(logger, exc, context={"method": request.method, "path": request.url.path})
    return _error_response(exc.error_code, 200)


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """返回系统错误的固定说明与状态；未配置模型为 503，其他系统错误为 500。"""
    log_app_error(logger, exc, context={"method": request.method, "path": request.url.path})
    return _error_response(exc.error_code, exc.status_code)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """将参数或 JSON 校验失败统一转换为安全的 HTTP 422 响应。

    request、exc 由框架传入，保持处理器签名，但不读取或回传原始输入。
    """
    # 不回传 errors() 中的 input、ctx 或原始请求内容。
    return _error_response(ErrorCode.INVALID_ARGUMENT, 422)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一框架 HTTP 异常的响应体，保留 exc 的状态码和必要响应头。

    404、405、422 使用对应目录成员，其他 4xx 使用通用请求错误码；
    5xx 使用通用系统解释并在此记录堆栈，不将内部 detail 暴露给客户端。
    """
    error_code = (
        ErrorCode.INTERNAL_ERROR if exc.status_code >= 500
        else HTTP_ERROR_CODES.get(exc.status_code, ErrorCode.REQUEST_FAILED)
    )
    if exc.status_code >= 500:
        logger.error(
            "HTTP 服务异常 status=%d method=%s path=%r",
            exc.status_code, request.method, request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    return _error_response(error_code, exc.status_code, exc.headers)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """为未知异常或响应模型校验失败返回安全的 HTTP 500 响应。

    此处仅转换响应；Starlette 仍会重抛 exc，由 Uvicorn 记录原始堆栈。
    因此不在此重复写异常日志，也不把未知异常误判成业务失败。
    """
    # Starlette 在发送兜底响应后仍会重抛；由 Uvicorn 输出原始堆栈，避免重复记录。
    return _error_response(ErrorCode.INTERNAL_ERROR, 500)


def register_exception_handlers(app: FastAPI) -> None:
    """为 app 注册已知应用、请求、HTTP 和未知异常的统一处理器。

    注册发生在应用定义阶段，不依赖模型或数据库，也不会主动处理请求。
    未注册的异常最终进入 Exception 兜底，已知子类优先匹配对应处理器。
    """
    app.add_exception_handler(BusinessError, business_error_handler)
    app.add_exception_handler(RequestError, request_error_handler)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)


# 显式声明 422，覆盖 FastAPI 自动添加的默认校验响应 schema。
ERROR_RESPONSES = {
    status: {
        "model": ApiResponse[None],
        "description": error_code.message,
        "content": {"application/json": {"example": failure(error_code).model_dump(mode="json")}},
    }
    for status, error_code in {
        401: ErrorCode.UNAUTHENTICATED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
        409: ErrorCode.CONVERSATION_BUSY,
        413: ErrorCode.FILE_TOO_LARGE,
        422: ErrorCode.INVALID_ARGUMENT,
        500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.MODEL_NOT_CONFIGURED,
    }.items()
}
