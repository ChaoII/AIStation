"""跨模块边界守卫：聚合型模块不得直读其他模块的表/模型。

背景（逐处核对过，不是按 grep 计数想当然）：

- `overview`（控制台）曾直读 apps/knowledge/models/providers/report/workflow/agent 七个模块的
  ORM 模型做计数，并裸 SQL 读 `ai_pipeline_run` / `ai_query_writeback` / `ai_ont_version`；
- `workspace`（工作台）曾直读 agent/app/workflow 的模型做条目聚合；
- `providers` 曾直接 `db.add(AiModelModel(...))`（跨模块**写**模型表）；
- 反例（**不改**）：`query/*` 里命中的 `ai_call_logs` 全是提示词/few-shot/基准 SQL **字符串**，
  一处都不碰表；`ontology` 早已收敛到自己的表。

现全部改走各模块自己的服务接口（`list_*` / `count_*` / `import_models` / `pipeline_run_status`
/ `count_pending_tasks` 等），本测试把这条边界钉死：聚合型模块里不得 import 他模块模型，
也不得对他模块的表执行裸 SQL。
"""
import pathlib
import re

_BASE = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_ai"
#: 被检查的「聚合型」模块：职责是聚合展示/编排，不拥有这些表
_CONSUMERS = ("overview", "workspace", "providers")
#: 跨模块模型导入（本模块自己的模型是 `from .model import ...`，不会命中）
_CROSS_MODEL = re.compile(r"from app\.plugin\.module_ai\.[a-z_]+\.model import")
#: 跨模块裸 SQL（只认"真在执行 SQL"的行，避开提示词/文档里的表名字符串）
_CROSS_SQL = re.compile(
    r"(text|execute|scalar)\s*\(.*\b("
    r"ai_pipeline_run|ai_query_writeback|ai_ont_version|ai_apps|ai_workflows|ai_models|"
    r"ai_agents|ai_providers|ai_reports|ai_knowledge_bases|ai_call_logs)\b",
    re.IGNORECASE,
)


def test_consumer_modules_do_not_touch_other_modules_directly():
    hits: list[str] = []
    for mod in _CONSUMERS:
        for f in sorted((_BASE / mod).glob("*.py")):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if _CROSS_MODEL.search(line) or _CROSS_SQL.search(line):
                    hits.append(f"{mod}/{f.name}:{i}: {line.strip()[:110]}")
    assert not hits, (
        "聚合型模块不得直读其他模块的表/模型，请改走对应模块的服务接口：\n" + "\n".join(hits)
    )
