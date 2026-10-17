# 工作流引擎与 agno 的能力差距评估（谁有、谁补）

> 目的：在「AI 调用一律走 agno」的前提下，**逐项判断**工作流引擎里哪些能力 agno 本来就有、
> 哪些是 agno 没有而我们必须自研。结论用于决定「能借就借、不能借就明确保留自研」，
> 避免把 agno 已有的轮子再造一遍，也避免为了"统一"而把自研图引擎换成不匹配的范式。
>
> 评估方式：读本仓 `app/plugin/module_ai/workflow/engine.py` + 实测已安装 agno 包
> （`agno.workflow` 导出清单、`Workflow.__init__` 形参、`agno.agent` 的 HITL 相关 API）。

## 一、双方范式不同（这是全部结论的根）

| | 我们的工作流 | agno.workflow |
|---|---|---|
| 定义方式 | **可视化节点图**（前端画布 + JSON 图持久化） | **代码定义的步骤流水线**（Python 里写 `Steps`） |
| 控制流 | 节点 + **边（handle）分支**，栈式图遍历 | `Condition` / `Loop` / `Parallel` / `Router` 步骤 |
| 执行者 | 自研 `WorkflowEngine.run()`（栈遍历、边选择、预算、超时、受限模式） | `Workflow.arun()` |
| 可编辑性 | 用户在画布上拖拽连线 | 只能改代码 |

**范式差异决定了：节点图层无法用 agno 步骤替换**（要换就是重写产品形态，不是重构）。

## 二、agno **确实没有**、必须自研的部分（保留）

| 能力 | 说明 |
|---|---|
| 可视化节点图 + JSON 图持久化 | agno 无图结构，只有代码步骤 |
| 图遍历器（`run()`） | 栈式遍历、**按 handle 选边**、`visited` 去重、超时/预算/受限模式 |
| 节点类型层（22 种） | `start / end / answer / llm / agent / knowledge / tool / code / condition / variable / variable_aggregator / http / iteration / classifier / extractor / template / doc_extractor / web_search / database / sub_workflow / loop / parallel` |
| Dify 式「变量赋值 / 变量聚合 / 模板转换」节点 | agno 里变量就是 Python 变量，无节点概念 |
| 「开始 / 结束 / 回答」节点 | agno 的流程天然有起止，无需节点 |
| 受限模式（公开分享白名单 `_RESTRICTED_ALLOW`） | agno 无此安全档位 |
| 节点级输入快照 / `node-status` 帧协议 | agno 事件流是另一套语义，前端画布依赖我们的帧 |

## 三、agno **有**、我们**重复实现**的部分（值得注意）

| 能力 | agno 提供 | 我们的实现 | 评估 |
|---|---|---|---|
| 条件分支 | `agno.workflow.Condition`（含 CEL 表达式 `validate_cel_expression`） | `_exec_condition`（图分支） | 语义不同（图边 vs 步骤跳转），**不能直接替换**；分支判定逻辑可参考 CEL |
| 循环 / 迭代 | `agno.workflow.Loop` | `_exec_loop` / `_exec_iteration` | 同上，保留自研 |
| 并行 | `agno.workflow.Parallel` | `_exec_parallel` | 同上，保留自研 |
| 路由 | `agno.workflow.Router` | `_exec_classifier`（LLM 分类后选边） | 我们的分类器是**节点**，Router 是**步骤**；保留自研 |
| 子流程 | `Workflow` 嵌套 / `RemoteWorkflow` | `_exec_sub_workflow` | 保留自研（需要图内嵌套语义） |
| **人工审批（HITL）** | `agno.workflow.HumanReview` 步骤 | ✅ **已用 agno**：agent 工具级 `requires_confirmation` → `RunPaused` → `RunRequirement` → `acontinue_run`（`engine.py` 的 `resume_after_approval`） | **已对齐**（走的是 agno 的 agent 工具审批通道，而非 HumanReview 步骤） |
| 运行持久化 | `Workflow(db=...)` + `session_id` / `session_state` | 自研 run 记录（业务表） | 业务侧要自己的审计/权限，**保留自研**；agno 的 db 仅用于 HITL 续跑 |
| 流式事件 | `stream_events` / `stream_executor_events` / `store_events` | 自研帧协议（SSE） | 前端画布绑定我们的帧，**保留自研** |
| 输入/输出契约 | `input_schema` / `output_schema` | 节点级 schema（部分） | 节点级已够用 |

## 四、与范式无关的**横切能力**（该借就借）

这些不受「图 vs 步骤」影响，是本轮真正补齐的对象：

| 能力 | 状态 | 落地位置 |
|---|---|---|
| **agno tracing**（agent/模型/工具调用链） | ✅ 已接入 | `agno_tools/tracing.py` + `init_app` 启动调用；落 `agno_traces` / `agno_spans` |
| **structured output**（模型侧 JSON schema 约束） | ✅ 已接入 | `query/llm_schemas.py` + `query/service.py::_llm_structured`（替代「提示词要求 JSON + 事后解析」） |
| background / cancellation | ⏳ 待评估 | agno 支持；我们目前靠超时 + 取消请求 |
| run 持久化到 agno db（可选） | ⏳ 待评估 | 仅当需要 agno 侧会话/记忆时 |

## 五、结论（不做什么 / 做什么）

**不做**：
- ❌ 不把图遍历器换成 `agno.workflow.Steps`——范式不匹配，是重写而非重构，零收益高风险。
- ❌ 不把 `condition/loop/parallel` 节点换成 agno 步骤——图分支语义无法映射。

**要做**（按优先级）：
1. ✅ 横切能力优先借 agno：tracing（已完成）、structured output（已完成）。
2. ⏳ 逐节点评估「节点执行体是否已走 agno」：`llm/agent/knowledge/extractor/classifier/web_search` 已走 agno Agent；
   `tool/code/http/database` 属**确定性执行**（不是 AI 调用），保持自研合理。
3. ⏳ HITL 已有 agno 通道，后续若需要「非工具类」审批点，再评估 `agno.workflow.HumanReview`。

**一句话**：工作流的**产品形态（节点图）必须自研**，agno 补的是**执行体与横切能力**；
当前已完成 tracing + structured output，其余横切项按需推进。
