"""问数评测：LLM 出题（提示 + 容错解析）+ 金标校验 + 入库。

要点（此前实测踩过）：
- 模型会用 ``` 围栏或夹带解释 → 解析必须容错；
- 生成的金标 SQL 可能不可执行/空结果 → **必须执行校验**，否则精度统计被错题拉低。
"""
from __future__ import annotations

import json
import re

from app.core.logger import log

_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def build_prompt(
    schema_rows: list[dict] | None,
    metrics: list[dict] | None,
    terms: list[dict] | None,
    difficulty: str,
    form: str,
    n: int,
) -> str:
    """构造出题提示：只给真实表/字段，要求可直接执行的只读 SELECT。"""
    lines = [
        f"你是 NL2SQL 测试集出题专家。请出 {n} 道「{difficulty}」难度、形式为「{form}」的中文问题，",
        "并为每题给出**可直接执行**的 PostgreSQL 只读 SELECT 金标 SQL：",
        "1) 只能使用下面列出的表与字段；2) 表名/字段名为英文大写时必须用双引号引用；",
        "3) 聚合列起中文别名；4) 问题口语化、贴近业务；5) 结果应至少有 1 行数据。",
        '严格只返回 JSON，不要解释：{"cases":[{"question","gold_sql","difficulty",'
        '"scenario","form","expected_metric"}]}。',
        "【可用表与字段】",
    ]
    for r in (schema_rows or [])[:30]:
        cols = ", ".join(
            f"{c.get('name')}({c.get('comment') or ''})" for c in (r.get("columns") or [])[:14]
        )
        lines.append(f"{r.get('table')}（{r.get('comment') or '无中文名'}）：{cols}")
    if metrics:
        lines.append("【已沉淀指标】" + "；".join(
            f"{m.get('name')}({m.get('key')})" for m in metrics[:15]))
    if terms:
        lines.append("【业务术语】" + "；".join(
            f"{t.get('term')}→{t.get('metric_key') or t.get('field_path')}" for t in terms[:15]))
    return "\n".join(lines)


def parse_cases(text: str) -> list[dict]:
    """容错解析 LLM 输出：去 ``` 围栏、取 JSON；只保留有 question 与 gold_sql 的项。"""
    raw = (text or "").strip()
    raw = _JSON_FENCE_RE.sub("", raw).strip()
    items = None
    # 先试数组：若先抽 `{...}` 只会拿到第一条（实测踩到）
    s2, e2 = raw.find("["), raw.rfind("]")
    if 0 <= s2 < e2:
        try:
            arr = json.loads(raw[s2 : e2 + 1])
            items = arr if isinstance(arr, list) else None
        except Exception:  # noqa: BLE001
            items = None
    if items is None:
        start, end = raw.find("{"), raw.rfind("}")
        data = None
        if 0 <= start < end:
            try:
                data = json.loads(raw[start : end + 1])
            except Exception:  # noqa: BLE001
                data = None
        if isinstance(data, dict):
            items = data.get("cases")
            if items is None and data.get("question") and (
                data.get("gold_sql") or data.get("sql")
            ):
                items = [data]  # 裸的单条 case
        elif isinstance(data, list):
            items = data
    out: list[dict] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        q = str(it.get("question") or "").strip()
        sql = str(it.get("gold_sql") or it.get("sql") or "").strip()
        if not q or not sql:
            continue
        out.append({
            "question": q, "gold_sql": sql,
            "difficulty": str(it.get("difficulty") or ""),
            "scenario": str(it.get("scenario") or ""),
            "form": str(it.get("form") or ""),
            "expected_metric": str(it.get("expected_metric") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# 金标校验与入库
# ---------------------------------------------------------------------------
async def _run_gold(sql: str, datasource: str, auth) -> dict:
    """执行金标 SQL：``system`` 走本地只读；``ds:{id}`` 走该数据源连接器。

    返回 ``{"ok": bool, "rows": list, "error": str}``；不抛异常（交由调用方计数）。
    """
    from .service import SYSTEM_DS, _execute_custom_ds_sql, _execute_sql

    ds = str(datasource or SYSTEM_DS)
    try:
        if ds == SYSTEM_DS:
            res = await _execute_sql(sql)
        else:
            res = await _execute_custom_ds_sql(int(ds.split(":")[-1]), sql, auth)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "rows": [], "error": str(e)[:200]}
    rows = res.get("rows") or []
    err = str(res.get("error") or "")
    return {"ok": (not err) and bool(res.get("ok", True)), "rows": rows, "error": err}


async def verify_and_save(cases: list[dict], datasource: str, auth) -> dict:
    """**执行校验后入库**：SQL 可执行且行数 > 0 才 ``verified=true`` 收录。"""
    from .eval_set import upsert_case

    saved = rejected = 0
    reasons: list[str] = []
    for c in cases or []:
        sql = str(c.get("gold_sql") or "").strip()
        res = await _run_gold(sql, datasource, auth)
        if not res["ok"] or not res["rows"]:
            rejected += 1
            reasons.append(
                f"{str(c.get('question') or '?')[:24]} → {(res.get('error') or '空结果')[:80]}"
            )
            continue
        await upsert_case({**c, "datasource": datasource, "verified": True})
        saved += 1
    log.info(f"[ai-eval] 生成校验：收录 {saved} 题，拒绝 {rejected} 题")
    return {"saved": saved, "rejected": rejected, "reasons": reasons[:10]}


# ---------------------------------------------------------------------------
# LLM 调用（复用问答模型；解析走 parse_cases）
# ---------------------------------------------------------------------------
async def generate_round(
    datasource: str, difficulty: str, form: str, n: int, auth
) -> dict:
    """跑**一轮**出题：LLM → 解析 → **维度以调用方为准** → 校验入库。

    返回 ``{"parsed", "saved", "rejected", "reasons"}``。
    前端/接口可按需重复调用它来逐步补足题集。
    """
    from .service import SYSTEM_DS, AiQueryService, list_ds_schema

    if (datasource or SYSTEM_DS) == SYSTEM_DS:
        schema = await AiQueryService._system_schema()
        rows = [
            {"table": t, "comment": "", "columns": [
                {"name": c.split("(", 1)[0], "comment": ""} for c in cols]}
            for t, cols in schema.items()
        ]
    else:
        rows = await list_ds_schema(int(str(datasource).split(":")[-1]))
    metrics = await AiQueryService.list_metrics(datasource)
    terms = await AiQueryService.list_terms(datasource)
    text = await call_llm(build_prompt(rows, metrics, terms, difficulty, form, n))
    cases = parse_cases(text)
    # 实测：模型会忽略提示里指定的难度/形式（一律回「简单」）→ 以调用方为准
    # 同时把 expected_metric 对齐到**真实指标 key**（模型常写中文名/近似名），
    # 否则语义准确率的分母被一堆「永远不可能命中」的题污染。
    keys = {str(m.get("key")) for m in metrics if m.get("key")}
    by_name = {str(m.get("name")): str(m.get("key")) for m in metrics if m.get("key")}
    for c in cases:
        c["difficulty"], c["form"] = difficulty, form
        em = str(c.get("expected_metric") or "").strip()
        if em and em not in keys:
            c["expected_metric"] = by_name.get(em, "")
        else:
            c["expected_metric"] = em
    out = await verify_and_save(cases, datasource, auth)
    out["parsed"] = len(cases)
    return out


async def call_llm(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str:
    try:
        from openai import AsyncOpenAI

        from app.plugin.module_ai.models.service import build_headers

        from .service import AiQueryService

        rt = await AiQueryService._get_runtime()
        client = AsyncOpenAI(
            base_url=rt["base_url"], api_key=rt.get("api_key") or "sk-none", timeout=timeout,
            default_headers=build_headers(rt["base_url"], rt.get("extra_headers"), "aistation-eval"),
        )
        resp = await client.chat.completions.create(
            model=rt["model"], messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        log.warning(f"[ai-eval] LLM 调用失败: {str(e)[:120]}")
        return ""
