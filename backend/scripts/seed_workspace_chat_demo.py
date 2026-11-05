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
