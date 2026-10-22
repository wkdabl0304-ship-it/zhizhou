"""SSE 支撑回归：完整响应与异步事件读取采用一致的协议解析规则。"""

from types import SimpleNamespace

import pytest

from tests.support.sse import SSEEvent, parse_events, read_event


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_complete_response_keeps_unicode_and_json_newline(newline):
    """验证行结束符、注释和 JSON 转义换行不会改变事件边界及中文正文。"""
    body = newline.join([
        ": heartbeat", "", "event: delta", 'data: {"text":"你好\\n世界"}', "",
        "event: done", "data: {}", "", "",
    ])
    assert parse_events(SimpleNamespace(text=body)) == [
        SSEEvent("delta", {"text": "你好\n世界"}), SSEEvent("done", {}),
    ]


@pytest.mark.anyio
async def test_stream_reader_consumes_exactly_one_event():
    """验证逐事件读取合并多行 data，并把下一事件留给后续消费。"""
    async def lines():
        """提供两个事件的行流，模拟 HTTP 客户端尚未读取完的连接。"""
        for line in ["event: delta", 'data: {"text":', 'data: "中文"}', "", "event: done", "data: {}", ""]:
            yield line

    stream = lines()
    assert await read_event(stream) == SSEEvent("delta", {"text": "中文"})
    assert await read_event(stream) == SSEEvent("done", {})


@pytest.mark.anyio
async def test_stream_reader_rejects_truncated_event():
    """验证断在事件结束空行之前的连接不会被当作完整事件。"""
    async def lines():
        """提供缺少终止空行的网络输入，模拟连接提前关闭。"""
        yield "event: done"
        yield "data: {}"

    with pytest.raises(AssertionError, match="完整事件"):
        await read_event(lines())
