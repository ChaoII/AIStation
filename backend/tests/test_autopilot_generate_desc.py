"""自动修复「补全描述」回归（P1-2）。

修复前有两个缺口，都会让「自主修复」白跑：

1. ``autopilot_auto_fix`` 调 ``autopilot_execute`` **不传 auth**，而
   ``autopilot_execute`` 的 ``generate_desc`` 分支会调
   ``generate_asset_descriptions(auth, force=False)``，其内部写 ``auth.user.id``
   → ``auth=None`` 时抛 AttributeError → 被 except 吞成 ``ok=False``，
   即「自主修复补描述」**必然失败**；
2. ``generate_desc`` **忽略 table 参数**（生成器自己扫描所有缺描述资产），
   却被放在 ``autopilot_auto_fix`` 的**按表循环**里 → N 张表就把
   批量补齐全量重跑 N 次（白烧 N 轮 LLM）。

本文件用**假会话**隔离 DB、打桩 ``_profile_table`` / ``_llm_structured`` 隔离 LLM，
其余走真实的 ``generate_asset_descriptions``，因此不依赖应用与数据库。
"""

import asyncio
from types import SimpleNamespace

import app.api.v1.module_system.user.model  # noqa: F401  注册 UserModel，避免 mapper 解析失败
from app.plugin.module_ai.query import service as qservice
from app.plugin.module_ai.query.llm_schemas import AssetDescriptionOut
from app.plugin.module_ai.query.model import (
    AiQueryAssetColumnModel,
    AiQueryAssetModel,
)
from app.plugin.module_ai.query.service import AiQueryService as S


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """只满足 ``generate_asset_descriptions`` 需要的两条 select + ``get``。"""

    def __init__(self, tables, columns):
        self.tables = tables
        self.columns = columns
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is AiQueryAssetModel:
            return _FakeResult(self.tables)
        if entity is AiQueryAssetColumnModel:
            return _FakeResult(self.columns)
        raise AssertionError(f"意外的查询：{stmt}")

    async def get(self, model, pk):
        if model is AiQueryAssetModel:
            return next((t for t in self.tables if t.id == pk), None)
        raise AssertionError(f"意外的 get：{model}")

    def add(self, obj):
        self.added.append(obj)


class _FakeDB:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session

    def begin(self):
        return self.session


def _install(monkeypatch, tables, columns):
    """把 DB / 画像 / LLM 全部打桩，返回假会话供断言。"""
    session = _FakeSession(tables, columns)
    monkeypatch.setattr(qservice, "async_db_session", _FakeDB(session))

    async def _profile(tname, colnames):
        return {"table": tname, "rows": 1,
                "cols": {c: {"null_pct": 0.0, "distinct": 1} for c in colnames}}

    async def _llm(prompt, schema, **kwargs):
        return AssetDescriptionOut(table="AI 生成描述", columns={"c0": "AI 生成字段"})

    monkeypatch.setattr(S, "_profile_table", staticmethod(_profile))
    monkeypatch.setattr(S, "_llm_structured", staticmethod(_llm))
    return session


def test_generate_descriptions_without_auth_does_not_crash(monkeypatch):
    """无 auth（内部调度）时也要能补齐；审计字段兜底为 None，不伪造操作人。"""
    table = SimpleNamespace(id=1, table_name="t_auto_desc_a", description="")
    column = AiQueryAssetColumnModel(
        table_name="t_auto_desc_a", column_name="c0", description="")
    _install(monkeypatch, [table], [column])

    r = asyncio.run(S.generate_asset_descriptions(None))

    assert r == {"tables": 1, "columns": 1}
    assert table.description == "AI 生成描述"
    assert column.description == "AI 生成字段"
    assert column.updated_id is None, "内部调度没有操作人，审计字段应留空"


def test_auto_fix_runs_generate_desc_once(monkeypatch):
    """generate_desc 是批量动作：N 张表也只能触发 1 次。"""
    plan = {"total": 1, "actions": [{
        "type": "enrich", "suggestion": "补全描述",
        "executable": "generate_desc", "tables": ["t1", "t2", "t3"],
    }]}

    async def _plan():
        return plan

    calls: list = []

    async def _desc(auth=None, force=False):
        calls.append(auth)
        return {"tables": 3, "columns": 5}

    monkeypatch.setattr(S, "autopilot", staticmethod(_plan))
    monkeypatch.setattr(S, "generate_asset_descriptions", staticmethod(_desc))

    r = asyncio.run(S.autopilot_auto_fix())

    assert len(calls) == 1, f"generate_desc 应只触发 1 次，实际触发 {len(calls)} 次"
    assert r["attempted"] == 1 and r["fixed"] == 1
    assert r["results"][0]["ok"] is True


def test_autopilot_execute_generate_desc_ok_without_auth(monkeypatch):
    """自主执行的 generate_desc 分支在无 auth 时必须返回 ok=True。"""
    table = SimpleNamespace(id=2, table_name="t_auto_desc_b", description="")
    column = AiQueryAssetColumnModel(
        table_name="t_auto_desc_b", column_name="c0", description="")
    _install(monkeypatch, [table], [column])

    r = asyncio.run(S.autopilot_execute("generate_desc", "", auth=None))

    assert r["ok"] is True, r["msg"]
    assert "生成描述完成" in r["msg"]


def test_autopilot_execute_generate_desc_still_accepts_table(monkeypatch):
    """带 table 的旧调用方式（前端逐行动作）不能被破坏。"""
    table = SimpleNamespace(id=3, table_name="t_auto_desc_c", description="")
    column = AiQueryAssetColumnModel(
        table_name="t_auto_desc_c", column_name="c0", description="")
    _install(monkeypatch, [table], [column])

    r = asyncio.run(S.autopilot_execute("generate_desc", "t_auto_desc_c", auth=None))

    assert r["ok"] is True, r["msg"]
    assert table.description == "AI 生成描述"


def test_unknown_executable_is_still_rejected():
    """无关行动仍按信息项处理（不要为了修 generate_desc 放宽所有分支）。"""
    r = asyncio.run(S.autopilot_execute("rebuild_everything", "t", auth=None))
    assert r["ok"] is False
    assert "暂不支持" in r["msg"]
