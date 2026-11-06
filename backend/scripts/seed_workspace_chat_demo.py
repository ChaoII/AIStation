"""造一份"多轮工具调用"的工作台会话，用来验证/调整对话页样式。

内容刻意包含：
- 一轮里调用 3 个工具（含 1 个失败）
- 连续两轮都调工具（多轮）
- 长度不一的消息，检查列表换行/省略

用法::

    python scripts/seed_workspace_chat_demo.py            # 建/覆盖演示会话
    python scripts/seed_workspace_chat_demo.py --clean    # 删掉演示会话
"""

import argparse
import asyncio
import json
import uuid

from sqlalchemy import text

from app.core.database import async_db_session

APP_ID = 4            # 智能体 id（/ai/workspace/chat/agent/4）
USER_ID = 1
TITLE = "【演示】多轮工具调用"


def _parts_tool(name: str, call_id: str, args: dict, out: dict | None = None,
                error: str | None = None) -> dict:
    if error:
        return {"type": f"tool-{name}", "toolCallId": call_id, "toolName": name,
                "state": "output-error", "input": args, "errorText": error}
    return {"type": f"tool-{name}", "toolCallId": call_id, "toolName": name,
            "state": "output-available", "input": args, "output": out or {}}


MESSAGES: list[tuple[str, list[dict]]] = [
    ("user", [{"type": "text", "text": "帮我查一下昨天有多少条告警，再按设备类型分一下。"}]),
    ("assistant", [
        _parts_tool("ontology_search", "c1", {"query": "告警 设备类型"}, {"hits": 3}),
        _parts_tool("query_metrics", "c2", {"metric": "alarm_count", "range": "昨天"},
                    {"value": 1489, "unit": "条"}),
        _parts_tool("sql_query", "c3", {"sql": "SELECT device_type, COUNT(*) FROM ..."},
                    None, "字段 device_type 不存在，已改用 type"),
        {"type": "text", "text": "昨天共 **1489** 条告警。按设备类型分布：摄像头 612 条、"
                                 "门禁 403 条、传感器 474 条。\n\n（第一次 SQL 用错了字段名，"
                                 "已自动改成 `type` 重试成功。）"},
    ]),
    ("user", [{"type": "text", "text": "那传感器里哪一类告警最多？给我一句结论。"}]),
    ("assistant", [
        _parts_tool("sql_query", "c4",
                    {"sql": "SELECT subtype, COUNT(*) c FROM alarms WHERE type='sensor' "
                            "GROUP BY 1 ORDER BY c DESC LIMIT 3"},
                    {"rows": [{"subtype": "温度越限", "c": 201},
                              {"subtype": "离线", "c": 168},
                              {"subtype": "电量低", "c": 105}]}),
        {"type": "text", "text": "传感器告警里 **温度越限** 最多，201 条。"},
    ]),
    ("user", [{"type": "text", "text": "把上面两条结论合成一段周报，不超过一百字。"}]),
    ("assistant", [
        {"type": "reasoning", "text": "用户要一段周报：需要合并告警总量、设备分布、传感器细分，"
                                      "控制在一百字内，语气正式。"},
        _parts_tool("write_note", "c5", {"title": "告警周报", "body": "..."}, {"ok": True}),
        {"type": "text", "text": "本周共收告警 1489 条，其中摄像头 612 条、门禁 403 条、"
                                 "传感器 474 条；传感器中温度越限最突出（201 条），"
                                 "建议优先排查相关点位。"},
    ]),
    # ---- 以下为「超长会话」补充轮次：验证问题导航能滚到任意一条 ----
    ("user", [{"type": "text", "text": "上周和这周比，告警量是涨还是跌？"}]),
    ("assistant", [
        _parts_tool("sql_query", "c6",
                    {"sql": "SELECT week, COUNT(*) FROM alarms WHERE week IN "
                            "('this','last') GROUP BY 1"},
                    {"rows": [{"week": "last", "c": 1620}, {"week": "this", "c": 1489}]}),
        {"type": "text", "text": "这周 1489 条，上周 1620 条，**下降 8.1%**。"},
    ]),
    ("user", [{"type": "text", "text": "重复告警最多的前 5 个设备是哪些？"}]),
    ("assistant", [
        _parts_tool("alarm_rank", "c7", {"by": "device", "top": 5},
                    {"rows": [{"device": "CAM-3201", "c": 96},
                              {"device": "CAM-1188", "c": 81},
                              {"device": "SEN-0452", "c": 77},
                              {"device": "DOOR-0210", "c": 63},
                              {"device": "CAM-2907", "c": 58}]}),
        {"type": "text", "text": "前五：CAM-3201（96）、CAM-1188（81）、SEN-0452（77）、"
                                 "DOOR-0210（63）、CAM-2907（58）。前两台贡献了近 12% 的告警。"},
    ]),
    ("user", [{"type": "text", "text": "门禁告警有没有集中在某个时间段？"}]),
    ("assistant", [
        _parts_tool("sql_query", "c8",
                    {"sql": "SELECT extract(hour FROM ts) h, COUNT(*) c FROM alarms "
                            "WHERE type='door' GROUP BY 1 ORDER BY c DESC LIMIT 3"},
                    {"rows": [{"h": 8, "c": 88}, {"h": 12, "c": 61}, {"h": 18, "c": 54}]}),
        {"type": "text", "text": "门禁告警集中在 **8 点（88 条）**、12 点（61 条）、18 点（54 条）——"
                                 "正好是上下班和午休高峰。"},
    ]),
    ("user", [{"type": "text", "text": "22 点以后的告警占比多少？"}]),
    ("assistant", [
        _parts_tool("query_metrics", "c9", {"metric": "alarm_night_ratio"},
                    {"value": 0.173, "unit": "%"}),
        {"type": "text", "text": "22 点之后占 **17.3%**（约 258 条），夜间无人值守，建议单独设阈值。"},
    ]),
    ("user", [{"type": "text", "text": "给我一份排查清单，按优先级排。"}]),
    ("assistant", [
        {"type": "reasoning", "text": "需要按影响面排序：先处理重复告警设备，再按时间段调阈值，"
                                      "最后补夜间巡检。"},
        _parts_tool("write_note", "c10", {"title": "告警排查清单", "body": "..."}, {"ok": True}),
        {"type": "text", "text": "1. 先查 CAM-3201 / CAM-1188 的重复告警（合计 177 条）；\n"
                                 "2. 门禁 8 点高峰核对权限策略；\n"
                                 "3. 22 点后 258 条单独设阈值；\n"
                                 "4. 传感器温度越限复核点位校准。"},
    ]),
    ("user", [{"type": "text", "text": "把上面全部结论压缩成 5 条要点。"}]),
    ("assistant", [
        {"type": "reasoning", "text": "合并总量、环比、集中设备、时段、夜间占比五项。"},
        {"type": "text", "text": "1. 本周 1489 条，环比降 8.1%；\n"
                                 "2. 摄像头 612 / 门禁 403 / 传感器 474；\n"
                                 "3. 传感器内温度越限最多（201）；\n"
                                 "4. 前五设备 375 条，CAM-3201 最突出；\n"
                                 "5. 夜间占 17.3%，门禁高峰在 8 点。"},
    ]),
    ("user", [{"type": "text", "text": "最后给运维一句建议。"}]),
    ("assistant", [
        {"type": "text", "text": "建议先把 CAM-3201 / CAM-1188 的重复告警降下来——两台设备占了近 12%，"
                                 "大概率是镜头遮挡或灵敏度设置问题。"},
    ]),
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    async with async_db_session() as db:
        ids = [r[0] for r in (await db.execute(text(
            "SELECT id FROM ai_assistant_sessions WHERE title=:t AND is_deleted=false"),
            {"t": TITLE})).fetchall()]

    if args.clean:
        if not ids:
            print("没有演示会话")
            return
        async with async_db_session.begin() as db:
            await db.execute(text("DELETE FROM ai_assistant_messages WHERE session_id = ANY(:i)"),
                             {"i": ids})
            await db.execute(text("DELETE FROM ai_assistant_sessions WHERE id = ANY(:i)"),
                             {"i": ids})
        print("已删除演示会话", ids)
        return

    # 覆盖：先删旧的
    if ids:
        async with async_db_session.begin() as db:
            await db.execute(text("DELETE FROM ai_assistant_messages WHERE session_id = ANY(:i)"),
                             {"i": ids})
            await db.execute(text("DELETE FROM ai_assistant_sessions WHERE id = ANY(:i)"),
                             {"i": ids})

    async with async_db_session.begin() as db:
        sid = (await db.execute(text(
            "INSERT INTO ai_assistant_sessions(app_id,user_id,title,message_count,uuid,status,"
            "is_deleted,created_time,updated_time) VALUES "
            "(:a,:u,:t,:n,:uuid,'0',false,now(),now()) RETURNING id"),
            {"a": APP_ID, "u": USER_ID, "t": TITLE, "n": len(MESSAGES),
             "uuid": uuid.uuid4().hex})).scalar()
        for role, parts in MESSAGES:
            await db.execute(text(
                "INSERT INTO ai_assistant_messages(session_id,app_id,role,parts,uuid,status,"
                "is_deleted,created_time,updated_time) VALUES "
                "(:s,:a,:r,CAST(:p AS jsonb),:uuid,'0',false,now(),now())"),
                {"s": sid, "a": APP_ID, "r": role,
                 "p": json.dumps(parts, ensure_ascii=False), "uuid": uuid.uuid4().hex})
    print(f"已建演示会话 id={sid}，消息 {len(MESSAGES)} 条（app_id={APP_ID}）")


if __name__ == "__main__":
    asyncio.run(main())
