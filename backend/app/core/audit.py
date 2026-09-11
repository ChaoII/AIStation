"""审计字段写入工具：统一设置 created_id / updated_id。

用于绕过 CRUDBase 直接构造 ORM 对象的写入路径（module_train、标注图片上传等）。
"""


def _uid(auth) -> int | None:
    user = getattr(auth, "user", None)
    return getattr(user, "id", None) if user is not None else None


def set_create_audit(obj, auth) -> None:
    """为新建对象写入创建人/更新人。"""
    uid = _uid(auth)
    if uid is None:
        return
    if hasattr(obj, "created_id"):
        obj.created_id = uid
    if hasattr(obj, "updated_id"):
        obj.updated_id = uid


def set_update_audit(obj, auth) -> None:
    """为更新对象写入更新人。"""
    uid = _uid(auth)
    if uid is None:
        return
    if hasattr(obj, "updated_id"):
        obj.updated_id = uid
