# AI 管理 + 大模型应用 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> **Spec:** `docs/superpowers/specs/2026-09-13-ai-management-apps-design.md`

**Goal:** 新增 DB 化大模型配置、工具调用型 AI 助手（问数/统计/报告/导航/简单操作）、AI 报告，并接入前端。

**Architecture:** 后端在 `app/plugin/module_ai/` 下新增 `provider`（模型配置）、`report`（报告）、`assistant`（工具+LLM 编排）三子模块（自动发现，前缀 `/ai`）；LLM 用现有 `openai` 依赖的 function calling；工具只读 + 待确认动作。

## Global Constraints

- 后端 `backend`：`uv run pytest`、`uv run ruff check`（只判断新增）；不新增后端依赖。
- 前端 `frontend`：`pnpm type-check`、目标文件 eslint/prettier clean；不新增依赖（`markdown-it` 已有）。
- 中文注释；提交 `feat(ai): 中文描述`；禁 `git add -A`。
- 插件子模块 `app/plugin/module_ai/<x>/controller.py` 会被自动发现；容器前缀 `/ai`。

---

### Task 1: 后端模型配置 CRUD

**Files:**
- Create: `backend/app/plugin/module_ai/provider/__init__.py`
- Create: `backend/app/plugin/module_ai/provider/model.py`
- Create: `backend/app/plugin/module_ai/provider/schema.py`
- Create: `backend/app/plugin/module_ai/provider/service.py`
- Create: `backend/app/plugin/module_ai/provider/controller.py`
- Modify: `backend/app/scripts/initialize.py`（导入模型）
- Modify: `backend/app/scripts/init_app.py`（`_ensure_ai_tables()` + 调用）
- Test: `backend/tests/test_ai_model_provider.py`

**Interfaces:**
- Produces：`AiModelModel`(表 `ai_models`)、`AiModelService.get_runtime_model() -> dict|None`、`/ai/model/*`。

- [ ] **Step 1: 模型与 schema**

`model.py`：
```python
from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiModelModel(ModelMixin, UserMixin):
    __tablename__ = "ai_models"
    __table_args__ = ({"comment": "大模型配置表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="配置名称")
    provider: Mapped[str] = mapped_column(String(32), default="openai_compatible", comment="提供方")
    base_url: Mapped[str] = mapped_column(String(512), default="", comment="API 基址")
    api_key: Mapped[str] = mapped_column(String(512), default="", comment="API Key")
    model: Mapped[str] = mapped_column(String(128), default="", comment="模型名")
    temperature: Mapped[float] = mapped_column(Float, default=0.3, comment="温度")
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, comment="最大 token")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
```

`schema.py`：`AiModelCreateSchema`（name, provider="openai_compatible", base_url, api_key, model, temperature=0.3, max_tokens=2048, enabled=True, is_default=False, description）、`AiModelUpdateSchema`（全可选）、`AiModelOutSchema`（含 `api_key_masked`，不含原 key）。

- [ ] **Step 2: 服务 + controller**

`service.py`：
```python
from sqlalchemy import select, update
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from .model import AiModelModel


def _mask(key: str | None) -> str:
    if not key:
        return ""
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


def _to_dict(m: AiModelModel) -> dict:
    return {
        "id": m.id, "name": m.name, "provider": m.provider, "base_url": m.base_url,
        "model": m.model, "temperature": m.temperature, "max_tokens": m.max_tokens,
        "enabled": m.enabled, "is_default": m.is_default, "description": m.description,
        "api_key_masked": _mask(m.api_key), "created_time": m.created_time,
    }


class AiModelService:
    @classmethod
    async def list_models(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (await db.execute(
                select(AiModelModel).where(AiModelModel.is_deleted.is_(False)).order_by(AiModelModel.id.desc())
            )).scalars().all()
            return [_to_dict(m) for m in rows]

    @classmethod
    async def get_runtime_model(cls) -> dict | None:
        async with async_db_session() as db:
            m = (await db.execute(
                select(AiModelModel).where(
                    AiModelModel.is_deleted.is_(False), AiModelModel.enabled.is_(True)
                ).order_by(AiModelModel.is_default.desc(), AiModelModel.id.desc()).limit(1)
            )).scalar_one_or_none()
            if m and m.base_url and m.model:
                return {"base_url": m.base_url, "api_key": m.api_key, "model": m.model,
                        "temperature": m.temperature, "max_tokens": m.max_tokens}
        if settings.OPENAI_BASE_URL and settings.OPENAI_MODEL:
            return {"base_url": settings.OPENAI_BASE_URL, "api_key": settings.OPENAI_API_KEY,
                    "model": settings.OPENAI_MODEL, "temperature": 0.3, "max_tokens": 2048}
        return None

    @classmethod
    async def create(cls, data, auth) -> dict:
        from app.core.base_model import set_create_audit  # 若不存在则手动设置
        ...
```

> 注：若 `set_create_audit` 不存在，直接 `created_id=auth.user.id`。实现时以实际为准。

`controller.py`：`AiModelRouter = APIRouter(route_class=OperationLogRoute, prefix="/model", tags=["AI-模型配置"])`，端点 list/create/update/delete/set-default/test，权限 `module_ai:model:*`。

- [ ] **Step 3: 建表兜底 + 初始化导入**

`initialize.py::__init_create_table` 增加：
```python
from app.plugin.module_ai.provider.model import AiModelModel
from app.plugin.module_ai.report.model import AiReportModel
_ = (AiModelModel, AiReportModel)
```
`init_app.py` 新增 `_ensure_ai_tables()`：用 `CREATE TABLE IF NOT EXISTS ai_models(...)` / `ai_reports(...)`（与 ORM 对齐），并在启动序列调用。

- [ ] **Step 4: 测试**

`backend/tests/test_ai_model_provider.py`：
- 创建模型（`POST /api/v1/ai/model/create`）→ 列表含 `api_key_masked` 且无 `api_key`。
- 设默认唯一：创建两个并分别 set-default，列表仅一个 default。
- 更新未传 api_key → 原 key 保留（用 `get_runtime_model` 验证）。

- [ ] **Step 5: 运行 + ruff + 提交**

Run: `uv run pytest tests/test_ai_model_provider.py -q && uv run ruff check app/plugin/module_ai/provider/`

```bash
git add backend/app/plugin/module_ai/provider backend/app/scripts/initialize.py backend/app/scripts/init_app.py backend/tests/test_ai_model_provider.py
git commit -m "feat(ai): 大模型配置管理（DB化/脱敏/默认/测试连接）"
```

---

### Task 2: 后端 AI 报告

**Files:**
- Create: `backend/app/plugin/module_ai/report/__init__.py` / `model.py` / `schema.py` / `service.py` / `controller.py`
- Test: `backend/tests/test_ai_report.py`

- [ ] **Step 1: 模型 `ai_reports`**

```python
class AiReportModel(ModelMixin, UserMixin):
    __tablename__ = "ai_reports"
    __table_args__ = ({"comment": "AI 生成报告表"},)
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="Markdown 内容")
    source: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="来源数据")
```

- [ ] **Step 2: 服务 + controller（list/detail/delete）**，权限 `module_ai:report:query|delete`。
- [ ] **Step 3: 测试**：插入一条（服务层）→ `GET /ai/report/list` 可查到。
- [ ] **Step 4: 提交**。

---

### Task 3: 后端 AI 助手（工具 + function calling）

**Files:**
- Create: `backend/app/plugin/module_ai/assistant/__init__.py` / `tools.py` / `service.py` / `schema.py` / `controller.py`
- Test: `backend/tests/test_ai_assistant.py`

**Interfaces:**
- Produces：`TOOL_SCHEMAS`、`TOOL_REGISTRY`、`run_assistant(message, auth) -> dict`、`POST /ai/assistant/chat`。

- [ ] **Step 1: 工具注册表 `tools.py`**

包含工具函数（直接查 DB / 复用 `StatsService`）：`get_annotation_overview`、`get_dataset_stats`、`list_datasets`、`list_annotation_tasks`、`list_train_tasks`、`list_models`、`list_evals`、`list_predicts`、`list_deploys`、`list_cameras`、`list_algorithm_tasks`、`list_alarm_records`、`generate_report`、`navigate`、`propose_create_dataset`、`propose_create_annotation_task`。

```python
TOOL_REGISTRY: dict[str, dict] = {}  # name -> {"schema": {...}, "fn": coro, "kind": "read"|"action"|"report"}
TOOL_SCHEMAS = [t["schema"] for t in TOOL_REGISTRY.values()]
```

- [ ] **Step 2: 助手服务 `service.py`**

```python
async def run_assistant(message: str, auth) -> dict:
    rm = await AiModelService.get_runtime_model()
    if not rm:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=rm["base_url"], api_key=rm["api_key"] or "sk-none")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": message}]
    tool_calls_log, action, report_id = [], None, None
    for _ in range(6):
        resp = await client.chat.completions.create(
            model=rm["model"], messages=messages, tools=TOOL_SCHEMAS,
            tool_choice="auto", temperature=rm["temperature"], max_tokens=rm["max_tokens"],
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"reply": msg.content or "", "tool_calls": tool_calls_log, "action": action, "report_id": report_id}
        messages.append(msg)
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            entry = TOOL_REGISTRY.get(name)
            try:
                result = await entry["fn"](**args) if entry else {"error": f"未知工具 {name}"}
            except Exception as e:
                result = {"error": str(e)}
            if isinstance(result, dict):
                if result.get("__action__"): action = result["__action__"]
                if result.get("__report_id__"): report_id = result["__report_id__"]
            tool_calls_log.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False, default=str)[:4000]})
    return {"reply": "已达到工具调用上限，请缩小问题范围。", "tool_calls": tool_calls_log, "action": action, "report_id": report_id}
```

- [ ] **Step 3: controller `POST /ai/assistant/chat`**，body `{message}`，权限 `module_ai:assistant:query`。
- [ ] **Step 4: 测试**（monkeypatch `AsyncOpenAI` 返回一次 tool_call `navigate` + 一次文本；断言 reply/action/tool_calls）。
- [ ] **Step 5: 提交**。

---

### Task 4: 菜单/权限种子

**Files:** Modify `backend/app/scripts/init_app.py`

- [ ] 新增 `_ensure_ai_menus()`：在「AI管理」父菜单下补「模型配置」`/ai/model`（`module_ai/model/index`，perm `module_ai:model:query`）、「AI 报告」`/ai/report`（`module_ai/report/index`，perm `module_ai:report:query`）；补按钮权限 `module_ai:model:{query,create,update,delete}`、`module_ai:report:{query,delete}`、`module_ai:assistant:query`，挂 role 1。启动序列调用。
- [ ] 重启后端使菜单生效；提交。

---

### Task 5: 前端 API + 模型配置页

**Files:**
- Create: `frontend/src/api/module_ai/model.ts`
- Create: `frontend/src/views/module_ai/model/index.vue`
- Test: `frontend/e2e/ai-model.spec.ts`

- [ ] API：`getAiModelList/createAiModel/updateAiModel/deleteAiModel/setDefaultAiModel/testAiModel`。
- [ ] 页面：`PageSearch`+`PageContent`+`EnhancedDialog`；列 name/provider/model/base_url/temperature/默认/启用/操作(编辑/删除/设为默认/测试)。表单含 api_key（password，编辑留空表示不变）。
- [ ] E2E：新增模型 → 列表出现；类型检查。
- [ ] 提交。

---

### Task 6: 前端报告页

**Files:**
- Create: `frontend/src/api/module_ai/report.ts`
- Create: `frontend/src/views/module_ai/report/index.vue`

- [ ] 列表（标题/时间/操作）+ 查看抽屉（`markdown-it` 渲染）+ 删除 + 导出 .md。
- [ ] 类型检查 + 提交。

---

### Task 7: 前端助手增强（工具结果/导航/报告/确认）

**Files:** Modify `frontend/src/components/AiAssistant/index.vue`; Create `frontend/src/api/module_ai/assistant.ts`

- [ ] API：`assistantChat({ message })` → `{reply, tool_calls, action, report_id}`。
- [ ] 助手：优先调 assistantChat；渲染 `tool_calls`（名称 + 结果折叠 JSON）；`action.type==="navigate"` → `router.push`；`action.type==="confirm"` → `ElMessageBox` 确认后调用 `action.api`（既有业务 API）并提示；`report_id` → 提供「查看报告」跳 `/ai/report`。
- [ ] 类型检查 + 提交。

---

### Task 8: 回归 + 账本

- [ ] `cd backend && uv run pytest -q`；`cd frontend && pnpm type-check`（新增文件 0 错误）+ 相关 E2E。
- [ ] 更新 `.superpowers/sdd/progress.md` 并提交。

---

## Self-Review

- Spec §3.1 → Task 1/4；§3.2-3.3 → Task 3；§3.4 → Task 2；§3.5 → Task 1/4；§4 → Task 5/6/7；§6 → Task 1/2/3/5/8。
- 命名一致：`AiModelService.get_runtime_model`、`TOOL_REGISTRY`、`run_assistant`、`assistantChat`。
- 风险：助手为无状态、非流式；工具只读且简单操作为待确认动作。
