"""执行与主体工具：真正落库取数的那一层（2026-11-08 从 service.py 拆出）。

测试里大量 monkeypatch 这些函数（``service._execute_sql`` 等），所以 service **保留同名
再导出**，且本模块内部交叉调用也走 ``_svc.``——否则打桩只对一半路径生效。
"""
from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc


async def _execute_sql(sql: str) -> dict:
    start = time.time()
    try:
        async with async_db_session() as db:
            result = await db.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 执行失败: {e}")
        raise CustomException(msg=f"查询执行失败：{e}")
    # 行数上限走设置项（clamp 到安全区间），不再直接吃常量 _svc.MAX_ROWS
    limit = _svc.MAX_ROWS
    try:
        limit = _svc._clamp_rows(_svc.AiQueryService._cfg_int(await _svc.AiQueryService._cfg(),
                                                    "query_max_rows", _svc.MAX_ROWS))
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 读取行数上限失败，回落 {_svc.MAX_ROWS}：{str(e)[:80]}")
    data = [[_svc._json_cell(v) for v in r] for r in rows[:limit]]
    return {"columns": cols, "rows": data, "took_ms": int((time.time() - start) * 1000),
            "truncated": len(rows) > limit}


async def _secure_ont_sql(sql: str, auth) -> dict:
    """把问数生成的 SQL 交给本体的行级/列级策略改写。

    返回 ``{"sql": <可能已改写>, "deny": bool, "msg": str, "rewritten": [...]}``。
    取不到身份时**不改写**（保持既有行为），但会在日志里留痕——
    宁可显式记录"这次没做权限改写"，也不要假装做了。
    """
    try:
        uid = getattr(getattr(auth, "user", None), "id", None)
    except Exception:  # noqa: BLE001
        uid = None
    if not uid:
        log.warning("[query] 无调用者身份，跳过本体权限改写")
        return {"sql": sql, "deny": False, "rewritten": [],
                "msg": "无身份，未改写"}
    try:
        from app.plugin.module_ai.ontology import security as _ont_sec

        principal = await _ont_sec.load_principal(uid)
        r = await _ont_sec.secure_sql(sql, principal)
    except Exception as e:  # noqa: BLE001
        # 权限改写失败 → **fail-closed**：宁可拒绝，也不要放行未过滤的查询
        log.warning(f"[query] 本体权限改写失败，拒绝执行：{e}")
        return {"sql": sql, "deny": True, "rewritten": [],
                "msg": f"权限校验失败，已拒绝执行：{str(e)[:120]}"}
    if not r.get("ok"):
        return {"sql": sql, "deny": True, "rewritten": r.get("rewritten") or [],
                "msg": r.get("note") or "存在无法安全改写的表，已拒绝执行"}
    return {"sql": r["sql"], "deny": False, "rewritten": r.get("rewritten") or [],
            "msg": r.get("note") or ""}


async def _execute_bound_metric(metric: dict, auth=None) -> dict:
    """执行**绑定型指标**：口径由「本体对象 + 属性 + 聚合」确定性推导（不写 SQL）。

    对齐设计 §2.2：绑定型指标既可走对象查询路径，也可走指标快路径——这里让快路径
    复用本体实例层（`instance_aggregate`），从而**无需 sql_template**。
    """
    from app.plugin.module_ai.ontology import security as _ont_sec
    from app.plugin.module_ai.ontology import service as ont

    obj = str(metric.get("object_code") or "")
    prop = str(metric.get("property_code") or "")
    fn = str(metric.get("agg_fn") or "count")
    # 快路径是**单值**语义（分组诉求由 `_wants_grouping` 挡在门外，交给对象查询路径）：
    # 故这里不按 bound_dimensions 自动分组，只给总量。
    gb = ""
    a: dict = {"fn": fn}
    if prop:
        a["prop"] = prop
    uid = getattr(getattr(auth, "user", None), "id", None)
    try:
        principal = await _ont_sec.load_principal(uid)
    except Exception:  # noqa: BLE001
        principal = None
    r = await ont.instance_aggregate(obj, group_by=gb, aggs=[a], principal=principal)
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg") or "指标执行失败")
    rows = r.get("rows") or []
    return {
        "sql": f"-- 绑定型指标：本体实例层执行 {obj}.{fn}({prop or '*'})",
        "columns": [gb or "合计", metric.get("name") or fn],
        "rows": rows, "took_ms": 0,
        "note": f"绑定型指标 {metric.get('key')} 由本体实例层确定性执行",
    }


async def _execute_metric(metric: dict, params: dict[str, Any], auth=None) -> dict:
    # 绑定型指标（object_code + agg_fn）：走本体实例层，**不依赖 sql_template**
    if str(metric.get("object_code") or "") and str(metric.get("agg_fn") or ""):
        return await _svc._execute_bound_metric(metric, auth)
    sql = _svc._render_template(metric["sql_template"], params)
    ds_code = metric.get("datasource") or _svc.SYSTEM_DS
    if ds_code == _svc.SYSTEM_DS:
        table = await _svc.AiQueryService._allowed_for_user(auth)
        sql = _svc.validate_sql(sql, table)
    # 安全补丁（P0-3）：执行一律走 `_execute_one`（与 ask / ask_stream / 报表共用
    # 的**唯一收口**）—— 字段级 ACL 与本体行/列改写都在那里做，指标不再直连
    # `_svc._execute_sql`，否则「指标模板」就是绕过敏感字段拦截的后门。
    # 第四个参数传**指标名**：软删除口径改写需要“问句”来判断是不是在问已删除。
    # 漏传过一次（只改了 ask 的两条路）—— 指标快路径把「每日耗用量合计」
    # 答成 41,827,138（含 3390 条软删行），金标 3,550,065，评测里就这一道暴露。
    # ``entry="metric"``：审计/shadow 差异按入口标记（P1 唯一收口的口径）。
    res = await _svc.AiQueryService._execute_one(
        sql, ds_code, auth, str(metric.get("name") or ""), entry="metric")
    res["sql"] = res.get("sql") or sql
    return res


async def _execute_custom_ds_sql(datasource_id: int, sql: str, auth=None) -> dict:
    """对自定义数据源执行只读 SQL（含 schema 白名单校验 + 角色授权）。"""
    if auth is not None:
        await _svc._assert_ds_access(datasource_id, auth)
    ds = await _svc._load_ds(datasource_id)
    schema_rows = await _svc.list_ds_schema(datasource_id)
    allowed = {r["table"] for r in schema_rows}
    from . import executor as _ex
    from .sql_quote import quote_schema_identifiers

    sql = _svc.validate_sql(sql, allowed)
    # 大小写敏感库（如 ds:4）必须把表/列名写成「真实大小写 + 双引号」，
    # 否则 PG 折成小写 → 关系/列不存在（实测把整题打崩的根因之一）。
    schema_map = {
        r["table"]: [c.get("name") for c in (r.get("columns") or [])]
        for r in schema_rows
    }
    sql = quote_schema_identifiers(sql, schema_map)
    # **值匹配纠错**：SQL 里的字面量若与库里的取值"归一后相等但写法不同"
    # （尾随空格 / 全角 / 大小写），换成库里的原样写法 —— 否则等值比较查不到行。
    # 这是 Genie「entity matching」的等价物（它做匹配纠错，而不是把值列进提示词）。
    if _svc.AiQueryService._cfg_bool(await _svc.AiQueryService._cfg(), "literal_fix_enabled", True):
        try:
            used = [t for t in schema_map if t.lower() in sql.lower()][:5]
            if used:
                vmap = await _svc.AiQueryService._ds_value_map(f"ds:{datasource_id}", used, schema_map)
                if vmap:
                    fixed, fixes = _svc.AiQueryService.fix_sql_literals(sql, vmap)
                    if fixes:
                        log.info("[query] 值匹配纠错：{}（{} 处）", "；".join(fixes[:3]), len(fixes))
                        sql = fixed
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 值匹配纠错失败（忽略）: {str(e)[:80]}")
    # **字段级 ACL 对自定义数据源同样生效**（fail-closed）。
    # 之前这道检查只在系统库分支：本体/资产里把「煤款单价」标成敏感，
    # 走 ds:4 的问数照样能查出来 —— 标记形同摆设。
    # `_ont_sql_violations` 本身是按**表名**匹配 `ai_query_asset_columns.sensitive`，
    # 对外部库的表一样成立，差的只是没人调用它。
    uid = getattr(getattr(auth, "user", None), "id", None) if auth is not None else None
    try:
        violations = await _svc.AiQueryService._ont_sql_violations(sql, uid)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 外部源字段级 ACL 校验失败，拒绝执行：{e}")
        raise CustomException(msg=f"字段级权限校验失败，已拒绝执行：{str(e)[:120]}") from e
    if violations:
        raise CustomException(
            msg=f"字段级权限：无权限访问 {', '.join(violations)}（请联系管理员申请可见权限）")
    # 行数上限 / 执行超时同样从设置读取：这两个 key 以前只在默认值表里躺着，
    # 实际生效的是 executor.MAX_ROWS / QUERY_TIMEOUT 常量 —— 界面改了没反应。
    _cfg = await _svc.AiQueryService._cfg()
    out = await _ex.execute_select(
        _svc._ds_cfg_from_model(ds), sql,
        max_rows=_svc.AiQueryService._cfg_int(_cfg, "query_max_rows", _ex.MAX_ROWS),
        timeout=_svc.AiQueryService._cfg_int(_cfg, "query_timeout_sec", int(_ex.QUERY_TIMEOUT)),
    )
    # 回传**实际执行**的 SQL（已加引号）：否则展示/排查看到的是未加引号的模板，会被误导
    out["sql"] = sql
    return out


async def _system_allowed() -> set[str]:
    """可查询表白名单 = 系统表 + 本体对象支撑表。

    注意：支撑表**不一定**叫 ``ont_{code}``——由数据源支撑的对象
    （如 ``video_cameras`` / ``demo_sales``）支撑表就是它自己。
    旧实现只拼 ``ont_{code}``，于是这些表**根本查不到**
    （表现为「表 xxx 不在可查询白名单内」）。两种都收进来。
    """
    now = time.monotonic()
    if _svc._ONT_ALLOW_CACHE is not None and (now - _svc._ONT_ALLOW_CACHE_AT) < _svc._ONT_ALLOW_TTL:
        return _svc._ONT_ALLOW_CACHE
    # 走本体的统一语义接口拿"真实支撑表名 → code"，不再自己拼 SQL
    try:
        from app.plugin.module_ai.ontology import semantic as _sem

        ont_tables = set((await _sem.object_table_map()).keys())
    except Exception:  # noqa: BLE001
        ont_tables = set()
    _svc._ONT_ALLOW_CACHE = set(_svc.SYSTEM_ALLOWED_TABLES) | ont_tables
    _svc._ONT_ALLOW_CACHE_AT = now
    return _svc._ONT_ALLOW_CACHE


def _scan_ont_tables(sql: str) -> list[str]:
    """从生成 SQL 中检测用到的本体物化表（ont_xxx），作为「问答使用本体」的可视溯源。"""
    if not sql:
        return []
    return list(dict.fromkeys(
        m.group(1) for m in re.finditer(r"\b(ont_[A-Za-z0-9_]+)\b", sql)
    ))


def _default_sensitive_return_cols(sql: str) -> list[str]:
    """筛出 SQL **返回结果列**中命中内置敏感名单的列名（原始形式）。

    - 用 sqlglot 精确提取 SELECT 投影表达式里的列（含函数内列、别名），
      避免正则误伤字符串；**不扫 WHERE / JOIN**（那里引用敏感列不拦）。
    - 别名场景（``id AS password``）以**别名**作为结果列名判定——结果列就叫 password，必须拦。
    - 解析失败时回退正则（宁可多报、不可漏报，保持 fail-closed）。
    """
    if not sql:
        return []
    try:
        import sqlglot
        from sqlglot import exp as _exp

        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        try:
            names = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)
        except Exception:  # noqa: BLE001
            return []
        return [n for n in names if n.lower() in _svc._DEFAULT_SENSITIVE_COLS]

    candidates: list[str] = []
    for sel in parsed.find_all(_exp.Select):
        for expr in sel.expressions:
            # 别名：以「别名」作为结果列名（如 `id AS password`）
            if isinstance(expr, _exp.Alias):
                candidates.append(expr.alias)
            # 内部列：覆盖直接列（password）、函数内列（MAX(api_token)）
            for col in expr.find_all(_exp.Column):
                candidates.append(col.name)

    seen: set[str] = set()
    hits: list[str] = []
    for name in candidates:
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        if low in _svc._DEFAULT_SENSITIVE_COLS:
            hits.append(name)
    return hits


def _auth_scope(auth) -> str:
    """SQL 缓存的主体指纹：不同用户/角色不能复用同一份生成结果。

    上下文裁剪与权限判定都依赖主体，生成的 SQL 可能不同（行条件、可见表）；
    缓存不加指纹 = 把 A 的 SQL 给 B 用。
    """
    uid = getattr(getattr(auth, "user", None), "id", None)
    if uid is None:
        return "anon"
    try:
        roles = ",".join(sorted(_svc._user_role_codes(auth)))
    except Exception:  # noqa: BLE001 - 角色取不到时退化为按用户隔离
        roles = ""
    return f"{uid}|{roles}"


def _actor_id(auth) -> int | None:
    """取当前操作人 id；**内部调度**（无 HTTP 用户上下文）返回 ``None``。

    背景（实测回归）：``generate_asset_descriptions`` 这类批量动作既会被 HTTP
    接口触发（有 auth），也会被自主巡检在**后台**触发（``auth=None``）。旧实现
    直接写 ``auth.user.id`` → AttributeError → 整批「补全描述」必然失败。

    这里统一兜底为 ``None``（= 系统写入，审计字段留空），
    **不放宽任何 ACL**：归属过滤仍按真实 auth 走，``None`` 只影响审计列。
    """
    return getattr(getattr(auth, "user", None), "id", None)


def _user_role_codes(auth) -> set[str]:
    try:
        return {getattr(r, "code", "") for r in getattr(getattr(auth, "user", None), "roles", []) or []}
    except Exception:  # noqa: BLE001
        return set()


def _clamp_rows(n) -> int:
    """行数上限的**唯一**收敛点：设置项脏值/<=0 时回落到 ``_svc.MAX_ROWS``。

    与 `executor.clamp_max_rows` 同区间，两处必须一致（有守护测试比对）。
    """
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        return _svc.MAX_ROWS
    if v <= 0:
        return _svc.MAX_ROWS
    return max(1, min(5000, v))


def _json_cell(v):
    """把数据库返回值转成 JSON 安全类型（Decimal→float、日期→iso 等）。"""
    if v is None:
        return None
    if isinstance(v, bool) or isinstance(v, (int, float, str)):
        return v
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    from datetime import date, datetime, time

    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_json_cell(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_cell(x) for k, x in v.items()}
    return str(v)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) + 1e-9
    )


def _render_template(template: str, params: dict[str, Any]) -> str:
    """把 {key} 占位替换为安全值（仅支持数字/日期/白名单字符串）。"""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        val = params.get(key)
        if val is None:
            return m.group(0)
        if isinstance(val, (int, float)):
            return str(int(val) if float(val).is_integer() else val)
        s = str(val)
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fa5\- ]+", s):
            raise CustomException(msg=f"参数「{key}」包含非法字符")
        return s

    return re.sub(r"\{(\w+)\}", repl, template)


def scope_tables_to_schema(ranked: list[str], schema_map: dict, core_tables,
                           top_k: int) -> list[str]:
    """**数据源隔离**：把召回结果限制在本次数据源的 schema 内。

    向量/本体通道是全局的（不认数据源），实测 ds:4 的问题会被召回到
    video_*/ai_* 等 system 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL。

    ⚠️ ``schema_map`` 为空表示**schema 未知**（如测试库取不到 information_schema）
    —— 此时不做隔离（否则会把召回清空），保持原行为。
    """
    if not schema_map:
        picked = list(ranked or [])[:top_k]
        return picked or list(core_tables or [])
    picked = [t for t in (ranked or []) if t in schema_map][:top_k]
    if not picked:
        picked = [t for t in (core_tables or []) if t in schema_map][:top_k]
    if not picked:
        picked = list(schema_map)[:top_k]
    return picked


def nl2sql_max_tokens(cfg: dict | None) -> int:
    """NL2SQL 生成用的 max_tokens：取配置值，但**不得低于下限**。"""
    raw = (cfg or {}).get("nl2sql_max_tokens")
    try:
        val = int(str(raw).strip()) if raw is not None else 0
    except (TypeError, ValueError):
        val = 0
    if val < _svc.NL2SQL_MIN_MAX_TOKENS:
        # 低于下限（含未配置/非法）一律用默认值，宁可多给预算也不要出空 SQL
        return _svc.NL2SQL_DEFAULT_MAX_TOKENS
    return val


def nl2sql_attempts(cfg: dict | None) -> int:
    """慢路径最多尝试几次（含首次）。

    设置项是 ``nl2sql_retry``，语义按**总尝试次数**解释：``2`` = 首次 + 1 次自纠错
    （与改动前硬编码的 ``range(2)`` 完全等价，默认行为不变）。
    想做"只试一次、不重试省时间"就把值改成 1。
    """
    raw = (cfg or {}).get("nl2sql_retry")
    try:
        val = int(float(str(raw).strip())) if raw not in (None, "") else 2
    except (TypeError, ValueError):
        val = 2
    return max(1, min(5, val))


def _ir_max_tokens(cfg: dict | None) -> int:
    """对象查询（IR 生成）的 max_tokens。

    ``object_query_max_tokens`` 的语义是**覆盖**主预算，``0``（或非法/负数）表示
    「跟随 _svc.nl2sql_max_tokens」。之前写的是
    ``_cfg_int(cfg, "object_query_max_tokens", _svc.nl2sql_max_tokens(cfg))`` ——
    默认值只在 key **缺失**时生效；而该 key 一进默认值表就恒为 "0"，
    于是 max_tokens=0，模型直接返回空（这个坑正是"键进默认值"时才暴露）。
    """
    raw = (cfg or {}).get("object_query_max_tokens")
    try:
        val = int(float(str(raw).strip())) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        val = 0
    return val if val > 0 else _svc.nl2sql_max_tokens(cfg)
