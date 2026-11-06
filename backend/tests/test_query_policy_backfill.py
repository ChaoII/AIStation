"""Task 8：旧权限规则 backfill（幂等 / 映射 / 跳过 / dry_run / 兜底 allow）。

覆盖点（全部走**注入的假存储**，``PYTEST_NO_APP=1`` 可跑）：

1. **幂等**：连跑两次，第二次 ``created == 0``，策略行不重复（判重靠
   ``ai_policy_migration(source_table, source_id)``）；
2. **五行映射**：
   - ``ai_data_domain`` → ``allow`` + ``subject_kind=domain``（按表拆行，因为
     ``ai_policy`` 一行只能挂一个 ``resource_code``）；
   - ``ai_access_rule`` → ``allow`` + ``subject_kind=role``；
   - ``ai_query_asset_columns.sensitive`` → 一条 ``deny`` + ``columns`` + ``marking=sensitive``
     （同表多列合并）；
   - ``ai_ont_row_policy``（allow）→ 物理表上的 ``allow`` + ``condition``；
   - ``legacy_default_allow`` → 按 ``_system_allowed()`` 逐表一条兜底 ``allow``；
3. **解析不到不静默**：对象码解析不到物理表、条件含 ``user.role()``、条件 deny 等
   一律进 ``skipped`` 并 ``log.warning``，**绝不**写成引擎不认的 ``resource_kind=object``；
4. **dry_run 不写库**（不建迁移表、不插策略、不记迁移）。
"""
from __future__ import annotations

import asyncio

import pytest


# ---------------------------------------------------------------------------
# 假存储：与 ``backfill._DbStore`` 同签名，内存里记账，便于断言「写了什么」
# ---------------------------------------------------------------------------
class _FakeStore:
    def __init__(
        self,
        *,
        domains=(),
        access_rules=(),
        sensitive_columns=(),
        row_policies=(),
        assets=(),
        object_table=None,
        system_tables=(),
        users=(),
        load_errors=(),
    ):
        self.domains = list(domains)
        self.access_rules = list(access_rules)
        self.sensitive_columns = list(sensitive_columns)
        self.row_policies = list(row_policies)
        self.assets = list(assets)
        self.object_table = dict(object_table or {})
        self.system_tables = set(system_tables)
        self.users = list(users)
        self.load_errors = list(load_errors)
        # 写入侧记账
        self.policies: list[dict] = []
        self.migrations: list[tuple[str, str, int]] = []
        self.ensure_calls = 0

    async def ensure_migration_table(self) -> None:
        self.ensure_calls += 1

    async def load_sources(self) -> dict:
        return {
            "domains": list(self.domains),
            "access_rules": list(self.access_rules),
            "sensitive_columns": list(self.sensitive_columns),
            "row_policies": list(self.row_policies),
            "asset_tables": set(self.assets),
            "object_table": dict(self.object_table),
            "system_tables": set(self.system_tables),
            "users": list(self.users),
            "migrations": [
                {"source_table": s, "source_id": i} for s, i, _ in self.migrations
            ],
            "errors": list(self.load_errors),
        }

    async def insert_policy(self, values: dict) -> int:
        self.policies.append(dict(values))
        return len(self.policies)

    async def record_migration(
        self, source_table: str, source_id: str, policy_id: int
    ) -> None:
        self.migrations.append((source_table, source_id, policy_id))


def _wire(monkeypatch, **kw):
    """把 ``backfill`` 的存储换成假存储，返回 ``(模块, 存储)``。"""
    from app.plugin.module_ai.query.policy import backfill as B

    store = _FakeStore(**kw)
    monkeypatch.setattr(B, "_make_store", lambda: store)
    return B, store


def _by_name(policies, prefix):
    return [p for p in policies if str(p.get("name", "")).startswith(prefix)]


def _full_house():
    """一套最小的旧数据：域 / ABAC / 敏感列 / 对象行策略 / 用户 / 系统表白名单。"""
    return {
        "domains": [
            {
                "id": 3,
                "name": "人力域",
                "code": "hr",
                "tables": ["t_domain_a", "T_Domain_B", "t_domain_a"],
                # 101 是域成员 → 不该拿到兜底 allow（否则域隔离被抹平）
                "members": [101],
            }
        ],
        "access_rules": [
            {
                "id": 4,
                "name": "分析师只读",
                "attribute": "role",
                "value": "ANALYST",
                "allowed_tables": ["t_abac_a"],
                "sensitive_ok": False,
            }
        ],
        "sensitive_columns": [
            {"table_name": "t_abac_a", "column_name": "phone"},
            {"table_name": "t_abac_a", "column_name": "id_card"},
        ],
        "row_policies": [
            {
                "id": 7,
                "object_code": "orders",
                "name": "只看本部门",
                "expression": "dept_id == user.attribute('dept')",
                "effect": "allow",
                "enabled": True,
                "priority": 10,
            }
        ],
        "assets": ["orders"],
        "object_table": {"ont_orders": "orders"},
        "system_tables": ["sys_user", "train_tasks"],
        "users": [
            {"id": 101, "is_superuser": False, "roles": ["USER"]},  # 域成员
            {"id": 102, "is_superuser": False, "roles": ["ANALYST"]},  # ABAC 命中
            {"id": 103, "is_superuser": False, "roles": []},  # 无人覆盖 → 兜底
            {"id": 104, "is_superuser": True, "roles": ["ADMIN"]},  # 超管不建
        ],
    }


# ---------------------------------------------------------------------------
# 1. 幂等
# ---------------------------------------------------------------------------
def test_backfill_is_idempotent(monkeypatch):
    """重复执行真的 0 新建（判重靠 ai_policy_migration）。"""
    B, store = _wire(monkeypatch, **_full_house())

    first = asyncio.run(B.backfill_policies())
    second = asyncio.run(B.backfill_policies())

    assert first["created"] > 0, first
    assert second["created"] == 0, second
    # 策略条数没有翻倍
    assert len(store.policies) == first["created"]
    assert len(store.migrations) == first["created"]
    # 第二轮不再建表（建表本身幂等，但重复调用应可接受）
    assert store.ensure_calls == 2


def test_backfill_creates_only_new_rows_on_rerun(monkeypatch):
    """第二轮只补新增的旧数据，已迁移的不重复。"""
    B, store = _wire(monkeypatch, **_full_house())
    first = asyncio.run(B.backfill_policies())

    # 新增一条 ABAC 规则后再跑
    store.access_rules.append(
        {
            "id": 9,
            "name": "新增规则",
            "attribute": "role",
            "value": "VIEWER",
            "allowed_tables": ["t_abac_new"],
            "sensitive_ok": False,
        }
    )
    second = asyncio.run(B.backfill_policies())

    assert second["created"] == 1, second
    assert len(store.policies) == first["created"] + 1
    assert len(_by_name(store.policies, "legacy_default_allow")) == 2  # 没重复建兜底


# ---------------------------------------------------------------------------
# 2. 五行映射
# ---------------------------------------------------------------------------
def test_domain_maps_to_domain_allow_per_table(monkeypatch):
    """域 → allow + subject_kind=domain，按表拆行，表名大小写去重。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_domain")
    assert {r["resource_code"] for r in rows} == {"t_domain_a", "T_Domain_B"}
    for r in rows:
        assert r["effect"] == "allow"
        assert r["subject_kind"] == "domain"
        assert r["subject_value"] == "hr"
        assert r["resource_kind"] == "table"


def test_access_rule_maps_to_role_allow(monkeypatch):
    """ABAC 规则（attribute=role）→ allow + subject_kind=role。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_abac")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["resource_code"] == "t_abac_a"
    assert row["subject_kind"] == "role"
    assert row["subject_value"] == "ANALYST"
    assert row["effect"] == "allow"


def test_sensitive_columns_merge_into_one_deny(monkeypatch):
    """同表多个敏感列合成一条 deny（columns 数组），marking=sensitive。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_sensitive")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["resource_code"] == "t_abac_a"
    assert row["effect"] == "deny"
    assert row["subject_kind"] == "everyone"
    assert row["marking"] == "sensitive"
    assert sorted(row["columns"]) == ["id_card", "phone"]


def test_row_policy_lands_on_physical_table(monkeypatch):
    """对象行策略必须落到**物理表**（resource_kind=table），condition 语法对齐。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_row")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["resource_kind"] == "table"
    # object_code="orders" → 真实支撑表 ont_orders（语义映射优先）
    assert row["resource_code"] == "ont_orders"
    assert row["effect"] == "allow"
    assert row["subject_kind"] == "everyone"
    # user.attribute('dept') → $attr.dept_id（Principal 只加载 dept_id）；== → =
    assert row["condition"] == "dept_id = $attr.dept_id"
    # 原表达式留痕，便于治理页人工核对
    assert "dept_id == user.attribute('dept')" in row["description"]


def test_translate_condition_maps_attributes_to_loaded_principal_attrs():
    """I3：``user.attribute('dept')`` 必须映射成 ``$attr.dept_id``。

    Principal 只加载 ``dept_id``（``principal._ATTR_COLUMNS``）；若翻译成
    ``$attr.dept``，属性永远绑不上 → 条件永不成立 → 迁移后的策略整表 deny。
    """
    from app.plugin.module_ai.query.policy.backfill import translate_condition

    assert translate_condition("dept_id == user.attribute('dept')") == (
        "dept_id = $attr.dept_id"
    )
    assert translate_condition("owner == user.id") == "owner = $user.id"
    assert translate_condition("dept_id == user.dept_id") == "dept_id = $attr.dept_id"


def test_translate_condition_skips_unmappable_attribute():
    """读不到的属性宁可不迁（留痕跳过），也不能固化一个永不成立的条件。"""
    from app.plugin.module_ai.query.policy.backfill import translate_condition

    assert translate_condition("region == user.attribute('region')") is None
    assert translate_condition("x == user.attribute('dept2')") is None


def test_translate_condition_skips_attrs_principal_never_loads():
    """I3 残留：``Principal`` 只加载 ``dept_id``，``username`` / ``name`` 永远绑不上。

    映射成 ``$attr.username`` 的条件会"永不成立"，迁移后整表 deny；
    宁可返回 ``None``（跳过 + 留痕）。
    """
    from app.plugin.module_ai.query.policy.backfill import translate_condition

    assert translate_condition("owner == user.name") is None
    assert translate_condition("owner == user.attribute('username')") is None
    assert translate_condition("owner == user.attribute('name')") is None


def test_legacy_default_allow_is_per_user_not_everyone(monkeypatch):
    """兜底 allow：按用户发（subject=user），逐表一条、priority 最低、无条件无列。"""
    B, store = _wire(monkeypatch, **_full_house())

    result = asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_default_allow")
    # 只有 103（无域、无 ABAC）拿到，2 张系统表 → 2 行
    assert {r["resource_code"] for r in rows} == {"sys_user", "train_tasks"}
    for r in rows:
        assert r["name"] == "legacy_default_allow"
        assert r["subject_kind"] == "user"
        assert r["subject_value"] == "103"
        assert r["effect"] == "allow"
        assert r["priority"] == 1
        assert r["columns"] == []
        assert r["condition"] == ""
        assert r["description"].startswith("legacy_default_allow")
        assert "仅限无域/无 ABAC 的存量用户" in r["description"]
    assert result["by_source"]["legacy_default_allow"] == {"users": 1, "rows": 2}


def test_domain_member_gets_no_default_allow(monkeypatch):
    """**关键回归**：域成员不拿兜底 allow（否则 enforce 后域隔离被抹平 = 越权）。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_default_allow")
    assert {r["subject_value"] for r in rows} == {"103"}, rows
    assert "101" not in {r["subject_value"] for r in rows}


def test_role_matched_user_gets_no_default_allow(monkeypatch):
    """命中启用 ABAC 角色的用户也不发兜底（他已被 role allow 覆盖）。"""
    B, store = _wire(monkeypatch, **_full_house())

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_default_allow")
    assert "102" not in {r["subject_value"] for r in rows}


def test_default_allow_rerun_creates_zero(monkeypatch):
    """兜底 allow 也走迁移台账判重：第二轮 0 新建。"""
    B, store = _wire(monkeypatch, **_full_house())

    first = asyncio.run(B.backfill_policies())
    second = asyncio.run(B.backfill_policies())

    assert first["by_source"]["legacy_default_allow"] == {"users": 1, "rows": 2}
    assert second["by_source"]["legacy_default_allow"] == {"users": 0, "rows": 0}
    assert second["created"] == 0


def test_default_allow_over_limit_skips_without_writing(monkeypatch):
    """超上限（用户×表 > 2000）不硬写：返回 skipped，一条策略都不落库。"""
    from app.plugin.module_ai.query.policy import backfill as B0

    monkeypatch.setattr(B0, "LEGACY_DEFAULT_ALLOW_MAX_ROWS", 3)
    data = _full_house()
    # 3 个无覆盖用户 × 2 张表 = 6 > 3
    data["users"] = [
        {"id": 201, "is_superuser": False, "roles": []},
        {"id": 202, "is_superuser": False, "roles": []},
        {"id": 203, "is_superuser": False, "roles": []},
    ]
    B, store = _wire(monkeypatch, **data)

    result = asyncio.run(B.backfill_policies())

    assert not _by_name(store.policies, "legacy_default_allow")
    assert store.migrations == [] or all(
        s != "legacy_default_allow" for s, _i, _p in store.migrations
    )
    skipped = [s for s in result["skipped"] if s["source"] == "legacy_default_allow"]
    assert skipped and "legacy_default_allow rows > 3" in skipped[0]["reason"]
    assert result["by_source"]["legacy_default_allow"] == {"users": 0, "rows": 0}


@pytest.mark.parametrize("bad_source", ["ai_data_domain", "ai_access_rule"])
def test_default_allow_skipped_when_coverage_read_fails(monkeypatch, bad_source):
    """覆盖判定读失败 → 一条兜底都不写（否则"人人全表"= 越权）。"""
    data = _full_house()
    data["load_errors"] = [{"source": bad_source, "reason": "no such column: members"}]
    B, store = _wire(monkeypatch, **data)

    result = asyncio.run(B.backfill_policies())

    assert not _by_name(store.policies, "legacy_default_allow")
    notes = [s for s in result["skipped"] if s["source"] == "legacy_default_allow"]
    assert any("覆盖判定读取失败" in n["reason"] for n in notes), notes
    assert result["by_source"]["legacy_default_allow"] == {"users": 0, "rows": 0}
    # 其它来源照常迁移：一个来源读失败不该拖垮整次迁移
    assert result["created"] > 0


def test_domain_without_code_still_covers_members(monkeypatch):
    """域「有表但 code 为空」的成员仍算被覆盖（与旧逻辑只看 tables 等价）→ 不拿兜底。"""
    B, store = _wire(
        monkeypatch,
        domains=[
            {"id": 9, "name": "缺 code 的域", "code": "", "tables": ["t_x"], "members": [301]}
        ],
        users=[
            {"id": 301, "is_superuser": False, "roles": []},
            {"id": 302, "is_superuser": False, "roles": []},
        ],
        system_tables=["sys_user"],
    )

    result = asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_default_allow")
    assert {r["subject_value"] for r in rows} == {"302"}, rows
    # code 为空写不出 domain 策略 → 该域有 skipped 提示（管理员需补 code）
    assert any(s["source"] == "ai_data_domain" for s in result["skipped"])


def test_system_tables_included_in_upper_bound_only(monkeypatch):
    """``ai_query_assets.included=false`` 的表不出现在兜底 allow 里时才安全 ——
    这里验证「兜底集合 = 系统白名单」，不额外放大到资产目录里的任意表。"""
    B, store = _wire(
        monkeypatch,
        system_tables=["sys_user"],
        assets=["t_not_in_system"],
        users=[{"id": 201, "is_superuser": False, "roles": []}],
    )

    asyncio.run(B.backfill_policies())

    rows = _by_name(store.policies, "legacy_default_allow")
    assert [r["resource_code"] for r in rows] == ["sys_user"]


# ---------------------------------------------------------------------------
# 3. 解析不到不静默
# ---------------------------------------------------------------------------
def test_unresolvable_object_code_is_skipped_not_object_kind(monkeypatch):
    """对象码解析不到物理表 → 跳过 + 记 skipped，绝不写成 resource_kind=object。"""
    B, store = _wire(
        monkeypatch,
        row_policies=[
            {
                "id": 11,
                "object_code": "ghost_object",
                "name": "幽灵",
                "expression": "x == 1",
                "effect": "allow",
                "enabled": True,
                "priority": 0,
            }
        ],
        assets=[],
        object_table={},
    )

    result = asyncio.run(B.backfill_policies())

    assert not [p for p in store.policies if p.get("resource_kind") == "object"]
    assert not _by_name(store.policies, "legacy_row")
    skipped = [s for s in result["skipped"] if s["source"] == "ai_ont_row_policy"]
    assert skipped and "ghost_object" in str(skipped[0])


def test_unsupported_expression_and_deny_are_skipped(monkeypatch):
    """``user.role()`` 无法表达成行条件；条件 deny 会被整表短路 —— 都跳过并留痕。"""
    B, store = _wire(
        monkeypatch,
        row_policies=[
            {
                "id": 21,
                "object_code": "orders",
                "name": "角色条件",
                "expression": "user.role('ADMIN') or owner == user.name",
                "effect": "allow",
                "enabled": True,
                "priority": 0,
            },
            {
                "id": 22,
                "object_code": "orders",
                "name": "排除作废行",
                "expression": "status == 'void'",
                "effect": "deny",
                "enabled": True,
                "priority": 0,
            },
        ],
        assets=["orders"],
        object_table={"ont_orders": "orders"},
    )

    result = asyncio.run(B.backfill_policies())

    assert not _by_name(store.policies, "legacy_row")
    reasons = {
        s["id"]: s["reason"] for s in result["skipped"] if s["source"] == "ai_ont_row_policy"
    }
    assert 21 in reasons and "user." in reasons[21]
    assert 22 in reasons and "deny" in reasons[22]


def test_unsupported_access_rule_attribute_is_skipped(monkeypatch):
    """ABAC 只支持 role；其它 attribute 不猜，进 skipped。"""
    B, store = _wire(
        monkeypatch,
        access_rules=[
            {
                "id": 31,
                "name": "按部门",
                "attribute": "dept",
                "value": "3",
                "allowed_tables": ["t_x"],
                "sensitive_ok": False,
            }
        ],
    )

    result = asyncio.run(B.backfill_policies())

    assert not _by_name(store.policies, "legacy_abac")
    skipped = [s for s in result["skipped"] if s["source"] == "ai_access_rule"]
    assert skipped and skipped[0]["id"] == 31


def test_sensitive_ok_is_reported_for_manual_handling(monkeypatch):
    """``sensitive_ok`` 无法用「everyone 列 deny」表达（引擎 deny>allow），必须报出来。"""
    B, _store = _wire(
        monkeypatch,
        access_rules=[
            {
                "id": 41,
                "name": "风控可看敏感列",
                "attribute": "role",
                "value": "RISK",
                "allowed_tables": ["t_risk"],
                "sensitive_ok": True,
            }
        ],
    )

    result = asyncio.run(B.backfill_policies())

    notes = [s for s in result["skipped"] if s["id"] == 41]
    assert notes and "sensitive_ok" in notes[0]["reason"]


def test_load_error_is_reported(monkeypatch):
    """旧表读不出来（不存在/无权限）不能静默 —— 进 skipped。"""
    B, _store = _wire(
        monkeypatch,
        load_errors=[{"source": "ai_ont_row_policy", "reason": "no such table"}],
    )

    result = asyncio.run(B.backfill_policies())

    assert any(s["source"] == "ai_ont_row_policy" for s in result["skipped"])


# ---------------------------------------------------------------------------
# 4. dry_run
# ---------------------------------------------------------------------------
def test_dry_run_writes_nothing(monkeypatch):
    """dry_run 只算数量：不建迁移表、不插策略、不记迁移。"""
    B, store = _wire(monkeypatch, **_full_house())

    result = asyncio.run(B.backfill_policies(dry_run=True))

    assert result["created"] > 0
    assert store.policies == []
    assert store.migrations == []
    assert store.ensure_calls == 0

    # 真跑一次后数量一致（dry_run 的预测可信）
    real = asyncio.run(B.backfill_policies())
    assert real["created"] == result["created"]
    assert real["by_source"] == result["by_source"]


def test_by_source_covers_all_five_sources(monkeypatch):
    """返回值形状固定：三个键 + 五类来源计数（含 0）。"""
    B, _store = _wire(monkeypatch, **_full_house())

    result = asyncio.run(B.backfill_policies())

    assert set(result) == {"created", "skipped", "by_source"}
    assert set(result["by_source"]) == {
        "ai_data_domain",
        "ai_access_rule",
        "ai_query_asset_columns",
        "ai_ont_row_policy",
        "legacy_default_allow",
    }
    assert result["by_source"]["legacy_default_allow"] == {"users": 1, "rows": 2}
    for source in (
        "ai_data_domain",
        "ai_access_rule",
        "ai_query_asset_columns",
        "ai_ont_row_policy",
    ):
        assert result["by_source"][source] >= 1, source


# ---------------------------------------------------------------------------
# 5. 迁移表 DDL（纯常量）
# ---------------------------------------------------------------------------
def test_migration_table_ddl_is_idempotent_with_unique_key():
    from app.plugin.module_ai.query.policy.backfill import MIGRATION_TABLE_SQL

    low = MIGRATION_TABLE_SQL.lower()
    assert "create table if not exists ai_policy_migration" in low
    assert "unique(source_table, source_id)" in low
    assert "policy_id" in low


# ---------------------------------------------------------------------------
# 6. 真库集成（``PYTEST_NO_APP=1`` 时自动 skip；全量/单文件带应用时跑）
# ---------------------------------------------------------------------------
def test_backfill_on_real_db_is_idempotent(test_client, db_run):
    """真跑一次：SQL 能执行、迁移表建得出、第二轮 0 新建、行策略真的落到物理表。"""
    import uuid

    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.model import (
        AiQueryAssetColumnModel,
        AiQueryAssetModel,
    )
    from app.plugin.module_ai.query.policy import backfill as B

    sfx = uuid.uuid4().hex[:6]
    dom_code = f"t8{sfx}"
    u_free_name, u_dom_name = f"t8u{sfx}", f"t8d{sfx}"
    t_dom_a, t_dom_b = f"t8_{sfx}_a", f"t8_{sfx}_b"
    t_abac = f"t8_{sfx}_abac"
    t_sec = f"t8_{sfx}_sec"
    t_obj = f"t8_{sfx}_obj"

    async def _cleanup():
        async with async_db_session.begin() as db:
            for sql in (
                "DELETE FROM ai_policy_migration",
                "DELETE FROM ai_policy WHERE name LIKE 'legacy_%'",
                "DELETE FROM ai_ont_row_policy WHERE object_code=:oc",
                "DELETE FROM ai_data_domain WHERE code=:code",
                "DELETE FROM ai_access_rule WHERE value='T8ROLE'",
                "DELETE FROM ai_query_asset_columns WHERE table_name=:sec",
                "DELETE FROM ai_query_assets WHERE table_name=:obj",
                "DELETE FROM sys_user WHERE username=:u1 OR username=:u2",
            ):
                params = {
                    "oc": t_obj,
                    "code": dom_code,
                    "sec": t_sec,
                    "obj": t_obj,
                    "u1": u_free_name,
                    "u2": u_dom_name,
                }
                try:
                    await db.execute(text(sql), params)
                except Exception:  # noqa: BLE001 - 清理尽力而为
                    pass

    async def _run():
        from sqlalchemy import text as _text

        from app.api.v1.module_system.user.model import UserModel

        await _cleanup()
        try:
            async with async_db_session.begin() as db:
                # 两个用户：一个"无域无 ABAC"（该拿兜底），一个域成员（**不许**拿）。
                # 域成员若也拿到兜底，等于 enforce 后域隔离被抹平 —— 这是本用例要守的线。
                u_free = UserModel(
                    username=u_free_name,
                    password="x",
                    name="t8无域用户",
                    is_superuser=False,
                    is_deleted=False,
                )
                u_dom = UserModel(
                    username=u_dom_name,
                    password="x",
                    name="t8域内用户",
                    is_superuser=False,
                    is_deleted=False,
                )
                db.add_all([u_free, u_dom])
                await db.flush()
                free_id, dom_id = int(u_free.id), int(u_dom.id)

                # 本体行策略表在 SQLite 上不会被启动建表建出来（DDL 是 PG 方言，
                # ontology 侧 best-effort 建表会跳过）；这里按方言翻译后自己建一次。
                from app.plugin.module_ai.ontology.service import _ONT_TABLES_SQL
                from app.plugin.module_ai.query.ddl_dialect import ddl_for_dialect

                row_policy_ddl = next(
                    s for s in _ONT_TABLES_SQL if "ai_ont_row_policy" in s
                )
                await db.execute(_text(ddl_for_dialect(row_policy_ddl)))
                await db.execute(
                    _text(
                        "INSERT INTO ai_data_domain (name, code, tables, members, enabled, "
                        "is_deleted) VALUES ('t8域', :code, :tables, :members, true, false)"
                    ),
                    {
                        "code": dom_code,
                        "tables": f'["{t_dom_a}", "{t_dom_b}"]',
                        "members": f"[{dom_id}]",
                    },
                )
                await db.execute(
                    _text(
                        "INSERT INTO ai_access_rule (name, attribute, value, allowed_tables, "
                        "sensitive_ok, enabled, is_deleted) VALUES ('t8规则', 'role', 'T8ROLE', "
                        ":tables, false, true, false)"
                    ),
                    {"tables": f'["{t_abac}"]'},
                )
                for col in ("phone", "id_card"):
                    db.add(
                        AiQueryAssetColumnModel(
                            table_name=t_sec,
                            column_name=col,
                            sensitive=True,
                            included=True,
                            is_deleted=False,
                        )
                    )
                db.add(
                    AiQueryAssetModel(
                        table_name=t_obj,
                        included=True,
                        object_enabled=True,
                        is_deleted=False,
                    )
                )
                await db.flush()
                await db.execute(
                    _text(
                        "INSERT INTO ai_ont_row_policy (object_code, name, expression, effect, "
                        "enabled, priority) VALUES (:oc, 't8部门', "
                        "'dept_id == user.attribute(''dept'')', 'allow', true, 5)"
                    ),
                    {"oc": t_obj},
                )
            first = await B.backfill_policies()
            second = await B.backfill_policies()
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        _text(
                            "SELECT resource_code, resource_kind, effect, subject_kind, "
                            "subject_value, condition, columns, name FROM ai_policy "
                            "WHERE name LIKE 'legacy_%' ORDER BY id"
                        )
                    )
                ).fetchall()
                mig = (
                    await db.execute(_text("SELECT count(*) FROM ai_policy_migration"))
                ).scalar()
            return first, second, rows, mig, free_id, dom_id
        finally:
            await _cleanup()

    first, second, rows, mig, free_id, dom_id = db_run(_run())

    assert first["created"] > 0, first
    assert second["created"] == 0, second
    assert mig == first["created"]

    by_code = {}
    for r in rows:
        by_code.setdefault(r[0], []).append(r)

    # 域：每个域 × 每张表一条 allow（subject=domain）
    for table in (t_dom_a, t_dom_b):
        assert table in by_code, f"域表 {table} 没迁出来：{list(by_code)}"
        assert by_code[table][0][3] == "domain"
        assert by_code[table][0][4] == dom_code

    # ABAC：role allow
    assert by_code[t_abac][0][3] == "role"
    assert by_code[t_abac][0][4] == "T8ROLE"

    # 敏感列：一条 deny，两列合并，marking 用 name 前缀间接验证（DDL 列在 rows 未取）
    sec = by_code[t_sec][0]
    assert sec[2] == "deny" and "phone" in str(sec[6]) and "id_card" in str(sec[6])

    # 行策略：落到物理表（table）+ 条件语法对齐
    obj = by_code[t_obj][0]
    assert obj[1] == "table" and obj[2] == "allow"
    assert obj[5] == "dept_id = $attr.dept_id"

    # 兜底 allow：按用户发 —— 无域无 ABAC 的用户拿到，**域成员绝不拿**（否则域隔离被抹平）
    user_rows = [r for r in rows if r[3] == "user"]
    subjects = {r[4] for r in user_rows}
    assert str(free_id) in subjects, f"无域用户 {free_id} 没拿到兜底 allow：{subjects}"
    assert str(dom_id) not in subjects, f"域成员 {dom_id} 不该拿到兜底 allow：{subjects}"
    assert all(r[7] == "legacy_default_allow" for r in user_rows)
    free_rows = [r for r in user_rows if r[4] == str(free_id)]
    assert "sys_user" in {r[0] for r in free_rows}
    assert first["by_source"]["legacy_default_allow"]["users"] >= 1
    assert first["by_source"]["legacy_default_allow"]["rows"] >= 1
