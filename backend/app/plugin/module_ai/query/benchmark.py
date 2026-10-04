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

import statistics
import time

import httpx

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


def run() -> dict:
    token = login()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    results = []
    # 复用连接池，避免每请求新建连接的客户端开销
    with httpx.Client(base_url=BASE, headers=headers, timeout=60) as client:
        # 预热：触发系统种子与缓存，让后续测的是稳态延迟
        client.post("/api/v1/ai/query/ask", json={"question": "今日告警数", "session_id": None, "datasource": "system"})
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


if __name__ == "__main__":
    print_report(run())
