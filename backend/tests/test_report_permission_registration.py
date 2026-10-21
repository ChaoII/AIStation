"""P1-1：module_ai/report 的权限码从未注册，导致 /ai/report/* 接口恒 403。

纯逻辑测试（PYTEST_NO_APP=1），不构造应用。验证：
① init_app 的注册源（AI_BUTTON_PERMS）包含 report 的 query/delete 权限码；
② ensure_perms 幂等补齐：report 码进入已注册集合，重复调用不重复注册。
"""
from app.scripts.init_app import AI_BUTTON_PERMS


def test_report_permission_codes_are_registered():
    """① 注册逻辑必须包含 module_ai:report:query / delete（修复前缺失 → FAILED）。"""
    registered = {code for code, _ in AI_BUTTON_PERMS}
    assert "module_ai:report:query" in registered, "缺失 module_ai:report:query"
    assert "module_ai:report:delete" in registered, "缺失 module_ai:report:delete"


def test_ensure_perms_registers_report_codes_idempotently():
    """② 幂等补齐：report 码进入已注册集合；重复调用不新增（幂等）。"""
    from app.scripts.init_app import ensure_perms

    registered: set[str] = set()
    added = ensure_perms(registered, AI_BUTTON_PERMS)
    added_codes = {code for code, _ in added}
    assert "module_ai:report:query" in added_codes, "新增项应包含 report:query"
    assert "module_ai:report:delete" in added_codes, "新增项应包含 report:delete"

    # 调用后 report 码出现在「已注册权限集合」
    assert "module_ai:report:query" in registered
    assert "module_ai:report:delete" in registered

    # 幂等：第二次调用不产生重复新增
    assert ensure_perms(registered, AI_BUTTON_PERMS) == []
