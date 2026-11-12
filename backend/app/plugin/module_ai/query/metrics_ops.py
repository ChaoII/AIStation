"""指标 / 术语 / 语义建模（2026-11-08 从 service.py 拆出）。

指标与术语是快慢两条路径共享的语义层底座：``list_metrics`` / ``upsert_metric``
定义口径，``list_terms`` / ``upsert_term`` 维护业务词表，``generate_modeling`` 用 LLM
把一句话口径变成指标定义，``promote_message_to_metric`` 把一次问答沉淀成指标。

``_norm_datasource`` / ``_system_allowed`` / ``validate_sql`` 仍留在 ``service.py``，
这里用**延迟转发**包装（导入期直接 import 会循环）。延迟导入也让测试对
``service._norm_datasource`` 之类的 monkeypatch 继续生效。
"""
from __future__ import annotations

import re

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from . import service as _svc
from .model import (
    AiQueryDictionaryModel,
    AiQueryMessageModel,
    AiQueryMetricModel,
    AiQuerySessionModel,
)

#: 与 service 同值（搬移期间重复定义，避免循环导入）
SYSTEM_DS = "system"


async def _norm_datasource(datasource):
    """延迟转发到 service 的实现（service 导入期未就绪）。"""
    from .service import _norm_datasource as _impl

    return await _impl(datasource)


async def _system_allowed():
    """延迟转发到 service 的实现（service 导入期未就绪）。"""
    from .service import _system_allowed as _impl

    return await _impl()


def validate_sql(*args, **kwargs):
    """延迟转发到 service 的实现（service 导入期未就绪）。"""
    from .service import validate_sql as _impl

    return _impl(*args, **kwargs)


def _to_metric_dict(m: AiQueryMetricModel) -> dict:
    # 绑定型指标（object_code + agg_fn）：不展示占位 SQL，改为展示「绑定对象/属性/聚合」口径。
    obj_code = getattr(m, "object_code", "") or ""
    prop_code = getattr(m, "property_code", "") or ""
    agg_fn = getattr(m, "agg_fn", "") or ""
    sql_template = m.sql_template
    if obj_code and agg_fn and (not sql_template or "SELECT 1" in (sql_template or "")):
        sql_template = f"绑定对象:{obj_code} 属性:{prop_code or '(整对象)'} 聚合:{agg_fn}"
    return {
        "id": m.id, "datasource": m.datasource, "key": m.key, "name": m.name,
        "description": m.description or "", "sql_template": sql_template,
        "params": m.params or [], "dimensions": m.dimensions or [], "agg": m.agg,
        "unit": m.unit or "", "permission_tag": m.permission_tag or "",
        "enabled": m.enabled, "sort": m.sort or 0, "cache_ttl": m.cache_ttl or 0,
        # 指标 ↔ 本体绑定（S1）
        "object_code": obj_code,
        "property_code": prop_code,
        "agg_fn": agg_fn,
        "bound_dimensions": getattr(m, "bound_dimensions", None) or [],
    }


class MetricsOps:
    @classmethod
    async def set_metric_enabled(cls, key: str, enabled: bool, auth=None) -> dict:
        """指标体检用：只改启用开关（不动口径），避免为了停用一条脏指标重传整份模板。"""
        from sqlalchemy import text as _t

        from app.core.database import async_db_session

        k = str(key or "").strip()
        if not k:
            raise ValueError("key 不能为空")
        async with async_db_session.begin() as db:
            res = await db.execute(_t(
                "UPDATE ai_query_metrics SET enabled=:e, updated_time=now() "
                "WHERE key=:k AND is_deleted=false"
            ), {"e": bool(enabled), "k": k})
            if not res.rowcount:
                raise ValueError("指标不存在")
        return {"key": k, "enabled": bool(enabled)}

    @classmethod
    async def stats(cls) -> dict:
        async with async_db_session() as db:
            from sqlalchemy import func, or_, select

            # 不计评测会话：评测会走同一条 ask 链路，混进来使用统计就失真了
            base = (
                select(func.count())
                .select_from(AiQueryMessageModel)
                .outerjoin(AiQuerySessionModel,
                           AiQuerySessionModel.id == AiQueryMessageModel.session_id)
                .where(
                    AiQueryMessageModel.is_deleted.is_(False),
                    or_(AiQuerySessionModel.is_eval.is_(False),
                        AiQuerySessionModel.is_eval.is_(None)),
                )
            )
            total = (await db.execute(base)).scalar_one()
            fast = (await db.execute(
                base.where(AiQueryMessageModel.path == "fast"))).scalar_one()
            errors = (await db.execute(
                base.where(AiQueryMessageModel.is_error.is_(True)))).scalar_one()
        return {
            "total": total, "fast": fast, "slow": max(0, total - fast),
            "errors": errors, "ok": max(0, total - errors),
        }

    @classmethod
    async def run_metric(cls, metric_key: str, datasource: str | None, params: dict, auth) -> dict:
        metrics = await cls.list_metrics(datasource)
        metric = next((m for m in metrics if m["key"] == metric_key), None)
        if not metric:
            raise CustomException(msg=f"指标「{metric_key}」不存在")
        res = await _svc._execute_metric(metric, params or {}, auth)
        return res

    @classmethod
    async def delete_metric(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for mid in ids:
                m = await db.get(AiQueryMetricModel, mid)
                if m:
                    await db.delete(m)

    @classmethod
    async def delete_term(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for tid in ids:
                t = await db.get(AiQueryDictionaryModel, tid)
                if t:
                    await db.delete(t)

    @classmethod
    async def list_metrics(cls, datasource: str | None = None) -> list[dict]:
        await cls.ensure_system_seed()
        datasource = await _norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import select

            q = select(AiQueryMetricModel).where(AiQueryMetricModel.is_deleted.is_(False))
            if datasource:
                q = q.where(AiQueryMetricModel.datasource == datasource)
            q = q.order_by(AiQueryMetricModel.datasource, AiQueryMetricModel.sort, AiQueryMetricModel.id)
            rows = (await db.execute(q)).scalars().all()
            return [_to_metric_dict(m) for m in rows]

    @classmethod
    async def upsert_metric(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryMetricModel).where(
                        AiQueryMetricModel.datasource == data.datasource,
                        AiQueryMetricModel.key == data.key,
                        AiQueryMetricModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for k in ("name", "description", "sql_template", "params", "dimensions",
                          "agg", "unit", "permission_tag", "enabled", "sort", "cache_ttl",
                          "object_code", "property_code", "agg_fn", "bound_dimensions"):
                    setattr(existing, k, getattr(data, k))
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryMetricModel(
                    datasource=data.datasource, key=data.key, name=data.name,
                    description=data.description, sql_template=data.sql_template,
                    params=data.params, dimensions=data.dimensions, agg=data.agg,
                    unit=data.unit, permission_tag=data.permission_tag,
                    enabled=data.enabled, sort=data.sort, cache_ttl=data.cache_ttl,
                    object_code=data.object_code, property_code=data.property_code,
                    agg_fn=data.agg_fn, bound_dimensions=data.bound_dimensions,
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return _to_metric_dict(obj)

    @classmethod
    async def generate_modeling(cls, kind: str, datasource: str, auth,
                                max_objects: int = 12, dry: bool = False,
                                offset: int = 0) -> dict:
        """触发大模型自动建模（``kind``：``metrics`` / ``annotate``），并失效语义缓存。

        建模会**写指标/对象/属性** → 必须失效缓存，否则前端与问数看不到刚生成的内容
        （`_SETTINGS_CACHE`/`_SEMANTIC_INDEX`/`_ASSET_TMETA` 均为进程内缓存）。
        """
        # 三个缓存是 **service 模块** 的进程级全局；搬进 mixin 后必须显式回写
        # service，否则只是在本模块建了三个新变量，前端永远看不到新指标。
        from . import modeling as _m
        from . import service as _svc

        datasource = await _norm_datasource(datasource)

        if kind == "metrics":
            out = await _m.generate_metrics(datasource, auth, max_objects=max_objects,
                                            dry=dry, offset=offset)
        elif kind == "annotate":
            out = await _m.generate_annotations(datasource, auth, max_objects=max_objects,
                                                offset=offset)
        else:
            raise CustomException(msg=f"未知建模类型：{kind}")
        if not dry:
            _svc._SETTINGS_CACHE = None
            _svc._SEMANTIC_INDEX = None
            _svc._ASSET_TMETA = None
        return out

    @classmethod
    async def promote_message_to_metric(cls, message_id: int, name: str, key: str, auth) -> dict:
        """FDE 复用闭环：把一条已验证问答沉淀为「可复用指标」（确定性快路径）。

        校验 SQL 合法后落为系统指标，并把该问题登记为术语（黑话→指标），
        下次同类问题直接走快路径（100%、秒级），不再依赖 LLM 生成。
        """
        name = (name or "").strip()
        key = (key or "").strip()
        if not name or not key:
            raise CustomException(msg="请提供指标名称(key)与显示名(name)")
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            raise CustomException(msg="指标 key 仅允许字母/数字/下划线")
        async with async_db_session.begin() as db:
            from sqlalchemy import select as _sel

            m = await db.get(AiQueryMessageModel, message_id)
            if not m or not (m.sql or ""):
                raise CustomException(msg="问答记录无效或缺少 SQL")
            # 归属校验：message_id 只是自增主键，枚举即可命中他人问答。
            # 先按 session_id 反查会话并复用统一归属校验，再谈"沉淀成指标"。
            cls._ensure_session_owner(
                await db.get(AiQuerySessionModel, m.session_id), auth)
            try:
                validate_sql(m.sql, await _system_allowed())
            except CustomException as e:  # noqa: BLE001
                raise CustomException(msg=f"该 SQL 无法作为指标：{e}") from e
            existing = (
                await db.execute(
                    _sel(AiQueryMetricModel).where(
                        AiQueryMetricModel.datasource == SYSTEM_DS,
                        AiQueryMetricModel.key == key,
                        AiQueryMetricModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.name = name
                existing.sql_template = m.sql
                existing.enabled = True
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryMetricModel(
                    datasource=SYSTEM_DS, key=key, name=name,
                    description=f"由问答「{m.question[:40]}」沉淀", sql_template=m.sql,
                    params=[], dimensions=[], agg="count", unit="",
                    enabled=True, cache_ttl=60,
                    created_id=auth.user.id, updated_id=auth.user.id,
                ))
            # 把问题登记为术语（黑话 → 指标）
            term = (m.question or "").strip()[:128]
            if term:
                tex = (
                    await db.execute(
                        _sel(AiQueryDictionaryModel).where(
                            AiQueryDictionaryModel.datasource == SYSTEM_DS,
                            AiQueryDictionaryModel.term == term,
                            AiQueryDictionaryModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if tex:
                    tex.metric_key = key
                else:
                    db.add(AiQueryDictionaryModel(
                        datasource=SYSTEM_DS, term=term, metric_key=key,
                        field_path="", type="metric",
                    ))
            await db.flush()
            return {"key": key, "name": name, "term": term}

    # ---- 术语 ----

    @classmethod
    async def list_terms(cls, datasource: str | None = None) -> list[dict]:
        datasource = await _norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import select

            q = select(AiQueryDictionaryModel).where(AiQueryDictionaryModel.is_deleted.is_(False))
            if datasource:
                q = q.where(AiQueryDictionaryModel.datasource == datasource)
            rows = (await db.execute(q)).scalars().all()
            return [
                {"id": t.id, "datasource": t.datasource, "term": t.term,
                 "metric_key": t.metric_key or "", "field_path": t.field_path or "",
                 "type": t.type}
                for t in rows
            ]

    @classmethod
    async def upsert_term(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryDictionaryModel).where(
                        AiQueryDictionaryModel.datasource == data.datasource,
                        AiQueryDictionaryModel.term == data.term,
                        AiQueryDictionaryModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.metric_key = data.metric_key
                existing.field_path = data.field_path
                existing.type = data.type
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryDictionaryModel(
                    datasource=data.datasource, term=data.term, metric_key=data.metric_key,
                    field_path=data.field_path, type=data.type,
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return {"id": obj.id, "datasource": obj.datasource, "term": obj.term,
                    "metric_key": obj.metric_key or "", "field_path": obj.field_path or "",
                    "type": obj.type}

    # ---- 数据资产目录（表/字段筛选 + 中文描述维护）----
