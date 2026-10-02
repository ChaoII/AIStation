# AI 管理完备化（借鉴 BSIAP + Dify 低代码编排）设计与分阶段方案

> 状态：设计稿（对齐用），实现按阶段推进并逐步回填。
> 参考：`D:\BSIAP`（BSIAP v2，AI 智能体开发平台），目标形态参考 Dify 工作流编排。
> 落地模块：`backend/app/plugin/module_ai/`（插件，`module_ai/**/controller.py` 自动挂 `/ai/{suffix}`）+ `frontend/src/views/module_ai/`。

## 1. 背景与目标

现有 AI 管理偏「模型调用 + 应用」：供应商/模型配置、应用（模型+提示词+工具+流式）、提示词、工具目录、会话、调用日志、报表。功能可用但偏「粗糙、零散」，缺少企业级 Agent 平台的**编排、生态与体验**。

用户要求：借鉴 BSIAP 做「AI 管理完备化」，并额外提供**类 Dify 的 Agent 低代码编排**；前端视觉对齐 BSIAP 精致风格（用本项目 Element Plus + `--el-*` 变量落地，不造割裂外壳）。

## 2. 现状能力与复用点（不推倒重来）

| 能力 | 现有 | 复用方式 |
|------|------|----------|
| 模型供应商/模型 | `providers/provider`，`AiModelService.get_runtime_model` | 直接复用 |
| 提示词 | `prompts`（`render_prompt`） | 直接复用 |
| 工具目录 | `tools_catalog` + `agno_tools/registry` | 直接复用 |
| 流式底座 | `apps.run_app_ui_stream`（OpenAI 兼容 + AI SDK UI Message Stream）+ `assistant.run_agent_ui_stream` | 编排运行时装在「LLM 节点」上 |
| 会话/消息 | `sessions`（`ai_sessions/ai_messages`） | 复用 |
| 调用日志/统计/报表 | `overview` / `logs_center` / `report` | 复用 |
| 向量检索 | `module_video/face_gallery` 的 pgvector「可移植方案」（`store.py`：无 pgvector 时 Python 侧余弦 + dimension 过滤） | RAG 复用该模式 |
| 编排画布 | 前端 `@vue-flow/core`（已装） | Dify 式画布直接用它 |
| Agent 编排运行时 | 后端 `Agno 2.5.8` + `openai` | 编排节点内复用 |

## 3. 总体架构

```
前端 (views/module_ai)
 ├─ agent/       智能体大厅(分类树+卡片) / 管理 / 对话详情 / 工作流编排画布
 ├─ workflow/    可视化节点编排画布(@vue-flow/core) + 节点设置面板 + 运行调试
 ├─ skill/       技能广场 + Agent 技能绑定
 ├─ knowledge/   知识库 + 数据源(RAG)
 ├─ chat/        对话(SSE/WS 流式 + 推理 + 工具 + 引用 + 反馈 + 会话)
 └─ (复用) model/prompt/tool/logs/overview

后端 (plugin/module_ai，均自动发现注册)
 ├─ agent/       Agent 实体(绑定 workflow/模型/技能/知识库/温度/头像/主题色/分类)
 ├─ workflow/    工作流定义(节点 DAG JSON) + 运行时引擎(节点执行/流式/变量/条件)
 ├─ skill/       技能广场 + 脚本技能→Agno 工具化 + Agent 绑定
 ├─ knowledge/   知识库(上传/分块/向量化/检索) + 数据源(SQL/API)
 ├─ chat/        对话(事件流 WS/SSE + 引用/反馈/会话记忆/HITL)
 └─ (复用) providers/provider/prompts/tools_catalog/sessions/overview/report
```

## 4. 核心数据模型（新增，均走 `ModelMixin` 基类）

- `ai_agents`（Agent 实体）：`agent_name`、`category_id`、`agent_role`、`description`、`model_id`、`prompt_id`、`temperature`、`markdown`、`workflow_id`（绑定低代码编排）、`tool_ids`(JSON)、`skill_ids`(JSON)、`knowledge_ids`(JSON)、`input_schema`(JSON)、`avatar`、`color`、`status`、`uuid`。
- `ai_agent_categories`（分类树）：`name`、`parent_id`、`sort`。
- `ai_workflows`（工作流定义）：`name`、`description`、`graph`(JSON 节点/边)、`version`、`status`。
- `ai_skills`（技能）：`name`、`description`、`skill_type`、`content`(SKILL.md)、`scripts`(JSON)、`config`(JSON)、`version`、`install_count`、`status`。
- `ai_agent_skills`（Agent↔技能绑定）。
- `ai_knowledge_bases`（知识库）：`name`、`description`、`embed_model`、`chunk_count`、`file_type`。
- `ai_knowledge_chunks`（分块）：`knowledge_id`、`file_name`、`chunk_index`、`content`、`meta`(JSON)、`vector`(可移植/可选)、`dimension`。
- `ai_datasources`（数据源）：`ds_type`(db/api)、`dialect`、`uri`、`api_config`(JSON)。
- `ai_workflow_runs`（运行记录，调试用）：`workflow_id`、`session_id`、`status`、`node_traces`(JSON)、`started_at`。

> 拓扑说明：Workflow 是可复用的「编排图」，Agent 通过 `workflow_id` 引用；运行时由 LLM/工具/知识库等节点组装，输出经流式回填。

## 5. 低代码编排引擎设计（类 Dify）

### 5.1 节点集（V1，够用闭环）
- **开始**：定义输入变量（来自 `input_schema`/会话首条消息）。
- **LLM**：模型 + 提示词模板（`{{变量}}` 插值）+ 温度；流式输出。
- **知识检索**：绑定知识库，RAG 召回注入上下文。
- **工具调用**：调用工具目录里的工具/Agno 工具。
- **代码转换**：Python 节点，对变量做转换（沙箱限制）。
- **条件分支**：IF/ELSE，按表达式走不同下游。
- **变量赋值**：把上游输出写回变量。
- **结束**：输出最终回复/结构化结果。

### 5.2 运行时引擎
- 图 = `{nodes:[{id,type,data}], edges:[{source,target,sourceHandle}]}`。
- 执行器按 DAG 拓扑 + 条件分支求值，维护 `variables` 上下文。
- 流式：LLM 节点产出 `ai/@ai-sdk` 的 UI Message Stream 帧，经统一 pipeline 透传前端（复用 `run_agent_ui_stream` 的事件模型）。
- 节点结果写入 `ai_workflow_runs.node_traces` 供调试。

### 5.3 编排画布
- 前端 `@vue-flow/core` 渲染节点/连线；属性面板用 `el-form` 按节点类型动态渲染；支持拖拽新增、删除、运行调试、变量引用补全。

## 6. 技术选型与依据（账本）

| 项 | 选型 | 依据 |
|----|------|------|
| 编排画布 | `@vue-flow/core`（已装 1.48.x） | 成熟、Vue3 原生、MIT、活跃；免新增依赖；Dify/Flowise 同类 |
| 流式 | `ai` + `@ai-sdk/vue`（已装） | 项目已在用，负责 UI Message Stream |
| 编排运行时 | 自研 DAG 执行器（复用 Agno/openai/工具底座） | BSIAP 无画布式 DAG，需自建；客户端库无现成通用 DAG Agent 编排 |
| RAG 向量 | 复用 `module_video/face_gallery`「pgvector / Python 可移植」双方案 | 项目已验证，避免新引入向量库 |
| Agent 运行 | Agno `Agent`/`Team`（已装 2.5.8） | 项目已在用；BSIAP 同款 |
| 技能→工具 | Agno Skills + 自研递归 SKILL.md loader | BSIAP 同款机制 |
| 前端视觉 | Element Plus 原生组件 + `--el-*` 变量 | AGENTS.md 强制，禁止自造割裂外壳 |

## 7. 分阶段路线与验收标准

- **阶段 1（本轮，核心闭环）**：Agent 实体 + 低代码编排（节点引擎 + 画布 + 运行调试）+ Agent 大厅/管理 + 对话接入。验收：能在画布拖出「开始→LLM→条件→结束」，对话流式返回并落会话/日志。
- **阶段 2**：技能广场 + 脚本技能工具化 + Agent 绑定。验收：上传技能→自动变为可调用工具，Agent 挂技能后可调用。
- **阶段 3**：知识库/数据源 RAG。验收：上传文档→分块→向量化→检索→Agent 引用 source。
- **阶段 4**：对话体验增强（引用/反馈/会话记忆/HITL）+ 模型供应商增强 + 全量视觉对齐 BSIAP。

## 8. 账本
- BSIAP Agent 为「配置式编排」，**无 Dify 式 DAG 画布** → 低代码编排为自研新增。
- 前端已装 `@vue-flow/core`、`ai`、`@ai-sdk/vue`、`wangeditor`、`markdown-it`、`highlight.js`，无需新增前端依赖。
- 后端已有 `Agno/openai/pgvector(可移植)/asyncpg`，无需新增后端依赖。
