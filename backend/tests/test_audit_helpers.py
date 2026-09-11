"""审计字段工具单元测试。"""
from types import SimpleNamespace

from app.core.audit import set_create_audit, set_update_audit


class _Obj:
    def __init__(self):
        self.created_id = None
        self.updated_id = None


def _auth(uid):
    return SimpleNamespace(user=SimpleNamespace(id=uid))


def test_set_create_audit_sets_both():
    obj = _Obj()
    set_create_audit(obj, _auth(7))
    assert obj.created_id == 7
    assert obj.updated_id == 7


def test_set_update_audit_sets_only_updated():
    obj = _Obj()
    obj.created_id = 3
    set_update_audit(obj, _auth(9))
    assert obj.updated_id == 9
    assert obj.created_id == 3


def test_audit_helpers_tolerate_missing_auth():
    obj = _Obj()
    set_create_audit(obj, None)
    set_update_audit(obj, SimpleNamespace(user=None))
    assert obj.created_id is None
    assert obj.updated_id is None


def test_audit_helpers_skip_objects_without_fields():
    obj = SimpleNamespace(no_audit=1)
    set_create_audit(obj, _auth(5))  # must not raise
    assert not hasattr(obj, "created_id")
