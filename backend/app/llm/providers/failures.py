"""上游失败分类：只跨层传递固定错误码，不携带供应商响应或请求凭据。"""

import httpx
from contextlib import aclosing

from app.core.errors.codes import ErrorCode


class ProviderFailure(Exception):
    """表示已脱敏的供应商调用失败，原始 SDK 异常不跨越此边界。"""

    def __init__(self, error_code: ErrorCode):
        """保存可公开的失败类别，异常字符串只包含固定目录说明。"""
        self.error_code = error_code
        super().__init__(error_code.message)


def classify_failure(error: Exception) -> ErrorCode:
    """把 SDK 状态和网络失败归类，不读取可能含密钥的 body 或异常字符串。"""
    status = getattr(error, "status_code", None)
    if status in {401, 403}:
        return ErrorCode.MODEL_AUTH_FAILED
    if status in {402, 429}:
        return ErrorCode.MODEL_RATE_LIMITED
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or type(error).__name__ == "APITimeoutError":
        return ErrorCode.MODEL_TIMEOUT
    return ErrorCode.MODEL_TEST_FAILED


class SafeStreamMixin:
    """在专用客户端的异步调用边界转换异常，保留原生流解析及工具绑定行为。"""

    async def _astream(self, *args, **kwargs):
        """转发原生模型流，失败时切断原始异常链以防请求信息进入应用日志。"""
        try:
            async with aclosing(super()._astream(*args, **kwargs)) as stream:
                async for chunk in stream:
                    yield chunk
        except ProviderFailure:
            raise
        except Exception as error:
            raise ProviderFailure(classify_failure(error)) from None
