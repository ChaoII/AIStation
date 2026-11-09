"""数据源核心：加载、编号、schema 同步与访问校验（2026-11-08 从 service.py 拆出）。

``_load_ds`` / ``_ds_code`` 是所有外部源代码路径的入口（``ds:{id}`` ↔ 库行）；
``list_ds_schema`` / ``sync_datasource_schema`` 拉取并落库外部库表结构；
``_assert_ds_access`` 是数据源级授权（谁能连哪个源）。
"""
from __future__ import annotations

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from .filtering import DEFAULT_FILTER_RULES, is_audit_field, is_system_table
from .model import AiQueryDatasourceModel, AiQuerySchemaModel


def _svc():
    """延迟取 service 模块：顶层 import 会与 service 的按名导入互相等待（循环）。"""
    from . import service

    return service


async def _load_ds(datasource_id: int):
    async with async_db_session() as db:
        ds = await db.get(AiQueryDatasourceModel, datasource_id)
        if not ds or ds.is_deleted:
            raise CustomException(msg="数据源不存在")
        return ds


def _ds_code(datasource_id: int) -> str:
    return f"ds:{datasource_id}"


def _ds_cfg_from_model(ds) -> dict:
    return {
        "type": ds.type or "postgres", "host": ds.host or "", "port": ds.port or 0,
        "database": ds.database or "", "username": ds.username or "",
        "password": ds.password or "",
    }


async def _norm_datasource(datasource) -> str | None:
    """把数据源入参**归一化**为后端口径：``system`` / ``ds:{id}``。

    背景（实测踩坑）：前端下拉的 `:value` 用的是**数据源编码**（如 ``ezdcs_pg``），
    而后端语义层（指标 `datasource`、`_svc().list_ds_schema`、`_svc()._execute_custom_ds_sql`）
    统一用 ``ds:{id}``。不归一化会导致 `int('ezdcs_pg')` 报错、
    ``list_metrics('ezdcs_pg')`` 匹配不到任何指标。

    接受 ``None``/``''``（→None，表示不限）、``system``、``ds:{id}``、编码（→查 id）。
    """
    from sqlalchemy import text as _t

    ds = str(datasource or "").strip()
    if not ds:
        return None
    if ds == "system" or ds.startswith("ds:"):
        return ds
    try:
        async with async_db_session() as db:
            row = (await db.execute(_t(
                "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"),
                {"c": ds})).fetchone()
        if row:
            return _svc()._ds_code(int(row[0]))
    except Exception:  # noqa: BLE001
        pass
    return ds


async def test_datasource_conn(datasource_id: int) -> dict:
    ds = await _svc()._load_ds(datasource_id)
    from . import executor as _ex

    return await _ex.test_connection(_svc()._ds_cfg_from_model(ds))


async def sync_datasource_schema(datasource_id: int) -> dict:
    ds = await _svc()._load_ds(datasource_id)
    from . import executor as _ex

    tables = await _ex.introspect_schema(_svc()._ds_cfg_from_model(ds))
    code = _svc()._ds_code(datasource_id)
    # Task3：同步时按该数据源 filter_rules 给每个字段打 is_audit 标
    rules = ds.filter_rules or DEFAULT_FILTER_RULES
    async with async_db_session.begin() as db:
        from sqlalchemy import delete
        from sqlalchemy import text as _t

        # 运行时补列（本项目 ai_* 表不走 Alembic，惯用 ADD COLUMN IF NOT EXISTS）
        try:
            await db.execute(_t(
                "ALTER TABLE ai_query_schema "
                "ADD COLUMN IF NOT EXISTS table_comment VARCHAR(255) DEFAULT ''"))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 补 ai_query_schema.table_comment 失败: {e}")
        await db.execute(
            delete(AiQuerySchemaModel).where(AiQuerySchemaModel.datasource == code)
        )
        for t in tables:
            cols = t["columns"] or []
            for c in cols:
                if isinstance(c, dict) and c.get("name"):
                    c["is_audit"] = is_audit_field(c["name"], rules)
            db.add(
                AiQuerySchemaModel(
                    datasource=code, table_name=t["table"],
                    table_comment=str(t.get("comment") or "")[:255],
                    columns=cols,
                )
            )
    # 同步完顺手重算血缘：schema 变了，旧血缘就不准了。
    # ★ 必须 try/except —— 血缘是增强，不能因为它让 schema 同步失败。
    try:
        from .lineage import rebuild_lineage

        await rebuild_lineage(datasource_id)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 血缘重算失败（忽略）: {str(e)[:120]}")
    return {"tables": len(tables)}


async def list_ds_schema(datasource_id: int, included_only: bool = False) -> list[dict]:
    """某自定义数据源已同步的表结构。

    ``included_only=True`` 时只返回**数据资产目录里已纳入**的表 ——
    用于检索/prompt 的范围收敛（实测 ds:4 同步了 311 张表，其中 92 张是
    SYS_*/_BAK 等技术表，混进检索会污染召回与提示词）。
    """
    code = _svc()._ds_code(datasource_id)
    # Task3：按该数据源 filter_rules 现算 is_system/is_audit；数据源不存在时兜底默认规则
    try:
        rules = (await _svc()._load_ds(datasource_id)).filter_rules or DEFAULT_FILTER_RULES
    except CustomException:
        rules = DEFAULT_FILTER_RULES
    async with async_db_session() as db:
        from sqlalchemy import select
        from sqlalchemy import text as _t

        rows = (
            await db.execute(
                select(AiQuerySchemaModel).where(
                    AiQuerySchemaModel.datasource == code,
                    AiQuerySchemaModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        if included_only:
            # 一张表有三种状态：**显式纳入**（included=true）/ **显式排除**（included=false）/
            # **从未建过资产行**（同步过 schema 但没治理过）。
            #
            # 旧逻辑只认「显式纳入」⇒ 新数据源刚同步完表结构（ai_query_assets 还没有行）
            # 时交集为空，NL2SQL 的 prompt 里一张表都没有 → 模型开始「编表名」。
            # 现在：没治理过的表**默认纳入**（同步即可用，界面上标「未治理」），
            # 用户显式排除的仍然排除——这与前端「纳入」列的口径一致（见 integration/index.vue）。
            seen: dict[str, bool] = {}
            for row in (
                await db.execute(
                    _t(
                        "SELECT table_name, included FROM ai_query_assets WHERE is_deleted=false"
                    )
                )
            ).fetchall():
                seen[str(row[0]).upper()] = bool(row[1])
            rows = [r for r in rows if seen.get(str(r.table_name).upper(), True)]
    return [
        {
            "table": r.table_name,
            "comment": r.table_comment or "",
            # 每列现算 is_audit（存储的 columns 可能来自旧 schema，名字判定更可靠）
            "columns": [
                (
                    {**c, "is_audit": is_audit_field(c.get("name", ""), rules)}
                    if isinstance(c, dict)
                    else c
                )
                for c in (r.columns or [])
            ],
            "is_system": is_system_table(r.table_name, rules),
        }
        for r in rows
    ]


async def _assert_ds_access(datasource_id: int, auth) -> None:
    """校验当前用户是否有权访问该自定义数据源；超管/未限角色直接放行。"""
    ds = await _svc()._load_ds(datasource_id)
    allowed = ds.allowed_roles or []
    if not allowed:
        return
    if getattr(getattr(auth, "user", None), "is_superuser", False):
        return
    if not (_svc()._user_role_codes(auth) & set(allowed)):
        raise CustomException(msg="您无权限访问该数据源")
