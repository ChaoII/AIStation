"""问数权限模型（Task 1）：策略/审计/shadow 三张表的 DDL 常量与幂等建表。

覆盖这几件事：

1. ``POLICY_TABLES_SQL`` 真的包含三张表、每张都带 ``CREATE TABLE IF NOT EXISTS``（幂等）；
2. ``ensure_policy_tables()`` 能真的把表建出来，且连跑两次不报错；
3. ``sensitive_tables()`` 只取 ``sensitive=true`` 且未软删的表名，统一小写去重；
4. ``sensitive_tables()`` **并上本体侧敏感字段映射到的物理表**（C1：两套标记不一致时，
   只标在本体上的表也必须在星号止血清单里，否则 ``select *`` 会把明文读出来）；
5. 导出/浏览同样拒绝含敏感列的表（I1：不能绕过星号止血直读）；
6. ``save_setting`` 只允许超管改 ``policy_engine``（I2：否则任何能问数的人都能关判定）。

前两条的「建表」用例：常量与纯逻辑部分用 ``PYTEST_NO_APP=1`` 就能跑；
真正落库的用例走应用会话（需要应用，``PYTEST_NO_APP=1`` 时自动 skip）。
"""
from __future__ import annotations

import asyncio


def test_policy_tables_cover_three_tables():
    """三张表都在，且都是幂等建表语句（重复执行不能炸）。"""
    from app.plugin.module_ai.query.policy.model import POLICY_TABLES_SQL

    joined = "\n".join(POLICY_TABLES_SQL).lower()
    assert "ai_policy" in joined
    assert "ai_query_access_log" in joined
    assert "ai_policy_shadow_diff" in joined
    assert "create table if not exists" in joined
    # 一条 SQL 一张表：逐条执行时单条失败不牵连其它表
    assert len(POLICY_TABLES_SQL) == 3


def test_policy_tables_columns_match_design():
    """关键列必须齐（设计稿 §4），否则后续判定引擎/审计写入会缺字段。"""
    from app.plugin.module_ai.query.policy.model import POLICY_TABLES_SQL

    joined = "\n".join(POLICY_TABLES_SQL).lower()
    for col in (
        # ai_policy：表/列/行三级策略共用一张表
        "resource_kind",
        "resource_code",
        "effect",
        "subject_kind",
        "subject_value",
        "condition",
        "columns",
        "mask_expr",
        "marking",
        "priority",
        "enabled",
        "is_deleted",
        # 审计表
        "sql_hash",
        "sql_preview",
        "decision",
        "reason",
        "policy_ids",
        "rewrite",
        "elapsed_ms",
        # shadow 差异表
        "legacy_decision",
        "new_decision",
        "diff_kind",
    ):
        assert col in joined, f"缺少列：{col}"


def test_shadow_diff_ddl_has_rewrite_column():
    """shadow 差异表要带 ``rewrite`` 列（rewrite_only 差异的解释全靠它）。"""
    from app.plugin.module_ai.query.policy.model import POLICY_ALTER_COLS, POLICY_TABLES_SQL

    ddl = next(s for s in POLICY_TABLES_SQL if "ai_policy_shadow_diff" in s).lower()
    assert "rewrite" in ddl and "jsonb default '[]'" in ddl, ddl
    assert ("ai_policy_shadow_diff", "rewrite", "JSONB DEFAULT '[]'") in POLICY_ALTER_COLS


def test_ensure_policy_tables_creates_tables(test_client, db_run):
    """幂等建表：应用库上连跑两次都必须成功，且三张表真的存在。"""
    from sqlalchemy import inspect

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    async def _go():
        await ensure_policy_tables()
        await ensure_policy_tables()  # 幂等：第二次不能报错
        async with async_db_session() as db:
            conn = await db.connection()
            return await conn.run_sync(lambda c: set(inspect(c).get_table_names()))

    S.reset_degraded()
    names = db_run(_go())
    for t in ("ai_policy", "ai_query_access_log", "ai_policy_shadow_diff"):
        assert t in names, f"{t} 没建出来"
    st = S.degraded_status()
    assert not any(r["area"] == "policy_tables" for r in st["areas"]), st


def test_ensure_policy_tables_adds_missing_rewrite_column(test_client, db_run):
    """存量库补列：老表没有 ``rewrite`` 时必须幂等 ALTER 出来（连跑两次不报错）。"""
    from sqlalchemy import inspect, text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    old_ddl = (
        "CREATE TABLE ai_policy_shadow_diff ("
        "id BIGSERIAL PRIMARY KEY, sql_hash CHAR(64), user_id INTEGER, entry VARCHAR(32), "
        "legacy_decision VARCHAR(8), new_decision VARCHAR(8), diff_kind VARCHAR(32), "
        "policy_ids JSONB DEFAULT '[]', sql_preview TEXT, "
        "created_time TIMESTAMP DEFAULT now())"
    )

    async def _go():
        async with async_db_session.begin() as db:
            await db.execute(text("DROP TABLE IF EXISTS ai_policy_shadow_diff"))
            await db.execute(text(S._ddl_for_dialect(old_ddl)))
        await ensure_policy_tables()
        await ensure_policy_tables()  # 幂等：第二次不能重复 ADD COLUMN 报错
        async with async_db_session() as db:
            conn = await db.connection()
            return await conn.run_sync(
                lambda c: [
                    col["name"]
                    for col in inspect(c).get_columns("ai_policy_shadow_diff")
                ]
            )

    S.reset_degraded()
    cols = db_run(_go())
    assert "rewrite" in cols, f"存量库没补上 rewrite 列：{cols}"
    st = S.degraded_status()
    assert not any(r["area"] == "policy_table_columns" for r in st["areas"]), st


def test_sensitive_tables_lowercased_and_deduped(test_client, db_run):
    """敏感表清单：只取 sensitive=true 且未软删，表名小写去重。"""
    from sqlalchemy import delete

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.model import AiQueryAssetColumnModel
    from app.plugin.module_ai.query.policy.model import sensitive_tables

    like = "t_policy_sens_%"

    async def _go():
        try:
            async with async_db_session.begin() as db:
                await db.execute(delete(AiQueryAssetColumnModel).where(
                    AiQueryAssetColumnModel.table_name.like(like)))
                for table, sensitive, deleted in (
                    ("T_Policy_Sens_A", True, False),
                    ("t_policy_sens_a", True, False),   # 同表大小写重复 → 去重
                    ("t_policy_sens_b", False, False),  # 非敏感 → 不出现
                    ("t_policy_sens_c", True, True),    # 已软删 → 不出现
                ):
                    db.add(AiQueryAssetColumnModel(
                        table_name=table,
                        column_name="id",
                        sensitive=sensitive,
                        included=True,
                        is_deleted=deleted,
                    ))
                await db.flush()
            return await sensitive_tables()
        finally:
            async with async_db_session.begin() as db:
                await db.execute(delete(AiQueryAssetColumnModel).where(
                    AiQueryAssetColumnModel.table_name.like(like)))

    got = db_run(_go())
    mine = {t for t in got if t.startswith("t_policy_sens_")}
    # 大小写不同的同一张表只出现一次（小写），非敏感/已软删的都不出现
    assert mine == {"t_policy_sens_a"}, mine
    assert all(t == t.lower() for t in got), "表名必须统一小写"


# ---------------------------------------------------------------------------
# C1：敏感表清单必须并上「本体侧敏感字段」映射到的物理表
#
# 实测：``sensitive_diff()`` 本体 77 / 资产目录 66，``video_cameras.password``
# 只标在本体上 → ``sensitive_tables()`` 不含该表 → ``select * from video_cameras``
# 被放行，明文读出 password。下面用**假存储**（不依赖 dev 数据）锁死这个洞。
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """够 ``async with async_db_session() as db: db.execute(...).all()`` 用。"""

    def __init__(self, sink: dict, rows):
        self.sink = sink
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self.sink["sql"] = str(stmt)
        self.sink["params"] = params
        return _FakeResult(self.rows)


def _patch_sources(monkeypatch, *, catalog_rows, fields, table_map):
    """把「资产目录 + 本体语义」两个来源都换成假存储。"""
    # 先导入 UserModel：问数模型的关系（created_by/updated_by）指向它，
    # 否则 SQLAlchemy 配置 mapper 时报 "failed to locate a name 'UserModel'"
    # （PYTEST_NO_APP=1 不构造应用，没人替我们导入；冒烟脚本同样要显式加载）。
    from app.api.v1.module_system.user.model import UserModel  # noqa: F401
    from app.plugin.module_ai.ontology import semantic as ont
    from app.plugin.module_ai.query.policy import model as M

    sink: dict = {}
    monkeypatch.setattr(M, "async_db_session", lambda: _FakeSession(sink, catalog_rows))
    if fields is not None:

        async def _fields():
            return fields

        monkeypatch.setattr(ont, "restricted_fields", _fields)
    if table_map is not None:

        async def _tmap():
            return table_map

        monkeypatch.setattr(ont, "object_table_map", _tmap)
    return sink


def test_sensitive_tables_unions_ontology_marked_tables(monkeypatch):
    """本体标敏感、资产目录没标的表 → 也进清单（C1 的核心断言）。"""
    from app.plugin.module_ai.query.policy.model import sensitive_tables

    _patch_sources(
        monkeypatch,
        # 资产目录只标了 catalog_marked，**没有** video_cameras
        catalog_rows=[("catalog_marked",)],
        fields={"video_cameras": {"password"}, "orders": {"amount"}},
        # 本体对象：video_cameras 的支撑表就是自己；orders 有 ont_ 与真实表两种键
        table_map={
            "video_cameras": "video_cameras",
            "ont_orders": "orders",
            "orders": "orders",
        },
    )

    got = asyncio.run(sensitive_tables())

    assert "video_cameras" in got, f"本体侧敏感表漏了：{got}"
    assert "orders" in got, f"本体敏感对象映射不到物理表：{got}"
    assert "ont_orders" not in got, "同一对象优先用真实业务表，不要带上 ont_ 影子表"
    assert "catalog_marked" in got, "资产目录来源不能被本体覆盖掉（两边并集）"


def test_sensitive_tables_ontology_failure_is_best_effort(monkeypatch):
    """本体读失败不能连带资产目录一起失败（best-effort，来源互不影响）。"""
    from app.plugin.module_ai.query.policy.model import sensitive_tables

    _patch_sources(monkeypatch, catalog_rows=[("catalog_only",)], fields=None,
                   table_map=None)
    from app.plugin.module_ai.ontology import semantic as ont

    async def _boom():
        raise RuntimeError("本体库不可用")

    monkeypatch.setattr(ont, "restricted_fields", _boom)

    assert asyncio.run(sensitive_tables()) == {"catalog_only"}


def test_star_query_on_ontology_sensitive_table_is_denied(monkeypatch):
    """端到端：只在本体标敏感的表，``select *`` 在 legacy 下也必须拒。"""
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import model as M
    from app.plugin.module_ai.query.policy.principal import Principal

    _patch_sources(
        monkeypatch,
        catalog_rows=[],  # 资产目录：什么都没标
        fields={"video_cameras": {"password"}},
        table_map={"video_cameras": "video_cameras"},
    )
    # guard 模块导入时绑定了 sensitive_tables，这里换成真实现（内部用上面的假存储）
    monkeypatch.setattr(guard, "sensitive_tables", M.sensitive_tables)

    audited: list[dict] = []

    async def _audit(**kw):
        audited.append(kw)

    async def _mode():
        return "legacy"

    async def _tables(sql):
        return {"video_cameras"}

    monkeypatch.setattr(guard, "write_access_log", _audit)
    monkeypatch.setattr(guard, "_engine_mode", _mode)
    monkeypatch.setattr(guard, "_tables_of", _tables)

    async def _legacy():  # pragma: no cover - 星号必须在旧判定之前拒
        raise AssertionError("星号止血不该走到旧判定")

    d = asyncio.run(
        guard.prepare(
            sql="select * from video_cameras",
            principal=Principal(
                user_id=7, is_superuser=False, roles=(), attrs={}, entry="ask"
            ),
            entry="ask",
            datasource="ds:4",
            legacy_check=_legacy,
        )
    )

    assert not d.permit, "本体侧敏感表上的 select * 被放行了（明文 password 可读）"
    assert "video_cameras" in d.reason, d.reason
    assert audited and audited[-1]["decision"] == "deny", audited


# ---------------------------------------------------------------------------
# I1：导出/浏览不许绕过敏感表（``SELECT *`` 直读）
# ---------------------------------------------------------------------------
def test_export_and_browse_reject_sensitive_table(monkeypatch):
    """含敏感列的表：导出/浏览一律拒绝（桩敏感表清单，不碰库）。"""
    from app.plugin.module_ai.query.policy import model as M
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _require(cls, table, auth):
        return table

    async def _sensitive():
        return {"t_sensitive_export"}

    monkeypatch.setattr(Q, "_require_queryable_table", classmethod(_require))
    monkeypatch.setattr(M, "sensitive_tables", _sensitive)

    export = asyncio.run(Q.export_asset("T_Sensitive_Export", None, limit=10))
    browse = asyncio.run(Q.object_browse("t_sensitive_export", None, page=1, page_size=10))

    for out in (export, browse):
        assert out["ok"] is False, out
        assert "敏感" in out["msg"], out


# ---------------------------------------------------------------------------
# I2：``policy_engine`` 只允许超管写（任何能问数的人都不能关判定）
# ---------------------------------------------------------------------------
def _fake_auth(*, is_superuser: bool = False):
    from types import SimpleNamespace

    return SimpleNamespace(
        user=SimpleNamespace(id=9, name="设置写入测试", is_superuser=is_superuser)
    )


def test_policy_engine_setting_rejected_for_non_superuser():
    import pytest

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        asyncio.run(Q.save_setting("policy_engine", "legacy", "", _fake_auth()))
    assert "policy_engine" in ei.value.msg or "超级管理员" in ei.value.msg, ei.value.msg
