"""AI 能力插件（能力包，非平台代码插件）。

插件 = 一组可被 Agent 启用的能力包（如网页抓取、表格导出）。执行器以 key 注册，
平台内置若干 key；未实现执行器的 key 允许存在但标记 ``executor_ready=False``。
"""
from __future__ import annotations

from app.core.logger import log

#: 内置插件规格：**已清空**——原先的 web_fetch / table_export 已改为内置工具
#: （见 assistant/tools.py），「插件」在能力市场里表示**能力包**（技能+工具+MCP 的集合，
#: 见 market/seed.py 的 bundle）。保留此常量以便将来需要预置内置包时使用。
PLUGIN_SPECS: list[dict] = []

#: key -> 规格（供预置与就绪判定）
PLUGIN_SPEC_MAP: dict[str, dict] = {s["key"]: s for s in PLUGIN_SPECS}


async def run_web_fetch(args: dict, config: dict | None = None) -> dict:
    """抓取 URL 正文（只读）。"""
    import httpx

    url = (args or {}).get("url") or ""
    if not url:
        return {"error": "缺少 url 参数"}
    timeout = int((config or {}).get("timeout") or 15)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            resp = await c.get(url)
        text = resp.text or ""
        return {
            "url": url,
            "status": resp.status_code,
            "length": len(text),
            "text": text[:4000],
        }
    except Exception as e:  # noqa: BLE001  抓取失败不抛异常
        return {"error": f"{type(e).__name__}: {e}"}


async def run_table_export(args: dict, config: dict | None = None) -> dict:
    """把行数据导出为 CSV 文本。"""
    import csv
    import io

    rows = (args or {}).get("rows") or []
    columns = (args or {}).get("columns") or []
    if not isinstance(rows, list) or not rows:
        return {"error": "缺少 rows 参数（行列表）"}
    if not columns:
        first = rows[0]
        columns = list(first.keys()) if isinstance(first, dict) else []
    if not columns:
        return {"error": "无法推断列（请提供 columns）"}
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        if isinstance(r, dict):
            writer.writerow({c: r.get(c, "") for c in columns})
    content = buf.getvalue()
    return {"columns": columns, "rows": len(rows), "csv": content}


async def run_email_send(args: dict, config: dict | None = None) -> dict:
    """通过平台 SMTP 配置发送邮件（有副作用：真实发送）。

    参数：``to``（收件人，逗号分隔）、``subject``、``body``。SMTP 取自平台
    ``notify_smtp_*`` 全局参数；未配置则返回明确错误。
    """
    import asyncio
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    recipients = (args or {}).get("to") or (args or {}).get("recipients")
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]
    if not recipients:
        return {"error": "缺少收件人（to）"}
    subject = (args or {}).get("subject") or ""
    body = (args or {}).get("body") or ""

    from app.core.database import async_db_session
    from app.utils.notification import load_params

    async with async_db_session() as db:
        params = await load_params(
            db,
            "notify_smtp_host",
            "notify_smtp_port",
            "notify_smtp_user",
            "notify_smtp_pass",
            "notify_smtp_from",
            "notify_smtp_from_name",
            "notify_smtp_ssl",
        )
    host = params.get("notify_smtp_host")
    if not host:
        return {"error": "SMTP 未配置（notify_smtp_host）"}
    port = int(params.get("notify_smtp_port", 587) or 587)
    user = params.get("notify_smtp_user", "")
    password = params.get("notify_smtp_pass", "")
    from_addr = params.get("notify_smtp_from", user)
    from_name = params.get("notify_smtp_from_name", "")
    use_ssl = params.get("notify_smtp_ssl", "0") == "1"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject or "（无主题）"
    msg["From"] = formataddr((from_name or from_addr, from_addr))
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body or "", "plain", "utf-8"))

    def _send() -> None:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, recipients, msg.as_string())
        server.quit()

    try:
        # SMTP 握手为阻塞操作，放入线程池避免阻断事件循环
        await asyncio.to_thread(_send)
    except Exception as e:  # noqa: BLE001  发送失败不抛异常
        log.warning(f"邮件发送失败：{e}")
        return {"error": f"邮件发送失败：{type(e).__name__}: {e}"}
    return {"sent": True, "recipients": recipients}


async def run_report_generate(args: dict, config: dict | None = None, user_id: int | None = None) -> dict:
    """把内容保存为结构化报告（复用报告中心），返回 report_id。"""
    title = (args or {}).get("title") or ""
    content = (args or {}).get("content") or ""
    if not title:
        return {"error": "缺少报告标题（title）"}
    from app.plugin.module_ai.report.service import AiReportService

    saved = await AiReportService.create(
        title, content, {"plugin": "report_generate"}, user_id
    )
    return {"report_id": saved["id"], "title": saved["title"]}


async def run_data_pipeline(args: dict, config: dict | None = None) -> dict:
    """运行指定数据管道（ELT 拉取外部数据落库到目标对象），复用问数管道执行器。"""
    pipeline_id = (args or {}).get("pipeline_id")
    if not pipeline_id:
        return {"error": "缺少管道ID（pipeline_id）"}
    from app.plugin.module_ai.query.service import AiQueryService

    result = await AiQueryService.run_pipeline(int(pipeline_id))
    return result if isinstance(result, dict) else {"result": result}


#: key -> 执行器
PLUGIN_EXECUTORS = {
    "web_fetch": run_web_fetch,
    "table_export": run_table_export,
    "email_send": run_email_send,
    "report_generate": run_report_generate,
    "data_pipeline": run_data_pipeline,
}


async def execute_plugin(key: str, args: dict, config: dict | None = None) -> dict:
    """执行插件；未实现执行器的 key 返回明确错误。"""
    fn = PLUGIN_EXECUTORS.get(key)
    if fn is None:
        return {"error": f"插件 {key} 未实现执行器"}
    try:
        return await fn(args or {}, config or {})
    except Exception as e:  # noqa: BLE001  插件异常不中断对话
        log.warning(f"插件 {key} 执行失败：{e}")
        return {"error": f"{type(e).__name__}: {e}"}
