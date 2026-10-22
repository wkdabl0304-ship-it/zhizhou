"""SSE 测试支撑：共用事件表示，分别处理完整响应和真实逐行异步传输。"""

import json
from typing import Any, NamedTuple


class SSEEvent(NamedTuple):
    """表示事件名及 JSON 载荷，同时支持按名称和二元组读取。"""

    event: str
    payload: dict[str, Any]


def parse_events(response) -> list[SSEEvent]:
    """解析完整 HTTP 响应中的 SSE，保留 JSON 转义换行及多行 data 的含义。"""
    result = []
    for block in response.text.replace("\r\n", "\n").strip().split("\n\n"):
        name, data = "", []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].lstrip(" ")
            elif line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
        if data:
            result.append(SSEEvent(name, json.loads("\n".join(data))))
    return result


async def read_event(lines) -> SSEEvent:
    """从真实异步行流读取一个完整事件，连接提前结束时使测试明确失败。"""
    name, data = "", []
    async for line in lines:
        if line.startswith("event:"):
            name = line[6:].lstrip(" ")
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line and data:
            return SSEEvent(name, json.loads("\n".join(data)))
    raise AssertionError("SSE 在完整事件结束前关闭")
