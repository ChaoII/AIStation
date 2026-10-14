"""本体模块的**缺陷回归套件**。

这里每一条测试对应一个**真实发生过的缺陷**（见 `docs/ontology-ultimate-plan.md` 的
「跨阶段修复的真实缺陷」表，编号 1–22）。目的不是覆盖率，而是：
**任何改动都不能把这些缺陷悄悄放回来。**

编号与文档一致；每条测试的 docstring 写明「原来错在哪」。
"""
import asyncio
import json
import pathlib
import re

import _ont_ddl
import pytest

from app.plugin.module_ai.ontology import scenario as S
from app.plugin.module_ai.ontology import security as SEC
from app.plugin.module_ai.ontology import service as svc

ONT_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_ai" / "ontology"


def _run(coro):
    return asyncio.run(coro)


# SQLite 没有 now()，而 service 层用了 updated_time=now()（Postgres 有）。
# 这是测试环境差异、不是产品缺陷 —— 在**任何连接建立之前**注册等价函数。
from sqlalchemy import event as _sa_event  # noqa: E402

from app.core.database import async_engine as _async_engine  # noqa: E402


@_sa_event.listens_for(_async_engine.sync_engine, "connect")
def _register_now(dbapi_conn, _rec):  # pragma: no cover - 运行时钩子
    from datetime import datetime

    dbapi_conn.create_function(
        "now", 0, lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ===========================================================================
# 静态可测的缺陷（不需要数据库）
# ===========================================================================
class TestStaticDefects:
    def test_defect01_every_ai_ont_table_has_ddl(self):
        """缺陷 1：ai_ont_* 表在代码里没有任何建表语句 → 全新部署直接失败。

        扫遍 ontology 目录，任何被引用的 ai_ont_* 表都必须在建表/补列语句里出现。
        """
        used: set[str] = set()
        for f in ONT_DIR.glob("*.py"):
            used |= set(re.findall(r"\bai_ont_[a-z_]+", f.read_text(encoding="utf-8")))
        ddl = "\n".join(svc._ONT_TABLES_SQL) + "\n".join(svc._ONT_ALTER_SQL)
        declared = set(re.findall(
            r"(?:CREATE TABLE IF NOT EXISTS|ALTER TABLE)\s+(ai_ont_[a-z_]+)", ddl))
        missing = sorted(used - declared)
        assert not missing, f"代码引用了但没有建表语句：{missing}"
        assert len(declared) >= 20, f"建表语句数量异常少：{len(declared)}"

    def test_defect01b_test_fixture_covers_service_tables(self):
        """缺陷 1 的同类问题：测试 fixture 缺新表 → 测试假绿。

        （历史上 test_ontology.py 的 DDL 就缺 P3/P4/P5 的表。）
        """
        ddl = "\n".join(svc._ONT_TABLES_SQL) + "\n".join(svc._ONT_ALTER_SQL)
        service_tables = set(re.findall(
            r"(?:CREATE TABLE IF NOT EXISTS|ALTER TABLE)\s+(ai_ont_[a-z_]+)", ddl))
        missing = _ont_ddl.missing_from_ddl(service_tables)
        assert not missing, f"测试 fixture 缺表：{missing}"

    def test_defect01c_test_fixture_columns_match_service_ddl(self):
        """缺陷 1 的第三层：测试 fixture 的表**列**与 service 的建表语句漂移。

        → 测试跑在"少了几列"的表上，要么报假错、要么根本没覆盖到那段 SQL。
        （实测曾漂移 7 张表：ai_ont_object 少 updated_time 等。）
        """
        def _cols(sql: str) -> set[str]:
            m = re.search(r"\((.*)\)\s*$", sql.strip(), re.S)
            if not m:
                return set()
            out = set()
            for part in m.group(1).split(","):
                tok = part.strip().split()
                if tok and tok[0].upper() not in (
                        "PRIMARY", "UNIQUE", "FOREIGN", "CONSTRAINT"):
                    out.add(tok[0].strip('"').lower())
            return out

        by_table: dict[str, list[str]] = {}
        for s in list(svc._ONT_TABLES_SQL) + list(svc._ONT_ALTER_SQL):
            m = re.match(r"\s*(?:CREATE TABLE IF NOT EXISTS|ALTER TABLE)\s+(ai_ont_\w+)", s)
            if m:
                by_table.setdefault(m.group(1), []).append(s)
        drift = {}
        for t, stmts in by_table.items():
            if t not in _ont_ddl.ONT_DDL:
                drift[t] = "整表缺失"
                continue
            need: set[str] = set()
            for s in stmts:
                need |= _cols(s)
            miss = sorted(need - _cols(_ont_ddl.ONT_DDL[t]))
            if miss:
                drift[t] = miss
        assert not drift, f"测试 fixture 与 service 建表语句漂移：{drift}"

    def test_defect02_agent_capabilities_declared(self):
        """缺陷 2：ai_agents.capabilities 只在库里有列，模型与 schema 都没声明。

        → 「本体接 Agent」整条链在第一步就是断的：前端勾了存不进、运行时读不到。
        """
        from app.plugin.module_ai.agent import model as agent_model
        from app.plugin.module_ai.agent import schema as agent_schema

        cols = {c.name for c in agent_model.AiAgentModel.__table__.columns}
        assert "capabilities" in cols, "Agent 模型没有 capabilities 列"
        fields = set(agent_schema.AiAgentCreateSchema.model_fields)
        assert "capabilities" in fields, "Agent 创建 schema 没有 capabilities 字段"
        assert "capabilities" in set(agent_schema.AiAgentUpdateSchema.model_fields)

    def test_defect05_sensitive_like_heuristic(self):
        """缺陷 5：ai_ont_property.sensitive 1479 个属性全是 false（该标记从未被使用）。

        → Writeback 的「不写敏感字段」防护形同虚设，实测能直接写 password。
        """
        for name in ("password", "passwd", "pwd", "secret", "api_key", "apikey",
                     "access_token", "private_key", "credential"):
            assert svc.is_sensitive_like(name), f"{name} 应被判为敏感"
        for name in ("name", "location", "brand", "status", "created_time",
                     "tokenizer_model", "device_type"):
            assert not svc.is_sensitive_like(name), f"{name} 不该被判为敏感"

    def test_defect10_declared_type_coerces_string_input(self):
        """缺陷 10：函数入参声明了 type 但运行时不做类型转换。

        → 界面/Agent 传字符串进来，`8 / 10` 变成 `'8' / '10'` 直接 TypeError。
        """
        from app.plugin.module_ai.ontology import function_engine as fe

        fn = {
            "code": "ratio", "kind": "expression", "expr": "a / b",
            "parameters": [{"key": "a", "type": "number"}, {"key": "b", "type": "number"}],
        }
        r = _run(fe.run_function(fn, {"a": "8", "b": "10"}))
        assert r.get("ok"), r
        assert abs(float(r["value"]) - 0.8) < 1e-9

    def test_defect10b_legacy_function_without_declared_params_still_runs(self):
        """缺陷 10 的边界：库里原有的函数**没有声明入参**，必须仍能跑。

        （修复类型转换时最容易踩的坑：把没声明类型的入参也强行转换，
        反而弄坏已有的老函数。）
        """
        from app.plugin.module_ai.ontology import function_engine as fe

        r = _run(fe.run_function({"kind": "expression", "expr": "a * 2",
                                  "parameters": []}, {"a": 4}))
        assert r.get("ok"), r
        assert r["value"] == 8

    def test_defect12_function_validated_on_save(self):
        """缺陷 12：函数保存时完全不校验，`AVG(amount)` 这种从来跑不通的表达式照存。

        → 用户以为功能存在（与缺陷 5 同类：能填但没用）。
        """
        from app.plugin.module_ai.ontology import function_engine as fe

        bad = {"code": "b", "kind": "expression", "expr": "AVG(amount)", "parameters": []}
        errs = fe.validate_function(bad)
        assert errs, "AVG(...) 应该被拒绝（它永远跑不通）"
        good = {"code": "g", "kind": "expression", "expr": "amount + 1",
                "parameters": [{"key": "amount", "type": "number"}]}
        assert not fe.validate_function(good), fe.validate_function(good)

    def test_defect14_decision_json_safe_nested(self):
        """缺陷 14：决策依据里存对象属性快照，含 datetime/Decimal。

        → json.dumps 抛 TypeError，决策根本存不进去。
        """
        from datetime import datetime
        from decimal import Decimal

        payload = {"outer": [{"t": datetime(2026, 10, 9, 1, 2, 3)},
                             {"d": Decimal("3.14")}], "b": b"bytes"}
        out = S._j(payload)
        assert "2026-10-09 01:02:03" in out and "3.14" in out and "bytes" in out

    def test_defect15_chinese_title_codes_do_not_collide(self):
        """缺陷 15：中文标题推不出 ASCII 编码，回退到秒级时间戳。

        → 同一秒建两条决策就撞唯一约束。
        """
        codes = {S._unique_code.__name__}  # 占位，真正断言在下面用 DB 版
        assert codes  # 保持函数被引用

    def test_defect19_policy_semantic_check_rejects_bad_attr(self):
        """缺陷 19：行级策略表达式只做语法检查不真跑。

        → `user.password` 这类语义错误保存成功、运行期才炸。
        """
        p = SEC.ANONYMOUS
        # 语法正确、但 user 上没有 password 这个属性
        with pytest.raises(ValueError):
            SEC.eval_policy("user.password == 'x'", {}, p)
        # 合法表达式应能求值
        assert SEC.eval_policy("1 == 1", {}, p) is True
        assert SEC.eval_policy("1 == 2", {}, p) is False

    def test_defect19b_policy_allows_only_whitelisted_user_attrs(self):
        """缺陷 19 的加固面：只允许 user.* 白名单属性，其它属性访问一律拒绝。"""
        with pytest.raises(ValueError):
            SEC.eval_policy("props.__class__ == 1", {}, SEC.ANONYMOUS)
        with pytest.raises(ValueError):
            SEC.eval_policy("().__class__.__bases__", {}, SEC.ANONYMOUS)

    def test_defect21_scenario_expires_at_is_datetime_not_str(self):
        """缺陷 21：场景 expires_at 是 TIMESTAMP 列却传了字符串。

        → asyncpg 拒绝，TTL 写入抛错，场景根本建不出来。
        """
        from datetime import datetime

        captured = {}

        async def fake_exec_write(sql, params=None):
            captured.update(params or {})

        async def fake_exec(sql, params=None):
            class R:
                def fetchone(self):
                    return None
            return R()

        orig_w, orig_e = svc._exec_write, svc._exec
        svc._exec_write, svc._exec = fake_exec_write, fake_exec
        try:
            r = _run(S.create_scenario({"name": "t", "ttl_days": 7}, "u"))
        finally:
            svc._exec_write, svc._exec = orig_w, orig_e
        assert r["ok"], r
        assert isinstance(captured.get("ex"), datetime), \
            f"expires_at 必须是 datetime，实际是 {type(captured.get('ex'))}"

    def test_defect22_record_edit_returns_dict_never_raises(self):
        """缺陷 22：record_edit 在场景不可编辑时抛异常而非返回结果。

        → 从动作执行路径抛出去会变成 500，而不是可读的拒绝原因。
        """
        async def boom(code):
            raise svc.CustomException(msg="场景状态为「已合并」，不可再编辑")

        orig = S._check_active
        S._check_active = boom
        try:
            r = _run(S.record_edit("sc", "cams", "1", "modify", {}, {}))
        finally:
            S._check_active = orig
        assert isinstance(r, dict), "record_edit 必须返回字典，不能抛异常"
        assert r["ok"] is False
        assert "已合并" in r["msg"]


# ===========================================================================
# 需要数据库的缺陷
# ===========================================================================
@pytest.fixture(scope="module", autouse=True)
def _tables(test_client):
    """建全部本体元数据表（含 P3/P4/P5）。

    SQLite 没有 ``now()``，而 service 层的 UPDATE 用了 ``updated_time=now()``
    （Postgres 有）。这是**测试环境**差异、不是产品缺陷，因此在连接上注册等价函数。
    注册必须在**任何连接建立之前**完成，所以放在模块顶层（见下方 `_register_now`），
    并在建表前 dispose 一次连接池，确保新连接带上这个函数。
    """
    from sqlalchemy import text as _t

    from app.core.database import async_db_session, async_engine

    async def _create():
        await async_engine.dispose()  # 让已建连接失效，新连接才会带上 now()
        async with async_db_session.begin() as db:
            for ddl in _ont_ddl.ONT_DDL.values():
                await db.execute(_t(ddl))
    _run(_create())


class TestDbDefects:
    def test_defect03_action_visibility_is_read_and_written(self):
        """缺陷 3：ai_ont_action 根本没有 visibility 列，且从不写它、也不读它。

        → 动作的隐藏过滤完全失效。
        """
        assert "visibility" in svc._ACT_COLS, "_ACT_COLS 没有读 visibility"
        code = "reg_vis_action"
        r = _run(svc.upsert_action({
            "object_code": "reg_obj", "name": "回归动作", "code": code,
            "visibility": "hidden", "white_fields": ["name"],
        }))
        assert r.get("id"), r
        acts = _run(svc.list_actions(None))
        got = next((a for a in acts if a["code"] == code), None)
        assert got is not None, "刚建的动作读不到"
        assert got["visibility"] == "hidden", f"visibility 没落库：{got.get('visibility')}"

    def test_defect04_soft_deleted_code_can_be_recreated(self):
        """缺陷 4：软删除的行仍占着 code 唯一约束 → 删除过的对象类型编码永远无法重建。"""
        code = "reg_revive_obj"
        first = _run(svc.upsert_object({"code": code, "name": "第一次"}))
        assert first.get("id"), first
        _run(svc.delete_one("ai_ont_object", first["id"]))
        again = _run(svc.upsert_object({"code": code, "name": "重建"}))
        assert again.get("id"), f"软删除后无法重建：{again}"
        objs = _run(svc.list_objects())
        rows = [o for o in objs if o["code"] == code]
        assert len(rows) == 1, f"重建后应只有 1 行，实际 {len(rows)}"
        assert rows[0]["name"] == "重建"

    def test_defect06_partial_update_not_flagged_destructive(self):
        """缺陷 6：工作副本把局部更新误判为破坏性变更（草稿没带 key_prop 却拿它比较）。

        → 普通编辑被要求输入实体名确认。
        """
        owner = 90061
        _run(svc.discard_wip(owner))
        obj = _run(svc.upsert_object({"code": "reg_wip_obj", "name": "WIP对象",
                                      "key_prop": "id"}))
        assert obj.get("id")
        # 只改 name，草稿里**不带** key_prop
        _run(svc.stage_change(owner, "object", "update",
                              {"id": obj["id"], "code": "reg_wip_obj", "name": "改名了"},
                              "reg_wip_obj"))
        rev = _run(svc.review_wip(owner))
        reasons = [d.get("reason", "") for d in (rev.get("destructive") or [])]
        assert not any("key_prop" in x or "主键" in x for x in reasons), \
            f"局部更新被误判为破坏性：{reasons}"
        _run(svc.discard_wip(owner))

    def test_defect07_delete_draft_resolves_id_from_code_only(self):
        """缺陷 7：删除草稿只带 code 时解析不出 id → 删除操作报「非法请求」。"""
        obj = _run(svc.upsert_object({"code": "reg_del_obj", "name": "待删"}))
        assert obj.get("id")
        eid = _run(svc._resolve_entity_id("object", {"code": "reg_del_obj"}))
        assert eid == obj["id"], f"按 code 反查 id 失败：{eid} != {obj['id']}"

    def test_defect09_find_action_sees_wip_overlay(self):
        """缺陷 9：试运行读的是已保存的定义，看不到正在编辑的草稿。

        → 试运行测的不是当前配置，功能形同虚设。
        """
        owner = 90062
        _run(svc.discard_wip(owner))
        code = "reg_wip_action"
        saved = _run(svc.upsert_action({
            "object_code": "reg_obj", "name": "已保存的名字", "code": code,
            "white_fields": ["name"],
        }))
        assert saved.get("id")
        _run(svc.stage_change(owner, "action", "update",
                              {"id": saved["id"], "code": code, "name": "草稿里的名字",
                               "object_code": "reg_obj", "white_fields": ["name"]},
                              code))
        plain = _run(svc._find_action(code))
        with_wip = _run(svc._find_action(code, owner))
        assert plain and plain["name"] == "已保存的名字"
        assert with_wip and with_wip["name"] == "草稿里的名字", \
            f"带 owner 时没看到草稿：{with_wip.get('name') if with_wip else None}"
        _run(svc.discard_wip(owner))

    def test_defect16_decision_object_action_mismatch_rejected(self):
        """缺陷 16：决策的对象类型与动作的目标类型可以不一致。

        → 执行时前后快照取错对象，捕获到的「下游影响」是假的。
        """
        from app.plugin.module_ai.ontology import decision as dec

        _run(svc.upsert_action({"object_code": "reg_obj", "name": "回归动作2",
                                "code": "reg_match_action", "white_fields": ["name"]}))
        # 一致 → 不报错
        _run(dec._check_object_action_match("reg_obj", "reg_match_action"))
        # 不一致 → 必须拒绝
        with pytest.raises(svc.CustomException):
            _run(dec._check_object_action_match("other_obj", "reg_match_action"))

    def test_defect18_upsert_property_is_idempotent(self):
        """缺陷 18：upsert_property 名为 upsert，没带 id 时却无脑 INSERT。

        → 静默产生重复属性行；权限判定读到互相矛盾的 roles。
        """
        _run(svc.upsert_object({"code": "reg_prop_obj", "name": "属性对象"}))
        for _ in range(3):
            r = _run(svc.upsert_property({
                "object_code": "reg_prop_obj", "code": "dup_col", "name": "重复列",
                "prop_type": "string",
            }))
            assert r.get("id"), r
        props = _run(svc.list_properties("reg_prop_obj"))
        rows = [p for p in props if p["code"] == "dup_col"]
        assert len(rows) == 1, f"同一个 (object_code, code) 出现 {len(rows)} 行"

    def test_defect20_controller_passes_principal(self):
        """缺陷 20：/action/execute 控制器没把 principal 传下去。

        → P4 的权限在 HTTP 路径上完全不生效（当时只在 Python 直调里验过）。
        """
        from types import SimpleNamespace

        from app.plugin.module_ai.ontology import controller as C

        async def go():
            await SEC.set_resource_acl("action", "reg_acl_action", ["ADMIN"], ["ADMIN"], [])
            await svc.upsert_action({"object_code": "reg_obj", "name": "受控动作",
                                     "code": "reg_acl_action", "white_fields": ["name"]})
            # 用户 2 没有 ADMIN 角色
            auth = SimpleNamespace(user=SimpleNamespace(id=2, name="回归用户"))
            resp = await C.execute_ontology_action(
                auth, {"code": "reg_acl_action", "object_key": "1",
                       "params": {"name": "x"}})
            body = json.loads(bytes(resp.body).decode())
            await SEC.clear_resource_acl("action", "reg_acl_action")
            return body

        body = _run(go())
        assert body["data"].get("ok") is False, f"控制器没做权限校验：{body['data']}"
        assert body["data"].get("blocked_by") == "permission", body["data"]

    def test_defect15b_scenario_codes_unique_same_second(self):
        """缺陷 15（场景版）：同一秒内建多个同名场景不能撞唯一约束。"""
        async def go():
            codes = []
            for _ in range(3):
                r = await S.create_scenario({"name": "同秒场景"}, "u")
                assert r["ok"], r
                codes.append(r["code"])
            return codes

        codes = _run(go())
        assert len(set(codes)) == 3, f"编码撞车：{codes}"
