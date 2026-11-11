"""问数提示词规则（**可配置**）：把原来写死在 ``nl2sql_ops.py`` 里的生成规则搬到库里。

为什么要这张表
--------------
``_nl2sql`` 里原本用 ``rules.append("（1）…")`` 写死 8 条规则，改一句话要发版，
也没法按数据源/方言区分。这里把**书写规范**（别名、格式、占比写法、Top-N 空值）
收进 ``ai_query_prompt_rules``，由界面启停/改文案/调顺序。

三条边界（别搞混）
------------------
1. **核心安全约束**（只读 SELECT、必须 FROM、只用给定表/字段）留在代码里，
   以 :data:`CORE_RULES` 为唯一真源，**不可关闭**——它是护栏不是偏好。
2. **确定性口径**（软删过滤、时间口径、权限）继续由代码改写，不进提示词：
   实测「软删」的提示词版规则两轮自翻 5 题，改代码才稳定。
3. 本表只放**书写偏好**类规则：没有唯一正确答案、不同业务/模型口味不同的那些。

行为等价
--------
播种文案与改造前``nl2sql_ops`` 里的文本**逐字一致**（仅去掉行首编号，编号由渲染时
统一生成）⇒ 默认配置下拼出的 prompt 与改造前相同。

失败姿势
--------
读库失败（表未建/库抖动）时**回退**到 :data:`DEFAULT_RULES`（代码内默认），
绝不让「配置表读不到」变成「问数不可用」。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .ddl_dialect import ddl_for_dialect
from .dialect import CORE_RULES as _CORE_RULES

#: 表 DDL（PG 写，SQLite 由 ``ddl_for_dialect`` 翻译）
TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_query_prompt_rules (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    title VARCHAR(120) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    scope VARCHAR(16) NOT NULL DEFAULT 'all',
    scope_value VARCHAR(64) NOT NULL DEFAULT '',
    source_setting VARCHAR(64) NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    is_core BOOLEAN NOT NULL DEFAULT FALSE,
    is_custom BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMP DEFAULT now(),
    updated_time TIMESTAMP DEFAULT now(),
    is_deleted BOOLEAN DEFAULT FALSE
)
"""

UNIQUE_CODE_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_query_prompt_rules_code "
    "ON ai_query_prompt_rules(code)"
)

#: 核心安全约束：**唯一真源**在 ``dialect.CORE_RULES``（纯逻辑、可快测导入），
#: 这里只做再导出，避免两份文案漂移。
CORE_RULES: tuple[str, ...] = _CORE_RULES

#: 默认规则（= 改造前写死在 nl2sql_ops 里的 8 条，去掉行首编号）。
#:
#: ``source_setting``：该规则由哪个**已有开关**额外控制（空 = 无额外开关）。
#: 这样「设置页里的力度开关」与「规则文案」是两件事：开关决定要不要，表决定写什么。
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "code": "entity_name",
        "title": "实体名要 JOIN 取名称",
        "body": (
            "问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时，"
            "应 JOIN 对应表用其「name」列，而不是直接返回外键 id；"
        ),
        "priority": 10,
        "source_setting": "entity_name_rule",
        "setting_default": True,
    },
    {
        "code": "enum_hint",
        "title": "枚举字段用真实取值",
        "body": "status/framework/severity/task_type 等枚举字段必须使用【取值】里给出的原始值；",
        "priority": 20,
        "source_setting": "enum_hint_enabled",
        "setting_default": False,
    },
    {
        "code": "ratio_formula",
        "title": "占比算法",
        "body": "占比用“COUNT(*) * 100.0 / 总数”或“FILTER (WHERE ...)”计算；",
        "priority": 30,
    },
    {
        "code": "sql_format",
        "title": "SQL 格式（不加注释）",
        "body": "多行 SQL 直接换行输出即可，不要加注释。",
        "priority": 40,
    },
    {
        "code": "agg_alias",
        "title": "聚合列中文别名",
        "body": (
            "**所有聚合列和计算列必须起中文别名**（如 COUNT(*) AS 告警数、"
            "SUM(amount) AS 销售额），不要用 c / count / total 这类占位名——"
            "用户会直接看到列头。"
        ),
        "priority": 50,
    },
    {
        "code": "decompose_plan",
        "title": "先判断查询形态",
        "body": "先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；",
        "priority": 60,
        "source_setting": "decomposed_planning",
        "setting_default": True,
    },
    {
        "code": "detail_vs_agg",
        "title": "明细 vs 汇总",
        "body": (
            "先看要的是「明细」还是「汇总」：出现 平均/均值/占比/百分比/比例/最多/最少/最高/最低/"
            "最大/最小 时，**先按组聚合、再在外层汇总或取 TOP1**"
            "（例：平均每个供应商关联几个矿点 = AVG(每组 COUNT)；关联最多的那家占多少 = 按组计数后 "
            "ORDER BY 计数 DESC LIMIT 1）；这类题即使句式里有「每个/各」，也**不要**返回全量分组明细。"
        ),
        "priority": 70,
    },
    {
        "code": "topn_null",
        "title": "Top-N 排除空值",
        "body": (
            "按某个数值列排序取 Top N（最高/最低/最大/最小/前 N/最早/最晚）时，"
            "必须排除该列为 NULL 的行（加 `\"列\" IS NOT NULL`）——PostgreSQL 的 DESC 排序默认把 "
            "NULL 排在最前，不排除就会把空值当成最大值；若该列以文本存储数值，先 "
            "`CAST(\"列\" AS numeric)` 再排序。"
        ),
        "priority": 80,
    },
]

#: 进程内缓存（60s）。写操作与启动播种会立即失效。
_CACHE: dict[str, Any] = {"at": 0.0, "rows": None}
_CACHE_TTL = 60.0


def invalidate_cache() -> None:
    """让规则缓存立即失效（写操作/播种后调用）。"""
    _CACHE["at"] = 0.0
    _CACHE["rows"] = None


def default_rows() -> list[dict[str, Any]]:
    """代码内默认规则（DB 不可用时的兜底，也是播种来源）。"""
    return [
        {
            "id": 0, "code": r["code"], "title": r["title"], "body": r["body"],
            "scope": "all", "scope_value": "", "source_setting": r.get("source_setting", ""),
            "enabled": True, "priority": r["priority"], "is_core": False, "is_custom": False,
        }
        for r in DEFAULT_RULES
    ]


def _setting_default(code: str) -> bool:
    for r in DEFAULT_RULES:
        if r["code"] == code:
            return bool(r.get("setting_default", True))
    return True


async def ensure_prompt_rules() -> None:
    """幂等建表 + 播种缺失的默认规则（**不覆盖**用户已改的文案）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(ddl_for_dialect(TABLE_DDL)))
        await db.execute(text(UNIQUE_CODE_INDEX))
        existing = {
            row[0]
            for row in (await db.execute(
                text("SELECT code FROM ai_query_prompt_rules WHERE is_deleted = false")
            )).fetchall()
        }
        for r in DEFAULT_RULES:
            if r["code"] in existing:
                continue
            await db.execute(
                text(
                    "INSERT INTO ai_query_prompt_rules"
                    "(code,title,body,scope,scope_value,source_setting,enabled,priority,"
                    "is_core,is_custom,created_time,updated_time,is_deleted) "
                    "VALUES (:code,:title,:body,'all','',:ss,true,:pr,false,false,:ts,:ts,false)"
                ),
                {
                    "code": r["code"], "title": r["title"], "body": r["body"],
                    "ss": r.get("source_setting", ""), "pr": r["priority"],
                    "ts": datetime.now(),
                },
            )
    invalidate_cache()


async def _load_rows() -> list[dict[str, Any]]:
    """读启用/停用的全部规则（含缓存）。读失败抛异常，由调用方兜底。"""
    now = time.time()
    cached = _CACHE.get("rows")
    if cached is not None and (now - float(_CACHE["at"])) < _CACHE_TTL:
        return cached
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rows = (await db.execute(
            text(
                "SELECT id,code,title,body,scope,scope_value,source_setting,enabled,priority,"
                "is_core,is_custom FROM ai_query_prompt_rules "
                "WHERE is_deleted = false ORDER BY priority ASC, id ASC"
            )
        )).fetchall()
    items = [
        {
            "id": int(r[0]), "code": r[1], "title": r[2], "body": r[3],
            "scope": r[4] or "all", "scope_value": r[5] or "",
            "source_setting": r[6] or "", "enabled": bool(r[7]),
            "priority": int(r[8] or 100), "is_core": bool(r[9]), "is_custom": bool(r[10]),
        }
        for r in rows
    ]
    # 表为空（旧库未播种）→ 视为"没有配置"，让调用方回退代码默认
    _CACHE["rows"] = items
    _CACHE["at"] = now
    return items


def _bool(cfg: dict, key: str, default: bool) -> bool:
    """与 ``SettingsOps._cfg_bool`` 同语义：显式值优先，缺失才回落默认。"""
    raw = cfg.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _render(items: list[dict[str, Any]], cfg: dict, datasource: str,
            dialect_name: str) -> list[str]:
    """按作用域与开关过滤，再统一编号（编号在渲染时生成，改顺序不会串号）。"""
    out: list[str] = []
    ds = (datasource or "").strip()
    dname = (dialect_name or "").strip().lower()
    for r in sorted(items, key=lambda x: (int(x.get("priority") or 100), int(x.get("id") or 0))):
        if not r.get("enabled"):
            continue
        scope = (r.get("scope") or "all").lower()
        if scope == "datasource" and (r.get("scope_value") or "") not in ("", ds):
            continue
        if scope == "dialect" and (r.get("scope_value") or "").strip().lower() not in ("", dname):
            continue
        setting = r.get("source_setting") or ""
        if setting and not _bool(cfg, setting, _setting_default(r.get("code") or "")):
            continue
        body = (r.get("body") or "").strip()
        if body:
            out.append(f"（{len(out) + 1}）{body}")
    return out


async def render_rules(cfg: dict, datasource: str = "",
                       dialect_name: str = "") -> list[str]:
    """生成注入 prompt 的规则列表（带编号）。

    任何异常都回退到代码默认规则集合：问数可用性优先于配置可编辑性。
    """
    try:
        items = await _load_rows()
        if not items:
            items = default_rows()
    except Exception:  # noqa: BLE001 - 配置读不到不能拖垮问数
        items = default_rows()
    return _render(items, cfg, datasource, dialect_name)


async def list_rules() -> dict[str, Any]:
    """供界面：全部规则 + 核心安全约束（只读展示）+ 设置开关说明。"""
    try:
        items = await _load_rows()
        if not items:
            items = default_rows()
    except Exception:  # noqa: BLE001
        items = default_rows()
    return {
        "items": sorted(items, key=lambda x: (int(x.get("priority") or 100), int(x.get("id") or 0))),
        "core_rules": list(CORE_RULES),
        "source_settings": {
            r["code"]: {"key": r["source_setting"],
                        "default": bool(r.get("setting_default", True))}
            for r in DEFAULT_RULES if r.get("source_setting")
        },
    }


def _clean(payload: dict[str, Any], allow_code: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if allow_code and payload.get("code") is not None:
        out["code"] = str(payload["code"]).strip()[:64]
    if payload.get("title") is not None:
        out["title"] = str(payload["title"]).strip()[:120]
    if payload.get("body") is not None:
        out["body"] = str(payload["body"]).strip()
    if payload.get("scope") is not None:
        scope = str(payload["scope"]).strip().lower()
        out["scope"] = scope if scope in ("all", "datasource", "dialect") else "all"
    if payload.get("scope_value") is not None:
        out["scope_value"] = str(payload["scope_value"]).strip()[:64]
    if payload.get("priority") is not None:
        try:
            out["priority"] = int(payload["priority"])
        except (TypeError, ValueError):
            pass
    if payload.get("enabled") is not None:
        out["enabled"] = bool(payload["enabled"])
    return out


async def update_rule(rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """更新一条规则（核心规则只允许改标题/顺序，不允许改文案与关闭）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    fields = _clean(payload, allow_code=False)
    if not fields:
        raise ValueError("没有可更新的字段")
    async with async_db_session.begin() as db:
        row = (await db.execute(
            text("SELECT is_core, code FROM ai_query_prompt_rules WHERE id=:i AND is_deleted=false"),
            {"i": rule_id},
        )).first()
        if not row:
            raise ValueError("规则不存在")
        if row[0]:
            # 核心安全约束：只读展示；只允许调整排序
            fields = {k: v for k, v in fields.items() if k == "priority"}
            if not fields:
                raise ValueError("核心安全约束不可修改或关闭")
        sets = ", ".join(f"{k}=:{k}" for k in fields)
        await db.execute(
            text(f"UPDATE ai_query_prompt_rules SET {sets}, updated_time=:ts WHERE id=:rid"),
            {**fields, "rid": rule_id, "ts": datetime.now()},
        )
        code = row[1]
        item = (await db.execute(
            text(
                "SELECT id,code,title,body,scope,scope_value,source_setting,enabled,priority,"
                "is_core,is_custom FROM ai_query_prompt_rules WHERE id=:i"
            ),
            {"i": rule_id},
        )).first()
    invalidate_cache()
    return {
        "id": int(item[0]), "code": item[1], "title": item[2], "body": item[3],
        "scope": item[4], "scope_value": item[5], "source_setting": item[6],
        "enabled": bool(item[7]), "priority": int(item[8] or 100),
        "is_core": bool(item[9]), "is_custom": bool(item[10]), "_code": code,
    }


async def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """新增自定义规则（``is_custom=true``）：id 由库生成，code 自动补。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    fields = _clean(payload, allow_code=True)
    body = (fields.get("body") or "").strip()
    if not body:
        raise ValueError("规则内容不能为空")
    code = fields.get("code") or f"custom_{int(time.time() * 1000)}"
    async with async_db_session.begin() as db:
        exists = (await db.execute(
            text("SELECT 1 FROM ai_query_prompt_rules WHERE code=:c"), {"c": code},
        )).first()
        if exists:
            raise ValueError(f"规则代码已存在：{code}")
        row = (await db.execute(
            text(
                "INSERT INTO ai_query_prompt_rules"
                "(code,title,body,scope,scope_value,source_setting,enabled,priority,"
                "is_core,is_custom,created_time,updated_time,is_deleted) "
                "VALUES (:code,:title,:body,:scope,:scope_value,'',"
                ":enabled,:priority,false,true,:ts,:ts,false) RETURNING id"
            ),
            {
                "code": code, "title": fields.get("title") or "自定义规则",
                "body": body, "scope": fields.get("scope") or "all",
                "scope_value": fields.get("scope_value") or "",
                "enabled": fields.get("enabled", True),
                "priority": fields.get("priority", 900),
                "ts": datetime.now(),
            },
        )).first()
    invalidate_cache()
    return await _get_rule(int(row[0]))


async def _get_rule(rule_id: int) -> dict[str, Any]:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        item = (await db.execute(
            text(
                "SELECT id,code,title,body,scope,scope_value,source_setting,enabled,priority,"
                "is_core,is_custom FROM ai_query_prompt_rules WHERE id=:i AND is_deleted=false"
            ),
            {"i": rule_id},
        )).first()
    if not item:
        raise ValueError("规则不存在")
    return {
        "id": int(item[0]), "code": item[1], "title": item[2], "body": item[3],
        "scope": item[4], "scope_value": item[5], "source_setting": item[6],
        "enabled": bool(item[7]), "priority": int(item[8] or 100),
        "is_core": bool(item[9]), "is_custom": bool(item[10]),
    }


async def delete_rule(rule_id: int) -> None:
    """删除**自定义**规则；内置规则只能停用，不允许删除。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        row = (await db.execute(
            text("SELECT is_custom FROM ai_query_prompt_rules WHERE id=:i AND is_deleted=false"),
            {"i": rule_id},
        )).first()
        if not row:
            raise ValueError("规则不存在")
        if not row[0]:
            raise ValueError("内置规则不可删除，请改为停用")
        # 配置行做物理删除：软删会占用唯一 code，且历史文案没有保留价值
        await db.execute(text("DELETE FROM ai_query_prompt_rules WHERE id=:i"), {"i": rule_id})
    invalidate_cache()


async def reset_rule(rule_id: int) -> dict[str, Any]:
    """把内置规则恢复成代码默认文案（用户改坏了能一键回退）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        row = (await db.execute(
            text("SELECT code,is_core,is_custom FROM ai_query_prompt_rules "
                 "WHERE id=:i AND is_deleted=false"),
            {"i": rule_id},
        )).first()
        if not row:
            raise ValueError("规则不存在")
        if row[1]:
            raise ValueError("核心安全约束不可修改")
        if row[2]:
            raise ValueError("自定义规则没有默认文案")
        default = next((r for r in DEFAULT_RULES if r["code"] == row[0]), None)
        if not default:
            raise ValueError("找不到默认文案")
        await db.execute(
            text("UPDATE ai_query_prompt_rules SET title=:t, body=:b, priority=:p, "
                 "enabled=true, updated_time=:ts WHERE id=:i"),
            {"t": default["title"], "b": default["body"], "p": default["priority"],
             "i": rule_id, "ts": datetime.now()},
        )
    invalidate_cache()
    return await _get_rule(rule_id)


__all__ = [
    "CORE_RULES", "DEFAULT_RULES", "TABLE_DDL", "ensure_prompt_rules", "render_rules",
    "list_rules", "update_rule", "create_rule", "delete_rule", "reset_rule",
    "invalidate_cache", "default_rows",
]
