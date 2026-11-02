"""问数评测：对比结果导出为**自包含 HTML 报告**（可直接打开/打印为 PDF）。

为什么是 HTML 而不是 CSV：
- CSV 适合再做数据处理，但评审要看的是「结论 + 回退清单 + SQL 对照」；
- 单文件 HTML 不依赖任何外部资源，发给别人就能看，浏览器可直接打印成 PDF。

所有动态内容都走 `html.escape`：SQL 里有 `<`、`&`、引号，不转义会把报告写坏。
"""
from __future__ import annotations

from datetime import datetime
from html import escape

_STATUS_LABEL = {
    "regressed": "回退",
    "fixed": "修复",
    "same": "不变",
    "only_base": "仅基线",
    "only_target": "仅对比",
}
_STATUS_COLOR = {
    "regressed": "#f56c6c",
    "fixed": "#67c23a",
    "same": "#909399",
    "only_base": "#e6a23c",
    "only_target": "#409eff",
}

_CSS = """
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:32px auto;
max-width:1040px;color:#303133;line-height:1.6;padding:0 16px;background:#fff}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 10px;padding-left:8px;border-left:3px solid #409eff}
.sub{color:#909399;font-size:12px;margin-bottom:18px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}
.kpi{border:1px solid #ebeef5;border-radius:6px;padding:12px 14px}
.kpi .n{font-size:20px;font-weight:600}
.kpi .l{font-size:12px;color:#909399}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{border:1px solid #ebeef5;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f5f7fa;font-weight:600}
.tag{display:inline-block;padding:0 6px;border-radius:3px;color:#fff;font-size:12px}
pre{background:#f5f7fa;padding:8px;border-radius:4px;white-space:pre-wrap;word-break:break-all;
margin:0;font-size:11px}
.meta td:first-child{width:120px;color:#909399}
.diff{background:#fdf6ec}
"""


def _tag(status: str) -> str:
    return (
        f'<span class="tag" style="background:{_STATUS_COLOR.get(status, "#909399")}">'
        f"{escape(_STATUS_LABEL.get(status, status))}</span>"
    )


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _config_rows(base_cfg: dict, target_cfg: dict) -> str:
    keys = sorted(set(base_cfg or {}) | set(target_cfg or {}))
    rows = []
    for k in keys:
        b, t = (base_cfg or {}).get(k), (target_cfg or {}).get(k)
        cls = ' class="diff"' if str(b) != str(t) else ""
        rows.append(
            f"<tr{cls}><td>{escape(str(k))}</td><td>{escape(str(b))}</td>"
            f"<td>{escape(str(t))}</td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="3">（两轮都没有记录配置指纹）</td></tr>')
    return "".join(rows)


def _items_table(items: list[dict], want: tuple[str, ...] | None = None,
                 with_sql: bool = True) -> str:
    picked = [i for i in items if want is None or i.get("status") in want]
    if not picked:
        return '<p class="sub">（无）</p>'
    head = ("<th>变化</th><th>问题</th><th>路径</th><th>耗时(ms)</th>"
            + ("<th>基线 SQL</th><th>对比 SQL</th>" if with_sql else ""))
    rows = []
    for it in picked:
        cells = (
            f"<td>{_tag(it.get('status', ''))}</td>"
            f"<td>{escape(str(it.get('question') or ''))}</td>"
            f"<td>{escape(str(it.get('base_path') or '-'))} → "
            f"{escape(str(it.get('target_path') or '-'))}</td>"
            f"<td>{it.get('base_ms', 0)} → {it.get('target_ms', 0)}"
            f"（{it.get('delta_ms', 0):+d}）</td>"
        )
        if with_sql:
            cells += (
                f"<td><pre>{escape(str(it.get('base_sql') or '-'))}</pre></td>"
                f"<td><pre>{escape(str(it.get('target_sql') or '-'))}</pre></td>"
            )
        rows.append(f"<tr>{cells}</tr>")
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def render_compare_html(cmp: dict, base_meta: dict | None = None,
                        target_meta: dict | None = None) -> str:
    """把 compare_runs() 的结果渲染成一页 HTML 报告。"""
    base_meta = base_meta or {}
    target_meta = target_meta or {}
    b_fp = base_meta.get("fingerprint") or {}
    t_fp = target_meta.get("fingerprint") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    items = cmp.get("items") or []

    acc_b = _pct((cmp.get("base") or {}).get("data_accuracy"))
    acc_t = _pct((cmp.get("target") or {}).get("data_accuracy"))
    changed = "是" if cmp.get("model_changed") else "否"
    same_model = "（模型未变）" if not cmp.get("model_changed") else "（**模型已变更**）"

    html = [
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
        "<title>问数评测对比报告</title><style>", _CSS, "</style></head><body>",
        "<h1>问数评测 · 两次运行对比报告</h1>",
        f'<div class="sub">生成时间 {escape(now)}　|　对比口径：按题目 ID 对齐，'
        "退化题（金标空/全 NULL/单值 0）不计入准确率</div>",
        '<div class="kpis">',
        f'<div class="kpi"><div class="n">{escape(str(cmp.get("total", 0)))}</div>'
        '<div class="l">对齐题数</div></div>',
        f'<div class="kpi"><div class="n" style="color:{_STATUS_COLOR["regressed"]}">'
        f'{escape(str(cmp.get("regressed", 0)))}</div><div class="l">回退</div></div>',
        f'<div class="kpi"><div class="n" style="color:{_STATUS_COLOR["fixed"]}">'
        f'{escape(str(cmp.get("fixed", 0)))}</div><div class="l">修复</div></div>',
        f'<div class="kpi"><div class="n">{escape(str(cmp.get("same", 0)))}</div>'
        '<div class="l">不变</div></div>',
        f'<div class="kpi"><div class="n">{escape(str(cmp.get("net", 0)))}</div>'
        '<div class="l">净提升（修复−回退）</div></div>',
        f'<div class="kpi"><div class="n">{escape(acc_b)} → {escape(acc_t)}</div>'
        '<div class="l">准确率</div></div>',
        "</div>",
        "<h2>运行信息</h2>",
        '<table class="meta"><tbody>',
        f"<tr><td>基线</td><td>{escape(str(base_meta.get('run_id', '-')))}"
        f"　模型：{escape(str(b_fp.get('model') or '（未记录）'))}"
        f"　时间：{escape(str(base_meta.get('started_at') or '-'))}</td></tr>",
        f"<tr><td>对比</td><td>{escape(str(target_meta.get('run_id', '-')))}"
        f"　模型：{escape(str(t_fp.get('model') or '（未记录）'))}"
        f"　时间：{escape(str(target_meta.get('started_at') or '-'))}</td></tr>",
        f"<tr><td>是否换模型</td><td>{changed} {escape(same_model)}</td></tr>",
        "</tbody></table>",
        "<h2>配置差异（高亮=两轮不同）</h2>",
        "<table><thead><tr><th>配置项</th><th>基线</th><th>对比</th></tr></thead><tbody>",
        _config_rows(b_fp.get("config") or {}, t_fp.get("config") or {}),
        "</tbody></table>",
        "<h2>逐题结果（共 " + escape(str(cmp.get("total", 0))) + " 题）</h2>",
        _items_table(items, None, with_sql=False),
        "<h2>回退题（优先排查）</h2>",
        _items_table(items, ("regressed",)),
        "<h2>修复题</h2>",
        _items_table(items, ("fixed",)),
        "<h2>仅出现在单边的题</h2>",
        _items_table(items, ("only_base", "only_target")),
        '<p class="sub">说明：路径 fast=指标模板，object=对象查询，slow=NL2SQL，clarify=澄清反问。</p>',
        "</body></html>",
    ]
    return "".join(html)
