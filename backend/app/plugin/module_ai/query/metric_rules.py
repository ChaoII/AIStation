"""指标规则：匹配 / 快路径阻断 / 参数构造（2026-11-08 从 service.py 拆出）。

全部是**确定性**规则（不调模型）：
1. ``match_metric``：问句 → 指标（术语优先、对象别名、打分阈值），决定能否走快路径；
2. ``fast_path_blockers``：时间/分组/排序/多表等诉求把快路径挡回慢路径；
3. ``build_params`` / ``effective_agg`` / ``metric_main_table``：把命中指标变成可执行 SQL 参数；
4. ``pick_fewshots`` / ``score_fewshot``：慢路径的相似样例检索。

测试对 ``service._match_metric`` / ``_wants_grouping`` 有打桩：``service.py`` 保留
同名再导出，调用方（``_select_metric`` / ``_object_query_path``）走模块全局名或
``_svc.``，两者都能命中打桩。
"""
from __future__ import annotations

import re
from contextvars import ContextVar as _ContextVar
from typing import Any

from .language_rules import current as _lang
from .question_rules import detect_time_frame, metric_time_hint, parse_time_range

#: 与 service 同值（常量，避免顶层 import service 造成循环）
SYSTEM_DS = "system"

GENERIC_BIGRAMS = {
    "多少", "数量", "合计", "统计", "所有", "每个", "分别", "共有", "总数", "总共",
    "一共", "几条", "几个", "哪些", "什么", "怎么", "是否", "有无", "多种", "多个",
    # 业务上到处都在用的词：不能作为「指向某张表/某个指标」的证据
    # （实测「小程序版本**管理**」撞上「卸煤**管理**记录数」，「人员**信息**表」撞上「存款记录」）
    "管理", "记录", "信息", "数据", "系统", "表格", "内容", "情况", "查询", "列表",
    "明细", "总计", "本月", "上月", "最近", "当前",
}


LATIN_WORD_RE = re.compile(r"[a-z0-9_]{2,}")


GROUPING_RE = re.compile(r"(每个|各|逐[个条]|分别|分布|按.{0,8}(分组|统计|汇总|分类))")


METRIC_NAME_SUFFIXES = ("记录数", "数量", "总数", "条数", "个数", "合计", "总和", "总计", "数", "量")


MIN_METRIC_SCORE = 4


NEEDS_SQL_RE = re.compile(
    r"(包含|含有|带.{0,4}字|等于|不等于|大于|小于|不少于|不超过|之间|其中|并且|而且|或者|除了|排除"
    r"|之后|之前|以后|以前|以上|以下|超过|不足|截至|截止|至今|起算"
    # 「多少*不同的」= COUNT(DISTINCT)：实测「多少家不同的供应商」漏过去，
    # 被「供应商数」指标答成总行数
    r"|几种|多少(家|个|种|条|位)?不同|多少个不同|去重|重复|排名|前\s*\d+|占比|比例|百分比"
    # 状态修饰 = WHERE 条件：实测「已删除的入厂煤批次有多少条」被总数指标抢答
    r"|已删除|未删除|已审核|未审核|已发布|未发布|已启用|未启用|已停用|已完成|未完成"
    r"|有效|无效|正常的|异常的|未关联|已关联"
    # 人群筛选 = WHERE 条件：实测「人员信息中男性有多少人」会被「人员总数」抢答
    r"|男性|女性|性别"
    # 「有…记录的」是存在性判断（EXISTS/JOIN），不是单纯的行数
    r"|有.{0,8}记录的|涉及"
    # 其余算子：极值、空值判断、前后缀匹配、百分比表述
    # 实测：「同一个供应商最多关联了多少个矿点」被「矿点数」指标抢答，
    #      「备注不为空」「以…字开头」「百分之多少」同样漏网
    r"|不为空|为空|非空|为\s*\d|以.{0,6}(开头|结尾)|百分之|最多|最少|最大|最高|峰值|最小|最低"
    # 跨表加减/两者比较：单表模板算不出来
    r"|加起来|之差|差额|减去|扣除|再加上|比.{0,8}(多|少))"
)


AGG_INTENT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("avg", ("平均", "均值")),
    ("max", ("最大", "最高", "峰值")),
    ("min", ("最小", "最低")),
    ("sum", ("合计", "总和", "总计", "累计", "求和", "总量", "吨数")),
)


AGG_NOUN_RE = re.compile(
    r"(平均|最大|最小|最高|最低)([\u4e00-\u9fff]{2,12}?)(?=是多少|为多少|一共|共有|多少|呢|吗|？|\?|$)")

# 「计数意图」：问「多少条/多少份/多少个/数量」时，平均值/极值类指标不可能答对。
# 实测「燃煤合同一共有多少份」被描述里含「合同」的「平均合同单价」以 4 分抢走 →
# 快路径答成平均单价（数值对不上 gold 的 COUNT）。
COUNT_INTENT_RE = re.compile(
    r"(多少|几)\s*(条|份|个|张|家|次|种|名|项|台|套|样|批)|数量|条数|记录数|计数|总数")
NON_COUNT_AGG = {"avg", "max", "min", "ratio"}
NON_COUNT_NAME_RE = re.compile(r"^(平均|最大|最小|最高|最低)")

# 「物理量诉求」：问存煤量/总量/合计/吨数/金额时，**行数类指标**（条数/记录数/计数）
# 不可能答对。实测：「当前煤场的存煤量是多少」被「每日耗用量及存煤量条数」抢答，
# 返回 370（表行数）而不是吨数。
PHYSICAL_QTY_RE = re.compile(
    r"(存煤|库存|总量|合计|总和|吨数|多少吨|多少方|大卡|金额|余额|耗用|发热量|硫分|灰分|水分)")
# 问句明确问「条数/记录数」时，行数指标仍然有效（是用户要的）
ROWCOUNT_ASK_RE = re.compile(r"(条数|记录数|笔数|多少条|多少笔)")
ROWCOUNT_NAME_RE = re.compile(r"(条数|记录数|笔数)$")


def is_rowcount_metric(metric: dict) -> bool:
    """指标是否在数「行数」（而不是求和/求平均）。"""
    name = str(metric.get("name") or "").strip()
    key = str(metric.get("key") or "").strip().lower()
    return (bool(ROWCOUNT_NAME_RE.search(name)) or key.startswith("count_")
            or key.endswith("_count"))


def prefers_rowcount(question: str, metric: dict) -> bool:
    """问句明确问「条数/记录数」，且当前指标就是在数行数 → 术语不应把它改判走。

    实测：「每日耗用量及存煤量**条数**是多少」里有「存煤量」，会被术语改判到
    「煤场存煤量」（吨），把 370 条答成 23 万吨。
    """
    return bool(_lang()["rowcount"].search(question or "")) and is_rowcount_metric(metric)


ORDER_WORD_RE = re.compile(r"(排序|升序|降序|从大到小|从小到大|按.{0,6}排|前\s*\d+\s*(名|条|个)|排名)")


TIME_QUALIFIER_RE = re.compile(
    r"(最近|近\s*\d|近一|过去|本(月|周|年|季度)|这个月|这周|当月|今年|去年"
    r"|上(个?月|个?周|个?年|个?季度)|今天|今日|昨天|昨日|\d{4}\s*年|\d+\s*(天|日|周|个?月|年))"
)


def score_fewshot(question: str, ex_question: str) -> int:
    """few-shot 示例与问句的相关度：**中文二元组** + 英文/数字词 的重叠数。

    旧实现 `re.findall(r"[\\w\\u4e00-\\u9fa5]{2,}", question)` 把整句中文当成**一个 token**
    （中文都是 `\\w`），于是 `tok in 示例问句` 几乎永不成立 → 所有示例同分 →
    实际返回"最老的 4 条"，与问句无关（实测：补 few-shot 反而让准确率下降）。
    """
    return len(bigrams(question) & bigrams(ex_question)) + len(
        latin_words(question) & latin_words(ex_question)
    )


def pick_fewshots(question: str, examples: list[dict], datasource: str | None = None,
                  k: int = 4) -> list[dict]:
    """按相关度挑 top-K 示例；同数据源加权，同分时**新示例优先**。

    ⚠️ **防泄漏**：排除与当前问句**完全相同**的示例 —— 否则"把错题沉淀成示例"
    会让评测时模型直接看到本题答案，分数虚高（实测 80.7% → 95.0% 里有很大水分）。
    """
    qkey = re.sub(r"\s+", "", (question or "").strip())
    scored: list[tuple[int, int, dict]] = []
    for i, f in enumerate(examples or []):
        fq = str(f.get("question") or "")
        if re.sub(r"\s+", "", fq.strip()) == qkey:
            continue
        s = score_fewshot(question, fq)
        if not datasource or f.get("datasource") == datasource or datasource == SYSTEM_DS:
            s += 1
        scored.append((s, i, f))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [f for _, _, f in scored[:k]]


def bigrams(text: str) -> set[str]:
    """取中文二元组（剔除非中文与通用词），用于"指标自己的用词"是否出现在问句里。"""
    zh = re.sub(r"[^\u4e00-\u9fff]+", " ", text or "")
    out: set[str] = set()
    for part in zh.split():
        for i in range(len(part) - 1):
            bg = part[i:i + 2]
            if bg not in GENERIC_BIGRAMS:
                out.add(bg)
    return out


def latin_words(text: str) -> set[str]:
    return set(LATIN_WORD_RE.findall((text or "").lower()))


def wants_grouping(question: str) -> bool:
    """问句是否要求**按实体分组/逐个**（单值指标答不了）。"""
    return bool(_lang()["grouping"].search(question or ""))


def metric_name_core(name: str) -> str:
    """剥掉指标名尾部的度量词，得到"实体名"（矿点数 → 矿点）。"""
    n = (name or "").strip()
    for suf in METRIC_NAME_SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf) + 1:
            return n[: -len(suf)]
    return n


#: 指标护栏参数**默认值**（可在「问数设置 → 语言规则 → 指标护栏」里改）。
#: 原则：能改说法/阈值就不写死；代码只保留默认值，运行期用 `guard_rules()` 读取。
DEFAULT_GUARD_RULES: dict = {
    "sibling_qualifiers": [
        "明细", "主表", "分仓", "结果", "限制", "台账", "参数", "历史", "流水", "汇总表",
    ],
    "min_alias_len": 4,
    "min_core_len": 3,
}

_GUARD_CTX: _ContextVar[dict | None] = _ContextVar("query_metric_guard_rules", default=None)


def _as_str_list(v, fallback: list[str]) -> list[str]:
    if isinstance(v, list):
        out = [str(x).strip() for x in v if str(x).strip()]
        if out:
            return out
    return list(fallback)


def set_guard_rules(raw) -> None:
    """从设置装载护栏参数（`metric_guard_rules`）；坏配置回落默认。"""
    if isinstance(raw, str) and raw.strip():
        try:
            import json as _json

            raw = _json.loads(raw)
        except Exception:  # noqa: BLE001
            raw = None
    if not isinstance(raw, dict):
        _GUARD_CTX.set(None)
        return
    base = dict(DEFAULT_GUARD_RULES)
    # 空列表是**有意义的配置**（=关掉这条否决），不能像词表那样回落默认
    if isinstance(raw.get("sibling_qualifiers"), list):
        base["sibling_qualifiers"] = [
            str(x).strip() for x in raw["sibling_qualifiers"] if str(x).strip()
        ]
    else:
        base["sibling_qualifiers"] = list(DEFAULT_GUARD_RULES["sibling_qualifiers"])
    for k in ("min_alias_len", "min_core_len"):
        try:
            if raw.get(k) is not None:
                base[k] = max(1, int(raw[k]))
        except (TypeError, ValueError):
            pass
    _GUARD_CTX.set(base)


def guard_rules() -> dict:
    return _GUARD_CTX.get() or dict(DEFAULT_GUARD_RULES)


def guard_effective(raw=None) -> dict:
    """给界面：生效值（默认 + 覆盖）。"""
    set_guard_rules(raw) if raw is not None else None
    try:
        return dict(guard_rules())
    finally:
        if raw is not None:
            _GUARD_CTX.set(None)


#: 兼容旧引用：默认兄弟限定词（运行期请用 guard_rules()["sibling_qualifiers"]）
SIBLING_QUALIFIERS: tuple[str, ...] = tuple(DEFAULT_GUARD_RULES["sibling_qualifiers"])


def _competitor_alias(
    question: str, own_table: str, alias_map: dict[str, list[str]] | None,
    own_aliases: list[str] | None = None,
) -> str:
    """问句里是否点到了**别的表**的业务别名（且比本表别名更具体）。

    为什么需要（2026-11-12）：指标护栏只管住了计数型，`sum/avg` 仍会跨表抢答——
    「期初库存明细的 QTY 合计」被库存指标（绑定进煤流水）抢；「配煤结果的混煤量」被
    「配煤方案结果明细表STOQTY合计」抢。它们的共同点是：**问句里出现了另一张表的
    业务别名**（期初库存明细 / 配煤结果），而指标绑定表对不上。

    只认长度 ≥4 的别名，且不与本表别名互相包含，避免「库存」「合同」这类短词误伤。
    """
    if not alias_map:
        return ""
    q = (question or "").lower()
    own = [str(a).lower() for a in (own_aliases or []) if str(a).strip()]
    own_tbl = str(own_table or "").upper()
    own_best = max((len(a) for a in own if a in q), default=0)
    best_alias = ""
    best_len = own_best
    for tbl, arr in alias_map.items():
        if str(tbl).upper() in (own_tbl, own_tbl[4:] if own_tbl.startswith("ONT_") else own_tbl):
            continue
        for a in arr or []:
            al = str(a).strip().lower()
            if len(al) < guard_rules()["min_alias_len"] or al not in q:
                continue
            if any(al in o or o in al for o in own):
                continue
            if len(al) > best_len:
                best_alias, best_len = al, len(al)
    return best_alias


def _metric_table_evidence(question: str, metric_name: str, metric_core: str,
                           table: str, aliases: list[str] | None = None) -> bool:
    """计数型指标是否有资格回答（防「通用词重合 = 同一张表」的误劫持）。

    证据（满足其一）：
    1. 指标名出现在问句；
    2. 指标核心名（去掉通用词后 ≥3 字）出现在问句，且它不是表名/别名本身；
    3. 绑定表的**表名或业务别名**出现在问句，且问句没有点出同族更具体的限定词。

    数据来源（2026-11-12 补齐后）：资产中文名 + 本体对象别名。此前别名全空，
    同样的规则一拦就误伤正确指标，所以先补数据再上规则。
    """
    q = (question or "").lower()
    name = (metric_name or "").lower()
    core = (metric_core or "").lower()
    aliases = [str(a).strip().lower() for a in (aliases or []) if str(a).strip()]
    t = (table or "").lower()
    if name and name in q:
        return True
    core_is_table = bool(core) and (
        core in t or any(core in a or a in core for a in aliases)
    )
    if len(core) >= guard_rules()["min_core_len"] and core in q and not core_is_table:
        return True
    if not any((x and len(x) >= 2 and x in q) for x in [t, *aliases]):
        return False
    return not any(
        (qual in q) and (qual not in name) and all(qual not in a for a in aliases)
        for qual in guard_rules()["sibling_qualifiers"]
    )


def match_metric(question: str, metrics: list[dict], terms: list[dict],
                  concepts: list[dict] | None = None,
                  objects: dict[str, dict] | None = None,
                  table_alias: dict[str, list[str]] | None = None) -> dict | None:
    """按得分选指标：**指标自己的用词**命中 + 术语绑定 + 概念(含同义词)绑定 + 时间语境对齐。

    打分（实测调过）：
      - 指标名整体出现在问句：+6；key 出现：+4；绑定术语命中：+3；
      - 与**指标名**的中文二元组重合：每个 +3；与**描述**重合：每个 +1
        （名称比描述更具体，权重更高）；
      - 时间语境一致 +4，冲突 -2；
      - 总分需 ≥ ``MIN_METRIC_SCORE`` 才算命中。

    旧实现用「类型/分布/数量/多少」这类通用词给所有指标一起加分，
    导致「合同**数量**」被描述里含「数量」的「结算**量**」抢走（真实误命中）。
    """
    q = question.lower()
    q_grams = bigrams(question)
    frame = detect_time_frame(question)
    _lr = _lang()
    count_intent = bool(_lr["count_intent"].search(question))
    physical_qty = bool(_lr["physical_qty"].search(question))
    rowcount_asked = bool(_lr["rowcount"].search(question))
    # 业务概念（含同义词）→ 指标：与术语同等参与快路径匹配，闭合「概念→指标」
    concept_bind: list[tuple[str, str]] = []
    for c in concepts or []:
        mk = (c.get("metric_key") or "").strip()
        if not mk:
            continue
        syns = c.get("synonyms") or ""
        syn_list = [x.strip() for x in str(syns).split(",") if x.strip()] if syns else []
        for nm in [c.get("name"), *syn_list]:
            if nm:
                concept_bind.append((str(nm).lower(), mk))
    best = None
    best_score = 0
    for m in metrics:
        if not m["enabled"]:
            continue
        name = (m.get("name") or "").lower()
        key = (m.get("key") or "").lower()
        core = metric_name_core(m.get("name")).lower()
        # 问的是物理量（存煤量/总量/金额…）时，数行数的指标不参与竞争。
        if physical_qty and not rowcount_asked and is_rowcount_metric(m):
            continue
        # 计数意图下，平均值/极值类指标不参与竞争（除非问句明确说了完整口径）。
        # 「燃煤合同一共有多少份」与「平均合同单价」都含「合同」，不拦就会答成平均单价。
        if count_intent and (
            (m.get("agg") or "").lower() in NON_COUNT_AGG
            or _lr["non_count_prefixes"].match(m.get("name") or "")
        ) and not (core and core in q):
            continue
        # 计数型指标必须「问的就是这张表」：挡掉「供应商煤质限制 → 供应商数量」这类
        # 由通用词（供应商/数量/计划/明细）造成的误劫持。只拦计数型：
        # sum/avg 指标常被命名为「XX量」，与表名天生不同（库存量 vs 进煤流水）。
        if table_alias is not None and (
            (m.get("agg") or "").lower() == "count" or is_rowcount_metric(m)
        ):
            # 绑定型指标（object_code + agg_fn）没有 FROM，用对象 code 当表标识
            _tbl = metric_main_table(m) or str(m.get("object_code") or "")
            if _tbl:
                _al = (table_alias.get(_tbl) or table_alias.get(_tbl.upper())
                       or table_alias.get(str(m.get("object_code") or "")) or [])
                if isinstance(_al, str):
                    _al = [_al]
                if not _metric_table_evidence(
                    question, m.get("name") or "", core, _tbl, list(_al)
                ):
                    continue
        # 问句点到了别的表的业务别名 → 本指标不参战（对所有聚合类型生效）
        if table_alias is not None:
            _tbl2 = metric_main_table(m) or str(m.get("object_code") or "")
            if _tbl2:
                _own = table_alias.get(_tbl2) or table_alias.get(_tbl2.upper()) or []
                if isinstance(_own, str):
                    _own = [_own]
                if _competitor_alias(question, _tbl2, table_alias, list(_own)):
                    continue
        # 问「多少条/多少笔」是数行数：非计数指标不参战
        if rowcount_asked and not physical_qty and (m.get("agg") or "").lower() != "count":
            continue
        # 「词证据」：指标自己的用词出现在问句里才算数；名称权重 > 描述，且不重复计同一个词
        n_grams = bigrams(m.get("name"))
        d_grams = bigrams(m.get("description")) - n_grams
        word = 3 * len(q_grams & n_grams) + 1 * len(q_grams & d_grams)
        if name and name in q:
            word += 6
        else:
            # 实体名命中：指标「矿点数」的实体是「矿点」，问句说的也是「矿点」
            if core and len(core) >= 2 and core in q:
                word += 5
        if key and key in q:
            word += 4
        # **本体桥**：指标绑定到哪个对象，那个对象的中文名/别名也是"用户会怎么说"。
        # 这是本体存在的意义 —— 名字对不上时靠对象语义兜底（不带属性的轻量查询）。
        obj = (objects or {}).get(str(m.get("object_code") or ""))
        if obj:
            oname = str(obj.get("name") or "").lower()
            if oname and len(oname) >= 2 and oname in q:
                word += 4
            for al in (obj.get("aliases") or []):
                al = str(al).lower()
                if len(al) >= 2 and al in q:
                    word += 3
                    break
        for t in terms:
            if t.get("metric_key") == m["key"] and t.get("term") and t["term"].lower() in q:
                # 术语是**人工绑定**的映射：用户说「热值」就是指 avg_rz，
                # 权重必须高到能单独过阈值（+3 时低于 MIN_METRIC_SCORE=4，
                # 实测「热值是多少」永远匹配不到 → 走慢路径且模型返回空 SQL）。
                word += 6
        for nm, mk in concept_bind:
            if mk == m["key"] and nm in q:
                word += 3
        # 时间语境：指标自身的时间维度与问句一致（允许"只靠时间维度"选中，
        # 如「这个月…报警」→ 本月告警数，其名称与问句没有共同词）
        mtime = metric_time_hint(m)
        time_bonus = 0
        if frame and mtime == frame:
            time_bonus = 4
        elif frame and mtime and mtime != frame:
            # 时间语境是**硬约束**：问「这个月」时，"今日告警"这类指标不该参与竞争。
            # 以前只 -2，术语权重一提高它就会反超（实测 alert_count_today 抢走本月题）。
            continue
        # 合格门槛：词证据够强，或时间维度正好对上
        if word < MIN_METRIC_SCORE and not (frame and mtime == frame):
            continue
        score = word + time_bonus
        if score > best_score:
            best_score = score
            best = m
    return best if best and best_score > 0 else None


def needs_custom_sql(question: str) -> bool:
    """问句是否带有指标模板无法表达的条件/去重语义。"""
    return bool(NEEDS_SQL_RE.search(question or ""))


def effective_agg(metric: dict) -> str:
    """指标**实际**在算什么聚合：以 SQL 模板/``agg_fn`` 为准，不信 ``agg`` 字段。

    ``agg`` 是人工维护的元数据，实测存在 ``SELECT SUM(CHECKQTY)`` 却标成
    ``count`` 的（``total_settlement_qty``）。拿它校验问句会把合法问题拦掉
    （「验收量合计」就是这种），所以口径必须从表达式本身读。
    """
    if str(metric.get("object_code") or "") and str(metric.get("agg_fn") or ""):
        return str(metric["agg_fn"]).strip().lower()
    sql = (metric.get("sql_template") or "").upper()
    for fn in ("AVG", "MAX", "MIN", "SUM", "COUNT"):
        if re.search(rf"\b{fn}\s*\(", sql):
            return fn.lower()
    return str(metric.get("agg") or "").strip().lower()


def metric_accepts_time(metric: dict) -> bool:
    """模板是否真的把时间参数用上了（目前只支持 ``{days}``）。"""
    return "{days}" in (metric.get("sql_template") or "")


def fast_path_blockers(question: str, metric: dict,
                        terms: list[dict] | None = None,
                        concepts: list[dict] | None = None) -> list[str]:
    """**准入检查**：指标模板能不能解释清楚这句话？返回拦下来的理由（空=可以答）。

    为什么用白名单而不是黑名单：黑名单是"出现危险词才拦"，永远漏（实测已经漏了
    「最近一个月」）；白名单是"模板必须能解释每一处限定，解释不了就让位 NL2SQL"，
    漏的方式变成"慢一点"，而不是"自信地答错"。

    目前能判定的限定：
    - 时间范围（问句有时间词 → 模板必须有 ``{days}`` 且能解析出天数）；
    - 聚合口径（问「最大」而模板是 SUM 之类）。
    """
    reasons: list[str] = []
    q = question or ""

    if TIME_QUALIFIER_RE.search(q):
        parsed = parse_time_range(q)
        if not parsed.get("days"):
            reasons.append("时间限定无法解析为参数")
        elif not metric_accepts_time(metric):
            reasons.append("模板没有时间参数（会答成全量）")

    # 排序诉求：模板只出一个聚合值，给不了"按X排序"的结果集
    if _lang()["order"].search(q):
        reasons.append("问句要求排序（模板只出聚合值）")

    # 聚合对象必须与模板一致：问「平均灰分」却命中「平均发热量」的模板 —— 实测会
    # 自信地报出另一个指标的数字。只在 平均/最大/最小/最高/最低 时检查（合计/总量
    # 常是泛化说法，误伤风险高）。
    m = AGG_NOUN_RE.search(q)
    if m:
        # 去掉提问尾巴（「平均发热量是多少」→ 发热量）
        noun = re.sub(r"(是多少|为多少|一共|共有|多少|呢|吗|？|\?)+$", "", m.group(2))
        hay = f"{metric.get('name') or ''} {metric.get('sql_template') or ''}"
        if noun and noun not in hay:
            reasons.append(f"聚合对象不符：问的是「{noun}」，模板算的不是它")

    eff = effective_agg(metric)
    if eff:
        for want, words in AGG_INTENT:
            if any(w in q for w in words) and eff != want:
                reasons.append(f"聚合口径不符：问句要 {want}，模板是 {eff}")
                break

    return reasons


def metric_main_table(metric: dict) -> str:
    """指标的主表：优先从 SQL 模板的 FROM 取；绑定型指标（SQL 是注释）返回空。"""
    m = re.search(r"\bFROM\s+\"?([A-Za-z_][A-Za-z0-9_]*)\"?",
                  metric.get("sql_template") or "", re.IGNORECASE)
    return m.group(1) if m else ""


def build_params(metric: dict, question: str) -> dict[str, Any]:
    """从问句抽取指标所需参数（时间、实体等）。"""
    params = parse_time_range(question)
    # 指标声明的 value 型参数若未从问句得到则给默认
    for p in metric.get("params") or []:
        if p.get("key") not in params:
            if p.get("type") == "value" and p.get("default") is not None:
                params[p["key"]] = p["default"]
            else:
                params[p["key"]] = 30
    return params


def metric_prompt_hint(metric: dict | None) -> str:
    """命中指标时，给 IR 提示词加一条**确定性**建议（让模型直接填 metric）。"""
    if not metric:
        return ""
    return (
        f"【强烈建议】本问题已匹配到指标 `{metric.get('key')}`（{metric.get('name')}，"
        f"对象 {metric.get('object_code')}）。请**直接填 `metric`**，"
        "不要自己拼 group_by+aggregations——由系统用该指标的权威口径执行。\n\n"
    )


def prioritize_metric_object(allowed: dict, metric: dict | None) -> dict:
    """把命中指标所属对象排到白名单**最前**（提示词按顺序展示，越前越易被选中）。"""
    if not metric or not allowed:
        return allowed
    code = str(metric.get("object_code") or "")
    if code and code in allowed:
        return {code: allowed[code], **{k: v for k, v in allowed.items() if k != code}}
    return allowed
