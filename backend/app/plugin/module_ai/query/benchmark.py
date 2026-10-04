"""智能问数 精度/速度 基准测试（HTTP 客户端版）。

运行（需后端已启动在 8001）：
    uv run python -m app.plugin.module_ai.query.benchmark

报告：
- 语义精度：问题解析到的指标 key 与期望一致的比例。
- 快路径命中率：走模板快路径的比例。
- 执行成功率：非错误返回的比例。
- 速度：快路径 P50/P95 延迟（ms）。
"""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = os.environ.get("ENVIRONMENT", "dev")

import asyncio
import statistics
import time

import httpx
from sqlalchemy import text

from app.core.database import async_db_session

BASE = "http://localhost:8001"
USERNAME = "admin"
PASSWORD = "123456"

GOLDEN = [
    {"q": "今日告警数", "metric": "alert_count_today"},
    {"q": "今天报警多少条", "metric": "alert_count_today"},
    {"q": "本月告警数", "metric": "alert_count_month"},
    {"q": "这个月产生多少报警", "metric": "alert_count_month"},
    {"q": "按告警类型分布", "metric": "alert_by_type"},
    {"q": "最近7天各类告警数量", "metric": "alert_by_type"},
    {"q": "在线摄像头数", "metric": "camera_online_count"},
    {"q": "在线设备有几台", "metric": "camera_online_count"},
    {"q": "训练任务总数", "metric": "train_task_count"},
    {"q": "近7天模型调用量", "metric": "call_count_7d"},
    {"q": "系统用户数", "metric": "user_count"},
    {"q": "有多少用户", "metric": "user_count"},
]


def login() -> str:
    r = httpx.post(
        f"{BASE}/api/v1/system/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=20,
    )
    j = r.json()
    token = j.get("data", {}).get("access_token") or j.get("data", {}).get("token") or ""
    if not token:
        raise RuntimeError(f"登录失败: {j}")
    return token


def run(client: httpx.Client) -> dict:
    results = []
    for item in GOLDEN:
        t0 = time.perf_counter()
        r = client.post(
            "/api/v1/ai/query/ask",
            json={"question": item["q"], "session_id": None, "datasource": "system"},
        )
        ms = (time.perf_counter() - t0) * 1000
        j = r.json()
        d = j.get("data") or {}
        results.append(
            {
                "q": item["q"], "expected": item["metric"],
                "resolved": (d.get("metric") or {}).get("key"),
                "correct": (d.get("metric") or {}).get("key") == item["metric"],
                "path": d.get("path"), "ok": not d.get("is_error") and r.status_code == 200,
                "ms": round(ms, 1),
            }
        )

    n = len(results)
    sem = sum(1 for x in results if x["correct"]) / n
    fast = sum(1 for x in results if x["path"] == "fast") / n
    ok = sum(1 for x in results if x["ok"]) / n
    fast_ms = [x["ms"] for x in results if x["path"] == "fast" and x["ms"] is not None]
    p50 = statistics.median(fast_ms) if fast_ms else 0
    fast_ms_sorted = sorted(fast_ms)
    p95 = fast_ms_sorted[min(int(len(fast_ms_sorted) * 0.95), len(fast_ms_sorted) - 1)] if fast_ms else 0
    return {
        "total": n, "semantic_accuracy": round(sem, 3), "fast_path_rate": round(fast, 3),
        "exec_ok_rate": round(ok, 3), "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
        "results": results,
    }


# ---------------------------------------------------------------------------
# 生成 SQL（慢路径 NL2SQL）金标集：使用真实告警数据（1489 条/55 摄像头/多类型）
# gold 为手写正确 SQL，用于比对 LLM 生成 SQL 的结果是否一致（数据级精度）。
# ---------------------------------------------------------------------------
NL2SQL_GOLDEN = [
    {
        "q": "按告警类型统计各类告警的数量",
        "gold": ("SELECT alarm_type AS 类型, COUNT(*) AS 数量 FROM video_alarm_records "
                 "GROUP BY 类型 ORDER BY 数量 DESC LIMIT 50"),
    },
    {
        "q": "按严重程度统计告警的分布情况",
        "gold": ("SELECT COALESCE(severity,'未知') AS 级别, COUNT(*) AS 数量 "
                 "FROM video_alarm_records GROUP BY 级别 ORDER BY 数量 DESC LIMIT 50"),
    },
    {
        "q": "每个摄像头各产生多少条告警",
        "gold": ("SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(r.id) AS 告警数 "
                 "FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id "
                 "GROUP BY 摄像头 ORDER BY 告警数 DESC LIMIT 50"),
    },
    {
        "q": "告警记录总数是多少",
        "gold": "SELECT COUNT(*) AS 总数 FROM video_alarm_records",
    },
]


async def _run_gold(sql: str) -> list:
    """执行手写金标 SQL，返回排序后的行元组列表作为期望结果。"""
    async with async_db_session() as db:
        result = await db.execute(text(sql))
        rows = [tuple(str(v) for v in r) for r in result.fetchall()]
    return sorted(rows)


def _norm(rows: list) -> list:
    return sorted(tuple(str(v) for v in r) for r in rows)


async def run_nl2sql(client: httpx.Client) -> dict:
    results = []
    for item in NL2SQL_GOLDEN:
        expected = await _run_gold(item["gold"])
        t0 = time.perf_counter()
        r = client.post(
            "/api/v1/ai/query/ask",
            json={"question": item["q"], "session_id": None, "datasource": "system",
                  "force_slow": True},
        )
        ms = (time.perf_counter() - t0) * 1000
        j = r.json()
        d = j.get("data") or {}
        actual = _norm(d.get("rows") or [])
        # 精度：LLM 生成 SQL 的结果与金标一致（忽略列名/顺序，按数据行比较）
        correct = actual == expected and not d.get("is_error")
        results.append(
            {
                "q": item["q"], "correct": correct, "path": d.get("path"),
                "ok": not d.get("is_error") and r.status_code == 200,
                "ms": round(ms, 1), "n_rows": len(actual),
            }
        )
    n = len(results)
    acc = sum(1 for x in results if x["correct"]) / n
    slow_rate = sum(1 for x in results if x["path"] == "slow") / n
    ms_all = [x["ms"] for x in results]
    return {
        "total": n, "accuracy": round(acc, 3), "slow_rate": round(slow_rate, 3),
        "p50_ms": round(statistics.median(ms_all), 1) if ms_all else 0,
        "results": results,
    }


def print_report(rep: dict) -> None:
    print("\n===== 智能问数 Benchmark 报告 =====")
    print(f"题目数: {rep['total']}")
    print(f"语义精度(正确指标): {rep['semantic_accuracy']:.1%}")
    print(f"快路径命中率:        {rep['fast_path_rate']:.1%}")
    print(f"执行成功率:          {rep['exec_ok_rate']:.1%}")
    print(f"快路径 P50: {rep['p50_ms']} ms   P95: {rep['p95_ms']} ms")
    print("\n--- 逐题明细 ---")
    for x in rep["results"]:
        mark = "✓" if x["correct"] else "✗ "
        print(
            f"  {mark} {x['q']:<16} -> {str(x['resolved'] or ''):<22} "
            f"期望={x['expected']:<22} 路径={x['path']} 耗时={x['ms']}ms"
        )
    print("===============================\n")


def print_nl2sql_report(rep: dict) -> None:
    print("\n===== 生成SQL(NL2SQL/慢路径) Benchmark 报告 =====")
    print(f"题目数: {rep['total']}")
    print(f"结果数据精度(与金标一致): {rep['accuracy']:.1%}")
    print(f"走 LLM 慢路径占比:      {rep['slow_rate']:.1%}")
    print(f"全程 P50: {rep['p50_ms']} ms")
    print("\n--- 逐题明细 ---")
    for x in rep["results"]:
        mark = "✓" if x["correct"] else "✗ "
        print(
            f"  {mark} {x['q']:<22} 路径={x['path']} 行数={x['n_rows']} 耗时={x['ms']}ms"
        )
    print("===============================\n")


if __name__ == "__main__":
    token = login()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=BASE, headers=headers, timeout=60) as client:
        # 预热：触发系统种子与缓存，让后续测的是稳态延迟
        client.post(
            "/api/v1/ai/query/ask",
            json={"question": "今日告警数", "session_id": None, "datasource": "system"},
        )
        fast_rep = run(client)
        print_report(fast_rep)
        nl2sql_rep = asyncio.run(run_nl2sql(client))
        print_nl2sql_report(nl2sql_rep)
