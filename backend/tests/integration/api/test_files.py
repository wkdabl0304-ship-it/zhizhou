"""文件 HTTP 边界集成测试：真实 multipart 解析的限额、清理和 OpenAPI 协议。"""

import pytest
from starlette.requests import Request

from app.api.file_streaming import upload_form
from app.core.errors.exceptions import RequestError
from tests.support.apps import make_app


def multipart_request(content, *, length=None, header_extra=b"", closing=True):
    """构造分块 ASGI 请求，不依赖真实磁盘或数据库；长度可故意与正文不一致。"""
    body = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="a.bin"\r\n' + header_extra
    body += b"\r\n" + content + (b"\r\n--boundary--\r\n" if closing else b"")
    headers = [(b"content-type", b"multipart/form-data; boundary=boundary")]
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    chunks = iter([body[index:index + 7] for index in range(0, len(body), 7)])

    async def receive():
        """逐次交付小块正文，确保限额检查不依赖 Content-Length。"""
        chunk = next(chunks, None)
        return {"type": "http.request", "body": chunk or b"", "more_body": chunk is not None}

    return Request({"type": "http", "headers": headers}, receive)


@pytest.mark.anyio
@pytest.mark.parametrize("length", [None, 1])
async def test_multipart_size_is_enforced_for_chunked_or_forged_length(length):
    """没有长度或声明伪造长度均不能绕过实际文件字节上限。"""
    request = multipart_request(b"123", length=length)
    with pytest.raises(RequestError) as error:
        await upload_form(request, 2)
    assert error.value.error_code.code == 41301


@pytest.mark.anyio
async def test_multipart_exact_limit_empty_file_and_incomplete_body():
    """恰好达到上限和空文件均可解析，不完整文件不会被当作有效上传。"""
    for content in (b"", b"12"):
        form = await upload_form(multipart_request(content), 2)
        try:
            assert await form["file"].read() == content
        finally:
            await form.close()
    with pytest.raises(RequestError) as error:
        await upload_form(multipart_request(b"12", closing=False), 100)
    assert error.value.error_code.code == 42200


@pytest.mark.anyio
async def test_oversized_multipart_headers_and_declared_body_are_rejected():
    """超大 multipart 头不会无限缓存在内存，过大的声明正文在解析前被拒绝。"""
    with pytest.raises(RequestError) as error:
        await upload_form(multipart_request(b"", header_extra=b"X-Extra: " + b"x" * 33000 + b"\r\n"), 100000)
    assert error.value.error_code.code == 42200
    with pytest.raises(RequestError) as error:
        await upload_form(multipart_request(b"", length=100000), 1)
    assert error.value.error_code.code == 41301


def test_openapi_documents_auth_binary_transfer_and_private_metadata():
    """文档公开单文件 multipart、二进制附件及统一错误，不暴露内部原文件信息。"""
    from app.main import app
    schema = app.openapi()
    assert schema == make_app().openapi()
    upload = schema["paths"]["/api/files/spaces/{space_id}/files"]["post"]
    assert upload["security"] == [{"HTTPBearer": []}]
    body = upload["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert body["required"] == ["file"] and body["properties"]["file"]["format"] == "binary"
    download = schema["paths"]["/api/files/entries/{entry_id}/download"]["get"]
    assert set(download["responses"]["200"]["content"]) == {"application/octet-stream"}
    assert "413" in upload["responses"]
    assert not {"storage_key", "blob_id", "deleted_at"} & set(schema["components"]["schemas"]["EntryInfo"]["properties"])
