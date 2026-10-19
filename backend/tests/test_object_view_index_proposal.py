"""对象视图 / 索引 / 提案 / 演示数据 的单元与回归测试。

对齐的三块官方文档：
· `object-views/*`      —— Standard vs Configured、Full vs Panel、tabs→widgets
· `object-indexing/*`   —— Funnel 流水线、状态就绪=绿勾、瞬时失败 5 分钟后重试
· `ontologies/ontologies-proposals` —— 分支/提案/任务/审查/合并、关闭不可重开
"""
import asyncio
import inspect

import _ont_ddl
import pytest

from app.plugin.module_ai.ontology import demo as D
from app.plugin.module_ai.ontology import indexing as IX
from app.plugin.module_ai.ontology import object_view as OV
from app.plugin.module_ai.ontology import proposal as PR
from app.plugin.module_ai.ontology import service as svc


def _run(coro):
    return asyncio.run(coro)


#: 测试用对象类型（自建、自物化 —— SQLite 测试库没有种子数据）
CAM = "reg_cam"


@pytest.fixture(scope="module", autouse=True)
def _tables(test_client):
    """建全部本体元数据表 + 一个**真的物化**的测试对象类型。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session, async_engine

    async def _create():
        await async_engine.dispose()
        async with async_db_session.begin() as db:
            for ddl in _ont_ddl.ONT_DDL.values():
                await db.execute(_t(ddl))
            # 支撑表（真实存在于 SQLite，索引/渲染/图表都要用）
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS reg_cams (id INTEGER PRIMARY KEY, "
                "name TEXT, status TEXT, group_id INTEGER, device_type TEXT)"))
            await db.execute(_t(
                "INSERT OR IGNORE INTO reg_cams (id,name,status,group_id,device_type) "
                "VALUES (1,'回归摄像机','ONLINE',1,'IP_CAMERA')"))
            await db.execute(_t(
                "INSERT OR IGNORE INTO reg_cams (id,name,status,group_id,device_type) "
                "VALUES (2,'回归摄像机2','OFFLINE',2,'IP_CAMERA')"))
        # 对象类型 + 属性
        await svc.upsert_object({"code": CAM, "name": "回归摄像机表",
                                 "key_prop": "id", "name_prop": "name",
                                 "backing_table": "reg_cams"})
        for code, name, ptype in (("name", "名称", "string"),
                                  ("status", "状态", "string"),
                                  ("group_id", "分组", "int"),
                                  ("device_type", "设备类型", "string")):
            await svc.upsert_property({"object_code": CAM, "code": code,
                                       "name": name, "prop_type": ptype})
    _run(_create())


def _is_postgres() -> bool:
    from app.core.database import async_engine

    return async_engine.dialect.name == "postgresql"


pg_only = pytest.mark.skipif(not _is_postgres(),
                             reason="断言依赖 Postgres 专属对象（如 pg_indexes）")


# ===========================================================================
# A) 对象视图
# ===========================================================================
class TestObjectView:
    def test_form_factors_are_full_and_panel(self):
        """官方两种形态：Full（完整）与 Panel（面板，供其它应用嵌入）。"""
        assert set(OV.ONT_FORM_FACTORS) == {"full", "panel"}
        assert OV.ONT_FORM_FACTOR_LABEL["full"] == "完整视图"
        assert OV.ONT_FORM_FACTOR_LABEL["panel"] == "面板视图"

    def test_widget_categories_match_official_docs(self):
        """官方把 widget 分成 properties-links / visualization / filtering / layout / apps-files。"""
        for w in OV.ONT_WIDGET_TYPES:
            assert w in OV.ONT_WIDGET_CATEGORY, w
        cats = set(OV.ONT_WIDGET_CATEGORY.values())
        assert {"properties-links", "visualization", "filtering", "layout"} <= cats
        # 每个 widget 都有中文名
        for w in OV.ONT_WIDGET_TYPES:
            assert OV.ONT_WIDGET_LABEL[w]

    def test_validate_tabs_rejects_bad_config(self):
        assert OV.validate_tabs("nope") == ["tabs 必须是数组"]
        errs = OV.validate_tabs([{"key": "", "label": ""}])
        assert any("key" in e for e in errs)
        # 未知 widget 类型必须被拒
        errs = OV.validate_tabs([{"key": "a", "label": "A",
                                  "widgets": [{"type": "bogus"}]}])
        assert any("不支持" in e for e in errs)
        # 重复 key
        errs = OV.validate_tabs([{"key": "a", "label": "A"}, {"key": "a", "label": "B"}])
        assert any("重复" in e for e in errs)
        assert OV.validate_tabs([{"key": "a", "label": "A",
                                  "widgets": [{"type": "properties"}]}]) == []

    def test_widget_meta_carries_category(self):
        m = OV.widget_meta({"type": "chart"})
        assert m["category"] == "visualization"
        assert m["label"] == "图表"

    @pg_only
    def test_standard_view_is_generated_not_stored(self):
        """官方：Standard 视图自动反映对象类型配置，不需要落库。"""
        std = _run(OV.standard_view(CAM, "full"))
        assert std["ok"] is True
        assert std["view_type"] == "standard"
        assert std["is_managed"] is False
        assert std["tabs"], "标准视图必须有内容"
        # 面板形态只保留属性（官方：只放关键信息）
        panel = _run(OV.standard_view(CAM, "panel"))
        types = [w["type"] for t in panel["tabs"] for w in t["widgets"]]
        assert types == ["properties"], types

    @pg_only
    def test_default_view_auto_created_and_idempotent(self):
        """官方：默认视图对每个对象类型**自动创建**；重复调用不应重复建。"""
        r1 = _run(OV.ensure_default_view("reg_ov_obj", "full", "t"))
        assert r1["ok"] is True
        r2 = _run(OV.ensure_default_view("reg_ov_obj", "full", "t"))
        assert r2["created"] is False, "第二次不应再创建"
        views = _run(OV.list_views("reg_ov_obj", "full"))
        assert len(views) == 1

    def test_sync_default_views_reuses_object_list(self):
        """回归：批量补齐默认视图**不能每个对象都重查一遍全量对象列表**。

        实测（2026-10，421 个对象）：单次 ``list_objects()`` 约 105ms，
        421 对象 × 2 形态 = 842 次重查 ⇒ 光重复查询就 ~89 秒，
        整批同步长到浏览器请求超时、用户以为"点了没反应"。
        """
        sync_src = inspect.getsource(OV.sync_default_views)
        assert "objects=objs" in sync_src, "批量补齐必须把对象列表传下去，避免 O(n²) 重查"
        assert "objects: list[dict] | None = None" in inspect.getsource(OV.standard_view)

    def test_ensure_default_view_tolerates_existing_code(self):
        """回归：编码已存在（并发/历史残留）时**跳过**，不能让整批补齐全盘失败。

        实测：并发补齐时 create_view 抛「视图编码 xxx 已存在」，
        导致 421 个对象的同步在中间炸掉（已建的留下、后面的全没建）。
        """
        src = inspect.getsource(OV.ensure_default_view)
        assert "except CustomException" in src
        assert "已存在视图，跳过" in src

    @pg_only
    def test_editing_marks_view_user_managed(self):
        """官方：一旦被编辑就转为 user-managed，不再跟随对象类型自动更新。"""
        _run(OV.ensure_default_view("reg_ov_obj2", "full", "t"))
        code = _run(OV.list_views("reg_ov_obj2", "full"))[0]["code"]
        assert _run(OV.get_view(code))["is_managed"] is False
        r = _run(OV.update_view(code, {"tabs": [{"key": "k", "label": "K",
                                                 "widgets": []}], "note": "首次编辑"}, "t"))
        assert r["became_managed"] is True
        assert _run(OV.get_view(code))["is_managed"] is True

    @pg_only
    def test_version_recorded_and_restorable(self):
        _run(OV.ensure_default_view("reg_ov_obj3", "full", "t"))
        code = _run(OV.list_views("reg_ov_obj3", "full"))[0]["code"]
        _run(OV.update_view(code, {"tabs": [{"key": "v2", "label": "V2",
                                             "widgets": []}]}, "t"))
        vers = _run(OV.list_view_versions(code))
        assert any(v["version"] == 2 for v in vers), vers
        _run(OV.restore_view_version(code, 2, "t"))
        assert _run(OV.get_view(code))["version"] == 3

    @pg_only
    def test_render_view_produces_real_data(self):
        """render_view 必须把配置解析成**真实数据**，而不是回显配置。"""
        _run(OV.ensure_default_view(CAM, "full", "t"))
        code = _run(OV.list_views(CAM, "full"))[0]["code"]
        r = _run(OV.render_view(code, "1"))
        assert r["ok"] is True
        assert r["object"]["key"] == "1"
        flat = [w for t in r["tabs"] for w in t["widgets"]]
        assert flat, "渲染结果不能是空的"
        prop_w = next((w for w in flat if w["type"] == "properties"), None)
        assert prop_w and prop_w.get("items"), "属性 widget 必须解析出属性项"
        # 每一项都有 code/name/value
        for it in prop_w["items"]:
            assert "code" in it and "name" in it and "value" in it

    @pg_only
    def test_render_chart_really_queries(self):
        """图表 widget 要真查库（分组统计），不是占位。"""
        view = _run(OV.create_view({
            "object_code": CAM, "code": "reg_ov_chart",
            "name": "回归图表视图", "form_factor": "full",
            "tabs": [{"key": "c", "label": "C", "widgets": [
                {"type": "chart", "config": {"group_by": "status", "limit": 5}}]}],
        }))
        assert view["ok"]
        r = _run(OV.render_view("reg_ov_chart", "1"))
        w = r["tabs"][0]["widgets"][0]
        assert w["type"] == "chart"
        assert "error" not in w, w
        assert w["series"], "分组统计应有结果"
        for s in w["series"]:
            assert "label" in s and isinstance(s["value"], int)

    @pg_only
    def test_default_view_is_unique_per_object_and_form(self):
        _run(OV.ensure_default_view("reg_ov_obj4", "full", "t"))
        a = _run(OV.list_views("reg_ov_obj4", "full"))[0]["code"]
        b = _run(OV.create_view({
            "object_code": "reg_ov_obj4", "code": "reg_ov_obj4__second",
            "name": "第二个", "form_factor": "full",
            "tabs": [{"key": "k", "label": "K", "widgets": []}], "is_default": True,
        }))
        assert b["ok"]
        views = _run(OV.list_views("reg_ov_obj4", "full"))
        assert sum(1 for v in views if v["is_default"]) == 1, "同形态只能有一个默认"
        assert _run(OV.get_view(a))["is_default"] is False


# ===========================================================================
# B) 索引
# ===========================================================================
class TestIndexing:
    def test_status_vocabulary_matches_official(self):
        """官方状态：未开始 / 构建中 / 就绪（绿勾）/ 失败 / 过期。"""
        assert set(IX.ONT_INDEX_STATUS) == {"not_started", "building", "ready",
                                           "failed", "stale"}
        for s in IX.ONT_INDEX_STATUS:
            assert IX.ONT_INDEX_STATUS_LABEL[s]

    def test_pipelines_match_official(self):
        """官方两种流水线 batch / streaming（另有 direct datasources）。"""
        assert set(IX.ONT_PIPELINE_KINDS) == {"batch", "streaming", "direct"}

    def test_auto_retry_is_five_minutes(self):
        """官方：瞬时失败约 **5 分钟**后自动重试。"""
        assert IX.AUTO_RETRY_MINUTES == 5

    def test_streaming_throughput_limit_documented(self):
        """官方：streaming 每对象类型 2 MB/s。"""
        assert IX.STREAMING_MAX_BYTES_PER_SEC == 2 * 1024 * 1024

    @pg_only
    def test_build_creates_real_pg_index(self):
        """构建索引必须**真的**在支撑表上建出索引（不是只改状态字段）。"""
        r = _run(IX.upsert_index({"object_code": CAM,
                                  "prop_code": "status", "index_kind": "property"}))
        assert r["ok"], r
        name = r["index_name"]
        b = _run(IX.build_index(r["id"]))
        assert b["ok"], b
        assert b["status"] == "ready"
        assert b["rows"] >= 0
        # 真的存在吗
        row = _run(svc._exec(
            "SELECT 1 FROM pg_indexes WHERE indexname=:n", {"n": name})).fetchone()
        assert row, f"底层没有建出索引 {name}"
        # 删掉后也应真的消失
        _run(IX.remove_index(r["id"]))
        row2 = _run(svc._exec(
            "SELECT 1 FROM pg_indexes WHERE indexname=:n", {"n": name})).fetchone()
        assert not row2, "删除后底层索引应被 DROP"

    @pg_only
    def test_build_fails_on_unmaterialized_object(self):
        """对象类型没物化时不能建索引，且要给可读原因。"""
        _run(svc.upsert_object({"code": "reg_ix_nomaterial", "name": "未物化对象"}))
        r = _run(IX.upsert_index({"object_code": "reg_ix_nomaterial",
                                  "prop_code": "", "index_kind": "primary"}))
        assert r["ok"], r
        b = _run(IX.build_index(r["id"]))
        assert b["ok"] is False
        assert "未物化" in b["msg"] or "元数据" in b["msg"], b["msg"]

    @pg_only
    def test_terminal_failure_has_no_auto_retry(self):
        """官方：终态错误**只在新数据到来时**重试 —— 因此不应排自动重试时间。"""
        _run(svc.upsert_object({"code": "reg_ix_terminal", "name": "终态失败对象"}))
        r = _run(IX.upsert_index({"object_code": "reg_ix_terminal", "prop_code": "",
                                  "index_kind": "primary"}))
        _run(IX.build_index(r["id"]))
        row = _run(svc._exec(
            "SELECT status, auto_retry_at, COALESCE(last_error,'') FROM ai_ont_index "
            "WHERE id=:i", {"i": r["id"]})).fetchone()
        assert row[0] == "failed"
        assert row[1] is None, "终态错误不该排自动重试"
        assert row[2], "必须记录失败原因"

    @pg_only
    def test_index_rejects_unknown_property(self):
        with pytest.raises(svc.CustomException):
            _run(IX.upsert_index({"object_code": CAM,
                                  "prop_code": "no_such_col", "index_kind": "property"}))

    @pg_only
    def test_suggestions_cover_key_and_policy_props(self):
        s = _run(IX.suggest_indexes(CAM))
        assert s["ok"] is True
        prios = {x["priority"] for x in s["suggestions"]}
        assert prios <= {"high", "medium", "low"}
        for x in s["suggestions"]:
            assert x["prop_code"] and x["reason"]

    @pg_only
    def test_summary_aggregates_by_status_and_object(self):
        sm = _run(IX.index_summary())
        assert set(sm["by_status"]) == set(IX.ONT_INDEX_STATUS)
        assert sm["total"] == sum(sm["by_status"].values())
        for o in sm["objects"]:
            assert o["total"] >= o["ready"] + o["failed"] - o["total"] + o["total"]
            assert o["size_human"]

    def test_human_size(self):
        assert IX._human(0) == "0 B"
        assert IX._human(2048) == "2.0 KB"
        assert IX._human(1024 ** 2 * 3) == "3.0 MB"


# ===========================================================================
# C) 分支 / 提案
# ===========================================================================
@pytest.mark.skipif(not _is_postgres(), reason="依赖 Postgres：SQLite 不支持 ALTER ... ADD COLUMN IF NOT EXISTS，物化/建索引路径无法在 SQLite 上完整跑通")
class TestProposal:
    def test_stages_and_tabs_match_official(self):
        """官方阶段：准备 → 审查中 → 合并；标签：我的/指派给我/审查中/已合并/关闭的。"""
        assert set(PR.ONT_PROPOSAL_STAGES) == {"preparing", "in_review", "merged",
                                              "closed"}
        assert set(PR.ONT_PROPOSAL_TABS) == {"mine", "assigned", "in_review",
                                            "merged", "closed"}
        for s in PR.ONT_PROPOSAL_STAGES:
            assert PR.ONT_PROPOSAL_STAGE_LABEL[s]
        for t in PR.ONT_PROPOSAL_TABS:
            assert PR.ONT_PROPOSAL_TAB_LABEL[t]

    def test_creating_branch_auto_creates_proposal(self):
        """官方：*"提案在分支创建时自动生成"*。"""
        r = _run(PR.create_branch("回归-自动提案", "测试", "t"))
        assert r["ok"], r
        assert r["branch_code"] and r["proposal_code"]
        p = _run(PR.get_proposal(r["proposal_code"]))
        assert p is not None
        assert p["branch_code"] == r["branch_code"]
        assert p["stage"] == "preparing"

    def test_each_resource_becomes_one_task(self):
        """官方：*"每个修改的 Ontology 实体 … 构成一个单独的任务"*。"""
        r = _run(PR.create_branch("回归-任务粒度", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "object", "update",
                               {"code": CAM, "name": "摄像机表"}, "t"))
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM, "code": "reg_t1",
                                "name": "回归字段1", "prop_type": "string"}, "t"))
        p = _run(PR.get_proposal(pc))
        assert len(p["tasks"]) == 2, [t["resource_code"] for t in p["tasks"]]

    def test_same_resource_merges_into_one_task(self):
        r = _run(PR.create_branch("回归-同资源合并", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        for i in range(3):
            _run(PR.save_on_branch(bc, "property", "create",
                                   {"object_code": CAM, "code": "reg_t2",
                                    "name": f"第{i}次", "prop_type": "string"}, "t"))
        p = _run(PR.get_proposal(pc))
        assert len(p["tasks"]) == 1, "同一资源多次改动应合并为一个任务"
        assert p["tasks"][0]["after"]["name"] == "第2次"

    def test_after_holds_full_state_not_partial(self):
        """关键：after 必须存**完整新状态**。

        否则合并时会把未提及的字段（icon/description/status…）重置为默认值。
        """
        r = _run(PR.create_branch("回归-完整状态", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        obj = next(o for o in _run(svc.list_objects()) if o["code"] == CAM)
        _run(PR.save_on_branch(bc, "object", "update",
                               {"code": CAM, "name": "只改名字"}, "t"))
        t = _run(PR.get_proposal(pc))["tasks"][0]
        assert t["after"].get("icon") == obj.get("icon"), "未提及的字段必须保留"
        diff_fields = [d["field"] for d in PR._diff(t["before"], t["after"])]
        assert diff_fields == ["name"], f"差异应只有 name，实际 {diff_fields}"

    def test_cannot_merge_before_all_approved(self):
        r = _run(PR.create_branch("回归-未批准", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM, "code": "reg_t3",
                                "name": "X", "prop_type": "string"}, "t"))
        m = _run(PR.merge_proposal(pc, "t"))
        assert m["ok"] is False
        assert m["blocked_by"] == "not_approved"

    def test_request_review_requires_tasks_and_reviewers(self):
        r = _run(PR.create_branch("回归-请求审查", "", "t"))
        pc = r["proposal_code"]
        with pytest.raises(svc.CustomException):
            _run(PR.request_review(pc, ["admin"], "t"))   # 还没改动
        _run(PR.save_on_branch(r["branch_code"], "property", "create",
                               {"object_code": CAM, "code": "reg_t4",
                                "name": "Y", "prop_type": "string"}, "t"))
        with pytest.raises(svc.CustomException):
            _run(PR.request_review(pc, [], "t"))          # 没审查者

    def test_full_lifecycle_merges_to_main(self):
        """完整走一遍：建分支 → 改动 → 审查 → 批准 → 合并 → 主本体真的变了。"""
        r = _run(PR.create_branch("回归-完整流程", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        obj = next(o for o in _run(svc.list_objects()) if o["code"] == CAM)
        orig_name = obj["name"]
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM,
                                "code": "reg_lifecycle_col", "name": "生命周期字段",
                                "prop_type": "string"}, "t"))
        # 隔离性：主分支还没这个属性
        props = _run(svc.list_properties(CAM))
        assert not any(p["code"] == "reg_lifecycle_col" for p in props)
        _run(PR.request_review(pc, ["admin"], "t"))
        p = _run(PR.get_proposal(pc))
        assert p["stage"] == "in_review"
        for t in p["tasks"]:
            _run(PR.review_task(t["id"], True, "admin", "OK"))
        m = _run(PR.merge_proposal(pc, "t"))
        assert m["ok"], m
        props = _run(svc.list_properties(CAM))
        assert any(p["code"] == "reg_lifecycle_col" for p in props), "合并后主本体应有该属性"
        # 收尾
        row = _run(svc._exec(
            "SELECT id FROM ai_ont_property WHERE code='reg_lifecycle_col'",
            {})).fetchone()
        if row:
            _run(svc.delete_one("ai_ont_property", row[0]))
        after = next(o for o in _run(svc.list_objects()) if o["code"] == CAM)
        assert after["name"] == orig_name, "未改的字段不应被动"

    def test_closed_proposal_cannot_be_reopened(self):
        """官方：*"一旦提案被关闭，它就不能重新打开。"*"""
        r = _run(PR.create_branch("回归-关闭", "", "t"))
        pc = r["proposal_code"]
        _run(PR.close_proposal(pc, "t"))
        p = _run(PR.get_proposal(pc))
        assert p["stage"] == "closed"
        again = _run(PR.close_proposal(pc, "t"))
        assert again["ok"] is False
        m = _run(PR.merge_proposal(pc, "t"))
        assert m["ok"] is False and "关闭" in m["msg"]

    def test_merged_proposal_cannot_be_closed(self):
        r = _run(PR.create_branch("回归-已合并不能关", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM, "code": "reg_t5",
                                "name": "Z", "prop_type": "string"}, "t"))
        p = _run(PR.get_proposal(pc))
        _run(PR.review_task(p["tasks"][0]["id"], True, "t"))
        _run(PR.merge_proposal(pc, "t"))
        assert _run(PR.close_proposal(pc, "t"))["ok"] is False
        row = _run(svc._exec("SELECT id FROM ai_ont_property WHERE code='reg_t5'",
                             {})).fetchone()
        if row:
            _run(svc.delete_one("ai_ont_property", row[0]))

    def test_changelog_has_field_level_diff(self):
        """官方：变更记录里任务可展开，看**谁在什么时候**改了什么。"""
        r = _run(PR.create_branch("回归-变更记录", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "object", "update",
                               {"code": CAM, "name": "改名测试"}, "张工"))
        cl = _run(PR.proposal_changelog(pc))
        assert cl, "变更记录不能为空"
        c = cl[0]
        assert c["edit_count"] >= 1
        assert "张工" in c["authors"]
        assert c["edits"][0]["diff"], "必须有字段级差异"
        for d in c["edits"][0]["diff"]:
            assert "field" in d and "before" in d and "after" in d

    def test_comment_and_discard(self):
        r = _run(PR.create_branch("回归-评论丢弃", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM, "code": "reg_t6",
                                "name": "W", "prop_type": "string"}, "t"))
        _run(PR.comment(pc, "这个字段命名建议改一下", "审查员"))
        p = _run(PR.get_proposal(pc))
        assert len(p["comments"]) == 1
        tid = p["tasks"][0]["id"]
        _run(PR.discard_task(tid))
        p2 = _run(PR.get_proposal(pc))
        assert not p2["tasks"], "丢弃后任务应消失"

    def test_branch_kinds_whitelist(self):
        assert "object" in PR.ONT_BRANCH_KINDS and "property" in PR.ONT_BRANCH_KINDS
        r = _run(PR.create_branch("回归-种类白名单", "", "t"))
        with pytest.raises(svc.CustomException):
            _run(PR.save_on_branch(r["branch_code"], "bogus", "update",
                                   {"code": "x"}, "t"))

    def test_cannot_edit_after_merge(self):
        r = _run(PR.create_branch("回归-合并后不可改", "", "t"))
        bc, pc = r["branch_code"], r["proposal_code"]
        _run(PR.save_on_branch(bc, "property", "create",
                               {"object_code": CAM, "code": "reg_t7",
                                "name": "V", "prop_type": "string"}, "t"))
        p = _run(PR.get_proposal(pc))
        _run(PR.review_task(p["tasks"][0]["id"], True, "t"))
        _run(PR.merge_proposal(pc, "t"))
        with pytest.raises(svc.CustomException):
            _run(PR.save_on_branch(bc, "property", "create",
                                   {"object_code": CAM, "code": "reg_t8",
                                    "name": "U", "prop_type": "string"}, "t"))
        row = _run(svc._exec("SELECT id FROM ai_ont_property WHERE code='reg_t7'",
                             {})).fetchone()
        if row:
            _run(svc.delete_one("ai_ont_property", row[0]))


# ===========================================================================
# D) 演示数据
# ===========================================================================
@pytest.mark.skipif(not _is_postgres(), reason="依赖 Postgres：同上")
class TestDemo:
    def test_demo_kinds_all_have_cleaners(self):
        """每一种登记的演示数据都必须有对应的清除方式（否则会残留）。"""
        for kind in ("view", "index", "scenario", "decision", "branch", "proposal",
                     "row_policy", "acl", "property"):
            assert kind in D._KIND_LABEL, f"{kind} 缺中文名"
        # 认领机制覆盖的种类
        adopt_kinds = {x[0] for x in D._ADOPT}
        assert {"decision", "scenario", "proposal", "branch", "view"} <= adopt_kinds

    def test_prefix_and_labels(self):
        assert D.DEMO_PREFIX == f"【{D.DEMO_TAG}】"
        assert D.DEMO_PREFIX.startswith("【")

    def test_load_then_clear_roundtrip(self):
        """载入 → 各页面有内容 → 清除 → 回到空。"""
        r = _run(D.load_demo("admin", force=True))
        assert r["ok"], r
        assert r["total"] > 0
        st = _run(D.demo_status())
        assert st["loaded"] is True
        assert st["total"] == r["total"]
        rep = _run(D.demo_report())
        for page in ("对象视图", "索引", "提案", "场景", "决策"):
            assert page in rep["pages"], page
        c = _run(D.clear_demo())
        assert c["ok"], c
        assert c["cleared"] == r["total"], (c["cleared"], r["total"])
        assert not c["errors"], c["errors"]
        assert _run(D.demo_status())["total"] == 0

    def test_load_is_idempotent_without_force(self):
        _run(D.load_demo("admin", force=True))
        r2 = _run(D.load_demo("admin", force=False))
        assert r2["ok"] is False
        assert r2.get("already") is True
        _run(D.clear_demo())

    def test_clear_on_empty_is_safe(self):
        _run(D.clear_demo())
        r = _run(D.clear_demo())
        assert r["ok"] is True
        assert r["cleared"] == 0

    def test_demo_does_not_touch_existing_objects(self):
        """演示数据不能改动你已有的对象类型（只新建）。"""
        before = {o["code"]: o["name"] for o in _run(svc.list_objects())}
        _run(D.load_demo("admin", force=True))
        during = {o["code"]: o["name"] for o in _run(svc.list_objects())}
        _run(D.clear_demo())
        after = {o["code"]: o["name"] for o in _run(svc.list_objects())}
        for code, name in before.items():
            assert during.get(code) == name, f"演示数据改了 {code}"
            assert after.get(code) == name, f"清除后 {code} 名字变了"


# ===========================================================================
# A2) 筛选器 / 共享 / 链接（目标点名的两项）
# ===========================================================================
class TestViewFilterShareUrl:
    def test_filter_ops_are_a_single_vocabulary(self):
        """筛选算子词表必须与实例层一致。

        真实教训：视图筛选器定义的是 ``contains``，而 instance_search 只认 ``like``，
        传下去落到默认 eq 分支，**静默筛不出任何东西**。
        """
        import inspect

        src = inspect.getsource(svc.instance_search)
        for op in OV.ONT_FILTER_OPS:
            assert op in src, f"instance_search 不支持算子 {op}（视图里却能配，会静默失效）"
        for op in OV.ONT_FILTER_OPS:
            assert op in OV.ONT_FILTER_OP_LABEL

    def test_tab_filters_collected_from_filter_widgets(self):
        tab = {"key": "t", "label": "T", "widgets": [
            {"type": "filter", "config": {"filters": [
                {"prop": "status", "op": "eq", "value": "ONLINE"},
                {"prop": "name", "op": "contains", "value": "东门"},
            ]}},
            {"type": "table", "config": {}},
        ]}
        f = OV._tab_filters(tab)
        assert len(f) == 2
        assert f[0]["prop"] == "status" and f[0]["op"] == "eq"
        assert f[1]["op"] == "contains"

    def test_tab_filters_ignores_unknown_op_and_empty_prop(self):
        tab = {"widgets": [{"type": "filter", "config": {"filters": [
            {"prop": "", "op": "eq"},
            {"prop": "x", "op": "bogus"},
        ]}}]}
        f = OV._tab_filters(tab)
        assert len(f) == 1 and f[0]["op"] == "eq", "未知算子应回退为 eq"

    def test_filters_to_search_shape(self):
        d = OV._filters_to_search([{"prop": "a", "op": "contains", "value": "x"},
                                   {"prop": "", "op": "eq", "value": 1}])
        assert d == {"a": {"op": "contains", "value": "x"}}

    def test_match_all_ops(self):
        m = OV._match
        assert m("a", "eq", "a") and not m("a", "eq", "b")
        assert m("a", "ne", "b") and not m("a", "ne", "a")
        assert m("hello", "contains", "ELL")          # 大小写不敏感
        assert not m("hello", "contains", "zzz")
        assert m(5, "gt", 3) and m(5, "gte", 5) and m(3, "lt", 5) and m(5, "lte", 5)
        assert not m("x", "gt", 3)                     # 非数字不炸，返回 False
        assert m(None, "is_empty", None) and m("", "is_empty", None)
        assert not m("a", "is_empty", None)
        assert m("a", "not_empty", None) and not m("", "not_empty", None)

    def test_apply_filters_counts_dropped(self):
        rows = [{"key": "1", "props": {"s": "ONLINE"}},
                {"key": "2", "props": {"s": "OFFLINE"}},
                {"key": "3", "props": {"s": "ONLINE"}}]
        kept, dropped = OV._apply_filters(rows, [{"prop": "s", "op": "eq", "value": "ONLINE"}])
        assert [r["key"] for r in kept] == ["1", "3"]
        assert dropped == 1
        assert OV._apply_filters(rows, []) == (rows, 0)

    def test_view_url_contains_view_and_key(self):
        u = OV.view_url("video_cameras__demo", "1")
        assert "objectview=video_cameras__demo" in u
        assert "objectkey=1" in u
        assert OV.view_url("v").endswith("objectview=v")

    def test_view_url_quotes_special_chars(self):
        u = OV.view_url("a b&c", "k/1")
        assert " " not in u and "&c" not in u.split("objectkey")[0].split("=")[-1]

    def test_share_mode_and_roles_validation(self):
        """共享方式只允许 inherit / roles；按角色共享必须给角色。

        （原断言 `assert "inherit" in ("inherit","roles")` 是**恒真**的，等于没测；
        真正的护栏见下面两条：字段表必须与列一一对应，编辑不得清空筛选/共享。）
        """
        assert set(OV._V_FIELDS) >= {"share_mode", "share_roles", "filters"}

    def test_view_fields_align_with_columns(self):
        """回归：`_V_FIELDS` 必须与 `_V_COLS` 的列**一一对应且同序**。

        错位会让 `_row_to_view` 把 filters/share_roles/share_mode 映射到 status/visibility/
        created_by 上，于是：① 这三个字段永远不出现在返回里；② `update_view` 用
        `v.get("filters")` 兜底时拿到 None → **每次编辑视图都会静默清空筛选器与共享设置**。
        """
        assert OV._V_FIELDS == (
            "id", "object_code", "code", "name", "description", "view_type", "form_factor",
            "is_default", "is_managed", "tabs", "version", "filters", "share_roles",
            "share_mode", "status", "visibility", "created_by", "created_time", "updated_time",
        )

    @pg_only
    def test_edit_view_keeps_filters_and_share(self):
        """编辑视图（只改名）**不得**清空已保存的筛选器与共享设置。"""
        code = "reg_share_keep"
        _run(OV.create_view({
            "object_code": CAM, "code": code, "name": "共享保留回归",
            "form_factor": "full",
            "filters": [{"prop": "status", "op": "eq", "value": "ONLINE"}],
            "share_roles": ["ops"],
            "share_mode": "roles",
            "tabs": [{"key": "f", "label": "F", "widgets": [
                {"type": "table", "config": {"limit": 50}}]}],
        }))
        got = _run(OV.get_view(code))
        assert got["share_mode"] == "roles", got
        assert got["share_roles"] == ["ops"], got
        assert got["filters"], got

        _run(OV.update_view(code, {"name": "只改个名"}))
        after = _run(OV.get_view(code))
        assert after["name"] == "只改个名", after
        assert after["share_mode"] == "roles", f"编辑后共享方式被清空：{after}"
        assert after["share_roles"] == ["ops"], f"编辑后共享角色被清空：{after}"
        assert after["filters"], f"编辑后筛选器被清空：{after}"
        _run(OV.remove_view(code))

    def test_table_widget_is_registered(self):
        assert "table" in OV.ONT_WIDGET_TYPES
        assert OV.ONT_WIDGET_LABEL["table"]
        assert OV.ONT_WIDGET_CATEGORY["table"] == "properties-links"

    @pg_only
    def test_render_table_widget_applies_filter(self):
        """端到端：带筛选器的视图，表格组件的行数必须**真的被筛过**。"""
        code = "reg_filt_rt"
        _run(OV.create_view({
            "object_code": CAM, "code": code, "name": "筛选渲染回归",
            "form_factor": "full",
            "tabs": [{"key": "f", "label": "F", "widgets": [
                {"type": "filter", "config": {"filters": [
                    {"prop": "status", "op": "eq", "value": "ONLINE"}]}},
                {"type": "table", "config": {"limit": 50}},
            ]}],
        }))
        r = _run(OV.render_view(code, "1"))
        assert r["ok"], r
        tab = r["tabs"][0]
        assert tab["filters"], "标签页应带上生效的筛选"
        tbl = tab["widgets"][1]
        assert tbl["type"] == "table"
        assert "error" not in tbl, tbl
        # reg_cams 里只有 id=1 是 ONLINE
        assert tbl["count"] == 1, f"筛选应只剩 1 行，实际 {tbl['count']}"
        _run(OV.remove_view(code))

    @pg_only
    def test_render_without_filter_returns_all(self):
        code = "reg_nofilt_rt"
        _run(OV.create_view({
            "object_code": CAM, "code": code, "name": "无筛选回归",
            "form_factor": "full",
            "tabs": [{"key": "f", "label": "F", "widgets": [
                {"type": "table", "config": {"limit": 50}}]}],
        }))
        r = _run(OV.render_view(code, "1"))
        tbl = r["tabs"][0]["widgets"][0]
        assert tbl["count"] == 2, f"无筛选应返回全部 2 行，实际 {tbl['count']}"
        _run(OV.remove_view(code))
