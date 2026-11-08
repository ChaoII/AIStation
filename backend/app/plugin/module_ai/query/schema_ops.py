"""Schema 上下文：系统库 / 外部库 / 取值 / 枚举提示（2026-11-08 从 service.py 拆出）。

四个**进程级缓存**（都归 ``service.py``，这里读写一律走 ``_svc.``）：
- ``_SCHEMA_CACHE``：系统库 schema（整体一份，重建时整体替换）；
- ``_DS_SCHEMA_CACHE`` / ``_DS_SCHEMA_TTL``：外部库 schema，按数据源分桶；
- ``_DS_TYPE_CACHE``：外部库方言探测结果；
- ``_ENUM_HINT_CACHE`` / ``_ENUM_HINT_TTL``：枚举字段真实取值（注入提示词用，默认关）。

⚠️ 搬移时**不要**写 ``global``：只会建本模块的新变量，service 的缓存永远不更新
（表现为「改了资产/同步了 schema，问数还是旧表结构」）。赋值也要写 ``_svc._SCHEMA_CACHE = ...``。
"""
from __future__ import annotations

import json
import re
import time

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .model import AiQueryAssetColumnModel, AiQueryAssetModel


class SchemaOps:
    @classmethod
    async def _system_schema(cls) -> dict:
        """拉取系统可查表的真实列（带类型）+ 资产目录筛选/中文描述。

        仅纳入数据资产目录中 included 的表/字段；字段有中文描述时附加，敏感字段标注。
        未同步资产目录时回退到内置白名单。结果缓存到进程级。
        """
        if _svc._SCHEMA_CACHE is not None:
            return _svc._SCHEMA_CACHE
        # 1) 资产目录（已纳入的表 + 字段描述/敏感）
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            asset_rows = (
                await db.execute(
                    _sel(AiQueryAssetModel).where(
                        AiQueryAssetModel.included.is_(True),
                        AiQueryAssetModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            col_rows = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.included.is_(True),
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
        if asset_rows:
            tables = {a.table_name for a in asset_rows}
        else:
            tables = set(_svc.SYSTEM_ALLOWED_TABLES)
        colmap = {(c.table_name, c.column_name): c for c in col_rows}
        # 2) 拉真实列类型
        async with async_db_session() as db:
            from sqlalchemy import text as _text

            result = await db.execute(
                _text(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' ORDER BY table_name, ordinal_position"
                )
            )
            rows = result.fetchall()
        schema: dict[str, list[str]] = {}
        coltype: dict[tuple[str, str], str] = {}
        for t, c, ty in rows:
            if t not in tables:
                continue
            coltype[(t, c)] = (ty or "").lower()
            label = f"{c}({ty})"
            ac = colmap.get((t, c))
            if ac and ac.description:
                label += f"【{ac.description}】"
            if ac and ac.related_table and ac.related_field:
                label += f"【关联:{ac.related_table}.{ac.related_field}】"
            if ac and ac.sensitive:
                label += "[敏感]"
            schema.setdefault(t, []).append(label)
        # 3) 低基数枚举列：注入真实取值，帮助 LLM 使用正确枚举值（如 status=ERROR/RUNNING/STOPPED）
        try:
            cfg = await cls._cfg()
            # 默认值必须与其它三处（本文件 8534/8790/10320 行）一致 = False：
            # 这里以前写 True，一旦设置行缺失，**系统库**会去远端跑一堆 DISTINCT，
            # 而同一开关在别处却是关的 —— 同一开关两种默认值，行为会随"哪条路径先跑"而变。
            if not cls._cfg_bool(cfg, "enum_hint_enabled", False):
                _svc._SCHEMA_CACHE = schema
                return schema
            _enum_re = re.compile(
                r"(^|_)(status|framework|severity|task_type|kind|usage|scene_type|state|result|level|format|stream_type)$",
                re.IGNORECASE,
            )
            from sqlalchemy import text as _text2

            async with async_db_session() as db:
                # 人工维护的字段枚举优先（ai_query_asset_columns.enum）：人工枚举 > 真实库 DISTINCT
                manual_enum: dict = {}
                try:
                    from sqlalchemy import select as _sel2

                    _rows = (
                        await db.execute(
                            _sel2(
                                AiQueryAssetColumnModel.table_name,
                                AiQueryAssetColumnModel.column_name,
                                AiQueryAssetColumnModel.enum,
                            ).where(AiQueryAssetColumnModel.is_deleted.is_(False))
                        )
                    ).all()
                    for _tn, _cn, _ev in _rows:
                        _vs = _ev if isinstance(_ev, list) else (json.loads(_ev) if _ev else [])
                        if _vs:
                            manual_enum[(_tn, _cn)] = [str(x) for x in _vs]
                except Exception:  # noqa: BLE001
                    manual_enum = {}
                for t, labels in list(schema.items()):
                    for i, lab in enumerate(labels):
                        c = lab.split("(")[0]
                        if not _enum_re.search(c):
                            continue
                        # 跳过 json/jsonb/text/数组等高基数/大字段，避免把大段数据写入 prompt
                        if coltype.get((t, c)) in {
                            "json", "jsonb", "text", "bytea", "character varying[]",
                            "jsonb[]", "uuid",
                        }:
                            continue
                        # 人工维护的枚举优先，其次回退真实库 DISTINCT
                        _me = manual_enum.get((t, c))
                        if _me:
                            labels[i] = lab + f"【取值:{','.join(_me[:16])}】"
                            continue
                        try:
                            vals = await db.execute(
                                _text2(
                                    f'SELECT DISTINCT "{c}" AS v FROM "{t}" '
                                    f'WHERE "{c}" IS NOT NULL LIMIT 16'
                                )
                            )
                            vs = [str(r[0]) for r in vals.fetchall() if r[0] is not None]
                            if vs:
                                labels[i] = lab + f"【取值:{','.join(vs)}】"
                        except Exception:  # noqa: BLE001
                            continue
        except Exception:  # noqa: BLE001
            pass

        # 4) 字段关联增强：外键列标注「关联目标表的名称列」，帮助模型 JOIN 后直接 SELECT 名称
        def _name_col_of(rt: str) -> str | None:
            cols = [c for (t, c) in coltype if t == rt]
            for cand in ("name", "title", "label", "camera_name", "algorithm_name", "dataset_name", "device_name"):
                if cand in cols:
                    return cand
            for cand in cols:
                if coltype.get((rt, cand)) in {"character varying", "varchar", "text"}:
                    return cand
            return None

        for _t, _labels in schema.items():
            for _i, _lab in enumerate(_labels):
                _c = _lab.split("(")[0]
                _ac = colmap.get((_t, _c))
                if not (_ac and _ac.related_table and _ac.related_field):
                    continue
                _name_col = _name_col_of(_ac.related_table)
                if _name_col and _name_col != _c:
                    _labels[_i] = _lab + f"➜{_ac.related_table}.{_name_col}"

        _svc._SCHEMA_CACHE = schema
        return schema

    @classmethod
    async def _ds_schema_map(
        cls, datasource: str, strict: bool = False
    ) -> dict[str, list[str]]:
        """自定义数据源已同步的表结构：``{表名: [列标签]}``。

        与 ``_system_schema`` 同形，方便复用同一套关键词检索（``_relevant_tables``）。
        带进程内缓存——331 张表的同步结果每次问答都读库太浪费。

        ``strict=True`` 时读取失败**上抛**：enforce 的权限判定不能把"读不到元数据"
        当成"没有列级限制"（那是 fail-open），由 guard 转成 deny。
        """
        key = str(datasource or "")
        hit = _svc._DS_SCHEMA_CACHE.get(key)
        if hit and time.time() - hit[0] <= _svc._DS_SCHEMA_TTL:
            return hit[1]
        out: dict[str, list[str]] = {}
        types: dict[str, dict[str, str]] = {}
        try:
            ds_id = int(key.split(":")[-1])
            # **只取已纳入资产目录的表**：范围收敛到关键业务表，
            # 避免 SYS_*/_BAK 等技术表混进检索与 prompt（实测污染召回）。
            rows = await _svc.list_ds_schema(ds_id, included_only=True)
            for r in rows:
                cols = []
                # 表注释放第一位，形如 `FUEL_CB_COALBALANCE(燃煤采购结算主表)`：
                # 既让检索能按中文表名命中，也让模型在 prompt 里看到业务含义
                tcmt = str(r.get("comment") or "").strip()
                if tcmt:
                    cols.append(f"{r['table']}({tcmt})")
                for c in (r.get("columns") or []):
                    if not isinstance(c, dict) or not c.get("name"):
                        continue
                    label = str(c["name"])
                    if c.get("comment"):
                        label += f"({c['comment']})"
                    cols.append(label)
                    if c.get("type"):
                        types.setdefault(r["table"], {})[str(c["name"])] = str(c["type"])
                out[r["table"]] = cols
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 读取数据源 {key} 表结构失败: {e}")
            if strict:
                raise
            return {}
        if len(_svc._DS_SCHEMA_CACHE) >= 20:
            _svc._DS_SCHEMA_CACHE.clear()
        _svc._DS_SCHEMA_CACHE[key] = (time.time(), out)
        _svc._DS_TYPE_CACHE[key] = (time.time(), types)
        return out

    @classmethod
    async def _ds_value_map(cls, datasource: str, tables: list[str],
                            ds_schema: dict[str, list[str]]) -> dict[tuple[str, str], list[str]]:
        """取「低基数列 → 真实取值列表」（(表, 列) → 值），供**值匹配纠错**与枚举提示共用。

        口径规范里一直写着「枚举字段必须使用【取值】里给出的原始值」，但此前没有代码
        产出它。这里从数据里取：只取前 5 张表、每表最多 2 个候选列、每列最多 8 个值，
        过滤技术列与长文本，结果按 (数据源, 表集合) 缓存 10 分钟。
        """
        import asyncio as _asyncio

        cache_key = "|".join([datasource or ""] + sorted(tables))
        hit = _svc._ENUM_HINT_CACHE.get(cache_key)
        if hit and time.time() - hit[0] <= _svc._ENUM_HINT_TTL:
            return hit[1]

        out: dict[tuple[str, str], list[str]] = {}
        try:
            ds = await _svc._load_ds(int(str(datasource).split(":")[-1]))
            cfg = _svc._ds_cfg_from_model(ds)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 取值映射：数据源不可用: {str(e)[:80]}")
            return {}

        async def _one(table: str) -> dict[tuple[str, str], list[str]]:
            cands = []
            for lab in ds_schema.get(table, []):
                col = lab.split("(", 1)[0]
                if cls._ENUM_COL_RE.match(col) and not col.startswith(cls._ENUM_SKIP_PREFIX):
                    cands.append(col)
                if len(cands) >= 2:
                    break
            if not cands:
                return {}
            subs = []
            for c in cands:
                # 分支里的 ORDER BY/LIMIT 必须加括号，否则 UNION ALL 语法错
                subs.append(
                    f"(SELECT '{c}' AS c, \"{c}\"::text AS v, COUNT(*) AS n FROM \"{table}\" "
                    f'WHERE "{c}" IS NOT NULL GROUP BY 2 ORDER BY 3 DESC LIMIT 9)')
            try:
                from . import executor as _ex

                res = await _asyncio.wait_for(
                    _ex.execute_select(cfg, " UNION ALL ".join(subs)), timeout=8)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 取 {table} 列取值失败（忽略）: {str(e)[:90]}")
                return {}
            got: dict[tuple[str, str], list[str]] = {}
            tmp: dict[str, list[str]] = {}
            for c, v, _n in (res.get("rows") or []):
                tmp.setdefault(str(c), []).append(str(v))
            for c, vals in tmp.items():
                if not (2 <= len(vals) <= 8):        # 单值无意义；9 行说明基数更高
                    continue
                if any(len(v) > 24 for v in vals):   # 长文本不注入/不纠错
                    continue
                got[(table, c)] = vals
            return got

        try:
            groups = await _asyncio.gather(*[_one(t) for t in tables[:5]], return_exceptions=True)
        except Exception:  # noqa: BLE001
            groups = []
        for g in groups:
            if isinstance(g, dict):
                out.update(g)
        if len(_svc._ENUM_HINT_CACHE) >= 200:
            _svc._ENUM_HINT_CACHE.clear()
        _svc._ENUM_HINT_CACHE[cache_key] = (time.time(), out)
        return out

    @classmethod
    async def _ds_enum_hints(cls, datasource: str, tables: list[str],
                             ds_schema: dict[str, list[str]]) -> list[str]:
        """把取值映射渲染成 prompt 里的【字段取值】块（默认关，实测无收益）。"""
        vmap = await cls._ds_value_map(datasource, tables, ds_schema)
        return [f"- {t}.{c}: {'、'.join(vals[:8])}" for (t, c), vals in vmap.items()]
