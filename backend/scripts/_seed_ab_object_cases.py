"""注入「对象查询 A/B」题集（B 半 · 系统库），gold_sql 先执行核对。

对象：annotation_dataset/annotation_task、ai_apps/ai_call_logs/ai_models。
每题 gold_sql 会先执行取回 rows，若执行失败则拒绝写入（保证 gold 可控）。

用法（backend 下）::

    python scripts/_seed_ab_object_cases.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

# (question, gold_sql, form, scenario, difficulty)
CASES = [
    ("所有标注任务按状态各有多少个", "SELECT status AS 状态, count(*) AS 任务数 FROM annotation_task GROUP BY status ORDER BY status",
     "对象聚合", "数据标注", "medium"),
    ("已完成状态的标注任务一共有多少个", "SELECT count(*) AS 已完成任务数 FROM annotation_task WHERE status='completed'",
     "对象聚合", "数据标注", "easy"),
    ("标注任务按任务类型各有多少个", "SELECT task_type AS 任务类型, count(*) AS 任务数 FROM annotation_task GROUP BY task_type ORDER BY task_type",
     "对象聚合", "数据标注", "medium"),
    ("每个标注数据集各有多少图片", "SELECT name AS 数据集名称, image_count AS 图片数 FROM annotation_dataset ORDER BY name",
     "对象明细", "数据标注", "easy"),
    ("标注数据集里已标注数最多的是哪个，有多少", "SELECT name AS 数据集名称, annotated_count AS 已标注数 FROM annotation_dataset ORDER BY annotated_count DESC LIMIT 1",
     "对象TopN", "数据标注", "medium"),
    ("沿数据集查其标注任务，任务按状态各有多少个", "SELECT status AS 状态, count(*) AS 任务数 FROM annotation_task GROUP BY status ORDER BY status",
     "对象遍历聚合", "数据标注", "medium"),
    ("模型调用日志按状态各有多少条", "SELECT status AS 状态, count(*) AS 调用次数 FROM ai_call_logs GROUP BY status ORDER BY status",
     "对象聚合", "模型调用分析", "medium"),
    ("每个模型被调用了多少次", "SELECT model_name AS 模型名, count(*) AS 调用次数 FROM ai_call_logs GROUP BY model_name ORDER BY 调用次数 DESC",
     "对象聚合", "模型调用分析", "medium"),
    ("模型调用日志的平均延迟是多少", "SELECT round(avg(latency_ms), 2) AS 平均延迟 FROM ai_call_logs",
     "对象聚合", "模型调用分析", "easy"),
    ("启用状态的AI应用有哪些", "SELECT name AS 应用名 FROM ai_apps WHERE enabled=true ORDER BY name",
     "对象明细", "应用管理", "easy"),
    # ---------- 新增：视频告警（alarm_type 是明确枚举维度，数据量最大且干净） ----------
    ("视频告警按告警类型各有多少条", "SELECT alarm_type AS 告警类型, count(*) AS 告警数 FROM video_alarm_records GROUP BY alarm_type ORDER BY 告警数 DESC",
     "对象聚合", "视频告警分析", "medium"),
    ("审计类告警一共有多少条", "SELECT count(*) AS 审计告警数 FROM video_alarm_records WHERE alarm_type='AUDIT'",
     "对象聚合", "视频告警分析", "easy"),
    ("入侵类告警有多少条", "SELECT count(*) AS 入侵告警数 FROM video_alarm_records WHERE alarm_type='INTRUSION'",
     "对象聚合", "视频告警分析", "easy"),
    ("视频告警记录总共有多少条", "SELECT count(*) AS 告警总数 FROM video_alarm_records",
     "对象聚合", "视频告警分析", "easy"),
    # ---------- 新增：annotation_dataset（252 非删，干净） ----------
    ("标注数据集一共有多少个", "SELECT count(*) AS 数据集总数 FROM annotation_dataset WHERE COALESCE(is_deleted,false)=false",
     "对象聚合", "数据标注", "easy"),
    ("图片数最多的标注数据集是哪个", "SELECT name AS 数据集名称, image_count AS 图片数 FROM annotation_dataset WHERE COALESCE(is_deleted,false)=false ORDER BY image_count DESC LIMIT 1",
     "对象TopN", "数据标注", "medium"),
    ("所有标注数据集的图片总共有多少张", "SELECT sum(image_count) AS 图片总数 FROM annotation_dataset WHERE COALESCE(is_deleted,false)=false",
     "对象聚合", "数据标注", "medium"),
    # ---------- 新增：annotation_task 状态/类型（干净明确） ----------
    ("待处理的标注任务有多少个", "SELECT count(*) AS 待处理任务数 FROM annotation_task WHERE status='pending'",
     "对象聚合", "数据标注", "easy"),
    ("进行中的标注任务有多少个", "SELECT count(*) AS 进行中任务数 FROM annotation_task WHERE status='in_progress'",
     "对象聚合", "数据标注", "easy"),
    ("检测类型的标注任务有多少个", "SELECT count(*) AS 检测任务数 FROM annotation_task WHERE task_type='DETECTION'",
     "对象聚合", "数据标注", "easy"),
]


async def main() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_set import ensure_eval_tables, list_cases, upsert_case

    await ensure_eval_tables()
    n_ok = 0
    for q, gold, form, scenario, diff in CASES:
        # 执行 gold 核对（能跑通且返回非空）
        try:
            async with async_db_session() as db:
                res = (await db.execute(text(gold))).fetchall()
        except Exception as e:  # noqa: BLE001
            print(f"✗ gold 失败：{q}  {str(e)[:80]}")
            continue
        if not res:
            print(f"? gold 返回空：{q}")
        await upsert_case({
            "question": q, "gold_sql": gold, "datasource": "system",
            "difficulty": diff, "scenario": scenario, "form": form,
            "notes": "split:B;对象查询A/B;gold_verified",
        })
        n_ok += 1
        print(f"✓ {q}  (gold rows={len(res)})")
    print(f"\n写入 {n_ok} 条")
    # 回读 B 半 · system
    cs = await list_cases()
    b = [c for c in cs if str(c.get("split") or "").upper() == "B"
         and (c.get("datasource") or "system") == "system"]
    print(f"当前 B 半 · system 题数 = {len(b)}")


asyncio.run(main())
