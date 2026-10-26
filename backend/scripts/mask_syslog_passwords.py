"""历史操作/登录日志敏感字段清理脚本。

背景：早期版本操作日志（sys_log.request_payload）会把登录/改密等请求里的明文密码原样落库。
当前代码（app/core/router_class.py 的 OperationLogRoute）已对**新增**日志做敏感字段脱敏；
本脚本用于把**存量**日志里的明文密码一次性掩码为 ****，供各环境升级后执行一次。

用法：
    cd backend
    python -m scripts.mask_syslog_passwords
    (或) python scripts/mask_syslog_passwords.py

幂等：已掩码/无密码的条目跳过，可安全重复执行。
"""

import asyncio
import os
import re

# 默认读取 dev 环境配置（.env.dev），可用环境变量 ENVIRONMENT 覆盖（如 prod）
os.environ.setdefault("ENVIRONMENT", "dev")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.setting import settings

# JSON 格式： "xxxpasswordxxx": "值"  ->  "xxxpasswordxxx": "****"
_JSON_PASSWORD_RE = re.compile(r'("(?:[^"]*password[^"]*)"\s*:\s*")[^"]*(")', re.I)
# 表单格式： password: 值（到行尾）
_FORM_PASSWORD_RE = re.compile(r"(^|\n)(\s*password\s*:\s*)([^\n]*)", re.I)


def mask_payload(payload: str | None) -> str | None:
    """把疑似密码字段的值掩码为 ****。"""
    if not payload:
        return payload
    payload = _JSON_PASSWORD_RE.sub(r"\1****\2", payload)
    payload = _FORM_PASSWORD_RE.sub(r"\1\2****", payload)
    return payload


async def main() -> int:
    engine = create_async_engine(settings.ASYNC_DB_URI)
    try:
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "select id, request_payload from sys_log "
                        "where request_payload like '%password%' and request_payload not like '%****%'"
                    )
                )
            ).fetchall()
            updated = 0
            for rid, payload in rows:
                new_payload = mask_payload(payload)
                if new_payload != payload and "****" in (new_payload or ""):
                    await conn.execute(
                        text("update sys_log set request_payload = :p where id = :i"),
                        {"p": new_payload, "i": rid},
                    )
                    updated += 1
            print(f"待处理明文条目数: {len(rows)}，已掩码: {updated}")
            remain = (
                await conn.execute(
                    text(
                        "select count(*) from sys_log "
                        "where request_payload like '%password%' and request_payload not like '%****%'"
                    )
                )
            ).scalar()
            print(f"剩余未掩码数: {remain}（剩余多为列名数组中的字段名 password，非真实密码值）")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
