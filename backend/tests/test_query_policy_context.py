"""上下文投影（Step 2a）：按主体裁剪表/列，mask 列标注为脱敏。"""
import asyncio

import pytest

from app.plugin.module_ai.query.policy import context
from app.plugin.module_ai.query.policy.engine import Policy
from app.plugin.module_ai.query.policy.principal import Principal


def P(uid=7, roles=("USER",), superuser=False, attrs=None):
    return Principal(user_id=uid, is_superuser=superuser, roles=tuple(roles),
                     attrs=dict(attrs or {}), entry="ask")


def pol(pid, effect, table, columns=(), subject="everyone", mask=""):
    return Policy(
        id=pid, effect=effect, resource_kind="table", resource_code=table,
        subject_kind=subject, subject_value="", condition="",
        columns=tuple(columns), mask_expr=mask, marking="",
        priority=100, enabled=True,
    )


def run(coro):
    return asyncio.run(coro)


def test_denies_table_and_columns(monkeypatch):
    policies = [
        pol(1, "allow", "A"),
        pol(2, "deny", "B"),
        pol(3, "deny", "A", ("c2",)),
        pol(4, "mask", "A", ("c3",), mask="left(c3,3)"),
    ]
    monkeypatch.setattr("app.plugin.module_ai.query.policy.repo.list_policies",
                        lambda: asyncio.sleep(0, result=policies))
    monkeypatch.setattr("app.plugin.module_ai.query.policy.repo.domain_codes_for_user",
                        lambda uid: asyncio.sleep(0, result=()))
    monkeypatch.setattr(context, "repo", __import__(
        "app.plugin.module_ai.query.policy.repo", fromlist=["x"]), raising=False)

    scope = run(context.build_context_scope(
        P(), ["A", "B"], {"A": ["c1", "c2", "c3"], "B": ["x"]}))
    assert scope.tables == ("A",)
    assert scope.columns["A"] == ("c1", "c3")
    assert scope.masked["A"] == ("c3",)
    assert scope.restricted is True


def test_superuser_not_trimmed(monkeypatch):
    monkeypatch.setattr("app.plugin.module_ai.query.policy.repo.list_policies",
                        lambda: asyncio.sleep(0, result=[pol(1, "deny", "A")]))
    scope = run(context.build_context_scope(P(superuser=True), ["A"], {"A": ["c1"]}))
    assert scope.tables == ("A",) and scope.restricted is False


def test_no_policies_keeps_legacy(monkeypatch):
    monkeypatch.setattr("app.plugin.module_ai.query.policy.repo.list_policies",
                        lambda: asyncio.sleep(0, result=[]))
    scope = run(context.build_context_scope(P(), ["A"], {"A": ["c1"]}))
    assert scope.tables == ("A",) and scope.restricted is False


def test_signature_differs_by_principal():
    assert context.scope_signature(P(uid=1)) != context.scope_signature(P(uid=2))
    assert context.scope_signature(None) == ""
