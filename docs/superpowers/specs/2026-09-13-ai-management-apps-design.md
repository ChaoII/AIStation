# AI 管理 + 大模型应用 设计

> 创建日期：2026-09-13
> 状态：用户批准直接开工
> 关联：既有 `module_ai/chat`（Agno + OpenAI 兼容协议流式聊天）

## 1. 目标

在现有 AI 聊天基础上，补齐「大模型配置管理」与「AI 应用」：

1. **模型配置**：DB 化多模型管理（OpenAI 兼容：base_url/api_key/model/temperature/max_tokens），支持启用/默认/测试连接。
2. **工具调用型助手**：LLM 通过 function calling 自主调用受控后端工具，实现 **问数 / 统计分析 / 报告生成 / 功能导航 / 简单操作**。
3. **报告**：助手生成 Markdown 报告并落库，可在 UI 查看/删除/导出。
4. **前端**：`AI 管理 → 模型配置`、`AI 管理 → AI 报告` 两个页面；增强全局 `AiAssistant`（工具结果、导航、报告、操作确认）。

**非目标**：RAG/embedding/向量库、多智能体编排、NL→SQL 自由查询（用工具替代）。

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| LLM 调用 | 使用现有依赖 `openai` 的 `AsyncOpenAI` + `tools`（function calling），不引入新依赖 |
| 数据访问 | **不做 NL→SQL**；工具调用受控只读查询（复用现有 Model/StatsService），避免注入 |
| 模型来源 | 默认启用模型 → 回退 env `OPENAI_*` → 均无则明确报错 |
| 变更操作 | 工具只返回「待确认动作」，由前端二次确认后再调既有业务 API，服务端不自动改数据 |
| 建表 | 复用 `create_tables()`（新库）+ 启动期 `CREATE TABLE IF NOT EXISTS` 兜底（旧库） |
| 会话持久化 | 助手对话**无状态**（前端本地历史）；保留既有 Agno 聊天页不动 |
| api_key | 出参脱敏，仅入参可写 |

## 3. 后端设计

### 3.1 模型配置 `module_ai/provider/`
- 表 `ai_models`（ModelMixin+UserMixin）：`name`(唯一)、`provider`(openai_compatible)、`base_url`、`api_key`、`model`、`temperature`(float)、`max_tokens`(int)、`enabled`(bool)、`is_default`(bool)、`description`。
- 端点（prefix `/model`，容器 `/ai`）：
  - `GET /ai/model/list`（`module_ai:model:query`）
  - `POST /ai/model/create`（`:create`）
  - `PUT /ai/model/update/{id}`（`:update`）
  - `DELETE /ai/model/delete`（`:delete`）
  - `POST /ai/model/set-default/{id}`（`:update`）
  - `POST /ai/model/test`（`:update`，body 可含 id 或完整配置）→ 调一次 LLM 验证
- 服务：`get_runtime_model()` 返回 `(base_url, api_key, model, temperature, max_tokens)`（默认>env）；`set_default` 保证唯一。

### 3.2 工具 `module_ai/assistant/tools.py`
只读工具（返回紧凑 JSON）：
- `get_annotation_overview()` → `StatsService.get_overview()`
- `get_dataset_stats(dataset_id)` → `StatsService.get_dataset_stats`
- `list_datasets(limit?)` / `list_annotation_tasks(limit?)`
- `list_train_tasks(limit?)` / `list_models(limit?)` / `list_evals(limit?)` / `list_predicts(limit?)` / `list_deploys(limit?)`
- `list_cameras(limit?)` / `list_algorithm_tasks(limit?)` / `list_alarm_records(limit?)`
- `generate_report(topic, scope_keyword?)` → 汇总数据生成 Markdown 并落库，返回 `report_id`
- `navigate(path, reason?)` → 返回 `{type:"navigate", path, reason}` 动作
- `propose_create_dataset(name)` / `propose_create_annotation_task(dataset_id,name,task_type)` → 仅返回待确认动作

工具注册表：`TOOL_REGISTRY = {name: {"schema": <openai tool schema>, "fn": coroutine, "mutating": bool}}`。

### 3.3 助手 `module_ai/assistant/service.py`
- `run_assistant(message, auth) -> dict`：
  1. `get_runtime_model()`；无配置抛 `CustomException`。
  2. 系统提示：系统助手，必须用工具取数，不得编造；中文作答；需要时调用 navigate/generate_report。
  3. function-calling 循环（最多 6 轮）：`chat.completions.create(model, messages, tools=TOOL_SCHEMAS, tool_choice="auto")`；有 tool_calls 则执行并回填，否则取内容。
  4. 返回 `{reply, tool_calls:[{name,args,result(截断)}], action(导航/待确认), report_id}`。
- `controller.py`：`POST /ai/assistant/chat`（`module_ai:assistant:query`）。

### 3.4 报告 `module_ai/report/`
- 表 `ai_reports`（ModelMixin+UserMixin）：`title`、`content`(Text, Markdown)、`source`(JSONB: 工具/参数)、`created_id`。
- 端点：`GET /ai/report/list`、`GET /ai/report/detail/{id}`、`DELETE /ai/report/delete`。

### 3.5 建表与菜单
- `initialize.py::__init_create_table` 增加导入 `AiModelModel`、`AiReportModel`。
- `init_app.py` 增加 `_ensure_ai_tables()`（`CREATE TABLE IF NOT EXISTS` 兜底，旧库）与 `_ensure_ai_menus()`（在「AI管理」下补「模型配置」`/ai/model`、`AI 报告` `/ai/report`，挂 admin；按钮权限 `module_ai:model:*`、`module_ai:report:*`、`module_ai:assistant:query`）。

## 4. 前端设计

- `api/module_ai/model.ts`、`report.ts`、`assistant.ts`。
- `views/module_ai/model/index.vue`：PageSearch+PageContent+EnhancedDialog；字段 name/provider/base_url/api_key/model/temperature/max_tokens/enabled/is_default/description；操作：编辑/删除/设为默认/测试连接；列表 api_key 显示 `****`。
- `views/module_ai/report/index.vue`：列表（标题/时间/操作）+ 查看抽屉（`markdown-it` 渲染）+ 删除 + 导出 .md。
- `components/AiAssistant/index.vue` 增强：优先调 `/ai/assistant/chat`；渲染 `tool_calls`（名称+结果表格/JSON 折叠）；`action.type==="navigate"` 执行 `router.push`；`report_id` 给出「查看报告」链接；`action.type==="confirm"` 弹确认后调用对应业务 API。
- 菜单组件路径 `module_ai/model/index`、`module_ai/report/index`。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 未配置模型 | `CustomException`「未配置大模型，请在 AI 管理→模型配置 中添加」 |
| LLM 请求失败/超时 | 返回明确错误信息，前端提示 |
| 工具执行异常 | 记入 `tool_calls.result` 错误，不中断对话 |
| api_key 为空但改配置未填 | 保留原值（不覆盖为空） |
| 默认模型删除 | 允许；`get_runtime_model` 回退 env |

## 6. 测试与验收

- 后端 pytest：
  - 模型 CRUD：创建/列表脱敏/设默认唯一/未填 api_key 更新保留原值。
  - 工具注册表：schema 合法、navigate/报告工具行为（报告落库）。
  - 助手循环：用假 OpenAI client（monkeypatch）验证「工具调用→回填→最终答复」与 action 解析。
- 前端 E2E：模型配置页创建并列表；报告页展示。
- 静态：新增文件 vue-tsc 0 错误、eslint/prettier clean。

## 7. 已知限制

- 助手对话不落库（无状态）；工具结果为只读快照，受数据权限影响（传入 auth 时按权限过滤，首版按全量只读）。
- 无流式输出（先做非流式，稳定后再评估 SSE）。
- 简单操作为前端确认后调用既有 API，后端不自动执行。
