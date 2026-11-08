"""运行时开关与进程级状态（2026-11-08 从 service.py 拆出）。

- ``bypass_caches`` / ``config_override`` / ``set_eval_context``：评测与消融用的上下文
  开关（**只作用于当前任务**，不改库、不污染全局缓存）；
- ``invalidate_ont_allow_cache``：本体白名单缓存失效；
- ``_mark_ir_fail`` / ``_ir_circuit_open``：IR 生成失败熔断；
- ``_ensure_query_tables`` / ``_ddl_for_dialect``：影子表幂等建表与方言适配。

⚠️ 这些函数直接改 service 的进程级状态（``_svc._BYPASS_CACHE`` / ``_svc._CFG_OVERRIDE`` /
``_svc._EVAL_CTX`` / ``_svc._IR_FAIL_AT`` / ``_svc._DEGRADED``），一律 ``_svc.`` 读写，**不写 global**。
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .degraded import degrade as _degrade
from .degraded import degraded_status


@contextmanager
def bypass_caches():
    """当前任务内旁路全部问数缓存（评测/对比用）。"""
    token = _svc._BYPASS_CACHE.set(True)
    try:
        yield
    finally:
        _svc._BYPASS_CACHE.reset(token)


@contextmanager
def config_override(overrides: dict | None):
    """当前任务内临时覆盖工程配置（不落库、不外溢）。"""
    if not overrides:
        yield
        return
    merged = {**(_svc._CFG_OVERRIDE.get() or {}),
              **{str(k): str(v) for k, v in overrides.items()}}
    token = _svc._CFG_OVERRIDE.set(merged)
    try:
        yield
    finally:
        _svc._CFG_OVERRIDE.reset(token)


def set_eval_context(on: bool = True) -> None:
    """评测执行器调用前打标（同任务内生效，子任务会继承）。"""
    _svc._EVAL_CTX.set(bool(on))


def invalidate_ont_allow_cache() -> None:
    """本体对象/支撑表变化后调用：让「可查询白名单」缓存立即失效。

    原先该缓存**只在进程启动时建立、永不失效** ⇒ 导入本体后必须重启后端，
    问数才认得新对象的支撑表（表现为「表 xxx 不在可查询白名单内」）。
    """
    _svc._ONT_ALLOW_CACHE = None
    _svc._ONT_ALLOW_CACHE_AT = 0.0


def _mark_ir_fail() -> None:
    _svc._IR_FAIL_AT = time.time()


def _ir_circuit_open() -> bool:
    return _svc._IR_FAIL_AT > 0 and (time.time() - _svc._IR_FAIL_AT) < _svc._IR_FAIL_COOLDOWN


async def _ensure_query_tables() -> None:
    """确保问数侧影子表与新增列存在（幂等、best-effort）。

    ⚠️ 不加"已执行"进程标记：测试会多次重建 SQLite 库，标记会让第二个库缺列。
    这里只有 3 次 inspect + 少量 CREATE IF NOT EXISTS，重复执行代价可接受。
    """
    for sql in _svc._QUERY_TABLES_SQL:
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(_svc._ddl_for_dialect(sql)))
        except Exception as e:  # noqa: BLE001
            _degrade("shadow_tables", e)
    for table, col, ddl in _svc._QUERY_ALTER_COLS:
        try:
            async with async_db_session.begin() as db:
                from sqlalchemy import inspect

                cols = await db.run_sync(
                    lambda s, _t=table: {c["name"] for c in inspect(s.connection()).get_columns(_t)}
                )
                if col not in cols:
                    await db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        except Exception as e:  # noqa: BLE001
            _degrade("shadow_table_columns", e)
    # 策略/审计/shadow 三张表（统一策略引擎的数据层），建表逻辑收敛在 policy/model.py
    from .policy.model import ensure_policy_tables

    await ensure_policy_tables()
    # 血缘表（`ai_query_lineage`）：enforce/shadow 的视图映射依赖它。strict 化后
    # "表不存在"会被当成读取失败 → enforce 全拒、shadow 静默零差异。必须与策略表
    # 在同一处幂等创建；失败只降级（可见），不拖垮启动。
    try:
        from .lineage import ensure_lineage_table

        await ensure_lineage_table()
    except Exception as e:  # noqa: BLE001
        _degrade("query_lineage_table", e)
    # T7 接线自检（addendum 第 4 条）：shadow 差异写入依赖
    # ``ai_policy_shadow_diff.rewrite`` 这一列。补列失败（无 DDL 权限）时差异会整条
    # 写不进去，而写入本身是 fail-open —— 表现为「差异表悄悄没数据」，灰度报告被
    # 静默骗过。启动时明确 warning，别让它沉在日志里。
    _policy_bad = [
        a["area"] for a in degraded_status()["areas"]
        if a["area"] in ("policy_tables", "policy_table_columns")
    ]
    if _policy_bad:
        log.warning(
            "[问数权限] 策略表就绪异常（degraded_status 含 {}）：shadow 差异可能整条"
            "写不进去（fail-open，不会报错），切 shadow/enforce 前先修表结构",
            "/".join(_policy_bad),
        )


def _ddl_for_dialect(sql: str) -> str:
    """兼容旧调用名：统一走 ``ddl_dialect.ddl_for_dialect``（方言规则只有一份）。"""
    from .ddl_dialect import ddl_for_dialect

    return ddl_for_dialect(sql)
