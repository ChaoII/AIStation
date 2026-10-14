"""问数「多轮查询重写」逻辑层（G7）。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.9 G7，
仿 SuperSonic `QueryRewritingStrategy`：用 LLM 把「那上周呢 / 换成华东呢」这类**指代/
省略**的追问，补全成**自包含**的完整问题，再交给路由（指标快路径 / 对象查询 / NL2SQL）。

成本纪律：本项目「多一次 LLM 调用必须证明值得」。因此 `needs_rewrite` 必须**严格**：
只有「看起来不自包含」且「有历史」时才触发，否则零额外调用。本模块是纯逻辑、无 IO，
可 `PYTEST_NO_APP=1` 快测。LLM 调用本身封装在 `service.py`（复用 agno 链路）。
"""
from __future__ import annotations

from typing import Any

#: 迹象词：出现即认为「可能是追问/指代」，值得重写。
#: 「还有 / 呢 / 又」这类放在句尾或转折处，是追问高发形态。
_REFERENCE_WORDS: tuple[str, ...] = (
    "这", "那", "它", "这些", "那些", "上面", "刚才", "换成", "改成",
    "再来", "还有", "呢", "又", "其余", "剩下", "别的", "其它", "其他",
)

#: 极短句阈值：<= SHORT_LIMIT 字，且无实体信息，基本是省略式追问。
_SHORT_LIMIT = 6

#: 重写结果上限：过长说明模型跑偏，直接弃用回退原文。
_MAX_REWRITTEN_LEN = 400

#: 引用最新历史轮数。
_HISTORY_N = 2


def needs_rewrite(question: str, history: list[dict] | None) -> bool:
    """是否需要对当前问题做多轮重写。

    - **无历史** → False（首轮无上下文可补，不该为补全而补全）。
    - 含迹象词（这/那/换成/还有/呢…）→ True。
    - 极短句（<= 6 字）→ True。
    - 其余（看起来已自包含）→ False（省钱，避免每轮都多一次 LLM）。
    """
    q = (question or "").strip()
    if not q or not history:
        return False
    if len(q) <= _SHORT_LIMIT:
        return True
    for w in _REFERENCE_WORDS:
        if w in q:
            return True
    return False


def recent_history(messages: list[dict] | None) -> list[dict]:
    """从会话消息里抽取「成功」的历史（question + sql + datasource），取最近 N 轮。

    ``messages`` 为 ``list_messages`` 的输出（每项含 ``question / sql / datasource``），已按
    时间升序排列。只保留**成功**（无 is_error / 非空 sql 更能代表可执行上下文）。
    """
    out: list[dict] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if m.get("is_error"):
            continue
        q = str(m.get("question") or "").strip()
        if not q:
            continue
        out.append({
            "question": q,
            "sql": str(m.get("sql") or "").strip()[:300],
            "datasource": str(m.get("datasource") or ""),
        })
    return out[-_HISTORY_N:]


def build_rewrite_prompt(question: str, history: list[dict]) -> str:
    """组装「把追问补全为自包含问题」的提示词。

    ``history`` 为 ``recent_history`` 的输出：``[{question, sql, datasource}]``。
    只输出重写后的问题，不要解释。
    """
    lines: list[str] = []
    for i, h in enumerate(history or [], start=1):
        lines.append(f"第{i}轮：\n用户问：{h['question']}")
        if h["sql"]:
            lines.append(f"生成的 SQL：{h['sql']}")
    hist_block = "\n".join(lines) if lines else "（无历史）"
    return (
        "你是查询改写助手。把用户**当前这一问**，结合下面的历史对话，改写成**一个自包含、"
        "无需历史也能看懂**的完整问题。\n"
        "只输出改写后的问题。保留原问题的实体/指标/维度/取值/时间范围，不要擅自增删业务条件。\n\n"
        f"# 历史对话（最近 {len(history or [])} 轮）\n{hist_block}\n\n"
        f"# 当前问题\n{question}\n\n"
        "只输出改写后的问题（一句话，不要解释、不要代码块）。"
    )


def finalize_rewrite(original: str, rewritten: str) -> str | None:
    """校验重写结果；非法/空/过长/与原句相同 → 返回 ``None``（调用方用原问题）。

    这是「重写不得改变原意」的兜底：宁可不用，不可用错。
    """
    if not rewritten:
        return None
    r = rewritten.strip().strip("。").strip()
    o = (original or "").strip()
    if not r or len(r) > _MAX_REWRITTEN_LEN:
        return None
    if r == o:
        return None
    # 去掉可能被模型加的引号/围栏（含中日韩全角引号与角括号）
    r = r.strip('“”"\'【】[]()（）「」『』')
    if not r or r == o:
        return None
    return r


__all__ = [
    "needs_rewrite", "recent_history", "build_rewrite_prompt", "finalize_rewrite",
    "_REFERENCE_WORDS",
]
