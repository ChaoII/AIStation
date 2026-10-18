"""``ai_call_logs`` 归属守卫：跨模块共享表只允许 owner 读写。

背景（实测核对，纠正过一次想当然的判断）：

- `agent/service.py` 曾**直读** `ai_call_logs` 做"每应用运行量/错误率/延迟"统计
  （唯一一处真实越界读），现改走 `logs_center` 的取数接口；
- `query/*` 里命中的 `ai_call_logs` **全是提示词/few-shot/基准 SQL 字符串**
  （NL2SQL 示例与 gold 对照），不碰表——按"直读"去改它们纯属误伤；
- `ontology` 早已收敛（工具调用用量记在自己的 `ai_ont_change_log`）。

职责边界（本测试锁死）：

- **写**（调用留痕）：`overview`（`AiOverviewService.add_log`）；
- **读/统计**：`logs_center`（`AiLogService.*`）；
- 其他模块一律经这两者取数，不得 import 模型或自行写 SQL。
"""
import pathlib
import re

#: 允许直接接触 ai_call_logs 的模块（写=overview，读/统计=logs_center）
ALLOWED = {"overview", "logs_center"}

_BASE = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_ai"
_MODEL = re.compile(r"\bAiCallLogModel\b")
#: 只认"真在执行 SQL"的行（`text(...)` / `execute(...)`），避开提示词与基准里的 SQL 字符串
_EXEC_SQL = re.compile(r"(text|execute|scalar)\s*\(.*\bai_call_logs\b", re.IGNORECASE)


def test_only_owner_modules_touch_call_logs():
    hits: list[str] = []
    for f in _BASE.rglob("*.py"):
        rel = f.relative_to(_BASE)
        if rel.parts[0] in ALLOWED:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _MODEL.search(line) or _EXEC_SQL.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:110]}")
    assert not hits, (
        "`ai_call_logs` 只允许 overview（写）与 logs_center（读/统计）接触；"
        "其他模块请改走 logs_center 的取数接口：\n" + "\n".join(hits)
    )
