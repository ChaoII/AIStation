"""问数召回服务：语义单元构建 + 多路召回通道 + RRF 融合。

设计见 ``docs/superpowers/specs/2026-10-10-query-recall-service-design.md``。

本模块以**纯函数**为主（接收显式数据、无 IO），便于单测；
取数据的副作用（DB / 本体 / 嵌入）留在 ``service.py`` 的 ``_recall_*`` 薄包装里。
"""
from __future__ import annotations

import re

#: 各召回通道默认权重（RRF 只用**排名**，权重决定通道影响力）。
#: 本体强信号（别名/同义词/属性名）最可信 → 权重最高；
#: 关键词次之（中文注释是业务语义）；对象名命中较泛 → 由向量/关键词兜底。
DEFAULT_WEIGHTS: dict[str, float] = {
    "vector": 1.0,
    "keyword": 0.8,
    "ontology": 1.2,
    "entity": 0.6,
}

#: RRF 平滑常数（业界常用 60，避免头部排名过度主导）。
RRF_K = 60


def fuse_rrf(
    channels: dict[str, list[str]],
    weights: dict[str, float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """多路召回结果按 RRF（Reciprocal Rank Fusion）融合。

    参数:
    - channels: ``{通道名: [表名(按相关度降序)]}``。
    - weights: 覆盖默认权重的部分字典。
    - k: RRF 平滑常数。

    返回:
    - ``[(表名, 分数)]``，按分数降序；同分时按表名字典序，保证**确定性**。

    公式: ``score(t) = Σ_c weight_c / (k + rank_c(t))``，``rank`` 从 1 起。
    未知通道权重按 0 处理（即忽略）；同一张表被多路命中时**累加**而非重复。
    """
    merged_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        merged_weights.update(weights)

    scores: dict[str, float] = {}
    for name, tables in (channels or {}).items():
        weight = merged_weights.get(name, 0.0)
        if weight <= 0:
            continue
        for rank, table in enumerate(tables or [], start=1):
            if not table:
                continue
            scores[table] = scores.get(table, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------------------------------------------------------------------
# 语义单元构建：把「本体 + 资产元数据 + 指标/术语」变成**高语义密度**的可检索文本。
#
# 关键动机（实测）：旧实现喂给向量库的单元是裸标识符（`数据表 {t}` /
# `表 {t} 的字段 {c}`），中文业务词（"煤款金额""设备健康度"）根本检索不到。
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 多路召回通道（纯函数，接收显式数据）
# ---------------------------------------------------------------------------
#: 无匹配时的核心业务表兜底（沿用旧实现的口径）。
CORE_TABLES: tuple[str, ...] = (
    "video_alarm_records", "video_cameras", "video_camera_groups",
    "train_tasks", "ai_call_logs", "sys_user", "video_edge_events",
)

#: 列标签里的中文片段：``col(type)【中文名】【关联:a.b】【取值:x,y】``
_LABEL_CN_RE = re.compile(r"【([^】]+)】")


def _label_terms(label: str) -> tuple[str, list[str]]:
    """从列标签抽出「列名」与「中文片段」。

    ⚠️ 旧实现用 ``label.split("(", 1)[1].rstrip(")")`` 取注释，得到的是
    ``type)【中文名】…``，**永远不可能命中问题**——即「中文注释打分」实际是死的。
    这里改为按 ``【】`` 提取，中文名/关联/取值都参与打分。
    """
    text = str(label or "")
    colname = text.split("(", 1)[0].strip().lower()
    cns = [m.strip() for m in _LABEL_CN_RE.findall(text) if m.strip()]
    return colname, cns


def recall_keyword(
    question: str,
    schema: dict[str, list[str]],
    metrics: list[dict] | None = None,
    terms: list[dict] | None = None,
) -> list[str]:
    """关键词通道：表名 6 分 / 中文片段 5 分 / 列名 3 分 / 词段 1 分，按分数降序。

    ``metrics`` / ``terms`` 目前不参与打分（保留入参以兼容调用方与后续扩展）。
    """
    q = (question or "").lower()
    scores: dict[str, float] = {}
    for table, labels in (schema or {}).items():
        s = 0.0
        if str(table).lower() in q:
            s += 6.0
        for lab in labels or []:
            colname, cns = _label_terms(lab)
            for cn in cns:
                if len(cn) >= 2 and cn.lower() in q:
                    s += 5.0
            if len(colname) >= 3 and colname in q:
                s += 3.0
            for seg in colname.split("_"):
                if len(seg) >= 3 and seg in q:
                    s += 1.0
        if s > 0:
            scores[table] = s
    if len(scores) < 3:  # 命中太少 → 回退核心业务表（沿用旧口径）
        for c in CORE_TABLES:
            if c in (schema or {}):
                scores[c] = scores.get(c, 0.0) + 1.0
    return [t for t, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def recall_ontology(
    question: str, objects: list[dict], table_map: dict[str, str]
) -> list[str]:
    """本体强信号通道：**别名 > 同义词 > 属性名 > 对象名**（分档，档内稳定）。

    旧实现为防通用词噪声只用别名且硬限 3 张；这里保留对象名档但排在最后，
    由 RRF 权重控制影响（对象名档权重最低）。
    """
    q = (question or "").lower()
    if not q:
        return []
    code_to_table: dict[str, str] = {}
    for tbl, code in (table_map or {}).items():
        code_to_table.setdefault(code, tbl)
    tiers: list[list[str]] = [[], [], [], []]
    for o in objects or []:
        code = o.get("code")
        tbl = code_to_table.get(code) or o.get("table")
        if not tbl:
            continue
        aliases = [str(a) for a in (o.get("aliases") or []) if a and len(str(a)) >= 2]
        syns = [s for s in re.split(r"[,，\s、/]+", str(o.get("synonyms") or "")) if len(s) >= 2]
        props = [str(p) for p in (o.get("properties") or []) if p and len(str(p)) >= 2]
        name = str(o.get("name") or "")
        if any(a.lower() in q for a in aliases):
            tiers[0].append(tbl)
        elif any(s.lower() in q for s in syns):
            tiers[1].append(tbl)
        elif any(p.lower() in q for p in props):
            tiers[2].append(tbl)
        elif name and name.lower() in q:
            tiers[3].append(tbl)
    out: list[str] = []
    for tier in tiers:
        for tbl in tier:
            if tbl not in out:
                out.append(tbl)
    return out


def recall_entity(
    question: str, entity_map: dict[str, list[str]], schema: dict[str, list[str]]
) -> list[str]:
    """实体名词通道：问题里出现的实体名词 → 对应表（顺序稳定）。"""
    q = question or ""
    out: list[str] = []
    for noun, tables in (entity_map or {}).items():
        if noun and noun in q:
            for t in tables or []:
                if t in (schema or {}) and t not in out:
                    out.append(t)
    return out


def _unit(kind: str, ref: str, text: str, tables: list[str], **extra) -> dict:
    """组装一个召回单元；``meta["tables"]`` 直接给出**表归属**（不再靠子串反推）。"""
    meta: dict = {"tables": [t for t in tables if t]}
    meta.update(extra)
    return {"kind": kind, "ref": ref, "text": text, "meta": meta}


def build_table_unit(
    table: str, meta: dict, columns: list[dict], kind: str = "table"
) -> dict:
    """表单元（``kind="ds_table"`` 用于外部数据源表，模板相同）。"""
    parts = [f"表 {table}"]
    if meta.get("alias"):
        parts.append(f"中文名:{meta['alias']}")
    if meta.get("domain"):
        parts.append(f"业务域:{meta['domain']}")
    if meta.get("description"):
        parts.append(f"描述:{meta['description']}")
    if meta.get("business_scenarios"):
        parts.append(f"场景:{meta['business_scenarios']}")
    cols: list[str] = []
    for c in columns or []:
        name = c.get("column_name") or c.get("name") or ""
        cn = c.get("description") or c.get("comment") or ""
        if name:
            cols.append(f"{name}({cn})" if cn else name)
    if cols:
        parts.append("列: " + ", ".join(cols))
    return _unit(kind, table, "｜".join(parts), [table])


def build_object_unit(obj: dict, props: list[dict], rels: list[dict]) -> dict:
    """本体对象单元：对象名 + 别名 + 同义词 + 属性 + 关系。

    ``meta["tables"]`` 只放**对象自身支撑表**；关系目标表进 ``text``，
    供阶段 2 的「关系扩表」使用，不计入本单元的表归属。
    """
    code = str(obj.get("code") or obj.get("name") or "")
    table = obj.get("table") or ""
    parts = [f"对象 {obj.get('name') or code}"]
    if obj.get("aliases"):
        parts.append("别名:" + ",".join(str(a) for a in obj["aliases"]))
    if obj.get("synonyms"):
        parts.append(f"同义词:{obj['synonyms']}")
    if props:
        parts.append(
            "属性: " + ", ".join(
                f"{p.get('name')}({p.get('code')})" if p.get("name") else str(p.get("code"))
                for p in props
            )
        )
    for r in rels or []:
        src, tgt = r.get("source"), r.get("target")
        if src or tgt:
            card = r.get("card") or ""
            parts.append(f"关系: {src}→{tgt}({card})")
    return _unit("object", code, "｜".join(parts), [table])


def build_metric_unit(m: dict) -> dict:
    parts = [f"指标 {m.get('name')}({m.get('key')})"]
    if m.get("sql_template"):
        parts.append(f"口径:{m['sql_template']}")
    if m.get("unit"):
        parts.append(f"单位:{m['unit']}")
    return _unit("metric", str(m.get("key") or m.get("name") or ""), "｜".join(parts), [])


def build_term_unit(t: dict) -> dict:
    parts = [f"术语 {t.get('term')}"]
    if t.get("metric_key"):
        parts.append(f"→指标 {t['metric_key']}")
    if t.get("field_path"):
        parts.append(f"→字段 {t['field_path']}")
    return _unit("term", str(t.get("term") or ""), "｜".join(parts), [])


def build_concept_unit(c: dict) -> dict:
    name = str(c.get("name") or "")
    parts = [f"概念 {name}"]
    if c.get("description"):
        parts.append(f"描述:{c['description']}")
    if c.get("synonyms"):
        parts.append(f"同义词:{c['synonyms']}")
    if c.get("domain"):
        parts.append(f"业务域:{c['domain']}")
    if c.get("metric_key"):
        parts.append(f"→指标:{c['metric_key']}")
    tables = [t for t in (c.get("tables") or []) if t]
    if tables:
        parts.append("→表:" + ",".join(tables))
    return _unit("concept", name, "｜".join(parts), tables)
