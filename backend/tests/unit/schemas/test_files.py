"""文件公开输入的单元测试：名称规范化、重复名称和严格的大小版本约束。"""

import pytest
from pydantic import ValidationError

from app.schemas.files import FolderCreate, EntryRename, UploadLimitUpdate, name_key, numbered_name


def test_names_normalize_unicode_case_and_preserve_display():
    """规范等价及大小写差异使用同一比较键，显示名称保留大小写。"""
    body = FolderCreate(name="  Cafe\u0301.PDF  ")
    assert body.name == "Café.PDF"
    assert name_key(body.name) == name_key("CAFÉ.pdf")
    assert name_key("Straße") == name_key("STRASSE")
    assert EntryRename(name="目录", version=1).name == "目录"


@pytest.mark.parametrize("name", ["", " ", ".", "..", "a/b", "a\\b", "a\x00", "a\n文件", "a" * 256, 1, None])
def test_unsafe_names_are_rejected(name):
    """文件名不能代表路径、控制字符、空值或超过显示长度限制。"""
    with pytest.raises(ValidationError):
        FolderCreate(name=name)


@pytest.mark.parametrize("value", [0, -1, True, "100", 1.5, 1099511627777])
def test_upload_limit_rejects_invalid_or_coerced_sizes(value):
    """字节上限只接受正整数，不能接受布尔、字符串或超出 1 TiB 的值。"""
    with pytest.raises(ValidationError):
        UploadLimitUpdate(max_file_size_bytes=value, version=1)


def test_strict_versions_unknown_fields_and_duplicate_suffixes():
    """修改需要真实正整数版本，未知字段被拒绝，重复名称优先保留扩展名。"""
    for version in (0, True, "1"):
        with pytest.raises(ValidationError):
            EntryRename(name="文档", version=version)
    with pytest.raises(ValidationError):
        FolderCreate(name="目录", owner_id="伪造")
    assert numbered_name("方案.pdf", 1) == "方案 (1).pdf"
    assert numbered_name(".env", 2) == ".env (2)"
    assert len(numbered_name("名" * 251 + ".pdf", 123)) == 255
    assert numbered_name("名" * 251 + ".pdf", 123).endswith(" (123).pdf")
    assert len(numbered_name("a." + "x" * 253, 1)) == 255
