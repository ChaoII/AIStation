"""AI 能力插件（能力包，非平台代码插件）。

插件 = 一组可被 Agent 启用的能力包（如网页抓取、表格导出）。执行器以 key 注册，
平台内置若干 key；未实现执行器的 key 允许存在但标记 ``executor_ready=False``。
"""
from __future__ import annotations

from app.core.logger import log

#: 内置插件规格（首次访问列表时惰性预置到 ai_plugins）
PLUGIN_SPECS: list[dict] = [
    {
        "key": "web_fetch",
        "label": "网页抓取",
        "executor_ready": True,
        "description": "抓取指定 URL 的页面文本内容（只读，返回正文摘要）",
        "config_schema": {
            "type": "object",
            "properties": {"timeout": {"type": "integer", "default": 15}},
        },
    },
    {
        "key": "table_export",
        "label": "表格导出",
        "executor_ready": True,
        "description": "把结构化数据导出为 CSV 文本（返回内容，不落盘）",
        "config_schema": {"type": "object", "properties": {}},
    },
    {
        "key": "email_send",
        "label": "邮件发送",
        "executor_ready": False,
        "description": "发送邮件（需配置 SMTP，暂未实现执行器）",
        "config_schema": {
            "type": "object",
            "properties": {
                "smtp_host": {"type": "string"},
                "smtp_port": {"type": "integer"},
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
        },
    },
    {
        "key": "report_generate",
        "label": "报告生成",
        "executor_ready": False,
        "description": "生成分析报告（复用平台报告能力，暂未实现独立执行器）",
        "config_schema": {"type": "object", "properties": {}},
    },
    {
        "key": "data_pipeline",
        "label": "数据管道",
        "executor_ready": False,
        "description": "触发数据管道任务（暂未实现执行器）",
        "config_schema": {"type": "object", "properties": {}},
    },
]

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


#: key -> 执行器
PLUGIN_EXECUTORS = {
    "web_fetch": run_web_fetch,
    "table_export": run_table_export,
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
