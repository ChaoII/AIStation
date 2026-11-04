"""问数提交前冒烟：一条命令验证「路由没乱 + 快慢路都活着」。

为什么需要它
------------
2026-11 的一次事故：整段替换代码时把 `_prune_columns` 删掉了。
`py_compile` 通过、单测也通过（没人覆盖到），但**运行时 AttributeError**，
所有慢路径问题全挂（评测 accuracy 0.96 → 0.13）。
只有"真的问一句"才能发现。

用法::

    cd backend
    uv run python scripts/query_smoke.py                 # 路由 + 两条真实提问（约 40s）
    uv run python scripts/query_smoke.py --routing-only   # 只验路由（约 10s，不构造应用）

退出码非 0 表示失败，可直接接进提交前钩子。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

DS = "ds:4"

#: 期望走**快路径**的（术语/指标能确定性回答）
FAST_CASES = [
    "煤场进煤总量是多少？",
    "煤场取煤总量是多少？",
    "入厂煤堆放总量是多少？",
    "每日耗用量合计是多少？",
    "入厂煤化验单一共有多少条？",
    "矿点一共有多少个？",
    "区域一共有多少个？",
    "运损合计是多少？",
]

#: 期望**让位给 NL2SQL / 对象查询**的（条件/时间/去重/极值/排序/跨表/分组）
SLOW_CASES = [
    "煤场进煤记录里 2026 年 8 月的进煤量合计是多少？",   # 时间
    "堆放信息里堆煤量超过 10000 的记录有多少条？",         # 阈值
    "煤场进煤总量减去取煤总量是多少吨？",                  # 跨表减法
    "煤场进煤记录和取煤记录加起来一共多少条？",            # 跨表相加
    "煤场进煤记录比取煤记录多多少条？",                    # 跨表比较
    "化验单备注里有多少条包含自动生成？",                  # 条件
    "化验单里已删除的有多少条？",                          # 状态
    "矿点名称里带“煤”字的有多少个？",                     # LIKE
    "化验单里备注不为空的有多少条？",                      # 空值
    "出现过多少家不同的供应商？",                          # 去重
    "同一个供应商最多关联了多少个矿点？",                  # 极值
    "运损合计排名前3的供应商",                             # 排序
    "各煤种的平均干基全硫是多少？",                        # 分组
    "最近一个月平均收到基低位发热量是多少？",              # 时间
]

#: 真实提问冒烟（走完整链路，能抓到"方法被删/执行链断了"这类运行时问题）
ASK_CASES = [
    ("fast", "煤场进煤总量是多少？"),
    ("slow", "化验单备注里有多少条包含自动生成？"),
]

#: 慢路径依赖的类方法（删掉会导致所有慢问题 500，且编译/单测都不报）
REQUIRED_HELPERS = (
    "_prune_columns", "_ds_value_map", "_apply_softdelete_policy",
    "_build_schema_context", "_select_metric", "_object_query_path", "_slow_path",
)


def _load_orm_models() -> None:
    """让 ORM 关系能解析（route-only 模式不构造应用，省 20 秒）。

    不构造应用就没有任何 controller 去导入模型，`AiQueryDatasourceModel` 的
    `relationship("UserModel")` 找不到目标类会直接抛 InvalidRequestError。
    这里只导入被引用到的那个模型，实测 4 秒内就能完成 mapper 配置。
    """
    from app.api.v1.module_system.user.model import UserModel  # noqa: F401


def _check_helpers() -> list[str]:
    from app.plugin.module_ai.query.service import AiQueryService as S

    missing = [n for n in REQUIRED_HELPERS if not hasattr(S, n)]
    return [f"缺少类方法 {n}（慢路径会 500）" for n in missing]


async def _check_routing() -> list[str]:
    from app.plugin.module_ai.query.service import AiQueryService as S

    metrics = await S.list_metrics(DS)
    terms = await S.list_terms(DS)
    bad: list[str] = []
    for q in FAST_CASES:
        if await S._select_metric(q, DS, metrics, terms) is None:
            bad.append(f"应走快路径却让位：{q}")
    for q in SLOW_CASES:
        if await S._select_metric(q, DS, metrics, terms) is not None:
            bad.append(f"应让位却命中指标：{q}")
    return bad


async def _check_ask() -> list[str]:
    from app.plugin.module_ai.query import eval_runner
    from app.plugin.module_ai.query.service import AiQueryService as S

    bad: list[str] = []
    auth = eval_runner._auth()
    for want, q in ASK_CASES:
        t0 = time.perf_counter()
        try:
            d = await asyncio.wait_for(S.ask(q, auth, None, DS), timeout=180)
        except Exception as e:  # noqa: BLE001
            bad.append(f"提问异常 [{q}]：{type(e).__name__}: {str(e)[:120]}")
            continue
        ms = int((time.perf_counter() - t0) * 1000)
        path = d.get("path")
        rows = d.get("rows") or []
        ok_path = (path == "fast") if want == "fast" else (path in ("slow", "object"))
        if d.get("is_error"):
            bad.append(f"提问报错 [{q}]：{(d.get('answer') or '')[:80]}")
        elif not ok_path:
            bad.append(f"路径不符 [{q}]：期望 {want}，实际 {path}")
        elif not rows:
            bad.append(f"结果为空 [{q}]：path={path}")
        else:
            print(f"  ASK ok  {path:<6} {ms:>6}ms  {q[:34]}")
    return bad


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--routing-only", action="store_true", help="只验路由（不构造应用，约 10 秒）")
    args = ap.parse_args()

    problems: list[str] = []

    print("[1/3] 关键方法存在性")
    _load_orm_models()
    problems += _check_helpers()

    print("[2/3] 路由（快路径 vs 让位）")
    problems += await _check_routing()

    if not args.routing_only:
        from main import create_app

        create_app()          # 慢路径要 ORM，必须先构造应用
        print("[3/3] 真实提问冒烟")
        problems += await _check_ask()

    print()
    if problems:
        print(f"❌ 冒烟未通过（{len(problems)} 项）：")
        for p in problems:
            print("   -", p)
        sys.exit(1)
    print(f"✅ 冒烟通过（快路径 {len(FAST_CASES)} / 让位 {len(SLOW_CASES)}"
          + ("" if args.routing_only else f" / 提问 {len(ASK_CASES)}") + "）")


if __name__ == "__main__":
    asyncio.run(main())
