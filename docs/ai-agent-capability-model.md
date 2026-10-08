# AIStation Agent 能力模型（Capability Model）设计与集成方案

> 目标：把「能力」统一为 **Agno `Agent` 可装配的组件**（Agent 的「手脚」），
> 明确「本体能力 / 平台能力」的归属，并让 Agent **运行时按需调用**这些能力。

## 1. 核心定义

> **凡是 Agent 能配置/按需调用的，都是它的「能力」。在 Agno 里，能力 = 装配给 `Agent` 的组件。**

分两大类：

- **工具型能力（可调用）**：装配为 Agno `Agent(tools=[...])`，运行时由 Agno 的
  function-calling 循环**按需决定是否调用**。
- **组件型能力（配置类）**：装配为 Agno 的其它参数（`model` / `instructions` /
  `knowledge` / `skills` / `memory_manager` / `reasoning_*` …）。

## 2. Agno `Agent` 可装配组件（依据本机 agno 3.0.6 `Agent.__init__`）

| 类别 | Agno 参数 | 说明 |
|---|---|---|
| 大脑 | `model` / `fallback_models` | LLM |
| 推理/自省 | `reasoning_model` / `reasoning_agent` | 多轮自省 |
| 工具 | `tools` / `tool_choice` / `tool_call_limit` / `tool_hooks` | 可调用函数 |
| 知识 | `knowledge` / `knowledge_retriever` / `add_knowledge_to_context` | RAG 检索、接地 |
| 技能 | `skills` | Agno skills |
| 记忆 | `memory_manager` / `enable_agentic_memory` | 长期记忆 |
| 状态/会话 | `session_state` / `db` / `add_history_to_context` | 会话与历史 |
| 指令/角色 | `instructions` / `description` / `role` / `expected_output` | 系统提示 |
| 结构化输出 | `output_schema` / `parser_model` | 约束输出 |
| 钩子 | `pre_hooks` / `post_hooks` | 生命周期 |

## 3. 能力映射（来源 × Agno 组件）

| 能力 | 来源 | Agno 组件 | 现状 |
|---|---|---|---|
| 本体函数 Function | 本体 | `tools` | ❌ 仅拼进 system prompt，未注册为工具 |
| 对象动作 Action | 本体 | `tools` | ❌ 同上 |
| 对象模型接地（对象/属性/Link 摘要） | 本体 | `instructions`/上下文 | ⚠️ 部分（问数时注入） |
| 问数 | 平台 | `tools`（`ai_query`/`resolve_object`） | ✅ 已是真工具 |
| 数据治理（DQ/权限/数据域/血缘） | 平台 | `tools` | ❌ 未暴露为工具 |
| 内置只读工具 / HTTP 工具 | 平台 | `tools` | ✅ |
| 知识库检索 | 平台 | `knowledge` | ✅（RAG 注入） |
| 技能 | 平台 | `skills` | ⚠️ 拼进 prompt（可保留） |
| 模型 | 平台 | `model` | ✅ |
| 提示词 | 平台 | `instructions` | ✅ |
| 工作流 | 平台 | 子 Agent（`Team`）/ 工具 | ✅（workflow 节点） |
| 记忆 / 推理 | 平台 | `memory_manager` / `reasoning_*` | ❌ 未接 |

**结论**：Agent「按需调用问数」= Agno 的 function-calling 循环，机制已具备；
真正要补的是**把该成为能力的东西都注册成 Agno 工具**。

## 4. 统一能力目录（Capability Catalog）

### 4.1 数据模型

沿用 `ai_ont_capability`（本体侧登记）并新增/规整字段，形成**统一能力目录**：

- `source`：`ontology`（本体）/ `platform`（平台）
- `kind`：`tool`（工具型，可调用）/ `component`（组件型，配置类）
- `type`：具体类型（function/action/query/governance/knowledge/skill/model/prompt/workflow/memory/reasoning…）
- `code` / `name` / `description` / `enabled`

### 4.2 接口

- `GET /ai/ontology/capabilities`（已有）：统一返回目录，带 `source/kind/type`。
- `GET /ai/agents/{id}/capabilities`：某 Agent 已装配的能力（按 Agno 组件聚合）。

## 5. Agent 装配（前端）

Agent Studio 的「能力装配」按 **Agno 组件**分组呈现，每条标注「来源：本体/平台」：

```
工具 tools
  - 本体函数 / 对象动作   [本体]
  - 问数（数据源选择）     [平台]
  - 数据治理（DQ/权限/域/血缘）[平台]
  - 内置工具 / HTTP 工具   [平台]
知识 knowledge -> 知识库选择            [平台]
技能 skills -> 技能选择                 [平台]
模型 model -> LLM 选择                  [平台]
提示词 instructions -> 提示词模板        [平台]
工作流 -> 子 Agent（Team）              [平台]
记忆 / 推理 -> （后续）                  [平台]
```

## 6. 运行时（Agno）

- 装配的能力 → 组装为 `tools`（本体函数/动作 + 问数 + 治理 + 内置/HTTP）与
  其它组件（`model`/`instructions`/`knowledge`/`skills`）。
- 通过 `agno_tools.agent_factory.build_agent` 统一构建；`agent.arun(...)` 时由 Agno
  循环**按需调用**工具，无需手写 function-calling。

## 7. 落地步骤（分阶段，逐步提交/验收）

1. **本体 Function/Action → 真 Agno 工具**（最高收益）
   - 运行时按 Agent 授予的本体函数/动作，动态构建工具（schema 取 `input_schema`/`expr`），
     dispatch 执行（函数=表达式求值；动作=写回 `target_table`，`approval` 时走待确认）。
   - 移除「能力名拼 prompt」的假象（或保留说明）。
2. **数据治理 → Agno 工具**：把 DQ/权限/数据域/血缘查询暴露为工具，按需调用。
3. **统一能力目录**：`ai_ont_capability` 增 `source/kind/type`，`/capabilities` 返回分类。
4. **Agent 装配 UI**：按 Agno 组件分组 + 来源标注。
5. **本体页收敛**：本体页只留本体侧能力（函数/动作/接地），平台能力移到 Agent 装配。

## 8. 验收

- 后端：pytest 覆盖「本体函数/动作注册为工具并被 Agent 调用」「治理工具」「能力目录分类」。
- 前端：type-check 通过；Agent 装配页按 Agno 组件呈现。
- 端到端：给 Agent 授予本体函数/问数/治理能力，运行时按需触发对应工具。
