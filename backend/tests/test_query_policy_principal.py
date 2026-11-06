"""Task 2：统一主体 Principal（角色 + 属性 + 入口）。

纯逻辑用例全部用 monkeypatch 打桩，不连库：

- 角色来源 → ``service._user_role_codes``（打桩返回值，证明用的是既有函数）；
- 属性来源 → ``policy.principal._load_attrs``（打桩，避免连库）。

另有真正落库/落表的用例（需要应用，``PYTEST_NO_APP=1`` 时由 ``test_client`` 自动 skip）：

- ``dept_id`` 真的从 ``sys_user`` 读出来，并统一转成字符串；
- ``sys_user`` 没有 ``dept_id`` 列时返回 ``{}``（老库降级，不抛）；
- 会话异常时返回 ``{}`` 并记一条 warning（monkeypatch 会话模拟）。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace


def _role(code: str):
    """模拟 ``auth.user.roles`` 里的角色对象（真实对象只需带 ``code``）。"""
    return SimpleNamespace(code=code)


def _auth(uid, *, is_superuser: bool = False, roles=("ADMIN",)):
    """构造最小鉴权上下文：真实代码只读 ``auth.user.id`` / ``is_superuser`` / ``roles``。"""
    return SimpleNamespace(
        user=SimpleNamespace(
            id=uid,
            is_superuser=is_superuser,
            roles=[_role(c) for c in roles],
        )
    )


def _principal_mod():
    from app.plugin.module_ai.query.policy import principal

    return principal


# ---------------------------------------------------------------------------
# 纯逻辑：无法装出主体时必须返回 None（fail-closed，不伪造匿名身份）
# ---------------------------------------------------------------------------
def test_missing_auth_returns_none():
    P = _principal_mod()

    assert asyncio.run(P.load_principal(None)) is None
    # auth 在但 user 为空 / id 为 0：同样没有主体
    assert asyncio.run(P.load_principal(SimpleNamespace(user=None))) is None
    assert asyncio.run(P.load_principal(_auth(0))) is None


# ---------------------------------------------------------------------------
# 纯逻辑：Principal 字段真的来自「角色来源 + 属性来源 + 入口」
# ---------------------------------------------------------------------------
def test_principal_carries_roles_and_attrs(monkeypatch):
    from app.plugin.module_ai.query import service as S

    P = _principal_mod()
    # 角色来源：打桩既有函数，断言 Principal 的 roles 是它返回集合的**排序元组**
    monkeypatch.setattr(S, "_user_role_codes", lambda auth: {"USER", "ADMIN"})
    seen: dict = {}

    async def _fake_attrs(uid):
        seen["uid"] = uid
        return {"dept_id": "3"}

    monkeypatch.setattr(P, "_load_attrs", _fake_attrs)

    p = asyncio.run(P.load_principal(_auth(7), entry="cron"))

    assert p is not None
    assert p.user_id == 7 and p.entry == "cron"
    assert p.roles == ("ADMIN", "USER"), "集合必须归一成有序元组（可比较、可缓存）"
    assert p.attrs.get("dept_id") == "3"
    assert p.is_superuser is False
    assert seen["uid"] == 7, "属性必须按 user_id 读取"


def test_default_entry_is_ask_and_superuser_still_loads_attrs(monkeypatch):
    """默认入口是 ask；超管也照样加载属性（审计/explain 需要完整主体）。"""
    P = _principal_mod()
    calls: list[int] = []

    async def _fake_attrs(uid):
        calls.append(uid)
        return {}

    monkeypatch.setattr(P, "_load_attrs", _fake_attrs)

    p = asyncio.run(P.load_principal(_auth(9, is_superuser=True)))

    assert p is not None
    assert p.entry == "ask"
    assert p.is_superuser is True
    # roles 走真实 service._user_role_codes（只有属性被打了桩）
    assert p.roles == ("ADMIN",)
    assert calls == [9], "超管不能跳过属性加载"


# ---------------------------------------------------------------------------
# 纯逻辑：属性读取异常 → 空字典 + 一条 warning（不抛）
# ---------------------------------------------------------------------------
def test_attrs_failure_returns_empty_and_warns(monkeypatch):
    P = _principal_mod()

    class _BoomFactory:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(P, "async_db_session", _BoomFactory())

    warnings: list[str] = []

    class _Log:
        @staticmethod
        def warning(msg, *a):
            warnings.append(str(msg))

    monkeypatch.setattr(P, "log", _Log)

    assert asyncio.run(P._load_attrs(7)) == {}
    assert warnings and "属性" in warnings[0]


# ---------------------------------------------------------------------------
# 落库：dept_id 真的从 sys_user 读出并转成字符串
# ---------------------------------------------------------------------------
def test_attrs_reads_dept_id_from_sys_user(test_client, db_run):
    from sqlalchemy import delete, text

    from app.api.v1.module_system.user.model import UserModel
    from app.core.database import async_db_session
    from app.plugin.module_ai.query.policy.principal import _load_attrs, load_principal

    uname = "t_principal_user"

    async def _prepare():
        async with async_db_session.begin() as db:
            await db.execute(delete(UserModel).where(UserModel.username == uname))
            dept = (
                await db.execute(text("SELECT id FROM sys_dept ORDER BY id LIMIT 1"))
            ).fetchone()
            if not dept:
                return None
            row = UserModel(
                username=uname,
                password="x",
                name="主体测试",
                is_superuser=False,
                dept_id=int(dept[0]),
            )
            db.add(row)
            await db.flush()
            return int(row.id), int(dept[0])

    async def _cleanup():
        async with async_db_session.begin() as db:
            await db.execute(delete(UserModel).where(UserModel.username == uname))

    created = db_run(_prepare())
    if not created:
        import pytest

        pytest.skip("种子数据里没有 sys_dept，无法验证 dept_id")
    uid, dept_id = created
    try:
        attrs = db_run(_load_attrs(uid))
        p = db_run(load_principal(_auth(uid, roles=())))
        assert attrs == {"dept_id": str(dept_id)}, attrs
        assert p is not None and p.attrs == attrs
        assert p.user_id == uid and p.roles == () and p.entry == "ask"
    finally:
        db_run(_cleanup())


# ---------------------------------------------------------------------------
# 落表：sys_user 没有 dept_id 列 → 空字典（老库降级），且不抛
# ---------------------------------------------------------------------------
def test_missing_dept_id_column_returns_empty(monkeypatch, test_client, db_run):
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.policy import principal as P

    table = "t_principal_no_dept"

    async def _go():
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(f"DROP TABLE IF EXISTS {table}"))
                await db.execute(text(f"CREATE TABLE {table} (id INTEGER)"))
            # 指向一张没有 dept_id 列的表：列不存在必须静默降级为 {}
            monkeypatch.setattr(P, "_USER_TABLE", table)
            return await P._load_attrs(1)
        finally:
            async with async_db_session.begin() as db:
                await db.execute(text(f"DROP TABLE IF EXISTS {table}"))

    assert db_run(_go()) == {}
