"""AI 集成开放平台 —— 调用概览（统计 / 配额用量 / 导出）。

只读查询，不写任何状态：
- :func:`DevelopInsights.stats`：今日概览 + 最近 N 天趋势 + Top 能力 + 应用/审批计数；
- :func:`DevelopInsights.usage`：某应用当日的按品类调用次数（配额用量可视化）；
- :func:`DevelopInsights.export_csv`：按筛选条件导出调用日志 CSV（上限 5000 行）。

说明：``created_time`` 为**本地 naive 时间**（应用自己写入），因此用
``func.date(created_time)`` 分组即可（SQLite / PostgreSQL 均支持）。
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.core.database import async_db_session

from .capabilities import CATEGORIES
from .model import (
    AiIntegrationAppModel,
    AiIntegrationApprovalModel,
    AiIntegrationCallLogModel,
)


class DevelopInsights:
    """调用概览与导出的只读查询。"""

    @classmethod
    async def stats(cls, days: int = 7) -> dict:
        """返回今日概览、最近 N 天趋势、Top 能力与全局计数。"""
        days = max(1, min(int(days or 7), 30))
        today = date.today()
        since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time())

        async with async_db_session() as db:
            # 今日概览（按状态聚合）
            today_rows = (
                await db.execute(
                    select(
                        AiIntegrationCallLogModel.status,
                        func.count().label("n"),
                        func.avg(AiIntegrationCallLogModel.latency_ms).label("avg_ms"),
                    )
                    .where(AiIntegrationCallLogModel.created_time >= datetime.combine(today, datetime.min.time()))
                    .group_by(AiIntegrationCallLogModel.status)
                )
            ).all()
            today_map = {row.status: int(row.n) for row in today_rows}
            total_today = sum(today_map.values())
            success = today_map.get("success", 0)
            latencies = (
                await db.execute(
                    select(func.avg(AiIntegrationCallLogModel.latency_ms)).where(
                        AiIntegrationCallLogModel.created_time >= datetime.combine(today, datetime.min.time()),
                        AiIntegrationCallLogModel.status == "success",
                    )
                )
            ).scalar()

            # 最近 N 天趋势（按自然日）
            day_col = func.date(AiIntegrationCallLogModel.created_time)
            series_rows = (
                await db.execute(
                    select(
                        day_col.label("day"),
                        AiIntegrationCallLogModel.status,
                        func.count().label("n"),
                    )
                    .where(AiIntegrationCallLogModel.created_time >= since)
                    .group_by(day_col, AiIntegrationCallLogModel.status)
                    .order_by(day_col)
                )
            ).all()
            series_map: dict[str, dict] = {}
            for row in series_rows:
                key = str(row.day)
                bucket = series_map.setdefault(
                    key, {"date": key, "calls": 0, "success": 0, "failed": 0, "denied": 0, "pending": 0}
                )
                bucket["calls"] += int(row.n)
                if row.status in bucket:
                    bucket[row.status] += int(row.n)
            # 补齐空缺日期（前端画柱状图不跳格）
            series = []
            for offset in range(days):
                key = str(today - timedelta(days=days - 1 - offset))
                series.append(
                    series_map.get(
                        key, {"date": key, "calls": 0, "success": 0, "failed": 0, "denied": 0, "pending": 0}
                    )
                )

            # Top 能力（最近 N 天）
            top_rows = (
                await db.execute(
                    select(
                        AiIntegrationCallLogModel.capability,
                        AiIntegrationCallLogModel.category,
                        func.count().label("n"),
                    )
                    .where(AiIntegrationCallLogModel.created_time >= since)
                    .group_by(
                        AiIntegrationCallLogModel.capability, AiIntegrationCallLogModel.category
                    )
                    .order_by(func.count().desc())
                    .limit(6)
                )
            ).all()

            # 应用 / 审批计数
            app_total = (
                await db.execute(
                    select(func.count()).select_from(AiIntegrationAppModel).where(
                        AiIntegrationAppModel.is_deleted.is_(False)
                    )
                )
            ).scalar() or 0
            app_enabled = (
                await db.execute(
                    select(func.count()).select_from(AiIntegrationAppModel).where(
                        AiIntegrationAppModel.is_deleted.is_(False),
                        AiIntegrationAppModel.enabled.is_(True),
                    )
                )
            ).scalar() or 0
            expiring = (
                await db.execute(
                    select(func.count()).select_from(AiIntegrationAppModel).where(
                        AiIntegrationAppModel.is_deleted.is_(False),
                        AiIntegrationAppModel.expire_at.is_not(None),
                        AiIntegrationAppModel.expire_at <= datetime.now() + timedelta(days=7),
                        AiIntegrationAppModel.expire_at >= datetime.now(),
                    )
                )
            ).scalar() or 0
            pending_approvals = (
                await db.execute(
                    select(func.count()).select_from(AiIntegrationApprovalModel).where(
                        AiIntegrationApprovalModel.status == "pending"
                    )
                )
            ).scalar() or 0

        return {
            "today": {
                "calls": total_today,
                "success": success,
                "failed": today_map.get("failed", 0),
                "denied": today_map.get("denied", 0),
                "pending": today_map.get("pending", 0),
                "success_rate": round(success / total_today, 4) if total_today else 0.0,
                "avg_latency_ms": int(latencies or 0),
            },
            "series": series,
            "top_capabilities": [
                {
                    "capability": row.capability,
                    "category": row.category,
                    "category_label": CATEGORIES.get(row.category, row.category),
                    "calls": int(row.n),
                }
                for row in top_rows
            ],
            "apps": {"total": int(app_total), "enabled": int(app_enabled), "expiring_soon": int(expiring)},
            "approvals": {"pending": int(pending_approvals)},
            "days": days,
        }

    @classmethod
    async def usage(cls, app_id: int, day: date | None = None) -> dict:
        """某应用当日各品类调用次数（与配额上限一起用于「今日已用」展示）。"""
        target = day or date.today()
        start = datetime.combine(target, datetime.min.time())
        end = start + timedelta(days=1)
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiIntegrationCallLogModel.category, func.count().label("n"))
                    .where(
                        AiIntegrationCallLogModel.app_id == app_id,
                        AiIntegrationCallLogModel.created_time >= start,
                        AiIntegrationCallLogModel.created_time < end,
                        # 审计之外的「待审批」也算一次调用意图
                        AiIntegrationCallLogModel.status != "rejected",
                    )
                    .group_by(AiIntegrationCallLogModel.category)
                )
            ).all()
        usage = {row.category: int(row.n) for row in rows}
        return {"date": str(target), "app_id": app_id, "usage": usage}

    @classmethod
    async def export_csv(
        cls,
        *,
        app_id: int | None = None,
        category: str | None = None,
        method: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 5000,
    ) -> str:
        """按筛选条件导出调用日志 CSV（UTF-8 BOM，Excel 可直接打开）。"""
        wheres = []
        if app_id is not None:
            wheres.append(AiIntegrationCallLogModel.app_id == app_id)
        if category:
            wheres.append(AiIntegrationCallLogModel.category == category)
        if method:
            wheres.append(AiIntegrationCallLogModel.method == method)
        if status:
            wheres.append(AiIntegrationCallLogModel.status == status)
        if start_time is not None:
            wheres.append(AiIntegrationCallLogModel.created_time >= start_time)
        if end_time is not None:
            wheres.append(AiIntegrationCallLogModel.created_time <= end_time)

        async with async_db_session() as db:
            stmt = select(AiIntegrationCallLogModel).order_by(
                AiIntegrationCallLogModel.id.desc()
            ).limit(max(1, min(int(limit), 5000)))
            if wheres:
                stmt = stmt.where(*wheres)
            rows = (await db.execute(stmt)).scalars().all()

        buf = io.StringIO()
        buf.write("\ufeff")  # BOM：Excel 直接识别 UTF-8
        writer = csv.writer(buf)
        writer.writerow(
            ["时间", "应用ID", "AppID", "品类", "能力", "出海口", "状态", "耗时(ms)", "Tokens", "请求路径", "结果摘要", "错误"]
        )
        for row in rows:
            writer.writerow(
                [
                    row.created_time.strftime("%Y-%m-%d %H:%M:%S") if row.created_time else "",
                    row.app_id,
                    row.appid,
                    CATEGORIES.get(row.category, row.category),
                    row.capability,
                    row.method,
                    row.status,
                    row.latency_ms,
                    row.cost_tokens,
                    row.request_path or "",
                    row.result_summary or "",
                    row.error or "",
                ]
            )
        return buf.getvalue()
