"""本地文件适配单元测试：原始字节、空文件、大小边界和路径隔离。"""

import hashlib
from uuid import uuid4

import pytest

from app.core.errors.exceptions import RequestError
from app.storage.local import LocalFileStorage

pytestmark = pytest.mark.anyio


async def chunks(*values):
    """模拟网络分块输入，不把生产文件或开发目录带入测试。"""
    for value in values:
        yield value


@pytest.mark.parametrize("content", [b"", b"\x00\xffPDF\r\n\x00"])
async def test_binary_roundtrip_and_idempotent_cleanup(tmp_path, content):
    """任意二进制及空文件保存完整，大小摘要准确，重复清理仍可成功。"""
    storage = LocalFileStorage(tmp_path / "files")
    await storage.initialize()
    key = storage.key(uuid4())
    size, digest = await storage.write(key, chunks(content[:2], content[2:]), max(1, len(content)))
    assert size == len(content) and digest == hashlib.sha256(content).hexdigest()
    async with await storage.open_reader(key) as source:
        assert await source.read() == content
    assert not storage.path(key, partial=True).exists()
    await storage.remove(key)
    await storage.remove(key)
    assert not storage.path(key).exists()


async def test_limit_and_interrupted_write_leave_no_published_file(tmp_path):
    """超过上限或输入中断都不会发布原文件，残留临时内容可以幂等清理。"""
    storage = LocalFileStorage(tmp_path)
    key = storage.key(uuid4())
    with pytest.raises(RequestError) as error:
        await storage.write(key, chunks(b"12", b"3"), 2)
    assert error.value.error_code.code == 41301
    assert not storage.path(key).exists()
    await storage.remove(key)

    async def interrupted():
        """写入首段后模拟客户端故障，验证文件关闭及清理能力。"""
        yield b"first"
        raise OSError("模拟断开")

    with pytest.raises(OSError):
        await storage.write(key, interrupted(), 100)
    assert not storage.path(key).exists()
    await storage.remove(key)


async def test_paths_never_accept_user_names_or_traversal(tmp_path):
    """只有 UUID 存储键能够定位磁盘，用户路径及越界链接不能进入存储适配。"""
    storage = LocalFileStorage(tmp_path)
    for key in ("../private", "方案.pdf", "/etc/passwd", "aa/" + "b" * 32 + ".blob"):
        with pytest.raises(ValueError):
            storage.path(key)
