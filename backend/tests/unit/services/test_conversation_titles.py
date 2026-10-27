"""标题服务单元测试：验证输入边界、正文提取、异常传播和取消后的资源释放。"""

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.services.conversation_titles import ConversationTitleService
from tests.support.fakes.titles import TitleModelStub

pytestmark = pytest.mark.anyio


async def test_title_uses_snapshot_bounded_data_and_visible_text_only():
    """标题调用沿用给定快照并截断输入，只采用可见正文，不混入推理。"""
    model = TitleModelStub("  Vue\n 项目\t规划  ")
    snapshot = object()
    result = await ConversationTitleService(model_opener=model.open).generate(snapshot, "问" * 2100, "答" * 2200)
    assert result == "Vue 项目 规划"
    assert model.snapshots == [snapshot]
    assert json.loads(model.messages[0][-1].content) == {"question": "问" * 2000, "answer": "答" * 2000}
    assert model.messages[0][0].type == "system"
    assert model.closed and model.stream_closed


@pytest.mark.parametrize("reply", ["", "\n\t ", "中" * 101])
async def test_invalid_output_is_rejected_after_resources_close(reply):
    """空白或超长模型输出交给调用方降级，不截断成看似有效的正式标题。"""
    model = TitleModelStub(reply)
    with pytest.raises(ValidationError):
        await ConversationTitleService(model_opener=model.open).generate(object(), "问题", "回答")
    assert model.closed and model.stream_closed


async def test_failure_propagates_and_closes_model():
    """模型故障原样传播给会话层分类降级，同时确保本次流和客户端关闭。"""
    model = TitleModelStub()
    model.failure = RuntimeError("不能进入公开响应的供应商细节")
    with pytest.raises(RuntimeError):
        await ConversationTitleService(model_opener=model.open).generate(object(), "问题", "回答")
    assert model.closed and model.stream_closed


async def test_cancellation_closes_stream_and_model():
    """取消标题等待会及时释放专用资源，不吞掉 CancelledError。"""
    model = TitleModelStub()
    model.release = asyncio.Event()
    async with asyncio.timeout(5):
        task = asyncio.create_task(ConversationTitleService(model_opener=model.open).generate(object(), "问题", "回答"))
        try:
            await model.started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert model.closed and model.stream_closed
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
