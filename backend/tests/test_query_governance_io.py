"""治理包（别名/描述/术语）导入导出的纯逻辑 + 端到端预演。

- `diff_rows` / `_norm_aliases`：纯函数，`PYTEST_NO_APP=1` 可跑；
- `export → preview` 往返必须 **0 新增 0 更新**（幂等），需要构造应用，PYTEST_NO_APP 时跳过。
"""
from __future__ import annotations

import os

import pytest

from app.plugin.module_ai.query.governance_io import _norm_aliases, diff_rows


def test_diff_rows():
    cur = {"A": ("x", "y"), "B": ("m", "n")}
    want = {"A": ("x", "y"), "B": ("m", "changed"), "C": ("", "new")}
    d = diff_rows(cur, want)
    assert d == {"add": ["C"], "update": ["B"], "same": ["A"]}


def test_norm_aliases_accepts_string_and_list():
    assert _norm_aliases("期初库存|库存明细, 期初") == ["期初库存", "库存明细", "期初"]
    assert _norm_aliases(["a", " b ", ""]) == ["a", "b"]
    assert _norm_aliases(None) == []


@pytest.mark.skipif(os.environ.get("PYTEST_NO_APP") == "1", reason="需要构造应用（ORM）")
def test_export_preview_roundtrip_is_idempotent():
    import asyncio

    from app.plugin.module_ai.query.governance_io import export_bundle, preview_bundle

    bundle = asyncio.run(export_bundle("ds:6"))
    assert set(bundle) >= {"version", "assets", "ontology_aliases", "terms"}
    prev = asyncio.run(preview_bundle(bundle, "ds:6"))
    # 导出的包原样预演 → 必须 0 新增 0 更新（幂等），否则说明包和库口径不一致
    assert prev["assets"]["add"] == 0 and prev["assets"]["update"] == 0
    assert prev["terms"]["add"] == 0 and prev["terms"]["update"] == 0
    assert prev["ontology_aliases"]["add"] == 0 and prev["ontology_aliases"]["update"] == 0
    # 库里同名不同大小写的重复行要单独报出来（不是「更新」）
    assert "duplicates" in prev["assets"]
    assert prev["assets"]["same"] == len(bundle["assets"]) - prev["assets"]["duplicates"]
