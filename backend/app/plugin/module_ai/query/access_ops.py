"""访问控制：可查白名单、预览、矩阵、审计口径（2026-11-08 从 service.py 拆出）。

- ``_allowed_for_user``：**按用户收窄**的可查表集合（数据域 → ABAC → 兜底 allow），
  与问数主链路同口径；报表/指标/导出都必须用它，不能用全局 ``_system_allowed``；
- ``_require_queryable_table`` / ``_require_ident``：资产入口（导出/浏览/质量规则）的
  双重校验——先卡合法标识符，再查白名单（fail-closed）；
- ``_sensitive_table_deny`` / ``_can_see_sensitive`` / ``_sensitive_asset_cols``：
  敏感列的三层口径（整表禁、按角色放行、按列集合）；
- ``access_preview`` / ``access_matrix`` / ``access_walkthrough`` / ``permission_check``：
  治理页的「这个用户能查什么、为什么」。

``_system_allowed`` / ``_user_role_codes`` 仍归 ``service.py``，这里用 ``_svc.`` 解析。
"""
from __future__ import annotations

import re

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc
from .model import AiQueryAssetColumnModel


class AccessOps:
    @classmethod
    async def permission_check(cls, user_id: int, table: str) -> dict:
        """权限检查（Palantir checking permissions）：给定用户+资源，返回能否访问/原因/敏感字段可见性。"""
        from types import SimpleNamespace as SN
        try:
            uid = int(user_id or 0)
        except (TypeError, ValueError):
            uid = 0
        if await cls._is_superuser(uid):
            return {"user_id": uid, "table": table, "allowed": True,
                    "sensitive_visible": True, "reason": "超管（全量可见）"}
        roles = await cls._user_role_codes_by_id(uid)
        auth = SN(user=SN(id=uid, is_superuser=False, roles=[SN(code=r) for r in roles]))
        allowed_tables = await cls._allowed_for_user(auth)
        allowed = table in allowed_tables
        reason = "在可查白名单内" if allowed else "不在该用户可查范围（ABAC/数据域限定）"
        return {"user_id": uid, "table": table, "allowed": allowed,
                "roles": sorted(roles),
                "sensitive_visible": bool(await cls._can_see_sensitive(uid)),
                "reason": reason}

    @classmethod
    async def access_matrix(cls) -> dict:
        """数据域/表级权限矩阵：每个系统角色 → 合并后可查表 + 是否受限 + 敏感放行。"""
        from sqlalchemy import text as _t
        async with async_db_session() as db:
            rows = (await db.execute(_t(
                "SELECT code, name FROM sys_role WHERE is_deleted=false ORDER BY id"))).fetchall()
        roles = [{"code": r[0] or "", "name": r[1] or r[0] or ""} for r in rows]
        rules = await cls.list_access_rules()
        out = []
        for role in roles:
            code = role["code"]
            matched = [x for x in rules if x["enabled"] and x["attribute"] == "role" and x["value"] == code]
            if matched:
                tables = sorted({t for x in matched for t in (x["allowed_tables"] or [])})
                out.append({**role, "restricted": True, "tables": tables,
                            "sensitive_ok": any(x["sensitive_ok"] for x in matched)})
            else:
                out.append({**role, "restricted": False, "tables": [], "sensitive_ok": False})
        return {"roles": out}

    @classmethod
    async def access_preview(cls, user_id) -> dict:
        """权限沙箱：按 user_id 模拟该用户的问数可查表（超管/角色/数据域判定）+ 敏感放行。"""
        from types import SimpleNamespace as SN
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        su = await cls._is_superuser(uid)
        roles = await cls._user_role_codes_by_id(uid)
        auth = SN(user=SN(id=uid, is_superuser=su, roles=[SN(code=r) for r in roles]))
        tables = await cls._allowed_for_user(auth)
        domain_tables = await cls._domain_tables_for_user(uid)
        return {
            "user_id": uid, "superuser": su, "roles": sorted(roles),
            "domain_restricted": bool(domain_tables), "count": len(tables),
            "allowed_tables": sorted(tables),
        }

    @classmethod
    async def access_preview_role(cls, role: str) -> dict:
        """权限沙箱：按角色合并其 ABAC 规则的 allowed_tables + 敏感放行；无规则默认全开。"""
        role = (role or "").strip()
        rules = await cls.list_access_rules()
        matched = [x for x in rules if x["enabled"] and x["attribute"] == "role" and x["value"] == role]
        if matched:
            tables = sorted({t for x in matched for t in (x["allowed_tables"] or [])})
            return {"role": role, "restricted": True,
                    "sensitive_ok": any(x["sensitive_ok"] for x in matched),
                    "count": len(tables), "allowed_tables": tables}
        base = await _svc._system_allowed()
        return {"role": role, "restricted": False, "sensitive_ok": False,
                "count": len(base), "allowed_tables": sorted(base)}

    @classmethod
    async def access_walkthrough(cls, user_id: int = 0) -> dict:
        """数据访问沙箱/演练：为指定用户演示可访问/受限资源（ABAC/数据域）。"""
        assets = await cls.list_assets()
        allowed_tables = set()
        try:
            from types import SimpleNamespace as SN
            roles = await cls._user_role_codes_by_id(user_id)
            auth = SN(user=SN(id=user_id, is_superuser=False, roles=[SN(code=r) for r in roles]))
            allowed_tables = set(await cls._allowed_for_user(auth))
        except Exception:  # noqa: BLE001
            allowed_tables = set()
        can_see_sens = bool(await cls._can_see_sensitive(user_id)) if user_id else False
        allowed = []
        blocked = []
        for a in assets:
            t = a["table_name"]
            if t in allowed_tables:
                allowed.append({"table": t, "alias": a["alias"], "sensitive": a.get("sensitive_count") or 0})
            else:
                blocked.append({"table": t, "alias": a["alias"]})
        return {"user_id": user_id, "allowed_count": len(allowed),
                "blocked_count": len(blocked), "can_see_sensitive": can_see_sens,
                "allowed": allowed[:50], "blocked": blocked[:50]}

    @classmethod
    async def list_access_rules(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT id,name,attribute,value,allowed_tables,sensitive_ok,enabled "
                "FROM ai_access_rule WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "attribute": r[2] or "role", "value": r[3] or "",
            "allowed_tables": r[4] if isinstance(r[4], list) else (_json.loads(r[4]) if r[4] else []),
            "sensitive_ok": bool(r[5]), "enabled": bool(r[6]),
        } for r in rows]

    @classmethod
    async def upsert_access_rule(cls, data: dict) -> dict:
        import json as _json
        tables = _json.dumps(data.get("allowed_tables") or [], ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_access_rule SET name=:n, attribute=:a, value=:v, allowed_tables=:t, "
                    "sensitive_ok=:s, enabled=:e WHERE id=:i"), {
                    "n": data.get("name", ""), "a": data.get("attribute", "role"), "v": data.get("value", ""),
                    "t": tables, "s": bool(data.get("sensitive_ok", False)),
                    "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_access_rule(name,attribute,value,allowed_tables,sensitive_ok,enabled) "
                "VALUES (:n,:a,:v,:t,:s,:e) RETURNING id"), {
                "n": data.get("name", ""), "a": data.get("attribute", "role"), "v": data.get("value", ""),
                "t": tables, "s": bool(data.get("sensitive_ok", False)),
                "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def delete_access_rule(cls, id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t("UPDATE ai_access_rule SET is_deleted=true WHERE id=:id"), {"id": id})

    @classmethod
    async def approval_center(cls) -> dict:
        """审批中心统一视图：聚合「动作写回待审批」+「本体发布待审批」。"""
        actions = await cls.list_pending_actions(limit=100)
        from app.plugin.module_ai.ontology.service import list_version_pending as _ont_pending
        versions = await _ont_pending(100)
        return {"actions": actions, "versions": versions,
                "total": len(actions) + len(versions)}

    @classmethod
    async def _allowed_for_user(cls, auth) -> set[str]:
        """用户级可查表白名单（Palantir 数据域/表级权限拦截）。

        超管 → 全白名单（SYSTEM + ont_*）。非超管 →
          1) 若属于某启用「数据域」的成员 → 只能查该域 tables 的并集（数据域隔离）；
          2) 否则按 ABAC 规则（attribute=role、value∈用户角色）合并 allowed_tables；
          3) 未配置 → 默认全白名单（向后兼容，避免误锁）。
        均与全局白名单求交收紧。
        """
        base = await _svc._system_allowed()
        try:
            if getattr(getattr(auth, "user", None), "is_superuser", False):
                return base
        except Exception:  # noqa: BLE001
            pass
        uid = getattr(getattr(auth, "user", None), "id", None)
        domain_tables = await cls._domain_tables_for_user(uid)
        if domain_tables:
            return base & domain_tables
        roles = _svc._user_role_codes(auth)
        rules = await cls.list_access_rules()
        allowed: set[str] = set()
        for x in rules:
            if x["enabled"] and x["attribute"] == "role" and x["value"] in roles:
                allowed |= set(x["allowed_tables"] or [])
        if allowed:
            return base & allowed
        return base

    @classmethod
    async def _domain_tables_for_user(cls, user_id) -> set[str]:
        """用户所属启用「数据域」的 tables 并集（成员 id ∈ domain.members）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        if not uid:
            return set()
        domains = await cls.list_domains()
        result: set[str] = set()
        for d in domains:
            if d["enabled"] and uid in (d["members"] or []):
                result |= set(d["tables"] or [])
        return result

    @classmethod
    async def _sql_query_scope(
        cls, sql: str, dialect: str = "postgres"
    ) -> tuple[set[str], set[str]]:
        """用 sqlglot 按**数据源方言**解析查询涉及的表集与列名集；失败回退正则（不放过）。

        ``dialect`` 必须与真实库一致：MySQL 的反引号 ``select * from `T``` 用 postgres
        读会解析失败，正则也不认反引号 → 表集合为空（Step 1 复审 C1：会跳过整条编译）。
        """
        try:
            import sqlglot
            from sqlglot import exp as _exp

            parsed = sqlglot.parse_one(sql, read=dialect)
            tables = {t.name for t in parsed.find_all(_exp.Table)}
            cols = {c.name for c in parsed.find_all(_exp.Column)}
            return tables, cols
        except Exception:  # noqa: BLE001
            tables = set(re.findall(
                r"\b(?:from|join)\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)",
                sql or "", re.IGNORECASE,
            ))
            cols = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql or ""))
            return tables, cols

    @classmethod
    async def _can_see_sensitive(cls, user_id) -> bool:
        """ABAC：超管可看敏感字段；否则看是否有**针对该用户**的敏感放行规则。

        安全补丁（2026-10-19）：修前只判断"存在**任一**启用且 sensitive_ok 的规则"，
        完全不校验它是否命中当前用户 —— 于是 dev 库里一条 ``role=ADMIN`` 的放行规则
        让**所有用户**都能看敏感字段，`_ont_sql_violations` 被短路、字段级 ACL 形同虚设。
        现在按 ``attribute=value`` 命中当前用户的角色才放行（默认拒绝）。
        """
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                r = (await db.execute(_t(
                    "SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false"), {"id": user_id or 0})).fetchone()
            if r and r[0]:
                return True
            roles = await cls._user_role_codes_by_id(user_id)
            if not roles:
                return False
            rules = await cls.list_access_rules()
            return any(x["sensitive_ok"] and x["enabled"]
                       and x["attribute"] == "role" and x["value"] in roles
                       for x in rules)
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    async def _sensitive_asset_cols(cls, table: str) -> list[str]:
        """从字段资产目录取业务表被标记为敏感（sensitive）的字段清单。"""
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            rows = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel.column_name).where(
                        AiQueryAssetColumnModel.table_name == table,
                        AiQueryAssetColumnModel.sensitive.is_(True),
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).all()
        return [r[0] for r in rows]

    @staticmethod
    async def _sensitive_table_deny(table_name: str) -> str:
        """表命中敏感清单时返回拒绝文案，否则空串（导出/浏览共用，2026-11 复审 I1）。

        导出/浏览走的是 ``SELECT *`` 直读，绕过了星号止血与策略网关；含敏感列的表
        必须一律拒绝，否则 ``select * from video_cameras`` 的明文 password 能从
        「数据集导出」出去。

        读清单失败按**拒绝**处理（fail-closed）：判断不了就不能放行。
        """
        from .policy.model import sensitive_tables

        try:
            sensitive = await sensitive_tables()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[问数] 敏感表清单读取失败（导出/浏览按拒绝处理）: err={e}")
            return "敏感列清单读取失败，按拒绝处理（fail-closed）"
        if str(table_name or "").strip().lower() in sensitive:
            return "含敏感列的表不支持导出/浏览"
        return ""

    @classmethod
    async def _require_queryable_table(cls, table_name: str, auth) -> str:
        """资产入口统一白名单校验：表名必须在**按用户收窄**的可查白名单内。

        与问数主链路同口径：复用 ``_allowed_for_user(auth)``（数据域/ABAC 收窄），
        不是全局 ``_svc._system_allowed()`` —— 否则数据域隔离在这三个入口上失效。
        注意 ``validate_sql`` 的白名单正则 ``\\bfrom\\s+([A-Za-z_]…)`` 对
        ``FROM "x"`` 这种**带引号**的表名不匹配，单靠它会被绕过，所以这里
        先做标识符校验（拼出来的 SQL 只含已校验的标识符，无需再走一遍）。

        校验失败抛 CustomException（fail-closed），且发生在拼 SQL 之前。
        """
        name = cls._require_ident(table_name, "表名")
        allowed = await cls._allowed_for_user(auth)
        if name.lower() not in {str(t).lower() for t in allowed}:
            raise CustomException(msg=f"表「{name}」不在可查询白名单内")
        return name

    @staticmethod
    def _require_ident(name: str, what: str = "表名") -> str:
        """合法 SQL 标识符校验（表名/列名）：仅允许 ``[A-Za-z_][A-Za-z0-9_]*``。

        export_asset / object_browse / dq_rules_run 把路径/查询参数直接拼进
        ``SELECT ... FROM "x"``，表名含 ``"`` 即可闭合引号注入任意 SQL
        （psycopg2 允许多语句），所以必须先过这里。不合法抛 CustomException
        （fail-closed），绝不静默放行。
        """
        s = str(name or "").strip()
        if not _svc._IDENT_RE.match(s):
            raise CustomException(msg=f"非法{what}：{name!r}")
        return s
