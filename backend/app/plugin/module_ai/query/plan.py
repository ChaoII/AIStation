"""两段式分解生成：**先出执行计划，再据计划写 SQL**。

为什么：困难题（窗口函数/占比/联表）的失败常是"选错分组键/漏联表/漏过滤"，
而这些**在计划层就能看出来**。把计划做成可检查的中间产物，
就能在计划层纠正，而不是在 SQL 层反复猜。

约束：
- **只在** `decomposed_planning=true` **且**题目判定为多步时启用；
- 计划失败/解析不了 → **降级**为单段生成（绝不因计划失败而答不出来）；
- 多一次 LLM 调用 → 延迟↑，所以必须严格限定触发条件。
"""
from __future__ import annotations

import json
import re

#: 多步特征（需要分组+排名/占比/累计/联表/嵌套…）
_MULTISTEP_RE = re.compile(
    r"(排名|名次|前\s*\d+|top\s*\d+|每个.{0,10}(最高|最低|最新|最早|第一个|最大|最小)|"
    r"占比|比例|百分比|累计|累积|环比|同比|嵌套|子查询|"
    r"分组.{0,8}(排名|统计|汇总)|按.{0,8}分区)",
    re.IGNORECASE,
)


def is_multistep(question: str) -> bool:
    """是否需要分解规划（严格：只认明确的多步特征）。"""
    return bool(_MULTISTEP_RE.search(question or ""))


def plan_prompt(question: str) -> str:
    """第一段：只出**执行计划**（不写 SQL）。"""
    return (
        "你是 SQL 执行规划助手。**只输出执行计划，不要写 SQL**。\n"
        f"问题：{question}\n"
        "请严格只返回 JSON："
        '{"tables":["用到的表"],"joins":["a.x=b.y"],"group_by":["分组键"],'
        '"window":["窗口/排名表达式说明"],"filters":["过滤条件"],"outputs":["输出列"],'
        '"order_limit":"排序与截断"}\n'
        "要求：1) 分组键要写清用**名称列还是编号列**；2) 需要排名/累计时写明按什么排序；"
        "3) 只列真正需要的表与列。"
    )


def _first_json_object(text: str) -> dict | None:
    """从文本里取出**第一个完整**的 JSON 对象（按花括号配平，容错截断）。"""
    raw = str(text or "")
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(raw[start : i + 1])
                except Exception:  # noqa: BLE001
                    return None
                return obj if isinstance(obj, dict) else None
    return None


def parse_plan(text: str) -> dict | None:
    """解析计划；解析不了返回 ``None``（调用方降级为单段生成）。"""
    obj = _first_json_object(text)
    if not obj:
        return None
    out: dict = {}
    for k in ("tables", "joins", "group_by", "window", "filters", "outputs"):
        v = obj.get(k)
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
        elif v:
            out[k] = [str(v).strip()]
        else:
            out[k] = []
    ol = obj.get("order_limit")
    out["order_limit"] = str(ol).strip() if ol else ""
    # 至少要能看出用哪些表，否则视为无效计划
    if not out["tables"]:
        return None
    return out


def format_plan(plan: dict) -> str:
    """把计划渲染成给"第二段写 SQL"看的说明。"""
    labels = {
        "tables": "用到的表", "joins": "联表条件", "group_by": "分组键",
        "window": "窗口/排名", "filters": "过滤条件", "outputs": "输出列",
        "order_limit": "排序与截断",
    }
    lines = ["【执行计划（请严格按它写 SQL）】"]
    for k, lab in labels.items():
        v = plan.get(k)
        if not v:
            continue
        if isinstance(v, list):
            lines.append(f"- {lab}: " + "；".join(v))
        else:
            lines.append(f"- {lab}: {v}")
    return "\n".join(lines)


def sql_prompt(question: str, plan: dict, base_context: str) -> str:
    """第二段：把计划 + 原上下文交给模型写 SQL。"""
    return f"{base_context}\n\n{format_plan(plan)}\n\n请按上面的执行计划，只返回一条 SELECT SQL。"
