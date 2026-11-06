"""问数权限审计：SQL 指纹、预览打码、写入与回溯查询。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §4（审计表）。

四条硬约定（别各写一套）：

1. **写入 fail-open**：任何异常只 ``log.warning``（带 traceback），绝不向上抛 ——
   审计是附加能力，不能因为它把一次正常查询搞挂（计划 Review Focus 第 5 条）；
2. **不存全量 SQL**：只落 ``sql_hash``（空白折叠 + 小写后 sha256）+ 截断到 2KB、
   引号字面量已打码的 ``sql_preview``；
3. **``reason`` 也要打码**：上游会把原始 SQL 片段 / 异常文本塞进 reason（排查时需要），
   所以 reason 与 preview **走同一套**字面量替换，再按列宽截断 —— 宁可让说明略损可读性，
   也不让手机号等 PII 以明文进审计表。这里刻意**不**改成"reason 只能是枚举短语"：
   引擎给出的原因（命中哪条策略、缺哪个属性、SQL 里哪个字面量越界）是 explain 的核心信息，
   硬枚举要么丢信息、要么逼调用方把细节塞进别处绕过约束；
4. **不在这里建表**：三张策略表由 ``policy.model.ensure_policy_tables`` 在启动时
   幂等建好，每次写审计都去跑 DDL 会把查询拖慢。

写入用 **独立会话**（``async_db_session_fresh``），不复用请求会话。原因（2026-11 评审）：

- 本仓库 ``async_db_session`` 是**请求作用域包装**，请求内会复用中间件那条会话。
  ``RequestScopedSession.begin()`` 虽然把二次 ``begin()`` 降级成 SAVEPOINT（不抛
  ``InvalidRequestError``），但 ``_SessionFactory.begin()`` 退出时会
  ``await ambient.commit()`` —— 即**提前提交请求事务**；外层一旦回滚，审计行也会一起没。
- 审计的语义是"请求失败也必须留痕"（与 ``OperationLogRoute`` 的操作日志同源），
  必须独立提交。代价是每次写审计额外短暂持有一条连接（写完立即归还），
  相对"审计悄悄没数据"这个风险，这个代价可接受。

jsonb 列（``policy_ids`` / ``rewrite``）按**纯文本 JSON** 传参：PG 的 jsonb 与 SQLite
的 JSON 列都收字符串，避免 ``CAST(:p AS jsonb)`` 在 SQLite 上被亲和成数字。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime

from sqlalchemy import text

from app.core.database import async_db_session, async_db_session_fresh
from app.core.logger import log

#: 单/双引号字面量：``''`` / ``""`` 是 SQL 的转义写法，必须整段吃掉。
#:
#: 取舍（2026-11 评审要求写明）：
#:
#: - 标准 SQL 里双引号是**标识符**，理论上不需要打码；但这里的输入是**模型生成的 SQL**，
#:   它经常把字符串值写成 ``"张三"``。漏掉双引号就等于漏掉一整类 PII，
#:   所以两种引号都打码（代价只是 explain 里少看到被引号包住的标识符，纯观感问题）；
#: - 不加"数字字面量"打码：那会把 ``LIMIT 10`` / 日期常量 / 阈值全吃掉，
#:   explain 里就看不出结构了；手机号/证件号在生成的 SQL 里基本都是带引号的。
_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")

#: 审计写入（列宽见 ``policy.model`` 的 DDL）。
_INSERT_SQL = (
    "INSERT INTO ai_query_access_log"
    "(user_id, entry, datasource, sql_hash, sql_preview, decision, reason, "
    "policy_ids, rewrite, elapsed_ms) "
    "VALUES(:uid, :entry, :ds, :h, :prev, :dec, :reason, :pids, :rw, :ms)"
)

#: 回溯查询用到的列（顺序与 ``_log_row`` 一一对应）。
_LOG_COLS = (
    "id,user_id,entry,datasource,sql_hash,sql_preview,decision,reason,"
    "policy_ids,rewrite,elapsed_ms,created_time"
)


def sql_hash(sql: str) -> str:
    """SQL 指纹：**空白折叠 + 小写**后取 sha256 十六进制串。

    目的不是加密，而是把「同一语义、不同排版」的 SQL 归成一条
    （模型每次生成的换行/缩进/大小写都不一样，不归一就统计不出重复）。
    """
    normalized = " ".join(str(sql or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _mask_literals(value) -> str:
    """把引号内的字面量统一替换成 ``'?'``（``sql_preview`` 与 ``reason`` 共用）。

    任何"要落进审计表的人类可读文本"都必须过这里：上游把原始 SQL / 异常文本塞进
    ``reason`` 时，``phone='13800138000'`` 会原样带进来。
    """
    return _LITERAL_RE.sub("'?'", str(value or ""))


def sql_preview(sql: str, limit: int = 2048) -> str:
    """审计预览：引号字面量替换为 ``'?'``，再硬截断到 ``limit`` 个字符。

    - 打码只针对引号内的值，保留表名/列名/结构，供 explain 与治理回溯；
    - **先打码后截断**：截断不会把字面量的后半截（PII）留在库里；
    - 截断是**硬截断**（不追加省略号），保证「长度 <= limit」这条约束可断言；
    - ``limit <= 0`` 返回空串（调用方要的就是"别存"）。
    """
    masked = _mask_literals(sql)
    if limit <= 0:
        return ""
    return masked[: int(limit)]


def _clip(value, limit: int) -> str:
    """按列宽截断字符串：PG 的 ``VARCHAR(n)`` 超长会报错，整条审计就被丢了。"""
    return str(value or "")[:limit]


def _masked_clip(value, limit: int) -> str:
    """**先打码、再按列宽截断**（``reason`` 用）。

    顺序很重要：若先截断，一个跨在 255 边界的字面量会被切成半截 —— 正则再也匹配不到，
    剩下的一半 PII 反而会以明文落库。
    """
    return _clip(_mask_literals(value), limit)


def _warn_failed(err: BaseException) -> None:
    """审计写入失败的告警：带 traceback，且**告警本身也不允许抛**（fail-open 收尾）。"""
    message = f"[问数权限] 审计写入失败（已忽略，不影响查询）: err={err}"
    try:
        # loguru 用 opt(exception=True) 才真的带上 traceback（不是 logging 的 exc_info=）
        log.opt(exception=True).warning(message)
    except Exception:  # noqa: BLE001 - 日志设施异常同样不能影响查询
        try:
            log.warning(message)
        except Exception:  # noqa: BLE001
            pass


def _int_or_none(value) -> int | None:
    """安全转 int（耗时可能是 None / 字符串）；转不了就存 NULL，不拖垮写入。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_array(value) -> str:
    """把 list 序列化成 JSON 文本；序列化失败退回 ``"[]"``。

    ``rewrite`` 里可能带第三方对象（表达式节点等），``default=str`` 兜住大部分；
    真遇到环状结构就丢掉这项细节 —— 审计行本身（谁、什么 SQL、什么结论）更重要。
    """
    try:
        return json.dumps(list(value or ()), ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return "[]"


def _as_list(value) -> list:
    """读回 json 列：PG(jsonb) 可能给 str，SQLite 给 str；已是 list 就直接用。"""
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _time_text(value):
    """时间列转字符串（保持与既有接口一致的 ``YYYY-MM-DD HH:MM:SS``）。"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value) if value else None


def _log_row(row) -> dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "entry": row[2] or "",
        "datasource": row[3] or "",
        "sql_hash": row[4] or "",
        "sql_preview": row[5] or "",
        "decision": row[6] or "",
        "reason": row[7] or "",
        "policy_ids": _as_list(row[8]),
        "rewrite": _as_list(row[9]),
        "elapsed_ms": row[10],
        "created_time": _time_text(row[11]),
    }


async def write_access_log(
    *,
    principal,
    entry: str,
    datasource: str,
    sql: str,
    decision: str,
    reason: str,
    policy_ids: list[int],
    rewrite: list[dict],
    elapsed_ms: int,
) -> None:
    """写一条访问审计（放行也写），**永不抛异常**（fail-open）。

    ``principal`` 允许为 ``None``（非请求上下文拿不到身份时）：此时 ``user_id``
    写 NULL —— 判定侧已经按缺失主体拒绝，审计侧只需如实记录"没有主体"，
    不要在这里伪造 0 或匿名 id。

    会话选择见模块 docstring：这里用**独立会话**（``async_db_session_fresh``），
    保证 (1) 请求会话已有事务时也不会退化/提前提交请求事务，
    (2) 请求随后失败回滚，审计行仍留痕。
    """
    try:
        params = {
            "uid": getattr(principal, "user_id", None),
            "entry": _clip(entry, 32),
            "ds": _clip(datasource, 120),
            "h": sql_hash(sql),
            # 列宽是 TEXT（2KB 是业务约定，不是列限制）
            "prev": sql_preview(sql),
            "dec": _clip(decision, 8),
            # reason 与 preview 同一套打码：上游会塞原始 SQL / 异常文本进来
            "reason": _masked_clip(reason, 255),
            "pids": _json_array(policy_ids),
            "rw": _json_array(rewrite),
            "ms": _int_or_none(elapsed_ms),
        }
        async with async_db_session_fresh() as db:
            async with db.begin():
                await db.execute(text(_INSERT_SQL), params)
    except Exception as e:  # noqa: BLE001
        # 只记 warning（带 traceback）：调用方（查询主链路）绝不能因为审计失败而失败
        _warn_failed(e)


async def list_access_logs(limit: int = 100) -> list[dict]:
    """最近 ``limit`` 条审计，**新的在前**（explain / 治理看板回溯用）。

    ``limit`` 做安全钳制（1~1000），避免有人传 0 / 负数 / None 把 SQL 弄成
    ``LIMIT NULL`` 之类的怪查询。
    """
    try:
        n = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        n = 100
    async with async_db_session() as db:
        rows = (
            await db.execute(
                text(f"SELECT {_LOG_COLS} FROM ai_query_access_log ORDER BY id DESC LIMIT :n"),
                {"n": n},
            )
        ).fetchall()
    return [_log_row(r) for r in rows]
