import asyncio
import hashlib
import hmac
import json
import logging
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx
from sqlalchemy import select

from app.api.v1.module_system.params.model import ParamsModel

log = logging.getLogger(__name__)

_ws_manager = None

TEMPLATE_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def get_ws_manager():
    global _ws_manager
    if _ws_manager is None:
        from app.api.v1.module_video.alarm.ws import AlarmWSManager
        _ws_manager = AlarmWSManager()
    return _ws_manager


SEVERITY_COLORS = {"CRITICAL": "#F56C6C", "WARNING": "#E6A23C", "INFO": "#909399"}


def _build_payload(alarm: dict, rule: dict | None) -> dict:
    return {
        "alarm_id": alarm.get("id"),
        "alarm_type": alarm.get("alarm_type"),
        "severity": alarm.get("severity"),
        "alarm_time": str(alarm.get("alarm_time") or ""),
        "camera_name": (alarm.get("camera") or {}).get("name") or "",
        "camera_id": alarm.get("camera_id"),
        "rule_id": rule.get("id") if rule else None,
        "rule_name": rule.get("name") if rule else "",
        "description": alarm.get("description") or "",
        "snapshot_url": alarm.get("snapshot_path") or "",
    }


def _build_template_context(alarm: dict, rule: dict | None) -> dict:
    ctx = _build_payload(alarm, rule)
    ctx["payload"] = json.dumps(ctx, ensure_ascii=False)
    return ctx


def _build_email_html(alarm: dict, rule: dict | None) -> str:
    alarm_type = alarm.get("alarm_type", "")
    severity = alarm.get("severity", "")
    camera_name = (alarm.get("camera") or {}).get("name") or ""
    alarm_time = alarm.get("alarm_time", "")
    desc = alarm.get("description", "")
    rule_name = rule.get("name") if rule else ""
    color = SEVERITY_COLORS.get(severity, "#909399")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:20px">
<div style="max-width:600px;margin:0 auto;border:1px solid #e4e7ed;border-radius:8px;overflow:hidden">
<div style="background:{color};padding:16px 24px">
<h2 style="margin:0;color:#fff;font-size:18px">[{severity}] {alarm_type}</h2>
</div>
<div style="padding:24px">
<table style="width:100%;border-collapse:collapse">
<tr><td style="padding:8px 0;color:#666;width:80px">摄像机</td><td style="padding:8px 0">{camera_name}</td></tr>
<tr><td style="padding:8px 0;color:#666">告警时间</td><td style="padding:8px 0">{alarm_time}</td></tr>
<tr><td style="padding:8px 0;color:#666">规则名称</td><td style="padding:8px 0">{rule_name}</td></tr>
<tr><td style="padding:8px 0;color:#666">描述</td><td style="padding:8px 0">{desc or "-"}</td></tr>
</table>
</div></div></body></html>"""


def _render_template(template: str, context: dict) -> str:
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        val = context.get(key)
        return str(val) if val is not None else m.group(0)
    return TEMPLATE_VAR_RE.sub(_replacer, template)


def _sign_payload(secret: str, body: str) -> str:
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


async def load_params(db, *keys: str) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        stmt = select(ParamsModel).where(
            ParamsModel.config_key.in_(keys),
            ParamsModel.status == "0",
        )
        rows = await db.execute(stmt)
        for row in rows.scalars():
            result[row.config_key] = row.config_value or ""
    except Exception as e:
        log.warning("Failed to load params: %s", e)
    return result


async def dispatch_notification(auth, alarm_record: dict, rule: dict | None) -> None:
    if not rule:
        return
    channels = rule.get("notify_channels")
    if not channels:
        return

    db = getattr(auth, "db", None)
    if not db:
        return

    for entry in channels:
        entry_label = str(entry)
        try:
            if isinstance(entry, str):
                ch_type = entry
                local_cfg: dict = {}
            elif isinstance(entry, dict):
                ch_type = entry.get("channel", "")
                local_cfg = {k: v for k, v in entry.items() if k != "channel"}
            else:
                continue

            handler_name = f"_send_{ch_type.lower()}"
            handler = globals().get(handler_name)
            if handler:
                await handler(db, alarm_record, rule, local_cfg)
                log.info("Notification sent via %s", ch_type)
        except Exception as e:
            log.error("Notification channel %s failed: %s", entry_label, e)


async def _send_ws_push(db, alarm: dict, rule: dict | None, cfg: dict) -> None:
    manager = get_ws_manager()
    await manager.broadcast(_build_payload(alarm, rule))


async def _send_email(db, alarm: dict, rule: dict | None, cfg: dict) -> None:
    params = await load_params(
        db,
        "notify_smtp_host", "notify_smtp_port", "notify_smtp_user",
        "notify_smtp_pass", "notify_smtp_from", "notify_smtp_from_name",
        "notify_smtp_ssl", "notify_admin_email",
    )
    recipients = cfg.get("recipients") or (
        [params.get("notify_admin_email")] if params.get("notify_admin_email") else []
    )
    if not recipients:
        msg = "Email: no recipients configured"
        log.warning(msg)
        raise ValueError(msg)

    host = params.get("notify_smtp_host")
    if not host:
        msg = "SMTP host not configured"
        log.warning(msg)
        raise ValueError(msg)

    port = int(params.get("notify_smtp_port", 587))
    user = params.get("notify_smtp_user", "")
    password = params.get("notify_smtp_pass", "")
    from_addr = params.get("notify_smtp_from", user)
    from_name = params.get("notify_smtp_from_name", "")
    use_ssl = params.get("notify_smtp_ssl", "0") == "1"

    subject = f"[{rule.get('name', '告警') if rule else '告警'}] {alarm.get('alarm_type', '')} - {alarm.get('severity', '')}"
    html = _build_email_html(alarm, rule)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name or from_addr, from_addr))
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html", "utf-8"))

    def _send():
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port)
            else:
                server = smtplib.SMTP(host, port)
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, recipients, msg.as_string())
            server.quit()
            log.info("Email sent to %s", recipients)
        except Exception as e:
            log.error("Email send failed: %s", e)
            raise

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send)


async def _send_webhook(db, alarm: dict, rule: dict | None, cfg: dict) -> None:
    params = await load_params(
        db,
        "notify_webhook_default_url", "notify_webhook_default_method",
        "notify_webhook_retry_count", "notify_webhook_retry_interval",
        "notify_webhook_secret",
    )
    url = cfg.get("url") or params.get("notify_webhook_default_url")
    if not url:
        msg = "Webhook URL not configured"
        log.warning(msg)
        raise ValueError(msg)

    method = (cfg.get("method") or params.get("notify_webhook_default_method") or "POST").upper()
    retry_count = int(cfg.get("retry_count") or params.get("notify_webhook_retry_count") or 3)
    retry_interval = int(cfg.get("retry_interval") or params.get("notify_webhook_retry_interval") or 5)
    secret = cfg.get("secret") or params.get("notify_webhook_secret") or ""
    content_type = cfg.get("content_type") or "application/json"

    ctx = _build_template_context(alarm, rule)

    raw_template = cfg.get("template") or ""
    if raw_template:
        rendered = _render_template(raw_template, ctx)
        try:
            body_bytes = rendered.encode("utf-8")
        except Exception as e:
            log.warning("Webhook template render failed, fallback to JSON: %s", e)
            body_bytes = json.dumps(ctx, ensure_ascii=False).encode("utf-8")
    else:
        body_bytes = json.dumps(ctx, ensure_ascii=False).encode("utf-8")

    headers = dict(cfg.get("headers", {}))

    if content_type:
        headers.setdefault("Content-Type", content_type)

    if secret:
        sig = _sign_payload(secret, body_bytes.decode("utf-8"))
        headers.setdefault("X-Webhook-Signature", sig)
        headers.setdefault("X-Webhook-Timestamp", str(int(time.time())))

    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, retry_count + 1):
            try:
                if method == "GET":
                    resp = await client.get(url, params=ctx, headers=headers)
                else:
                    resp = await client.request(method, url, content=body_bytes, headers=headers)
                resp.raise_for_status()
                log.info("Webhook sent to %s: %s (attempt %d/%d)", url, resp.status_code, attempt, retry_count)
                return
            except httpx.HTTPStatusError as e:
                log.warning("Webhook attempt %d/%d failed: %s %s", attempt, retry_count, e.response.status_code, e.response.text[:200])
                last_exc = e
                if attempt < retry_count:
                    await asyncio.sleep(retry_interval * attempt)
            except (httpx.RequestError, httpx.TimeoutException) as e:
                log.warning("Webhook attempt %d/%d network error: %s", attempt, retry_count, e)
                last_exc = e
                if attempt < retry_count:
                    await asyncio.sleep(retry_interval * attempt)

    if last_exc:
        log.error("Webhook failed after %d attempts to %s: %s", retry_count, url, last_exc)
        raise last_exc


async def _send_sms(db, alarm: dict, rule: dict | None, cfg: dict) -> None:
    params = await load_params(
        db, "notify_sms_api_url", "notify_sms_access_key", "notify_sms_secret",
        "notify_sms_sign", "notify_sms_template",
    )
    phones = cfg.get("phones", [])
    if not phones:
        msg = "SMS: no phone numbers configured"
        log.warning(msg)
        raise ValueError(msg)
    api_url = params.get("notify_sms_api_url")
    if not api_url:
        msg = "SMS API URL not configured"
        log.warning(msg)
        raise ValueError(msg)

    ctx = _build_template_context(alarm, rule)

    raw_template = cfg.get("template") or params.get("notify_sms_template") or ""
    body_template = raw_template or json.dumps({
        "access_key": params.get("notify_sms_access_key", ""),
        "secret": params.get("notify_sms_secret", ""),
        "sign": params.get("notify_sms_sign", ""),
        "template": params.get("notify_sms_template", ""),
        "phones": phones,
        "alarm_type": ctx["alarm_type"],
        "severity": ctx["severity"],
        "camera": ctx["camera_name"],
        "description": ctx["description"],
    }, ensure_ascii=False)

    body_str = _render_template(body_template, {**ctx, "phones": json.dumps(phones, ensure_ascii=False)})
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(api_url, content=body_str.encode("utf-8"), headers=headers)
        resp.raise_for_status()
    log.info("SMS sent to %s: %s", phones, resp.status_code)


async def send_test_notification(db, channel: str, config: dict) -> dict:
    test_alarm = {
        "id": 0,
        "alarm_type": "TEST",
        "severity": "WARNING",
        "alarm_time": str(time.time()),
        "camera_name": "测试摄像机",
        "camera_id": 0,
        "description": "这是一条测试告警消息",
        "snapshot_path": "",
        "camera": {"name": "测试摄像机"},
    }
    test_rule = {"id": 0, "name": "测试规则", "notify_channels": []}

    handler_name = f"_send_{channel.lower()}"
    handler = globals().get(handler_name)
    if not handler:
        return {"success": False, "error": f"Unknown channel: {channel}"}

    try:
        await handler(db, test_alarm, test_rule, config)
        return {"success": True, "message": f"{channel} 推送测试成功"}
    except Exception as e:
        return {"success": False, "error": str(e)}
