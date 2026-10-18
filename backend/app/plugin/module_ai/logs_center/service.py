"""AI 调用日志查询服务（复用 ai_call_logs）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, func, or_, select

from app.core.database import async_db_session
from app.core.logger import log
from app.plugin.module_ai.overview.model import AiCallLogModel


def _log_dict(r: AiCallLogModel) -> dict:
    return {
        "id": r.id,
        "model_name": r.model_name,
        "usage": r.usage,
        "latency_ms": r.latency_ms,
        "result": r.result,
        "error": r.error,
        "app_id": r.app_id,
        "user_id": r.user_id,
        "created_time": r.created_time,
    }


class AiLogService:

    @classmethod
    async def page(
        cls,
        page_no: int = 1,
        page_size: int = 10,
        usage: str | None = None,
        result: str | None = None,
        keyword: str | None = None,
    ) -> dict:
        page_no = max(int(page_no or 1), 1)
        page_size = max(int(page_size or 10), 1)
        async with async_db_session() as db:
            stmt = select(AiCallLogModel).where(AiCallLogModel.is_deleted.is_(False))
            if usage:
                stmt = stmt.where(AiCallLogModel.usage == usage)
            if result:
                stmt = stmt.where(AiCallLogModel.result == result)
            if keyword:
                like = f"%{keyword}%"
                stmt = stmt.where(
                    or_(
                        AiCallLogModel.model_name.like(like),
                        AiCallLogModel.error.like(like),
                    )
                )
            total = int(
                await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            )
            rows = (
                await db.execute(
                    stmt.order_by(
                        desc(AiCallLogModel.created_time), desc(AiCallLogModel.id)
                    )
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page_no,
                "page_size": page_size,
                "total": total,
                "has_next": page_no * page_size < total,
                "items": [_log_dict(r) for r in rows],
            }

    @classmethod
    async def stats(cls, days: int = 7) -> dict:
        """调用日志统计：总量/成功率/耗时 + 按模型/用途分布 + 按日趋势。"""
        since = datetime.now() - timedelta(days=max(int(days or 7), 1))
        base = select(AiCallLogModel).where(
            AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since
        )
        async with async_db_session() as db:
            total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
            success = int(
                await db.scalar(
                    select(func.count()).select_from(AiCallLogModel).where(
                        AiCallLogModel.is_deleted.is_(False),
                        AiCallLogModel.created_time >= since,
                        AiCallLogModel.result == "success",
                    )
                )
                or 0
            )
            error = total - success
            avg_latency = await db.scalar(
                select(func.avg(AiCallLogModel.latency_ms)).where(
                    AiCallLogModel.is_deleted.is_(False),
                    AiCallLogModel.created_time >= since,
                )
            )
            max_latency = await db.scalar(
                select(func.max(AiCallLogModel.latency_ms)).where(
                    AiCallLogModel.is_deleted.is_(False),
                    AiCallLogModel.created_time >= since,
                )
            )
            by_model = (
                await db.execute(
                    select(AiCallLogModel.model_name, func.count().label("n"))
                    .where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
                    .group_by(AiCallLogModel.model_name)
                    .order_by(func.count().desc())
                )
            ).all()
            by_usage = (
                await db.execute(
                    select(AiCallLogModel.usage, func.count().label("n"))
                    .where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
                    .group_by(AiCallLogModel.usage)
                    .order_by(func.count().desc())
                )
            ).all()
            trend = (
                await db.execute(
                    select(
                        func.date(AiCallLogModel.created_time).label("d"),
                        func.count().label("n"),
                        func.count().filter(AiCallLogModel.result == "error").label("e"),
                    )
                    .where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
                    .group_by(func.date(AiCallLogModel.created_time))
                    .order_by(func.date(AiCallLogModel.created_time))
                )
            ).all()
        return {
            "total": total,
            "success": success,
            "error": error,
            "success_rate": round(success / total, 4) if total else 0,
            "avg_latency_ms": round(float(avg_latency), 1) if avg_latency else 0,
            "max_latency_ms": int(max_latency or 0),
            "by_model": [{"name": r[0] or "—", "count": int(r[1])} for r in by_model],
            "by_usage": [{"name": r[0] or "—", "count": int(r[1])} for r in by_usage],
            "trend": [
                {"date": str(r[0]), "count": int(r[1]), "error": int(r[2])} for r in trend
            ],
        }

    @classmethod
    async def console_overview(cls, recent_limit: int = 20) -> dict:
        """控制台调用概览（全量计数/今日/成功率/7 日趋势/按模型含 tokens·成本/最近明细）。

        调用日志聚合的唯一实现，供 `/overview/stats` 复用，避免与 overview 重复 SQL；
        职责边界：`logs_center` 独占 `ai_call_logs` 的读取、统计与明细。
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        since = datetime.now() - timedelta(days=7)
        async with async_db_session() as db:
            calls = await db.scalar(
                select(func.count())
                .select_from(AiCallLogModel)
                .where(AiCallLogModel.is_deleted.is_(False))
            )
            errors = await db.scalar(
                select(func.count())
                .select_from(AiCallLogModel)
                .where(
                    AiCallLogModel.is_deleted.is_(False),
                    AiCallLogModel.result == "error",
                )
            )
            avg_latency = await db.scalar(
                select(func.avg(AiCallLogModel.latency_ms)).where(
                    AiCallLogModel.is_deleted.is_(False),
                    AiCallLogModel.result == "success",
                )
            )
            today = await db.scalar(
                select(func.count())
                .select_from(AiCallLogModel)
                .where(
                    AiCallLogModel.is_deleted.is_(False),
                    AiCallLogModel.created_time >= today_start,
                )
            )
            trend_rows = (
                await db.execute(
                    select(
                        func.date(AiCallLogModel.created_time).label("d"),
                        func.count().label("n"),
                        func.count().filter(AiCallLogModel.result == "error").label("e"),
                    )
                    .where(
                        AiCallLogModel.is_deleted.is_(False),
                        AiCallLogModel.created_time >= since,
                    )
                    .group_by(func.date(AiCallLogModel.created_time))
                    .order_by(func.date(AiCallLogModel.created_time))
                )
            ).all()
            by_model_rows = (
                await db.execute(
                    select(
                        AiCallLogModel.model_name,
                        func.count().label("n"),
                        func.count().filter(AiCallLogModel.result == "error").label("e"),
                        func.sum(AiCallLogModel.prompt_tokens).label("pt"),
                        func.sum(AiCallLogModel.completion_tokens).label("ct"),
                        func.sum(AiCallLogModel.cost).label("cost"),
                    )
                    .where(AiCallLogModel.is_deleted.is_(False))
                    .group_by(AiCallLogModel.model_name)
                    .order_by(func.count().desc())
                )
            ).all()
            rows = (
                await db.execute(
                    select(AiCallLogModel)
                    .where(AiCallLogModel.is_deleted.is_(False))
                    .order_by(desc(AiCallLogModel.id))
                    .limit(recent_limit)
                )
            ).scalars().all()
        calls = int(calls or 0)
        errors = int(errors or 0)
        return {
            "calls": calls,
            "errors": errors,
            "avg_latency_ms": int(avg_latency or 0),
            "today_calls": int(today or 0),
            "success_rate": round((calls - errors) / calls, 4) if calls else 0,
            "trend": [
                {"date": str(r[0]), "count": int(r[1]), "error": int(r[2])}
                for r in trend_rows
            ],
            "by_model": [
                {
                    "name": r[0] or "—",
                    "count": int(r[1]),
                    "error": int(r[2]),
                    "prompt_tokens": int(r[3] or 0),
                    "completion_tokens": int(r[4] or 0),
                    "cost": float(r[5] or 0.0),
                }
                for r in by_model_rows
            ],
            "recent_calls": [_log_dict(r) for r in rows],
        }

    @classmethod
    async def stats_by_app(cls, usage: str = "agent") -> dict[int, dict]:
        """按 ``app_id`` 聚合调用量/错误数/平均延迟（跨模块取数入口）。

        职责边界：``ai_call_logs`` 的读取/统计**只在本模块实现**，其他模块（如 Agent
        运行看板）一律经本接口取数，不直读表（守卫见 tests/test_call_logs_ownership.py）。
        统计失败返回空表而非抛错：看板不该因为统计查不到就整体挂掉（与历史行为一致）。
        """
        out: dict[int, dict] = {}
        try:
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        select(
                            AiCallLogModel.app_id,
                            func.count().label("n"),
                            func.count().filter(AiCallLogModel.result == "error").label("e"),
                            func.avg(AiCallLogModel.latency_ms).label("lat"),
                        )
                        .where(
                            AiCallLogModel.usage == usage,
                            AiCallLogModel.app_id.isnot(None),
                            AiCallLogModel.is_deleted.is_(False),
                        )
                        .group_by(AiCallLogModel.app_id)
                    )
                ).fetchall()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[logs_center] 按应用聚合调用日志失败: {str(e)[:120]}")
            return out
        for r in rows:
            out[int(r[0])] = {
                "runs": int(r[1] or 0),
                "errors": int(r[2] or 0),
                "avg_latency": int(r[3] or 0),
            }
        return out

    @classmethod
    async def export(cls, days: int = 30, usage: str | None = None, result: str | None = None) -> list[dict]:
        """导出日志（供前端生成 CSV）。"""
        since = datetime.now() - timedelta(days=max(int(days or 30), 1))
        stmt = select(AiCallLogModel).where(
            AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since
        )
        if usage:
            stmt = stmt.where(AiCallLogModel.usage == usage)
        if result:
            stmt = stmt.where(AiCallLogModel.result == result)
        async with async_db_session() as db:
            rows = (
                await db.execute(stmt.order_by(desc(AiCallLogModel.created_time)))
            ).scalars().all()
        return [_log_dict(r) for r in rows]
