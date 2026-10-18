"""overview（AI 控制台）的跨模块边界：不得直读其他模块的表/模型。

背景（实测）：`overview/service.py` 曾直接 import apps/knowledge/models/providers/report/
workflow/agent 七个模块的 ORM 模型做计数，并裸 SQL 读 `ai_pipeline_run` /
`ai_query_writeback` / `ai_ont_version`——任一模块改表都会连带打断控制台。
现全部改走各模块自己的取数入口（`AiAppService.count_apps` / `AiWorkflowService.count_workflows`
/ `AiModelService.count_models` / `AiAgentService.count_agents` / `AiProviderService.count_providers`
/ `AiReportService.count_reports` / `AiKnowledgeService.count_knowledge_bases` /
`AiQueryService.pipeline_run_status` / `count_writeback_actions` / `ontology.count_pending_tasks`）。

规则：overview 只能 import **自己的**模型（`from .model import …`），跨模块一律走服务接口。
"""
import pathlib
import re

_FILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app" / "plugin" / "module_ai" / "overview" / "service.py"
)
#: 跨模块模型导入（本模块自己的模型是 `from .model import ...`，不会命中）
_CROSS_MODEL = re.compile(r"from app\.plugin\.module_ai\.[a-z_]+\.model import")
#: 跨模块裸 SQL（只认"真在执行 SQL"的行，避开提示词/文档里的表名字符串）
_CROSS_SQL = re.compile(
    r"(text|execute|scalar)\s*\(.*\b("
    r"ai_pipeline_run|ai_query_writeback|ai_ont_version|ai_apps|ai_workflows|ai_models|"
    r"ai_agents|ai_providers|ai_reports|ai_knowledge_bases|ai_call_logs)\b",
    re.IGNORECASE,
)


def test_overview_does_not_touch_other_modules_directly():
    hits: list[str] = []
    for i, line in enumerate(_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if _CROSS_MODEL.search(line) or _CROSS_SQL.search(line):
            hits.append(f"overview/service.py:{i}: {line.strip()[:110]}")
    assert not hits, (
        "控制台不得直读其他模块的表/模型，请改走对应模块的服务取数接口：\n" + "\n".join(hits)
    )
