"""AI 集成开放平台演示数据补充：MCP 会话 / 调用审批（空表时直接写库）。

这些审计表由真实 MCP 连接 / 需审批的能力调用产生，seed_ai_demo.py 走 API 无法创建，
故这里直接插入演示行（仅当对应表为空时插入，幂等）：
- ai_integration_mcp_sessions：MCP 会话（跨近 7 天分布，让趋势曲线有起伏）；
- ai_integration_approvals：调用审批（pending / approved / rejected 各态）。

用法：cd backend && .venv/Scripts/python.exe scripts/seed_develop_demo.py
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import asyncpg

# 仅演示用：与 backend/env/.env.dev 的 DATABASE_* 保持一致
DSN = "postgresql://root:ServBay.dev@127.0.0.1:5432/aistation"


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        apps = await conn.fetch("SELECT id, appid, name FROM ai_integration_apps ORDER BY id")
        if not apps:
            print("  [SKIP] 无接入应用，请先执行 seed_ai_demo.py")
            return
        rows = [dict(a) for a in apps]
        now = datetime.now()

        # ---------------- MCP 会话 ----------------
        mcp_n = await conn.fetchval("SELECT count(*) FROM ai_integration_mcp_sessions")
        if mcp_n:
            print(f"  [SKIP] MCP 会话（已有 {mcp_n}）")
        else:
            transports = ["streamable-http", "stdio"]
            sessions: list[tuple] = []
            for i, app in enumerate(rows):
                # 每个应用 3 条会话，跨近 7 天，让趋势折线有起伏
                for j in range(3):
                    ts = now - timedelta(days=6 - ((i + j) % 7), hours=(i + j) % 5)
                    start = ts.replace(microsecond=0)
                    dur = 180 + 200 * ((i * 3 + j) % 4)
                    sessions.append(
                        (
                            app["id"],
                            app["appid"],
                            f"mcp-demo-{i}-{j}-{ts.strftime('%m%d')}",
                            transports[(i + j) % 2],
                            f"{transports[(i + j) % 2]}-client-demo",
                            ts.replace(microsecond=0),
                            start + timedelta(seconds=dur),
                            dur,
                            5 + 6 * ((i + j) % 5),
                            "client_disconnect" if j % 2 else "closed_by_server",
                        )
                    )
            await conn.executemany(
                "INSERT INTO ai_integration_mcp_sessions "
                "(app_id, appid, session_id, transport, client_info, started_at, ended_at, duration_s, tool_calls, close_reason, created_time) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$6)",
                sessions,
            )
            print(f"  [OK] MCP 会话 x{len(sessions)}")

        # ---------------- MCP 会话内的工具调用日志（关联演示会话） ----------------
        mcp_log_n = await conn.fetchval(
            "SELECT count(*) FROM ai_integration_call_logs WHERE method='MCP' AND session_id LIKE 'mcp-demo-%'"
        )
        if mcp_log_n:
            print(f"  [SKIP] MCP 调用日志（已有 {mcp_log_n}）")
        else:
            srows = await conn.fetch(
                "SELECT id, app_id, appid, session_id, transport, client_info, started_at "
                "FROM ai_integration_mcp_sessions WHERE session_id LIKE 'mcp-demo-%'"
            )
            # 每会话 2..5 条工具调用，覆盖成功/待审批/限流/配额命中/无权限/失败各态
            tool_specs = [
                ("agent.list", "agent", "success", None, "items=3"),
                ("chat.send", "chat", "success", None, "id=210"),
                ("agent.delete", "agent", "pending", "待管理员审批", None),
                ("train.start", "train", "denied", "访问过于频繁，请稍后再试", None),
                ("agent.list", "agent", "denied", "今日调用配额已用完", None),
                ("chat.send", "chat", "failed", "能力执行失败：模型不可用", None),
            ]
            call_rows: list[tuple] = []
            for s in srows:
                n = 2 + (s["id"] % 4)
                for k in range(n):
                    cap, cat, status, error, summary = tool_specs[(s["id"] + k) % len(tool_specs)]
                    body = (
                        json.dumps({"id": 100 + (s["id"] + k)})
                        if status == "success" and cap.startswith("agent")
                        else None
                    )
                    call_rows.append(
                        (
                            s["app_id"], s["appid"], cat, cap, "request", "MCP",
                            s["transport"], s["session_id"], s["client_info"],
                            f"/mcp#{cap}", body, status, error,
                            120 + (s["id"] * 7 + k * 13) % 900, 0,
                            summary if status == "success" else None,
                            s["started_at"] + timedelta(seconds=k * 3),
                        )
                    )
            await conn.executemany(
                "INSERT INTO ai_integration_call_logs "
                "(app_id, appid, category, capability, log_type, method, transport, session_id, client_info, "
                "request_path, request_body, status, error, latency_ms, cost_tokens, result_summary, created_time) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
                call_rows,
            )
            print(f"  [OK] MCP 调用日志 x{len(call_rows)}")

        # ---------------- 调用审批 ----------------
        appr_n = await conn.fetchval("SELECT count(*) FROM ai_integration_approvals")
        if appr_n:
            print(f"  [SKIP] 调用审批（已有 {appr_n}）")
        else:
            caps = [("agent.delete", "agent"), ("train.stop", "train"), ("chat.send", "chat")]
            approvals: list[tuple] = []
            for i, app in enumerate(rows):
                cap, cat = caps[i % len(caps)]
                status = ["pending", "approved", "rejected"][i % 3]
                ts = now - timedelta(hours=3 * (i + 1))
                reviewed = now - timedelta(minutes=20 * (i + 1)) if status != "pending" else None
                note = {"approved": "同意执行", "rejected": "资源不足，暂缓"}.get(status)
                approvals.append(
                    (
                        app["id"],
                        app["appid"],
                        cap,
                        cat,
                        json.dumps(
                            {"target_id": 100 + i, "reason": "例行维护"}
                            if cat == "train"
                            else {"agent_id": 200 + i}
                        ),
                        status,
                        reviewed,
                        1,
                        note,
                        json.dumps({"id": 300 + i, "ok": True}) if status == "approved" else None,
                        None,
                        ts.replace(microsecond=0),
                    )
                )
            await conn.executemany(
                "INSERT INTO ai_integration_approvals "
                "(app_id, appid, capability, category, payload, status, reviewed_at, reviewed_by, review_note, result, error, created_time) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
                approvals,
            )
            print(f"  [OK] 调用审批 x{len(approvals)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
