"""普通 JSON 接口和 SSE 事件共用的数据外壳与构建函数。"""

from pydantic import BaseModel, Field

from app.errors.codes import ErrorCode


class ApiResponse[T](BaseModel):
    """JSON 响应或单个 SSE 事件的数据外壳，T 保留 data 的具体类型。

    code 为整数，0 表示成功；失败时 data 为 None。HTTP 状态由边界层
    另行决定，业务失败及流内失败可能使用 HTTP 200，调用方须判断 code。
    """

    code: int = Field(strict=True, description="0 表示业务成功，非零表示失败")
    message: str
    data: T | None


def success[T](data: T) -> ApiResponse[T]:
    """用中央成功码包装 data，返回带具体数据类型的成功响应模型。"""
    return ApiResponse[T](
        code=ErrorCode.SUCCESS.code,
        message=ErrorCode.SUCCESS.message,
        data=data,
    )


def failure(error_code: ErrorCode) -> ApiResponse[None]:
    """从已登记的 error_code 构建安全失败响应，固定 data=None，不选择 HTTP 状态。"""
    return ApiResponse[None](code=error_code.code, message=error_code.message, data=None)
