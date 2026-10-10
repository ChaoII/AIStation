"""火电厂（燃煤业务库）全流程种子：资产 → 字段元数据 → 本体 → 语义层 → 召回单元 → 覆盖率报告。

数据源：``ezdcs_pg``（id=4，331 张表）；核心业务域 = ``FUEL_*`` + ``CMMS_*`` + ``DTXY_*``。

用法（在 ``backend`` 下运行）::

    python scripts/seed_power_plant_ontology.py --ds=4 --dry-run        # 只看计划
    python scripts/seed_power_plant_ontology.py --ds=4 --limit=20       # 小批试跑
    python scripts/seed_power_plant_ontology.py --ds=4                  # 全量核心域
    python scripts/seed_power_plant_ontology.py --ds=4 --no-llm         # 不调 LLM（只用注释）

幂等：可重复执行（按 (kind, ref)/(table, column) upsert）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _auth():
    return SimpleNamespace(user=SimpleNamespace(id=1))


class Ctx:
    """运行上下文：dry-run、LLM 开关与预算。"""

    def __init__(self, dry: bool, use_llm: bool, budget: int) -> None:
        self.dry = dry
        self.use_llm = use_llm
        self.budget = budget
        self.llm_calls = 0
        self.stat: dict[str, int] = {}

    def bump(self, key: str, n: int = 1) -> None:
        self.stat[key] = self.stat.get(key, 0) + n

    def can_llm(self) -> bool:
        return self.use_llm and self.llm_calls < self.budget


async def _llm_json(ctx: Ctx, prompt: str, *, timeout: int = 120) -> dict | None:
    """调用问答模型并解析 JSON（复用 ``AiQueryService._get_runtime`` 的模型解析与请求头）。"""
    if not ctx.can_llm():
        return None
    try:
        from openai import AsyncOpenAI

        from app.plugin.module_ai.models.service import build_headers
        from app.plugin.module_ai.query.service import AiQueryService

        rt = await AiQueryService._get_runtime()
        client = AsyncOpenAI(
            base_url=rt["base_url"],
            api_key=rt.get("api_key") or "sk-none",
            timeout=timeout,
            default_headers=build_headers(rt["base_url"], rt.get("extra_headers"), "aistation-pp"),
        )
        ctx.llm_calls += 1
        resp = await client.chat.completions.create(
            model=rt["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000,
        )
        text = (resp.choices[0].message.content or "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        return json.loads(text[start : end + 1])
    except Exception as e:  # noqa: BLE001 - LLM 失败不阻断整体流程
        print(f"   [LLM] 调用失败（忽略）: {str(e)[:120]}")
        return None


# ---------------------------------------------------------------------------
# 步骤
# ---------------------------------------------------------------------------
async def step_assets(ctx: Ctx, records: list[dict], auth) -> None:
    from app.plugin.module_ai.query.power_plant import asset_payload
    from app.plugin.module_ai.query.service import AiQueryService as S

    need_desc = [r for r in records if not str(r.get("comment") or "").strip()]
    gen: dict[str, str] = {}
    if need_desc:
        batch = need_desc[:40]
        prompt = (
            "你是电力行业（燃煤火电厂）数据库元数据专家。为下列数据库表生成简洁的中文业务名"
            "（不超过20字，只说业务含义）。严格返回 JSON：{\"表名\":\"中文业务名\"}。\n"
            + "\n".join(
                f"{r['table']}：字段 {', '.join(str(c.get('name')) for c in (r.get('columns') or [])[:12])}"
                for r in batch
            )
        )
        data = await _llm_json(ctx, prompt)
        if isinstance(data, dict):
            gen = {str(k): str(v) for k, v in data.items()}
    for rec in records:
        payload = asset_payload(rec, description=gen.get(rec["table"], rec.get("comment")))
        if not payload["alias"]:
            payload["alias"] = gen.get(rec["table"], "")
        if ctx.dry:
            ctx.bump("asset_planned")
            continue
        await S.upsert_asset(SimpleNamespace(**payload), auth)
        ctx.bump("asset_saved")
    ctx.bump("asset_llm_names", len(gen))


async def step_columns(ctx: Ctx, records: list[dict], auth) -> None:
    from app.plugin.module_ai.query.power_plant import column_payloads
    from app.plugin.module_ai.query.service import AiQueryService as S

    for rec in records:
        for payload in column_payloads(rec):
            if not payload["description"] and not payload["sensitive"]:
                continue  # 无注释、不敏感 → 不必落库，省时间
            if ctx.dry:
                ctx.bump("column_planned")
                continue
            await S.upsert_asset_column(SimpleNamespace(**payload), auth)
            ctx.bump("column_saved")


async def step_ontology(ctx: Ctx, records: list[dict], auth) -> None:
    from app.plugin.module_ai.query.power_plant import (
        build_entity_index, find_key_col, find_name_col, infer_links,
    )
    from app.plugin.module_ai.ontology import service as ont

    tables = [r["table"] for r in records]
    index = build_entity_index(tables)
    has_id = {r["table"].upper(): bool(find_key_col(r.get("columns"))) for r in records}
    all_tables = list(index.values())

    # 1) 对象：中文名 / 描述
    for rec in records:
        t = rec["table"]
        comment = str(rec.get("comment") or "").strip()
        if ctx.dry:
            ctx.bump("object_planned")
            continue
        await ont.upsert_object(
            {
                "code": t,
                "backing_table": t,
                "name": comment or t,
                "description": comment,
                "key_prop": find_key_col(rec.get("columns")) or None,
                "name_prop": find_name_col(rec.get("columns")) or None,
            }
        )
        ctx.bump("object_saved")

    # 2) 属性：中文名取列注释（至少保留「中文名与列名不同」的）
    for rec in records:
        for c in rec.get("columns") or []:
            cname, cmt = str(c.get("name") or ""), str(c.get("comment") or "").strip()
            if not cname or (not cmt and not c.get("is_sensitive")):
                continue
            if ctx.dry:
                ctx.bump("prop_planned")
                continue
            await ont.upsert_property(
                {
                    "object_code": rec["table"],
                    "code": cname,
                    "name": cmt or cname,
                    "source_col": cname,
                    "prop_type": "string",
                    "sensitive": bool(c.get("is_sensitive")),
                }
            )
            ctx.bump("prop_saved")

    # 3) 关系：列名 xxxId → 表 token xxx
    for rec in records:
        links = infer_links(rec["table"], rec.get("columns"), index, has_id)
        for link in links:
            if ctx.dry:
                ctx.bump("link_planned")
                continue
            await ont.upsert_link(link)
            ctx.bump("link_saved")


async def step_semantics(ctx: Ctx, records: list[dict], ds_code: str, auth) -> None:
    """指标 / 术语：LLM 建议 + 只保留引用了核心域表的候选。"""
    from app.plugin.module_ai.query.service import AiQueryService as S

    if not records:
        return
    table_names = {r["table"].upper() for r in records}
    prompt = (
        "你是火电厂燃煤业务的数据分析师。根据下列表与中文名，给出 6 个最常用的**业务指标**"
        "（key 用英文小写下划线；sql_template 必须是 PostgreSQL 语法、只能引用给定表、只读 SELECT、"
        "聚合列起中文别名；unit 可为空）与 8 条**业务术语**（燃煤行业口语 → 指标 key 或 表.字段）。"
        "严格返回 JSON：{\"metrics\":[{\"key\",\"name\",\"description\",\"sql_template\",\"unit\"}],"
        "\"terms\":[{\"term\",\"metric_key\",\"field_path\"}]}。\n"
        + "\n".join(f"{r['table']}：{r.get('comment') or '(无中文名)'}" for r in records[:60])
    )
    data = await _llm_json(ctx, prompt)
    if not isinstance(data, dict):
        print("   [语义层] 未获得 LLM 建议（跳过指标/术语）")
        return

    for m in data.get("metrics") or []:
        sql = str(m.get("sql_template") or "")
        refs = {w.strip('"').upper() for w in sql.replace("(", " ").replace(")", " ").split()}
        if not sql or not (refs & table_names):
            continue  # 只保留确实引用核心域表的指标
        if ctx.dry:
            ctx.bump("metric_planned")
            continue
        await S.upsert_metric(
            SimpleNamespace(
                datasource=ds_code, key=str(m.get("key") or "").strip(),
                name=str(m.get("name") or "").strip(), description=str(m.get("description") or ""),
                sql_template=sql, params=[], dimensions=[], agg="count",
                unit=str(m.get("unit") or ""), permission_tag="", enabled=True, sort=0, cache_ttl=0,
            ),
            auth,
        )
        ctx.bump("metric_saved")

    for t in data.get("terms") or []:
        term = str(t.get("term") or "").strip()
        if not term:
            continue
        if ctx.dry:
            ctx.bump("term_planned")
            continue
        await S.upsert_term(
            SimpleNamespace(
                datasource=ds_code, term=term,
                metric_key=str(t.get("metric_key") or ""), field_path=str(t.get("field_path") or ""),
                type="term",
            ),
            auth,
        )
        ctx.bump("term_saved")


async def step_rebuild(ctx: Ctx) -> None:
    from app.plugin.module_ai.query.service import AiQueryService as S

    if ctx.dry:
        ctx.bump("rebuild_skipped")
        return
    info = await S.rebuild_recall_units()
    ctx.bump("recall_units", int(info.get("units") or 0))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def run(ds_id: int, ctx: Ctx, limit: int | None) -> None:
    from main import create_app

    create_app()  # 触发模块发现，加载全部 ORM 模型

    from app.plugin.module_ai.query.power_plant import is_core
    from app.plugin.module_ai.query.service import list_ds_schema

    auth = _auth()
    all_records = await list_ds_schema(ds_id)
    core = [r for r in all_records if is_core(r["table"])]
    if limit:
        core = core[:limit]
    ds_code = f"ds:{ds_id}"
    print(f"数据源 ds:{ds_id} 共 {len(all_records)} 张表；核心业务域 {len(core)} 张"
          f"（{'dry-run' if ctx.dry else '写入'}，LLM={'开' if ctx.use_llm else '关'}）")

    await step_assets(ctx, core, auth)
    await step_columns(ctx, core, auth)
    await step_ontology(ctx, core, auth)
    await step_semantics(ctx, core, ds_code, auth)
    await step_rebuild(ctx)

    print("\n=== 覆盖率报告 ===")
    with_comment = sum(1 for r in core if str(r.get("comment") or "").strip())
    print(f"核心表 {len(core)} 张，其中 {with_comment} 张有上游注释（{with_comment / max(1, len(core)):.0%}）")
    print(f"LLM 调用 {ctx.llm_calls} 次（预算 {ctx.budget}）")
    for k in sorted(ctx.stat):
        print(f"  {k} = {ctx.stat[k]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", type=int, default=4, help="数据源 id（默认 4 = ezdcs_pg 燃煤业务库）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--llm-budget", type=int, default=8)
    args = ap.parse_args()
    ctx = Ctx(dry=args.dry_run, use_llm=not args.no_llm, budget=args.llm_budget)
    asyncio.run(run(args.ds, ctx, args.limit or None))


if __name__ == "__main__":
    main()
