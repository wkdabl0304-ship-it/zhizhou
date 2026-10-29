"""文件 HTTP 传输边界：受限 multipart 解析及带资源上下文的下载响应。"""

from urllib.parse import quote

from fastapi import Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import Response, StreamingResponse

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError

MULTIPART_OVERHEAD = 65536


class BoundedMultipartParser(MultiPartParser):
    """在解析回调中限制文件和头部大小，避免未鉴权落盘或先缓存超大请求。"""

    def __init__(self, headers, stream, limit):
        """只允许一个文件和零个普通字段，并限制 multipart 元数据开销。"""
        super().__init__(headers, stream, max_files=1, max_fields=0, max_part_size=MULTIPART_OVERHEAD)
        self.limit = limit
        self.file_bytes = 0
        self.header_bytes = 0

    def on_part_data(self, data, start, end):
        """在分块进入框架临时文件前拦截实际文件大小超限。"""
        self.file_bytes += end - start
        if self.file_bytes > self.limit:
            raise RequestError(ErrorCode.FILE_TOO_LARGE)
        super().on_part_data(data, start, end)

    def check_header(self, start, end):
        """限制头部片段的累计字节数，阻止超大文件名或自定义头占满内存。"""
        self.header_bytes += end - start
        if self.header_bytes > MULTIPART_OVERHEAD // 2:
            raise RequestError(ErrorCode.INVALID_ARGUMENT)

    def on_header_field(self, data, start, end):
        """在拼接 multipart 头名称前执行元数据大小检查。"""
        self.check_header(start, end)
        super().on_header_field(data, start, end)

    def on_header_value(self, data, start, end):
        """在拼接 multipart 头值前执行元数据大小检查。"""
        self.check_header(start, end)
        super().on_header_value(data, start, end)


async def upload_form(request: Request, limit: int):
    """解析单文件表单，返回由调用方关闭的表单；缺少可信长度时仍逐块限流量。"""
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise RequestError(ErrorCode.INVALID_ARGUMENT)
    try:
        if "content-length" in request.headers:
            length = int(request.headers["content-length"])
            if length < 0:
                raise ValueError
            if length > limit + MULTIPART_OVERHEAD:
                raise RequestError(ErrorCode.FILE_TOO_LARGE)
    except ValueError:
        raise RequestError(ErrorCode.INVALID_ARGUMENT) from None

    async def bounded_stream():
        """对完整传输计数，包含 multipart 边界，不能通过伪造长度绕过限制。"""
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit + MULTIPART_OVERHEAD:
                raise RequestError(ErrorCode.FILE_TOO_LARGE)
            yield chunk

    try:
        form = await BoundedMultipartParser(request.headers, bounded_stream(), limit).parse()
    except MultiPartException:
        raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
    values = form.multi_items()
    if len(values) != 1 or values[0][0] != "file" or not isinstance(values[0][1], UploadFile):
        await form.close()
        raise RequestError(ErrorCode.INVALID_ARGUMENT)
    return form


class FileDownloadResponse(Response):
    """让文件句柄及共享锁覆盖完整 ASGI 响应生命周期，包括发送失败和取消。"""

    media_type = "application/octet-stream"

    def __init__(self, service, actor, entry_id):
        """保存已认证身份和条目标识，实际授权在响应开始前再次执行。"""
        super().__init__()
        self.service = service
        self.actor = actor
        self.entry_id = entry_id

    async def __call__(self, scope, receive, send):
        """持锁打开原文件并分块发送，错误发生在响应头前时使用统一异常响应。"""
        async with self.service.transfers.download(self.actor, self.entry_id) as (info, source):
            async def content():
                """按固定大小读取原始字节，避免整个文件进入响应内存。"""
                while chunk := await source.read(65536):
                    yield chunk

            response = StreamingResponse(content(), media_type=self.media_type, headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(info.name, safe=""),
                "Content-Length": str(info.size_bytes),
                "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            })
            await response(scope, receive, send)
