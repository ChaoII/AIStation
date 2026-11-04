"""设置项「接线」守护：代码读的每个 key 都必须能设，设置的值都必须真的生效。

背景（2026-11 审计）
--------------------
`query_max_rows` / `query_timeout_sec` / `nl2sql_retry` 三个 key 一直躺在
`get_settings()` 的默认值表里，界面也能改，但**运行时读的是模块常量**：

    MAX_ROWS = 1000          ← 而不是 query_max_rows
    QUERY_TIMEOUT = 10       ← 而且这个常量连自己都没被用过
    for attempt in range(2)  ← 而不是 nl2sql_retry

于是"改了不生效"，而且不报错、不告警 —— 这是最难发现的一类缺陷。
反向也有：新增开关只写代码分支、不进默认值表 → 设置弹窗里根本看不到它。

本文件用四种方式钉住：
1. 静态对账：`_cfg_*` 读到的 key ⊆ 默认值表；
2. 夹紧区间一致：`service._clamp_rows` 与 `executor.clamp_max_rows` 行为相同；
3. 真执行：sqlite 上 `max_rows=2` 必须只回 2 行；
4. 真执行：超时必须是 `CustomException`（上层只认它才会回退慢路径）。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.core.exceptions import CustomException

QUERY_DIR = Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_ai" / "query"


def _read_keys(src_file: Path) -> set[str]:
    """扫出 `_cfg_bool/_cfg_int/...` 与 `cfg.get("x")` 里出现的设置 key。"""
    tree = ast.parse(open(src_file, encoding="utf-8").read())
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name in ("_cfg_bool", "_cfg_int", "_cfg_str", "_cfg_float"):
            if len(node.args) >= 2:
                a = node.args[1]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.add(a.value)
        elif name == "get" and isinstance(fn, ast.Attribute):
            # cfg.get("x") / config.get("x")
            if getattr(fn.value, "id", "") in ("cfg", "config") and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.add(a.value)
    return keys


def _default_keys(src_file: Path) -> set[str]:
    tree = ast.parse(open(src_file, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "defaults":
            return {k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    raise AssertionError("service.py 里找不到 get_settings() 的 defaults 字典")


def test_every_read_setting_key_is_declared_in_defaults():
    """代码读的每个设置 key 都必须在默认值表里。

    否则：新库上「设置弹窗看不到这个键」（弹窗按 get_settings 的返回渲染），
    用户想改只能自己去 UPDATE 数据库 —— 我上一轮的三个开关就是这样。
    """
    service = QUERY_DIR / "service.py"
    declared = _default_keys(service)
    read = _read_keys(service)
    for extra in ("keepalive.py", "eval_runner.py"):
        read |= _read_keys(QUERY_DIR / extra)

    missing = sorted(read - declared)
    assert not missing, f"这些 key 有代码在读，但默认值表里没有：{missing}"


def test_prune_and_literal_fix_are_visible_and_default_on():
    """本轮两个"默认开"的开关必须能被看到、被回退。

    `schema_column_prune_enabled` / `literal_fix_enabled` 是 A/B 的产物，
    默认开；一旦不进默认值表，界面上就没有回退入口。
    """
    declared = _default_keys(QUERY_DIR / "service.py")
    assert "schema_column_prune_enabled" in declared
    assert "literal_fix_enabled" in declared


def test_enum_hint_default_is_same_everywhere():
    """同一个开关给了两种默认值 = 行为随"哪条路径先跑"而变。

    实测第四处（系统 schema 构建）曾写 `default=True`，其余三处 False：
    设置行一旦缺失，系统库会去跑一堆 DISTINCT，而外部库不会。
    """
    src = open(QUERY_DIR / "service.py", encoding="utf-8").read()
    assert '"enum_hint_enabled", True' not in src


def test_clamp_rows_is_identical_in_both_modules():
    """行数上限在两处实现，必须同区间（否则系统库/外部库行为不一致）。"""
    from app.plugin.module_ai.query import executor, service

    for probe in ["bad", None, -5, 0, 1, 9, 10, 1000, 5000, 99999, "20", 20.7]:
        assert service._clamp_rows(probe) == executor.clamp_max_rows(probe), probe


def test_nl2sql_attempts_default_keeps_old_behavior():
    """默认值必须等价于改动前硬编码的 `range(2)`，否则就是在偷偷改行为。"""
    from app.plugin.module_ai.query.service import nl2sql_attempts

    assert nl2sql_attempts({}) == 2
    assert nl2sql_attempts({"nl2sql_retry": "2"}) == 2
    assert nl2sql_attempts({"nl2sql_retry": "1"}) == 1     # 只试一次（省时间）
    assert nl2sql_attempts({"nl2sql_retry": "99"}) == 5    # 夹到上限
    assert nl2sql_attempts({"nl2sql_retry": "bad"}) == 2   # 脏值回落


def test_slow_path_actually_uses_the_setting():
    """循环必须读 `attempts`（而不是又写回 range(2)）。"""
    from app.plugin.module_ai.query.service import AiQueryService

    src = inspect.getsource(AiQueryService._slow_path)
    assert "nl2sql_attempts(cfg)" in src
    assert "range(attempts)" in src


def test_object_query_max_tokens_zero_follows_main_budget():
    """`0` 表示跟随主预算。

    这个 key 进默认值表后才暴露的坑：`_cfg_int(cfg, key, default)` 的 default
    只在 key **缺失**时生效；key 一旦恒为 "0"，max_tokens 就变成 0，模型返回空。
    """
    from app.plugin.module_ai.query.service import _ir_max_tokens, nl2sql_max_tokens

    cfg = {"nl2sql_max_tokens": "8000"}
    assert _ir_max_tokens(cfg) == nl2sql_max_tokens(cfg) == 8000
    assert _ir_max_tokens({**cfg, "object_query_max_tokens": "0"}) == 8000
    assert _ir_max_tokens({**cfg, "object_query_max_tokens": ""}) == 8000
    assert _ir_max_tokens({**cfg, "object_query_max_tokens": "12000"}) == 12000


def test_execute_select_applies_max_rows():
    """真的只回 2 行（不是"读了个设置项就算接线"）。

    ⚠️ 不用 pytest 的 `tmp_path`：这台机器上它一次要 62 秒（pytest 清理旧的
    临时目录），会让一个纯逻辑测试慢得像集成测试。用 tempfile 自己建自己删。
    """
    from app.plugin.module_ai.query import executor

    db = Path(tempfile.mkdtemp()) / "t.db"
    cfg = {"type": "sqlite", "database": str(db)}
    # 建表/插数用同步 sqlite3：execute_select 是"只读 SELECT"入口，
    # 拿它跑 DDL 会因 result 无行而报错（正好也是它该有的行为）。
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t(x INTEGER)")
    con.executemany("INSERT INTO t(x) VALUES (?)", [(i,) for i in (1, 2, 3, 4, 5)])
    con.commit()
    con.close()

    async def _run() -> tuple[dict, dict]:
        cut = await executor.execute_select(cfg, "SELECT x FROM t ORDER BY x", max_rows=2)
        full = await executor.execute_select(cfg, "SELECT x FROM t ORDER BY x", max_rows=100)
        return cut, full

    out, full = asyncio.run(_run())
    assert [r[0] for r in out["rows"]] == [1, 2]
    assert out["truncated"] is True
    assert "took_ms" in out          # 调用方会读，缺了就是 KeyError（真实踩过）
    assert len(full["rows"]) == 5
    assert full["truncated"] is False


def test_execute_select_timeout_is_custom_exception(monkeypatch):
    """超时必须抛 `CustomException`：上层只认它才会「记录错误 → 回退慢路径」。

    裸 `TimeoutError` 会冒泡把整题打崩（和当初裸 ProgrammingError 同一个坑）。
    """
    from app.plugin.module_ai.query import executor

    async def fake_wait_for(coro, timeout=None):
        coro.close()                 # 避免 "coroutine was never awaited"
        raise TimeoutError

    monkeypatch.setattr(executor.asyncio, "wait_for", fake_wait_for)
    cfg = {"type": "sqlite", "database": str(Path(tempfile.mkdtemp()) / "t.db")}

    with pytest.raises(CustomException) as ei:
        asyncio.run(executor.execute_select(cfg, "SELECT 1", timeout=1))
    assert "超时" in str(getattr(ei.value, "msg", "") or ei.value)


def test_ctx_cache_signature_covers_all_prompt_affecting_keys():
    """缓存 key 的配置指纹必须覆盖"会影响 prompt/召回"的开关。

    否则：管理员刚把 recall_top_k 从 12 调到 6，进程内缓存（TTL 600s）还在吐
    12 张表的旧结果 —— 表现就是"改了没反应"，而这正好会让 A/B 实验失效。
    """
    from app.plugin.module_ai.query.service import _CTX_CFG_KEYS

    declared = _default_keys(QUERY_DIR / "service.py")
    missing = [k for k in _CTX_CFG_KEYS if k not in declared]
    assert not missing, f"指纹里的 key 不在默认值表（拼错就会静默失效）：{missing}"

    # 这几个是"改了必须换缓存"的代表，缺一个都会出"改了没反应"
    for must in ("recall_top_k", "recall_enabled", "schema_column_prune_enabled",
                 "enum_hint_enabled", "schema_asset_meta_enabled"):
        assert must in _CTX_CFG_KEYS


def test_ctx_cache_signature_changes_with_settings():
    from app.plugin.module_ai.query.service import _cfg_sig

    base = {"recall_top_k": "12", "schema_column_prune_enabled": "true"}
    assert _cfg_sig(base) == _cfg_sig(dict(base))                    # 同配置同指纹
    assert _cfg_sig(base) != _cfg_sig({**base, "recall_top_k": "6"})  # 改 top_k 就变
    assert _cfg_sig(base) != _cfg_sig({**base, "schema_column_prune_enabled": "false"})


def test_retrieval_cache_is_keyed_by_settings(monkeypatch):
    """真的换了缓存条目（不是只算了个指纹放那儿）。"""
    from app.plugin.module_ai.query import service as svc

    calls = {"n": 0}

    async def fake_uncached(cls, question, schema=None, metrics=None, terms=None):
        calls["n"] += 1
        return [f"t{calls['n']}"]

    cfg = {"recall_top_k": "12"}

    async def fake_cfg(cls):
        return dict(cfg)

    monkeypatch.setattr(svc.AiQueryService, "_cfg", classmethod(fake_cfg))
    monkeypatch.setattr(svc.AiQueryService, "_semantic_tables_uncached",
                        classmethod(fake_uncached))
    monkeypatch.setattr(svc, "_RETRIEVAL_CACHE", {})

    def run():
        return asyncio.run(
            svc.AiQueryService._semantic_tables("问一句", datasource="ds:4"))

    assert run() == ["t1"]
    assert run() == ["t1"]          # 同配置命中缓存
    cfg["recall_top_k"] = "6"
    assert run() == ["t2"]          # 改配置必须重新召回


def test_object_path_requires_columns_not_just_rows():
    """对象路径只认「有列」的结果。

    实测两次踩在同一个地方：「每日出入库报表一共有多少条记录」被 IR 接走，
    一次是无列无行、一次是**有行但无列** —— 旧判据 `not cols and not rows` 放行了
    后者，前端没有列名可渲染，用户看到空回答，评测判错。
    """
    import inspect

    from app.plugin.module_ai.query.service import AiQueryService

    src = inspect.getsource(AiQueryService._object_query_path)
    assert "if not cols:" in src
    assert "if not cols and not rows" not in src


def test_softdelete_rewrite_is_wired_and_gated():
    """软删除口径由**代码改写**保证，不再靠提示词。

    背景（3 组 × 78 题配对实测）：提示词版规则把准确率从 0.8846 拉到 0.8985~0.9103，
    但它自己两轮之间翻转 5 题（baseline 0 题）——收益 1~2 题 < 自身抖动，统计上不成立。
    改成执行前确定性改写：0 token、可单测、不随模型波动。
    """
    from app.plugin.module_ai.query.softdelete import (
        asks_about_deletion,
        inject_softdelete,
    )

    # 1) 只给直接引用的表补条件
    sql, hit = inject_softdelete(
        'SELECT COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH"',
        {"FUEL_CMCS_INFACTORYBATCH"})
    assert '"ISDELETED" = FALSE' in sql.upper() and hit == ["FUEL_CMCS_INFACTORYBATCH"]

    # 2) UNION 两个分支各自注入（只动最外层会把条件加到错的地方）
    sql2, hit2 = inject_softdelete(
        'SELECT COUNT(*) FROM "A" UNION ALL SELECT COUNT(*) FROM "B"', {"A", "B"})
    assert len(hit2) == 2 and sql2.upper().count('"ISDELETED" = FALSE') == 2

    # 3) 表里没有 ISDELETED 就不动
    same, hit3 = inject_softdelete('SELECT 1 FROM "C"', {"A"})
    assert same == 'SELECT 1 FROM "C"' and hit3 == []

    # 4) 问句在问"已删除"时必须放弃改写（否则问的就是反的）
    assert asks_about_deletion("入厂煤批次里已删除的有多少条？") is True
    assert asks_about_deletion("每日耗用量（排除已删除记录）合计是多少") is True
    assert asks_about_deletion("矿点名称为空的批次有多少条？") is False


def test_softdelete_rewrite_hook_and_setting_exist():
    """执行收口必须真的调用改写，且开关在默认值表里（否则设了也改不动）。"""
    import inspect

    from app.plugin.module_ai.query.service import AiQueryService as S

    assert "sql_softdelete_rewrite_enabled" in _default_keys(QUERY_DIR / "service.py")
    src = inspect.getsource(S._execute_one)
    assert "_apply_softdelete_policy" in src
    assert "sql_softdelete_rewrite_enabled" in src
    # 提示词里那两条已移除（A/B 证明不稳定/无效，留代码就是误导）
    conv = inspect.getsource(S._query_conventions)
    assert "ISDELETED" not in conv
