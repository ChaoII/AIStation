"""澄清反问：**确定性**歧义检测（不调 LLM，1 秒内返回）。

设计原则（见 spec §3）：
- 只在**检索/匹配阶段**就能拿到的信号上判定（规则，不是模型猜）；
- 每轮**最多反问 1 次**（由调用方计数），且用户可"跳过直接查"；
- 命中即**不生成 SQL**，把选择权交回用户 —— 猜错的成本远高于问一句。
"""
from __future__ import annotations

import re

#: 触发"分组口径"提问的问法
_GROUP_HINT = re.compile(r"(按|每个|各|分).{0,6}(分组|统计|汇总|分布)")
#: 实体名 → 该实体常见的"名称列 / 编号列"配对（中文列名/英文列名都收）
_ID_SUFFIXES = ("ID", "CODE", "NO", "NUM", "NUMBER")
_NAME_SUFFIXES = ("NAME", "NAMES")


def _col_code(label: str) -> str:
    """从 schema 的列标签 `CODE(中文名)` 里取出列代码。"""
    return str(label or "").split("(", 1)[0].strip().upper()


def _col_cn(label: str) -> str:
    m = re.search(r"\(([^)]*)\)", str(label or ""))
    return (m.group(1) if m else "").strip()


def _group_key_ambiguity(question: str, schema_map: dict) -> dict | None:
    """分组键歧义：问句要"按 X 分组"，而 X 在表里同时有**名称列**和**编号列**。

    实测：问「按原煤仓分组」，`FUEL_CMCS_INCOALBUNKER` 同时有 `BUNKERNAME`/`BUNKERID`
    → 模型自己挑一个（常常挑到与金标不同的那个）→ 判错。这里直接问用户。
    """
    if not _GROUP_HINT.search(question or ""):
        return None
    for table, labels in (schema_map or {}).items():
        by_code = {_col_code(lab): lab for lab in labels or []}
        for code, lab in by_code.items():
            base = next((code[: -len(s)] for s in _ID_SUFFIXES
                         if code.endswith(s) and len(code) > len(s)), None)
            if not base:
                continue
            name_code = next(
                (c for c in by_code
                 if c != code and c.startswith(base)
                 and any(c.endswith(s) for s in _NAME_SUFFIXES)),
                None,
            )
            if not name_code:
                continue
            # 问句里要提到该实体：用**两个列名的公共前缀**（原煤仓名称/原煤仓编号 → 原煤仓）
            cn_id = _col_cn(lab)
            cn_name = _col_cn(by_code[name_code])
            common = ""
            for a, b in zip(cn_id, cn_name):
                if a != b:
                    break
                common += a
            words = [w for w in (common, base) if len(w) >= 2]
            if not any(
                w in (question or "") or w.lower() in (question or "").lower() for w in words
            ):
                continue
            return {
                "field": "group_key",
                "question": f"按「{_col_cn(by_code[name_code]) or name_code}」还是"
                            f"「{_col_cn(lab) or code}」分组？",
                "options": [
                    {"label": f"{_col_cn(by_code[name_code]) or name_code}（{name_code}）",
                     "value": name_code},
                    {"label": f"{_col_cn(lab) or code}（{code}）", "value": code},
                ],
                "table": table,
                "allow_free_text": True,
            }
    return None


def detect_clarify(question: str, schema_map: dict | None) -> dict | None:
    """命中任一歧义信号即返回反问载荷；否则 ``None``（正常生成 SQL）。"""
    for detector in (_group_key_ambiguity,):
        got = detector(question or "", schema_map or {})
        if got:
            return got
    return None


def merge_clarify_answer(question: str, clarify: dict, value: str) -> str:
    """把用户的选择拼回问句（复用现有 /ask 链路，无需新接口）。"""
    label = value
    for o in (clarify or {}).get("options") or []:
        if o.get("value") == value:
            label = f"{o.get('label')}"
            break
    return f"{question}\n【澄清】分组口径使用 {label}"
