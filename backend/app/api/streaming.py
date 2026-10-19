"""SSE 编码与可取消响应，统一处理各 ASGI 版本的客户端断开。

Starlette 对 ASGI 2.4 通常依赖发送失败检测断开；模型长时间等待时没有
发送动作，因此此处始终并行监听 http.disconnect，并等待生成器清理。
"""

import asyncio

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.schemas.response import ApiResponse


def encode_event(event: str, payload: ApiResponse) -> str:
    """编码一个 JSON SSE 事件；JSON 转义换行，避免文本破坏事件边界。"""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


class DisconnectStreamingResponse(StreamingResponse):
    """监听断开并取消流式生产任务，包含排队、模型等待和发送中的情况。"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """并行发送及监听连接；任一结束即取消另一任务并等待迭代器关闭。

        清理使用屏蔽取消的作用域，避免数据库或图的异步 finally 被重复
        取消打断。发送 OSError 视为连接已断开，不交给 JSON 异常处理器。
        """
        async def stream() -> None:
            """发送响应并在同一任务中关闭迭代器，包括发送时发生断开的路径。"""
            try:
                await self.stream_response(send)
            except OSError:
                pass
            finally:
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()

        # 使用 asyncio 的单次取消，允许图内部的异步 finally 正常等待清理；
        # 避免任务组的持续取消反复打断底层数据库关闭或 checkpoint 收尾。
        producer = asyncio.create_task(stream())
        watcher = asyncio.create_task(self.listen_for_disconnect(receive))
        try:
            completed, _ = await asyncio.wait({producer, watcher}, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result() # 如果先完成的任务里面抛了异常，在这里把异常重新抛出来
        finally:
            for task in (producer, watcher):
                if not task.done():
                    task.cancel()
            # 外层服务器任务被取消时，仍等待两个子任务结束后再返回。
            with anyio.CancelScope(shield=True):
                await asyncio.gather(producer, watcher, return_exceptions=True) # 等待任务 cancel 完成
                await self.body_iterator.aclose()
        if self.background is not None:
            await self.background() # 这个 Response 结束后要执行的收尾任务；不为空就执行它
