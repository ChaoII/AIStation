"""本体 P1 数据正确性回归（2026-10-19 本体审查后修复）。

1. 重复物化：第二次物化把物化表自己读出来再插回去，行数翻倍
2. upsert_link / upsert_function / upsert_action 无 id 一律 INSERT ⇒
   回滚 / 导入 / 提案合并会累加重复活行；而执行时取第一条（旧行）⇒
   改了白名单/审批配置不生效，安全配置被"幽灵旧行"遮蔽
3. 多编辑动作逐条独立事务：第 1 条已提交、第 2 条失败不回滚
4. Agent 通用工具 run_ontology_function 缺 ACL/可见性检查（Agent 成为绕过本体
   资源权限的后门），与同文件的 list_ontology / propose_ontology_action 口径不一致
"""
import asyncio

import _ont_ddl  # noqa: F401  确保测试库表结构就位
import pytest

from app.plugin.module_ai.ontology import service as svc


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _tables(test_client):  # noqa: ARG001  依赖 conftest 的应用/库夹具
    """建全部本体元数据表（与 test_ontology_regressions 同口径）。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session, async_engine

    async def _create():
        await async_engine.dispose()
        async with async_db_session.begin() as db:
            for ddl in _ont_ddl.ONT_DDL.values():
                await db.execute(_t(ddl))

    _run(_create())


# ===========================================================================
# 1) 重复物化不得把数据翻倍
# ===========================================================================
def test_materialize_refuses_to_rematerialize():
    """已物化的对象再次物化必须被拒绝。

    修前：``src = src_table or code``，而第一次物化后 ``backing_table='ont_{code}'``
    ⇒ 源表就是物化表自己，``SELECT 自己 → INSERT 自己``，行数每次翻倍，
    基于该对象的实例/聚合/派生/决策快照全部失真。

    这里直接验证守卫行为：已物化对象调用物化必须返回"无需重复物化"且不落任何写入。
    """
    async def _scenario():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        code, tbl = "p1_mat_obj", "ont_p1_mat_obj"
        async with async_db_session.begin() as db:
            await db.execute(_t(f"DROP TABLE IF EXISTS {tbl}"))
            await db.execute(_t(
                "DELETE FROM ai_ont_property WHERE object_code=:c"), {"c": code})
            await db.execute(_t(
                "DELETE FROM ai_ont_object WHERE code=:c"), {"c": code})
            # 模拟"已经物化过"：支撑表已绑定为物化表自己
            await db.execute(_t(
                "INSERT INTO ai_ont_object(code,name,plural_name,api_name,key_prop,"
                "name_prop,backing_table,datasource_id,status) "
                "VALUES(:c,'P1物化对象','P1物化对象','P1MatObj','id','name',:bt,NULL,'active')"),
                {"c": code, "bt": tbl})
            await db.execute(_t(
                "INSERT INTO ai_ont_property(object_code,name,code,prop_type) "
                "VALUES(:o,:n,:c,:t)"), {"o": code, "n": "名称", "c": "name", "t": "string"})

        r = await svc.materialize_object(code)
        async with async_db_session() as db:
            exists = (await db.execute(_t(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": tbl})).scalar()
        return r, int(exists or 0)

    r, exists = _run(_scenario())
    assert r.get("ok") is False, f"已物化对象不该再次物化：{r}"
    assert "无需重复物化" in str(r.get("msg", "")), f"拒绝理由不明确：{r}"
    assert exists == 0, f"被拒绝的物化仍创建了表：{r}"

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_property WHERE object_code=:c"),
                             {"c": "p1_mat_obj"})
            await db.execute(_t("DELETE FROM ai_ont_object WHERE code=:c"),
                             {"c": "p1_mat_obj"})

    _run(_cleanup())


# ===========================================================================
# 2) upsert 去重
# ===========================================================================
def test_upsert_action_dedupes_by_code():
    """同 code 重复保存必须更新，不得新造活行。

    修前：回滚/导入/提案合并都用"无 id 的完整字典"重放 ⇒ 每次都 INSERT；
    而 ``_find_action`` 取 ``ORDER BY id`` 的第一条（旧行）⇒
    改了白名单/审批配置却不生效，安全配置被幽灵旧行遮蔽。
    """
    async def _scenario():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        code = "p1_dupe_action"
        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_action WHERE code=:c"), {"c": code})

        payload = {"object_code": "p1_obj", "name": "P1去重动作", "code": code,
                   "target_table": "p1_target", "white_fields": ["name"]}
        await svc.upsert_action(dict(payload))
        await svc.upsert_action(dict(payload))          # 第二次：应更新而非新增
        await svc.upsert_action({**payload, "white_fields": ["name", "status"]})

        async with async_db_session() as db:
            rows = (await db.execute(_t(
                "SELECT id, white_fields FROM ai_ont_action "
                "WHERE code=:c AND is_deleted=false"), {"c": code})).fetchall()
        return [(r[0], r[1]) for r in rows]

    rows = _run(_scenario())
    assert len(rows) == 1, f"同 code 出现 {len(rows)} 条活行（执行时会取到旧定义）：{rows}"

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_action WHERE code=:c"),
                             {"c": "p1_dupe_action"})

    _run(_cleanup())


def test_upsert_function_dedupes_by_code():
    """函数同理：无 id 时按 code 去重。"""
    async def _scenario():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        code = "p1_dupe_fn"
        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_function WHERE code=:c"), {"c": code})

        for expr in ("1+1", "2+2", "3+3"):
            await svc.upsert_function({"object_code": "p1_obj", "name": "P1去重函数",
                                       "code": code, "kind": "expression", "expr": expr})

        async with async_db_session() as db:
            rows = (await db.execute(_t(
                "SELECT id, expr FROM ai_ont_function "
                "WHERE code=:c AND is_deleted=false"), {"c": code})).fetchall()
        return [(r[0], r[1]) for r in rows]

    rows = _run(_scenario())
    assert len(rows) == 1, f"同 code 出现 {len(rows)} 条活行：{rows}"

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_function WHERE code=:c"),
                             {"c": "p1_dupe_fn"})

    _run(_cleanup())


def test_upsert_link_dedupes_by_natural_key():
    """关系表没有 code 列，自然键是（源对象, 目标对象, 源字段, 目标字段）。"""
    async def _scenario():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        payload = {"source_object": "p1_obj_a", "target_object": "p1_obj_b",
                   "name": "P1关系", "card": "many_to_one",
                   "source_field": "b_id", "target_field": "id"}
        async with async_db_session.begin() as db:
            await db.execute(_t(
                "DELETE FROM ai_ont_link WHERE source_object='p1_obj_a'"))

        await svc.upsert_link(dict(payload))
        await svc.upsert_link(dict(payload))
        await svc.upsert_link({**payload, "name": "P1关系v2"})

        async with async_db_session() as db:
            rows = (await db.execute(_t(
                "SELECT id, name FROM ai_ont_link WHERE source_object='p1_obj_a' "
                "AND is_deleted=false"))).fetchall()
        return [(r[0], r[1]) for r in rows]

    rows = _run(_scenario())
    assert len(rows) == 1, f"同自然键出现 {len(rows)} 条关系：{rows}"
    assert rows[0][1] == "P1关系v2", f"应更新为最新定义：{rows}"

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_link WHERE source_object='p1_obj_a'"))

    _run(_cleanup())


# ===========================================================================
# 3) 多编辑动作必须整体成功或整体失败
# ===========================================================================
def test_multi_edit_action_is_all_or_nothing():
    """含多条编辑的动作：第 2 条失败时第 1 条必须一并回滚。

    修前每条编辑各开一个事务，第 1 条已提交 ⇒ 返回"规则执行失败"但数据已改了一半。
    """
    async def _scenario():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        code, tbl = "p1_txn_action", "p1_txn_target"
        async with async_db_session.begin() as db:
            await db.execute(_t(f"DROP TABLE IF EXISTS {tbl}"))
            await db.execute(_t(
                f"CREATE TABLE {tbl} (id INTEGER PRIMARY KEY, name TEXT, status TEXT)"))
            await db.execute(_t(f"DELETE FROM {tbl}"))
            await db.execute(_t(f"INSERT INTO {tbl}(id,name,status) VALUES(1,'原始','a')"))
            await db.execute(_t("DELETE FROM ai_ont_action WHERE code=:c"), {"c": code})
        await svc.upsert_action({
            "object_code": "p1_txn_obj", "name": "P1事务动作", "code": code,
            "target_table": tbl, "white_fields": ["name", "status"],
            # 第 1 条合法；第 2 条引用不存在的列 → 必然失败
            "rules": [
                {"type": "modify_object", "assignments": [
                    {"property": "name", "source": "static", "value": "已改"}]},
                {"type": "modify_object", "assignments": [
                    {"property": "not_a_column", "source": "static", "value": "x"}]},
            ],
        })

        r = await svc.execute_ontology_action(code=code, object_key="1",
                                              params={"name": "x"}, operator="P1")

        async with async_db_session() as db:
            name = (await db.execute(_t(f"SELECT name FROM {tbl} WHERE id=1"))).scalar()
        return r, name

    r, name = _run(_scenario())
    assert r.get("ok") is False, f"含失败规则的动作不该成功：{r}"
    assert name == "原始", (
        f"第 2 条规则失败后，第 1 条的修改没有回滚（部分落库）：name={name}")

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DROP TABLE IF EXISTS p1_txn_target"))
            await db.execute(_t("DELETE FROM ai_ont_action WHERE code='p1_txn_action'"))

    _run(_cleanup())


# ===========================================================================
# 4) Agent 通用函数工具必须过 ACL
# ===========================================================================
def test_agent_function_tool_respects_visibility_and_acl(monkeypatch):
    """``run_ontology_function`` 必须过可见性 + 资源 ACL（与同文件其它工具一致）。

    修前：直接 ``ont.run_ontology_function(code, args)``，只要 code 猜得中就能执行
    被 ACL 限定角色、或被设为 hidden/deprecated 的函数（含 http 形态）——
    Agent 成为绕过本体资源权限的后门。
    """
    async def _scenario():
        from app.plugin.module_ai.ontology import agent_tools as AT

        # 构造一条"调用者无权查看"的函数（hidden）
        monkeypatch.setattr(
            "app.plugin.module_ai.ontology.service.list_functions",
            lambda object_code=None: asyncio.sleep(0, result=[{
                "code": "p1_hidden_fn", "name": "隐藏函数", "object_code": "p1_obj",
                "kind": "expression", "expr": "1/0", "visibility": "hidden",
                "status": "experimental",
            }]))
        monkeypatch.setattr(
            "app.plugin.module_ai.ontology.service.run_ontology_function",
            lambda code, args=None, object_key=None: asyncio.sleep(
                0, result={"ok": True, "value": "不该被执行"}))

        return await AT.run_ontology_tool(
            "run_ontology_function", {"code": "p1_hidden_fn"}, user_id=2)

    out = _run(_scenario())
    text = str(out)
    assert "不该被执行" not in text, f"隐藏/无权函数被 Agent 执行了：{out}"
    assert "error" in out, f"应返回可读错误而非执行结果：{out}"


# ===========================================================================
# 5) SSRF：http 形态函数不得打本机/云元数据
# ===========================================================================
def test_http_function_blocks_loopback_and_metadata():
    """http 形态函数的 URL 必须拒绝环回 / 链路本地 / 云元数据地址。

    修前只校验 scheme：持 edit 权限的人可配 ``http://127.0.0.1:8002/...`` 或
    ``http://169.254.169.254/latest/meta-data/``，把平台当内网探针、窃取云凭证，
    而且**响应原文会回传给调用方**（可读回的 SSRF）。

    取舍说明：平台自己就连着内网 LLM 网关（私有网段），因此**放行私有网段**，
    只拦 环回/链路本地/保留/组播/未指定 —— 这三类正是凭据窃取与本机探测的入口。
    """
    from app.plugin.module_ai.ontology import function_engine as FE

    bad = [
        "http://127.0.0.1:8002/openapi.json",
        "http://localhost:5181/web",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8002/",
        "http://0.0.0.0:8002/",
    ]
    for url in bad:
        msg = FE.is_forbidden_url(url)
        assert msg, f"未拦住明显危险的 URL：{url}"

    # 内网服务（平台自己的网关就在 172.168.x）必须仍然可用
    assert FE.is_forbidden_url("http://172.168.100.146:5000/v1/chat/completions") == "", (
        "内网私有网段被误拦（平台自己的网关就在这里）")
    assert FE.is_forbidden_url("https://api.example.com/v1") == ""


def test_http_function_rejects_dangerous_url_on_save():
    """保存时就该拒绝（不让危险配置落库），而不只是运行时。"""
    async def _scenario():
        from app.core.exceptions import CustomException
        from app.plugin.module_ai.ontology import service as svc

        try:
            await svc.upsert_function({
                "object_code": "p1_obj", "name": "SSRF探针函数", "code": "p1_ssrf_fn",
                "kind": "http", "config": {"url": "http://169.254.169.254/latest/meta-data/"},
            })
            return None
        except CustomException as e:
            return str(e)

    msg = _run(_scenario())
    assert msg and "内网" in msg or "禁止" in str(msg), f"保存时没拦住危险 URL：{msg}"

    async def _cleanup():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(_t("DELETE FROM ai_ont_function WHERE code='p1_ssrf_fn'"))

    _run(_cleanup())
