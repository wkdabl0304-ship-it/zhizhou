"""空间权限规则单元测试：全局范围不能越过个人内容边界，默认共享读取不等于写入。"""

from types import SimpleNamespace
from uuid import uuid4

from app.schemas.authorization import Grant
from app.services.files.access import permitted


def test_global_grant_cannot_read_someone_elses_personal_space():
    """超级管理员的全局文件权限始终不能访问他人的个人空间。"""
    user = SimpleNamespace(id=uuid4(), department_id=None)
    space = SimpleNamespace(kind="personal", owner_id=uuid4(), department_id=None)
    grants = [Grant(permission=f"file:{operation}", scope_type="global", scope_id=None)
              for operation in ("read", "upload", "update", "delete")]
    for operation in ("read", "upload", "update", "delete"):
        assert not permitted(user, grants, space, operation)


def test_shared_default_reads_do_not_grant_write_or_other_department_access():
    """普通用户默认读取全局及本部门资料，不可写入或访问其他部门。"""
    user = SimpleNamespace(id=uuid4(), department_id=uuid4())
    own = SimpleNamespace(kind="department", department_id=user.department_id)
    other = SimpleNamespace(kind="department", department_id=uuid4())
    public = SimpleNamespace(kind="global", department_id=None)
    assert permitted(user, [], public, "read")
    assert permitted(user, [], own, "read")
    assert not permitted(user, [], other, "read")
    for space in (public, own, other):
        assert not permitted(user, [], space, "upload")


def test_department_grants_only_cover_bound_department():
    """部门维护授权不能写入全局或其他部门，self 授权只服务本人个人空间。"""
    user = SimpleNamespace(id=uuid4(), department_id=uuid4())
    grant = Grant(permission="file:upload", scope_type="department", scope_id=user.department_id)
    assert permitted(user, [grant], SimpleNamespace(kind="department", department_id=user.department_id), "upload")
    assert not permitted(user, [grant], SimpleNamespace(kind="global", department_id=None), "upload")
    own = SimpleNamespace(kind="personal", department_id=None, owner_id=user.id)
    assert not permitted(user, [grant], own, "upload")
    assert permitted(user, [Grant(permission="file:upload", scope_type="self", scope_id=user.id)], own, "upload")
