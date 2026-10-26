"""执行步骤表（插件自建，不走 alembic）。

一次派活 = 一个 ``run_id``，里面按 ``seq`` 记录每一步：
``plan``（规划/思考）、``tool``（工具调用）、``reply``（成员回话）、``summary``（汇总）。

前端据此画"对话式时间线"：图标 + 类型 + 标题 + 耗时，点开看参数/结果。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text as _t

from app.core.database import async_db_session


def _as_dt(v):
    """raw SQL 读回来的时间统一成 datetime。

    PostgreSQL（asyncpg）直接给 datetime；SQLite 存的是文本、且 raw SQL 没有类型信息，
    读回来是 str —— 之前只有 PG 跑得通，SQLite 下 ``.strftime`` 会 AttributeError。
    """
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


_ENSURED = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_run_steps ("
    "id VARCHAR(40) PRIMARY KEY, "
    "run_id VARCHAR(40), "
    "seq INTEGER, "
    "agent_id INTEGER, "
    "agent_name VARCHAR(128), "
    "kind VARCHAR(16), "
    "title VARCHAR(255), "
    "detail TEXT, "
    "duration_ms INTEGER, "
    "ok BOOLEAN, "
    "created_time TIMESTAMP)"
)


async def ensure_steps() -> None:
    global _ENSURED
    if _ENSURED:
        return
    async with async_db_session.begin() as db:
        await db.execute(_t(_DDL))
    _ENSURED = True


async def add(
    run_id: str,
    seq: int,
    kind: str,
    title: str,
    agent_id: int | None = None,
    agent_name: str | None = None,
    detail: str | None = None,
    duration_ms: int | None = None,
    ok: bool = True,
) -> None:
    """记一步；失败只告警，不影响主流程。"""
    try:
        await ensure_steps()
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "INSERT INTO ai_run_steps "
                    "(id, run_id, seq, agent_id, agent_name, kind, title, detail, duration_ms, ok, created_time) "
                    "VALUES (:i, :r, :s, :a, :n, :k, :t, :d, :m, :o, :c)"
                ),
                {
                    "i": uuid.uuid4().hex,
                    "r": (run_id or "")[:40],
                    "s": int(seq),
                    "a": int(agent_id) if agent_id else None,
                    "n": (agent_name or "")[:120],
                    "k": (kind or "plan")[:16],
                    "t": (title or "")[:250],
                    "d": (detail or "")[:4000],
                    "m": int(duration_ms or 0),
                    "o": bool(ok),
                    "c": datetime.now(),
                },
            )
    except Exception as e:  # noqa: BLE001
        from app.core.logger import logger

        logger.warning(f"[run_steps] 写入失败: {str(e)[:120]}")


async def list_steps(run_id: str | None = None, agent_id: int | None = None, limit: int = 60) -> list[dict]:
    """取最近一次（或指定）run 的步骤；不给 run_id 时取最近 3 个 run 的全部步骤。"""
    await ensure_steps()
    params: dict = {}

    # 给了 agent 就找"他最近参与的 run"，然后返回这条 run 的全部步骤
    # （否则只看得到他本人那几步，看不到组员的回话）
    if agent_id and not run_id:
        async with async_db_session() as db:
            run_id = (
                await db.execute(
                    _t(
                        "SELECT run_id FROM ai_run_steps WHERE agent_id = :a "
                        "ORDER BY created_time DESC LIMIT 1"
                    ),
                    {"a": int(agent_id)},
                )
            ).scalar()

    sql = (
        "SELECT run_id, seq, agent_id, agent_name, kind, title, detail, duration_ms, ok, created_time "
        "FROM ai_run_steps"
    )
    where = []
    if run_id:
        where.append("run_id = :r")
        params["r"] = run_id
    if agent_id and not run_id:
        where.append("agent_id = :a")
        params["a"] = int(agent_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_time DESC, seq ASC LIMIT :l"
    params["l"] = max(1, min(int(limit or 60), 200))
    async with async_db_session() as db:
        rows = (await db.execute(_t(sql), params)).fetchall()
    out = [
        {
            "run_id": r[0],
            "seq": r[1],
            "agent_id": r[2],
            "agent_name": r[3],
            "kind": r[4],
            "title": r[5],
            "detail": r[6],
            "duration_ms": r[7],
            "ok": bool(r[8]),
            "time": (_as_dt(r[9]).strftime("%H:%M:%S") if _as_dt(r[9]) else ""),
        }
        for r in rows
    ]
    return out


async def today_stats() -> dict:
    """今日派活统计（按 ``run_id`` 聚合，和任务列表同一口径）。

    与 ``ai_call_logs`` 的调用次数不同：一次派活里每个成员都算一次调用，
    但用户眼里的"派活"是一轮 —— 所以统计条用这个。
    """
    from datetime import datetime as _dt

    await ensure_steps()
    since = _dt.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sql = _t(
        "SELECT run_id, MIN(created_time), MAX(created_time), "
        "SUM(CASE WHEN kind = 'error' THEN 1 ELSE 0 END) "
        "FROM ai_run_steps WHERE created_time >= :s GROUP BY run_id"
    )
    async with async_db_session() as db:
        rows = (await db.execute(sql, {"s": since})).fetchall()

    total = len(rows)
    errors = 0
    durs: list[int] = []
    last = None
    for r in rows:
        if int(r[3] or 0) > 0:
            errors += 1
        t0, t1 = _as_dt(r[1]), _as_dt(r[2])
        if t0 and t1:
            durs.append(int((t1 - t0).total_seconds() * 1000))
            if last is None or t1 > last:
                last = t1
    return {
        "total": total,
        "errors": errors,
        "error_rate": round(errors * 100 / total, 1) if total else 0.0,
        "avg_ms": int(sum(durs) / len(durs)) if durs else 0,
        "last_time": last.strftime("%H:%M") if last else None,
    }


async def list_runs(
    page_no: int = 1,
    page_size: int = 20,
    date: str | None = None,
    days: int = 30,
    agent_name: str | None = None,
    status: str | None = None,
) -> dict:
    """任务列表：一次派活 = 一条（按 run_id 聚合，分页返回）。

    - ``date``：只看某一天（``YYYY-MM-DD``）；
    - 不传 ``date`` 时看最近 ``days`` 天（默认 30）；
    - 返回 ``{page_no, page_size, total, has_next, items}``，与项目分页口径一致。

    ``status``：``ok``（有 summary）/ ``error``（有 error 步）/ ``running``（还没收尾）。
    """
    from datetime import timedelta

    await ensure_steps()

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date 需要 YYYY-MM-DD") from None
        since = day
        until = day + timedelta(days=1)
    else:
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=max(0, int(days or 1) - 1)
        )
        until = None

    where = "WHERE created_time >= :s"
    params: dict = {"s": since}
    if until is not None:
        where += " AND created_time < :u"
        params["u"] = until

    page_no = max(1, int(page_no or 1))
    page_size = max(1, min(int(page_size or 20), 100))

    # 成员 / 状态筛选是「聚合成一条之后」再过滤，所以用 HAVING
    having: list[str] = []
    if agent_name:
        having.append("SUM(CASE WHEN agent_name = :ag THEN 1 ELSE 0 END) > 0")
        params["ag"] = agent_name
    if status == "ok":
        having.append("MAX(CASE WHEN kind = 'summary' THEN 1 ELSE 0 END) = 1")
    elif status == "error":
        having.append("MAX(CASE WHEN kind = 'error' THEN 1 ELSE 0 END) = 1")
    elif status == "running":
        having.append("MAX(CASE WHEN kind IN ('summary', 'error') THEN 1 ELSE 0 END) = 0")
    having_sql = (" HAVING " + " AND ".join(having)) if having else ""

    sql_total = (
        "SELECT COUNT(*) FROM (SELECT run_id FROM ai_run_steps "
        f"{where} GROUP BY run_id{having_sql}) t"
    )
    sql_page = (
        "SELECT run_id, MIN(created_time), MAX(created_time), COUNT(*) AS steps, "
        "MAX(CASE WHEN kind = 'plan' THEN detail END) AS prompt, "
        "MAX(CASE WHEN kind IN ('summary', 'error') THEN kind END) AS last_kind, "
        "MAX(CASE WHEN kind = 'plan' THEN agent_name END) AS leader, "
        "MAX(CASE WHEN kind = 'error' THEN detail END) AS err "
        f"FROM ai_run_steps {where} GROUP BY run_id{having_sql} "
        "ORDER BY MIN(created_time) DESC LIMIT :l OFFSET :o"
    )
    sql_agents = (
        f"SELECT run_id, agent_name FROM ai_run_steps {where} "
        "GROUP BY run_id, agent_name ORDER BY MIN(created_time) ASC"
    )

    async with async_db_session() as db:
        total = int((await db.execute(_t(sql_total), params)).scalar() or 0)
        rows = (
            await db.execute(
                _t(sql_page), {**params, "l": page_size, "o": (page_no - 1) * page_size}
            )
        ).fetchall()
        agent_rows = (await db.execute(_t(sql_agents), params)).fetchall()

    agents: dict[str, list[str]] = {}
    for r in agent_rows:
        if r[1]:
            agents.setdefault(r[0], []).append(r[1])

    items: list[dict] = []
    for r in rows:
        last_kind = r[5]
        status = "ok" if last_kind == "summary" else ("error" if last_kind == "error" else "running")
        # 卡死的 running（服务重启 / 进程被杀 / 浏览器强关后旧版本没兜底）：
        # 超过 10 分钟没有任何新步骤就按"已中断"展示，否则任务列表永远转圈、
        # AI 办公室的提示条也一直挂着"执行中"。
        t_min, t_max = _as_dt(r[1]), _as_dt(r[2])
        stale = bool(
            status == "running"
            and t_max
            and (datetime.now() - t_max).total_seconds() > 600
        )
        if stale:
            status = "error"
        items.append(
            {
                "run_id": r[0],
                "started": t_min.strftime("%m-%d %H:%M") if t_min else "",
                "started_time": t_min.strftime("%H:%M:%S") if t_min else "",
                "duration_ms": int((t_max - t_min).total_seconds() * 1000)
                if t_min and t_max
                else 0,
                "steps": int(r[3] or 0),
                "prompt": " ".join((r[4] or "").split())[:200],
                "status": status,
                "stale": stale,
                "leader": r[6] or "",
                # 失败原因（列表里直接能看到，不用点开）
                "error": " ".join((r[7] or "").split())[:200],
                "agents": agents.get(r[0], []),
            }
        )

    return {
        "page_no": page_no,
        "page_size": page_size,
        "total": total,
        "has_next": page_no * page_size < total,
        "items": items,
    }
