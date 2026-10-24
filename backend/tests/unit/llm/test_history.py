"""历史投影单元回归：跨供应商与凭据变化不回传私有块，原 checkpoint 不被修改。"""

from dataclasses import replace
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import SecretStr

from app.llm.models.history import ORIGIN_KEY, project_history
from app.llm.types import ModelSnapshot


def snapshot():
    """提供不依赖数据库与网络的目标模型快照。"""
    return ModelSnapshot(uuid4(), uuid4(), 1, 1, 1, "anthropic", "messages", "anthropic:claude-sonnet-5",
                         "https://api.anthropic.com", {"model": "claude-sonnet-5"}, SecretStr("private-key"))


def test_same_origin_preserves_signature_and_foreign_origin_only_keeps_public_content():
    """同源思考块完整保留，跨模型或账号只重放公开文字及完整工具对。"""
    target = snapshot()
    ai = AIMessage(content=[{"type": "thinking", "thinking": "private-thought", "signature": "private-signature"},
                            {"type": "text", "text": "查一下天气"}],
                   tool_calls=[{"name": "weather", "args": {}, "id": "call-1"}],
                   additional_kwargs={"private": "private-data"}, response_metadata={ORIGIN_KEY: target.origin})
    messages = [HumanMessage(content="你好"), ai, ToolMessage(content="晴", tool_call_id="call-1", artifact={"private": 1})]
    same = project_history(messages, target)
    assert same[1].content == ai.content and same[1] is not ai
    assert same[2].artifact is None
    for other in (replace(target, credential_revision=2), replace(target, catalog_model_id="anthropic:claude-opus-5")):
        foreign = project_history(messages, other)
        assert foreign[1].text == "查一下天气" and foreign[1].tool_calls == ai.tool_calls
        assert "private" not in str(foreign)
    assert ai.content[0]["signature"] == "private-signature" and messages[2].artifact == {"private": 1}


def test_incomplete_parallel_tool_tail_and_orphan_results_are_removed():
    """中断的并行工具请求不产生孤立调用或伪造工具结果，公开助手文字仍保留。"""
    target = snapshot()
    messages = [ToolMessage(content="孤立结果", tool_call_id="orphan"),
                AIMessage(content="已开始查询", response_metadata={ORIGIN_KEY: target.origin}, tool_calls=[
                    {"name": "weather", "args": {}, "id": "one"}, {"name": "weather", "args": {}, "id": "two"}]),
                ToolMessage(content="仅第一个完成", tool_call_id="one"), HumanMessage(content="继续")]
    actual = project_history(messages, target)
    assert len(actual) == 2 and actual[0].text == "已开始查询" and actual[0].tool_calls == []
    assert actual[1].content == "继续"


def test_legacy_deepseek_does_not_accept_unmarked_foreign_signature():
    """旧 DeepSeek 消息仍回传普通思考字段，未标记的异源签名不能走旧消息兼容。"""
    target = replace(snapshot(), provider="deepseek", api_format="chat_completions", catalog_model_id="deepseek:deepseek-flash")
    legacy = AIMessage(content="旧回答", additional_kwargs={"reasoning_content": "旧思考"})
    foreign = AIMessage(content=[{"type": "thinking", "thinking": "秘密", "signature": "不应回传"}, {"type": "text", "text": "公开"}])
    actual = project_history([legacy, foreign], target)
    assert actual[0].additional_kwargs == legacy.additional_kwargs
    assert actual[1].content == "公开" and actual[1].additional_kwargs == {}
