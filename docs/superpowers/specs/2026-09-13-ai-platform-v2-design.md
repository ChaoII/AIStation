# AI 管理 v2 设计（可编排的大模型应用平台）

> 创建日期：2026-09-13
> 状态：用户批准全量开工（A-E）
> 取代：`2026-09-13-ai-management-apps-design.md` 的 MVP 范围

## 1. 目标

把"能填个模型问两句"升级为可真正干活的 AI 平台：

1. **多提供商 / 多模型**：自定义协议、base_url、密钥、请求头；能力标签、上下文、按用途设默认；测试连接、拉取远端模型列表。
2. **提示词工作台（画布）**：可编排多块提示词（系统/上下文/指令/示例/输出格式），变量自动识别与实时预览。
3. **AI 应用（Agent 编排）**：模型 + 提示词 + 工具集 + 输出格式 + 入参定义，可启停；内置若干应用。
4. **工具中心**：内置工具开关 + **自定义 HTTP 工具**（零代码扩展）。
5. **运行台 + 流式（SSE）**：选应用→流式输出，展示工具调用/耗时/错误。
6. **会话与日志**：按应用续聊；调用日志（模型/tokens/耗时/状态）。
7. **报告**：模板 + 生成记录。

## 2. 数据模型（新增/扩展）

- `ai_providers`：name(uniq)、protocol(openai/anthropic/ollama/custom)、base_url、api_key、extra_headers(JSONB)、enabled、description + 审计。
- `ai_models`（扩展）：新增 `provider_id`(FK, 可空)、`usage`(chat/assistant/embedding)、`capabilities`(JSONB, 如 ["chat","tool","vision"])、`context_window`(int)；保留既有 base_url/api_key/extra_headers/temperature/max_tokens/enabled/is_default。
- `ai_prompts`：name、category、blocks(JSONB：有序块 [{type,content}])、variables(JSONB)、version、enabled。
- `ai_apps`：name、icon、description、model_id、prompt_id、tools(JSONB 工具名列表)、output_format(text/table/report)、input_schema(JSONB)、enabled、order。
- `ai_tools`：name、kind(builtin/http)、method、url、headers(JSONB)、params_schema(JSONB)、enabled（http 工具）。
- `ai_sessions` / `ai_messages`：会话与消息（按 app 分组）。
- `ai_call_logs`：app_id、model_id、latency_ms、prompt_tokens、completion_tokens、status、error。
- `ai_reports`：已有，增强（template_id 可空）。

## 3. 运行时与流式

- `AiRuntime.resolve(usage="chat", app=None)`：app.model_id → 默认模型 → env；返回 base_url/api_key/model/headers/params。
- `build_headers(base_url)`：opencode 网关自动注入 `x-opencode-session`；再合并 provider/model 的自定义头。
- 流式：`POST /ai/apps/{id}/run/stream`（SSE, `text/event-stream`）：事件 `tool`/`delta`/`done`/`error`。
- 助手/聊天统一走运行时与流式，替换旧 Agno 流程（保留旧 WS 接口兼容，但聊天页迁移到新接口）。

## 4. 前端页面

- `ai/provider`：提供商 CRUD + 测试。
- `ai/model`：模型 CRUD（选提供商、拉取远端模型、能力/上下文/用途默认）。
- `ai/prompt`：提示词工作台（左侧块列表可拖拽，中间块编辑，右侧变量与预览）。
- `ai/app`：应用 CRUD（选模型/提示词/工具/输出格式/入参），一键“运行”。
- `ai/tool`：工具中心（内置开关 + 自定义 HTTP 工具 CRUD）。
- `ai/playground`：运行台（选应用，输入，SSE 流式展示 + 工具过程）。
- `ai/report`：报告（已有，增强模板/导出）。
- 全部菜单/权限种子。

## 5. 交付顺序

- A 提供商/模型 + 统一运行时 + SSE 流式（同时修复聊天页）
- B 提示词工作台（画布）
- C AI 应用 + 工具中心
- D 运行台 + 会话/日志
- E 报告增强 + 全量测试

## 6. 测试与验收

- 后端 pytest：providers/models/prompts/apps/tools CRUD；运行时解析（provider→model→env）；SSE 事件序列（假 LLM）；会话/日志落库；自定义 HTTP 工具调用。
- 前端 E2E：建提供商→建模型→测试；提示词画布保存与预览；建应用→运行台流式；报告。
- 静态：新增文件 0 vue-tsc 错误、eslint/prettier clean。

## 7. 兼容与迁移

- `ai_models` 旧行（无 provider_id）继续可用（用自身 base_url）。
- 启动 `_ensure_missing_columns` 补新列；`create_all` 建新表。
