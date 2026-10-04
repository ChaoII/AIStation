"""智能问数 精度/速度 基准测试（HTTP 客户端版）。

运行（需后端已启动在 8001）：
    uv run python -m app.plugin.module_ai.query.benchmark

报告：
- 语义精度：问题解析到的指标 key 与期望一致的比例。
- 快路径命中率：走模板快路径的比例。
- 执行成功率：非错误返回的比例。
- 速度：快路径 P50/P95 延迟（ms）。

题集设计（工程化）：
- ``GOLDEN``（快路径）：基于指标语义库的模板题，语义 100% 确定；扩充多种口语/近义问法。
- ``NL2SQL_GOLDEN``（慢路径）：覆盖 自定义报表/复杂维度/联表/时间窗口/占比占比/窗口函数 等，
  每条含手写金标 SQL，按「结果数据行」与 LLM 生成 SQL 的执行结果比对（数据级精度）。
- 题集按 ``tag`` 分组，支持 ``--tag`` 运行指定类别，便于回归定位。
"""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = os.environ.get("ENVIRONMENT", "dev")

import asyncio
import statistics
import sys
import time

# Windows GBK 控制台无法打印 ✓ 等字符，强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

import httpx
from sqlalchemy import text

from app.core.database import async_db_session

BASE = "http://localhost:8001"
USERNAME = "admin"
PASSWORD = "123456"

# ---------------------------------------------------------------------------
# 快路径：指标语义库模板题（语义 100% 确定）
# ---------------------------------------------------------------------------
GOLDEN = [
    # 今日告警
    {"q": "今日告警数", "metric": "alert_count_today"},
    {"q": "今天报警多少条", "metric": "alert_count_today"},
    {"q": "今天一共产生了多少条告警", "metric": "alert_count_today"},
    {"q": "今天有多少个视频告警", "metric": "alert_count_today"},
    {"q": "今日产生了几条报警记录", "metric": "alert_count_today"},
    # 本月告警
    {"q": "本月告警数", "metric": "alert_count_month"},
    {"q": "这个月产生多少报警", "metric": "alert_count_month"},
    {"q": "这个月有多少条视频告警", "metric": "alert_count_month"},
    # 按类型分布
    {"q": "按告警类型分布", "metric": "alert_by_type"},
    {"q": "最近7天各类告警数量", "metric": "alert_by_type"},
    {"q": "各类告警类型的数量是", "metric": "alert_by_type"},
    {"q": "近一周各类型的告警分布", "metric": "alert_by_type"},
    # 在线摄像头
    {"q": "在线摄像头数", "metric": "camera_online_count"},
    {"q": "在线设备有几台", "metric": "camera_online_count"},
    {"q": "当前在线摄像头多少", "metric": "camera_online_count"},
    # 训练任务
    {"q": "训练任务总数", "metric": "train_task_count"},
    {"q": "一共创建了多少个训练任务", "metric": "train_task_count"},
    # 模型调用
    {"q": "近7天模型调用量", "metric": "call_count_7d"},
    # 用户数
    {"q": "系统用户数", "metric": "user_count"},
    {"q": "有多少用户", "metric": "user_count"},
    # 负向：不是简单指标的陈述/写操作，应走慢路径或拒答（不计入命中率统计，仅作稳健性观察）
]


# ---------------------------------------------------------------------------
# 慢路径（NL2SQL）金标集：使用真实业务数据，覆盖复杂报表场景。
# tag: 类别标签（用于分组回归）。gold: 手写正确 SQL（结果作为期望数据）。
# 注意：
#   - video_alarm_records / video_record_files / video_camera_groups 等无 is_deleted 软删字段
#   - 时间窗口用数据存在区间（2026-09-14 ~ 09-17）以保证结果非空
#   - 占比/平均用 ::numeric + ROUND 保证 Postgres 兼容与精度一致
# ---------------------------------------------------------------------------
NL2SQL_GOLDEN = [
    # ===== 单一维度统计 =====
    {"tag": "单维统计", "q": "按告警类型统计各类告警的数量",
     "gold": "SELECT alarm_type AS 类型, COUNT(*) AS 数量 FROM video_alarm_records GROUP BY alarm_type ORDER BY 数量 DESC"},
    {"tag": "单维统计", "q": "每一种告警类型分别有多少条",
     "gold": "SELECT alarm_type, COUNT(*) AS c FROM video_alarm_records GROUP BY alarm_type ORDER BY c DESC"},
    {"tag": "单维统计", "q": "告警数量最多的前5种类型",
     "gold": "SELECT alarm_type, COUNT(*) AS c FROM video_alarm_records GROUP BY alarm_type ORDER BY c DESC LIMIT 5"},
    {"tag": "单维统计", "q": "统计不同状态的告警数量",
     "gold": "SELECT status, COUNT(*) AS c FROM video_alarm_records GROUP BY status"},
    {"tag": "单维统计", "q": "按严重级别统计告警数量",
     "gold": "SELECT severity, COUNT(*) AS c FROM video_alarm_records GROUP BY severity"},
    {"tag": "单维统计", "q": "告警记录总数是多少",
     "gold": "SELECT COUNT(*) AS 总数 FROM video_alarm_records"},
    {"tag": "单维统计", "q": "去重后一共有多少种告警类型",
     "gold": "SELECT COUNT(DISTINCT alarm_type) AS c FROM video_alarm_records"},
    # ===== 联表 JOIN =====
    {"tag": "联表", "q": "每个摄像头各产生多少条告警",
     "gold": "SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(r.id) AS 告警数 FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY 摄像头 ORDER BY 告警数 DESC"},
    {"tag": "联表", "q": "列出发生过告警的摄像头名称及告警数",
     "gold": "SELECT c.name, COUNT(r.id) AS c FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY c.name ORDER BY c DESC"},
    {"tag": "联表", "q": "哪些摄像头从来没有产生过告警",
     "gold": "SELECT c.name FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id WHERE r.id IS NULL ORDER BY c.name"},
    {"tag": "联表", "q": "触发告警最多的前3条告警规则",
     "gold": "SELECT r.name, COUNT(a.id) AS c FROM video_alarm_rules r JOIN video_alarm_records a ON a.rule_id=r.id GROUP BY r.name ORDER BY c DESC LIMIT 3"},
    {"tag": "联表", "q": "各算法类型分别挂了多少任务",
     "gold": "SELECT alg.algorithm_type, COUNT(t.id) AS c FROM video_algorithms alg LEFT JOIN video_algorithm_tasks t ON t.algorithm_id=alg.id GROUP BY alg.algorithm_type ORDER BY c DESC"},
    {"tag": "联表", "q": "每个算法被多少个任务使用",
     "gold": "SELECT alg.name, COUNT(t.id) AS c FROM video_algorithms alg LEFT JOIN video_algorithm_tasks t ON t.algorithm_id=alg.id GROUP BY alg.name ORDER BY c DESC"},
    {"tag": "联表", "q": "每个边缘设备各产生多少边缘事件",
     "gold": "SELECT COALESCE(d.name,'未知') AS 设备, COUNT(e.id) AS c FROM video_edge_devices d LEFT JOIN video_edge_events e ON e.edge_code=d.code GROUP BY 设备 ORDER BY c DESC"},
    {"tag": "联表", "q": "每个摄像头各有多少边缘事件",
     "gold": "SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(e.id) AS c FROM video_cameras c LEFT JOIN video_edge_events e ON e.camera_id=c.id GROUP BY 摄像头 ORDER BY c DESC"},
    {"tag": "联表", "q": "每个标注数据集下各有多少标注任务",
     "gold": "SELECT ds.name, COUNT(t.id) AS c FROM annotation_dataset ds LEFT JOIN annotation_task t ON t.dataset_id=ds.id GROUP BY ds.name ORDER BY c DESC LIMIT 20"},
    {"tag": "联表", "q": "按摄像头组统计告警数",
     "gold": "SELECT COALESCE(g.name,'未分组') AS 摄像头组, COUNT(r.id) AS 告警数 FROM video_cameras c LEFT JOIN video_camera_groups g ON c.group_id=g.id LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY 摄像头组 ORDER BY 告警数 DESC"},
    # ===== 时间窗口 / 趋势 =====
    {"tag": "时间窗口", "q": "2026年9月15日到9月17日每天产生多少告警",
     "gold": "SELECT TO_CHAR(alarm_time,'YYYY-MM-DD') AS d, COUNT(*) AS c FROM video_alarm_records WHERE alarm_time >= '2026-09-15' AND alarm_time < '2026-09-18' GROUP BY d ORDER BY d"},
    {"tag": "时间窗口", "q": "9月16日当天共有多少条告警",
     "gold": "SELECT COUNT(*) AS c FROM video_alarm_records WHERE alarm_time >= '2026-09-16' AND alarm_time < '2026-09-17'"},
    {"tag": "时间窗口", "q": "统计2026年9月15日到17日按天、按类型的告警数量",
     "gold": "SELECT TO_CHAR(alarm_time,'YYYY-MM-DD') AS d, alarm_type, COUNT(*) AS c FROM video_alarm_records WHERE alarm_time >= '2026-09-15' AND alarm_time < '2026-09-18' GROUP BY d, alarm_type ORDER BY d, c DESC"},
    {"tag": "时间窗口", "q": "最近7天每天的告警数量",
     "gold": "SELECT TO_CHAR(alarm_time,'YYYY-MM-DD') AS 日期, COUNT(*) AS 告警数 FROM video_alarm_records WHERE alarm_time >= CURRENT_DATE - 7 GROUP BY 日期 ORDER BY 日期"},
    {"tag": "时间窗口", "q": "过去一个月各严重程度的告警数量",
     "gold": "SELECT COALESCE(severity,'未知') AS 级别, COUNT(*) AS 数量 FROM video_alarm_records WHERE alarm_time >= CURRENT_DATE - INTERVAL '1 month' GROUP BY 级别 ORDER BY 数量 DESC"},
    # ===== 边缘事件 =====
    {"tag": "边缘事件", "q": "各算法类型的边缘事件有多少",
     "gold": "SELECT COALESCE(algorithm_type,'未知') AS 算法类型, COUNT(*) AS 事件数 FROM video_edge_events GROUP BY 算法类型 ORDER BY 事件数 DESC"},
    {"tag": "边缘事件", "q": "匹配成功的边缘事件有多少条",
     "gold": "SELECT COUNT(*) AS c FROM video_edge_events WHERE matched = true"},
    {"tag": "边缘事件", "q": "没有被匹配上的边缘事件数量",
     "gold": "SELECT COUNT(*) AS c FROM video_edge_events WHERE matched = false"},
    {"tag": "边缘事件", "q": "边缘事件的平均处理延迟是多少毫秒",
     "gold": "SELECT ROUND(AVG(latency_ms)::numeric,2) AS avg_latency FROM video_edge_events WHERE latency_ms IS NOT NULL"},
    {"tag": "边缘事件", "q": "各算法类型的平均延迟，取前5名",
     "gold": "SELECT algorithm_type, ROUND(AVG(latency_ms)::numeric,2) AS a FROM video_edge_events WHERE latency_ms IS NOT NULL GROUP BY algorithm_type ORDER BY a DESC LIMIT 5"},
    {"tag": "边缘事件", "q": "处理延迟最高的10条边缘事件",
     "gold": "SELECT id, latency_ms FROM video_edge_events WHERE latency_ms IS NOT NULL ORDER BY latency_ms DESC LIMIT 10"},
    {"tag": "边缘事件", "q": "边缘事件每天有多少条",
     "gold": "SELECT date(ts) AS d, COUNT(*) AS c FROM video_edge_events GROUP BY d ORDER BY d"},
    # ===== 边缘设备 =====
    {"tag": "设备", "q": "列出当前离线的边缘设备",
     "gold": "SELECT name, code FROM video_edge_devices WHERE status='offline' ORDER BY name"},
    {"tag": "设备", "q": "在线和离线的边缘设备各有多少",
     "gold": "SELECT status, COUNT(*) AS c FROM video_edge_devices GROUP BY status"},
    {"tag": "设备", "q": "距上次心跳最久的10台边缘设备",
     "gold": "SELECT name, last_heartbeat FROM video_edge_devices ORDER BY last_heartbeat ASC NULLS LAST LIMIT 10"},
    # ===== 摄像头 =====
    {"tag": "摄像头", "q": "当前离线的摄像头有多少",
     "gold": "SELECT COUNT(*) AS c FROM video_cameras WHERE status='OFFLINE'"},
    {"tag": "摄像头", "q": "摄像头总数是多少",
     "gold": "SELECT COUNT(*) AS c FROM video_cameras WHERE is_deleted=false"},
    # ===== 标注 =====
    {"tag": "标注", "q": "各类标注任务的数量",
     "gold": "SELECT task_type, COUNT(*) AS c FROM annotation_task GROUP BY task_type ORDER BY c DESC"},
    {"tag": "标注", "q": "各状态下的标注任务数量",
     "gold": "SELECT status, COUNT(*) AS c FROM annotation_task GROUP BY status"},
    {"tag": "标注", "q": "列出进行中的标注任务",
     "gold": "SELECT name FROM annotation_task WHERE status='in_progress' ORDER BY name"},
    {"tag": "标注", "q": "所有图片的标注覆盖率是多少",
     "gold": "SELECT ROUND(SUM(annotated_count)*100.0/NULLIF(SUM(image_count),0),2) AS pct FROM annotation_dataset"},
    # ===== 合成任务 =====
    {"tag": "合成", "q": "合成任务总共有多少个",
     "gold": "SELECT COUNT(*) AS c FROM synthesis_job WHERE is_deleted=false"},
    {"tag": "合成", "q": "各合成算法供应商的完成总量",
     "gold": "SELECT provider, SUM(done) AS done, SUM(total) AS total FROM synthesis_job GROUP BY provider"},
    # ===== AI 调用日志 =====
    {"tag": "调用日志", "q": "平均每次模型调用耗时多少毫秒",
     "gold": "SELECT ROUND(AVG(latency_ms),1) AS ms, COUNT(*) AS n FROM ai_call_logs WHERE is_deleted=false"},
    {"tag": "调用日志", "q": "各模型分别被调用了多少次",
     "gold": "SELECT model_name, COUNT(*) AS c FROM ai_call_logs WHERE is_deleted=false GROUP BY model_name"},
    {"tag": "调用日志", "q": "调用耗时超过10秒的有多少次",
     "gold": "SELECT COUNT(*) AS c FROM ai_call_logs WHERE latency_ms > 10000"},
    {"tag": "调用日志", "q": "不同用途各调用多少次",
     "gold": "SELECT usage, COUNT(*) AS c FROM ai_call_logs WHERE is_deleted=false GROUP BY usage"},
    {"tag": "调用日志", "q": "最慢的一次模型调用是哪个模型，耗时多少",
     "gold": "SELECT model_name, latency_ms FROM ai_call_logs ORDER BY latency_ms DESC LIMIT 1"},
    # ===== 算法/任务 =====
    {"tag": "算法任务", "q": "当前正在运行的视频算法任务有多少",
     "gold": "SELECT COUNT(*) AS c FROM video_algorithm_tasks WHERE status='RUNNING'"},
    {"tag": "算法任务", "q": "各状态下的算法任务数量",
     "gold": "SELECT status, COUNT(*) AS c FROM video_algorithm_tasks GROUP BY status"},
    {"tag": "算法任务", "q": "运行失败的算法任务编号",
     "gold": "SELECT id FROM video_algorithm_tasks WHERE status='ERROR' ORDER BY id"},
    {"tag": "算法任务", "q": "各算法类型各有多少个算法",
     "gold": "SELECT algorithm_type, COUNT(*) AS c FROM video_algorithms GROUP BY algorithm_type ORDER BY c DESC"},
    # ===== 复杂多维自定义报表 =====
    {"tag": "多维报表", "q": "统计每个摄像头各类告警的数量",
     "gold": "SELECT c.name, r.alarm_type, COUNT(*) AS c FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY c.name, r.alarm_type ORDER BY c.name, c DESC"},
    {"tag": "多维报表", "q": "9月15号每个摄像头的告警数量",
     "gold": "SELECT c.name, COUNT(*) AS c FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id WHERE r.alarm_time >= '2026-09-15' AND r.alarm_time < '2026-09-16' GROUP BY c.name ORDER BY c DESC"},
    {"tag": "多维报表", "q": "告警中 DET_ZONE 类型占比多少",
     "gold": "SELECT ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM video_alarm_records),2) AS pct FROM video_alarm_records WHERE alarm_type='DET_ZONE'"},
    {"tag": "多维报表", "q": "在线摄像头占全部摄像头的比例",
     "gold": "SELECT ROUND(COUNT(*) FILTER (WHERE status='ONLINE')*100.0/COUNT(*),2) AS pct FROM video_cameras WHERE is_deleted=false"},
    {"tag": "多维报表", "q": "告警量最高的摄像头及数量",
     "gold": "SELECT c.name, COUNT(r.id) AS c FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY c.name ORDER BY c DESC LIMIT 1"},
    {"tag": "多维报表", "q": "平均每个摄像头产生多少条告警",
     "gold": "SELECT ROUND(COUNT(*)*1.0/COUNT(DISTINCT camera_id),1) AS avg_cam FROM video_alarm_records WHERE camera_id IS NOT NULL"},
    {"tag": "多维报表", "q": "运行中的算法任务对应哪些摄像头",
     "gold": "SELECT c.name, t.id FROM video_algorithm_tasks t LEFT JOIN video_cameras c ON c.id=t.camera_id WHERE t.status='RUNNING'"},
    {"tag": "多维报表", "q": "各摄像头告警数与边缘事件数对比，取告警最多前5",
     "gold": "SELECT c.name, COUNT(DISTINCT r.id) AS alarms, COUNT(DISTINCT e.id) AS events FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id LEFT JOIN video_edge_events e ON e.camera_id=c.id GROUP BY c.name ORDER BY alarms DESC LIMIT 5"},
    # ===== 窗口函数（高级） =====
    {"tag": "窗口函数", "q": "给每种告警类型按数量排名",
     "gold": "SELECT alarm_type, COUNT(*) AS c, ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn FROM video_alarm_records GROUP BY alarm_type ORDER BY rn"},
    {"tag": "窗口函数", "q": "各告警类型数量及累计占比",
     "gold": "SELECT alarm_type, COUNT(*) AS c, ROUND(100.0*SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC)/SUM(COUNT(*)) OVER (),2) AS cum_pct FROM video_alarm_records GROUP BY alarm_type ORDER BY c DESC"},
    {"tag": "窗口函数", "q": "按告警数量给摄像头排名",
     "gold": "SELECT c.name, COUNT(r.id) AS c, RANK() OVER (ORDER BY COUNT(r.id) DESC) AS rk FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY c.name ORDER BY rk"},
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


def run(client: httpx.Client, tag: str | None = None) -> dict:
    items = [x for x in GOLDEN if tag is None or x.get("tag") == tag]
    results = []
    for item in items:
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
    if n == 0:
        return {"total": 0, "semantic_accuracy": 0, "fast_path_rate": 0, "exec_ok_rate": 0,
                "p50_ms": 0, "p95_ms": 0, "results": []}
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


async def _run_gold(sql: str) -> list:
    """执行手写金标 SQL，返回排序后的行元组列表作为期望结果。"""
    async with async_db_session() as db:
        result = await db.execute(text(sql))
        rows = [tuple(str(v) for v in r) for r in result.fetchall()]
    return sorted(rows)


def _norm(rows: list) -> list:
    return sorted(tuple(str(v) for v in r) for r in rows)


async def run_nl2sql(client: httpx.Client, tag: str | None = None) -> dict:
    items = [x for x in NL2SQL_GOLDEN if tag is None or x.get("tag") == tag]
    results = []
    for i, item in enumerate(items, 1):
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
        correct = actual == expected and not d.get("is_error")
        results.append(
            {
                "q": item["q"], "tag": item.get("tag"), "correct": correct,
                "path": d.get("path"), "ok": not d.get("is_error") and r.status_code == 200,
                "ms": round(ms, 1), "n_rows": len(actual),
                "sql": d.get("sql", ""),
            }
        )
        print(f"  [{i}/{len(items)}] {'✓' if correct else '✗'} {item['q']} ({ms:.0f}ms)", flush=True)
    n = len(results)
    if n == 0:
        return {"total": 0, "accuracy": 0, "slow_rate": 0, "p50_ms": 0,
                "by_tag": {}, "results": []}
    acc = sum(1 for x in results if x["correct"]) / n
    slow_rate = sum(1 for x in results if x["path"] == "slow") / n
    ms_all = [x["ms"] for x in results]
    by_tag: dict[str, dict] = {}
    for x in results:
        t = x.get("tag") or "未分类"
        b = by_tag.setdefault(t, {"total": 0, "correct": 0})
        b["total"] += 1
        b["correct"] += 1 if x["correct"] else 0
    for b in by_tag.values():
        b["acc"] = round(b["correct"] / b["total"], 3)
    return {
        "total": n, "accuracy": round(acc, 3), "slow_rate": round(slow_rate, 3),
        "p50_ms": round(statistics.median(ms_all), 1) if ms_all else 0,
        "by_tag": by_tag, "results": results,
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
            f"  {mark} {x['q']:<20} -> {str(x['resolved'] or ''):<22} "
            f"期望={x['expected']:<22} 路径={x['path']} 耗时={x['ms']}ms"
        )
    print("===============================\n")


def print_nl2sql_report(rep: dict) -> None:
    print("\n===== 生成SQL(NL2SQL/慢路径) Benchmark 报告 =====")
    print(f"题目数: {rep['total']}")
    print(f"结果数据精度(与金标一致): {rep['accuracy']:.1%}")
    print(f"走 LLM 慢路径占比:      {rep['slow_rate']:.1%}")
    print(f"全程 P50: {rep['p50_ms']} ms")
    if rep.get("by_tag"):
        print("\n--- 分类精度 ---")
        for tag, b in sorted(rep["by_tag"].items()):
            print(f"  {tag:<10} {b['correct']}/{b['total']} = {b['acc']:.1%}")
    print("\n--- 逐题明细 ---")
    for x in rep["results"]:
        mark = "✓" if x["correct"] else "✗ "
        print(
            f"  {mark} {x['q']:<24} 路径={x['path']} 行数={x['n_rows']} 耗时={x['ms']}ms"
        )
        if not x["correct"]:
            print(f"      SQL: {x['sql']}")
    print("===============================\n")


if __name__ == "__main__":
    tag = None
    for a in sys.argv[1:]:
        if a.startswith("--tag="):
            tag = a.split("=", 1)[1]
    if sys.argv and "nl2sql" not in sys.argv and "fast" not in sys.argv:
        mode = "all"
    else:
        mode = "all"
    if "--nl2sql" in sys.argv:
        mode = "nl2sql"
    if "--fast" in sys.argv:
        mode = "fast"

    token = login()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=BASE, headers=headers, timeout=120) as client:
        if mode in ("all", "fast"):
            # 预热：触发系统种子与缓存，让后续测的是稳态延迟
            client.post(
                "/api/v1/ai/query/ask",
                json={"question": "今日告警数", "session_id": None, "datasource": "system"},
            )
            fast_rep = run(client, tag)
            print_report(fast_rep)
        if mode in ("all", "nl2sql"):
            if tag is None:
                print(f"慢路径预测 | 共 {len(NL2SQL_GOLDEN)} 题，每题约 6s，请稍候...")
            nl2sql_rep = asyncio.run(run_nl2sql(client, tag))
            print_nl2sql_report(nl2sql_rep)
