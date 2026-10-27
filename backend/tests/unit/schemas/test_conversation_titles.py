"""标题请求单元测试：验证规范化顺序、严格输入及 Unicode 长度边界。"""

import pytest
from pydantic import ValidationError

from app.schemas.conversations import ConversationTitleUpdate


@pytest.mark.parametrize("title,expected", [
    ("  Vue\n 项目\t规划  ", "Vue 项目 规划"), ("中" * 100, "中" * 100),
    ("🙂" * 100, "🙂" * 100), (" " * 200 + "标题" + "\n" * 200, "标题"),
])
def test_normalizes_before_measuring_unicode_length(title, expected):
    """按规范化后的字符数接受标题，避免用原始空白长度或 UTF-8 字节数校验。"""
    assert ConversationTitleUpdate(title=title).title == expected


@pytest.mark.parametrize("body", [
    {}, {"title": None}, {"title": 1}, {"title": True}, {"title": []},
    {"title": ""}, {"title": "\u3000 \n\t"}, {"title": "中" * 101},
    {"title": "标题", "title_source": "auto"}, {"title": "标题", "user_id": "other"},
])
def test_rejects_invalid_or_undeclared_input(body):
    """拒绝空白、非字符串、超长及越权来源字段，不静默忽略多余参数。"""
    with pytest.raises(ValidationError):
        ConversationTitleUpdate.model_validate(body)
