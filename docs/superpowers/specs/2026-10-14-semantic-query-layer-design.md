# 智能问数「语义执行层」设计方案（对齐 Palantir Object Query）

> 版本：v1（评审稿）
> 日期：2026-10-14
> 适用范围：`backend/app/plugin/module_ai/query/`、`backend/app/plugin/module_ai/ontology/`、`frontend/src/views/module_ai/query/`
> 定位：在**不推翻现有问数**的前提下，把「LLM 直写物理 SQL」升级为「LLM 输出对象查询 → 确定性执行」，补齐本项目与 Palantir / SuperSonic / WrenAI 之间最关键的那一层。

---

## 0. 为什么是现在

前三轮调研得到的一致结论：

1. Palantir 的"问数"（AIP Object Query）**不写 SQL**——它对**语义对象**做 filter / aggregate / traverse link，由引擎执行。
2. SuperSonic 用 **S2SQL（语义 SQL）→ 物理 SQL** 的 8 级 parser 链 + Calcite 完成同样的"语义执行"。
3. WrenAI 用 **MDL → wren-core（Rust/DataFusion）LogicalPlan → dry-run → transpile** 完成同样的"语义执行"。
4. **只有本项目，让 LLM 直接写物理 SQL**，语义层仅做 prompt grounding。

这就是本项目评测里"困难题 42.9%、窗口函数 41.7%、多表 join 易错"的结构性来源。而本项目**已经具备**做语义执行的全部原料（本体对象/属性/链接 + 实例层 + 权限下推），缺的只是"把问数的执行后端从 SQL 换成对象查询"。

---

## 1. 五方能力对比与差距标注

图例：✅ 已有且完整 ｜ ⚠️ 部分/近似 ｜ ❌ 缺失

### 1.1 语义与执行

| 能力 | Palantir | SuperSonic | WrenAI | DB-GPT | **本项目** |
|---|---|---|---|---|---|
| 语义层形态 | 对象/链接/动作/函数/接口 | 指标/维度/实体/标签 | **MDL（JSON 清单，可版本化）** | AWEL 流 + 知识库 | 指标/术语/概念/**本体** |
| **语义→物理执行** | ✅ **Object Query（不写 SQL）** | ✅ **S2SQL→物理 SQL（8 parser+Calcite）** | ✅ **WrenSQL→LogicalPlan+dry-run** | ⚠️ 多步 agent | ❌ **NL2SQL 直写物理 SQL** |
| 校验时机 | 对象查询天然合法 | 语义修正器 + 物理 SQL 优化器 | **dry-run + 自动修复** | 报错回喂 | EXPLAIN 护栏 + 结果自校验 |
| Schema 给 LLM 方式 | **只暴露授权对象/属性（硬收敛）** | 检索语义模型 | 列裁剪 + MDL | 检索 | ⚠️ 检索命中 schema 灌 prompt（无硬收敛） |
| 多方言 | 专有 | ✅ JDBC 多库 + 方言优化 | ✅ **20+ 源 transpile** | 多库/文件 | ❌ 主 PG |

### 1.2 实例层与存储

| 能力 | Palantir | SuperSonic | WrenAI | DB-GPT | **本项目** |
|---|---|---|---|---|---|
| 实例存储 | ✅ **对象存储（物化+索引）** | 语义层 + 物理库 | 查询原地（不搬数据） | 多源连接器 | ⚠️ **直连 PG 支撑表** |
| 索引/物化管道 | ✅ **Funnel（batch/streaming/CDC）** | — | — | — | ❌ |
| 对象集操作 | ✅ filter/aggregate/traverse | ✅ 语义查询 | SQL | SQL/Python | ✅ instance_search/aggregate/pivot（已接权限） |
| 实例图 | ✅ Vertex | — | — | — | ✅（节点上限 150） |
| 写回 | ✅ Action（OSV2 索引回本体） | — | — | — | ✅ writeback + 动作七道闸 |

### 1.3 检索、记忆、Agent 与治理

| 能力 | Palantir | SuperSonic | WrenAI | DB-GPT | **本项目** |
|---|---|---|---|---|---|
| 检索/召回 | ✅ 向量语义检索对象 | 知识库 trie + 向量 exemplar | Qdrant | 向量 + GraphRAG | ✅ **四路召回 + RRF** |
| 多轮上下文 | ✅ Context 层每轮注入 | ✅ **查询重写（LLM rewrite）** | ✅ | ✅ | ⚠️ few-shot/历史（无重写） |
| 记忆/自学习 | ✅ 决策即数据 | ✅ **记忆自动评审** | ✅ Q-SQL 累积 | ⚠️ | ✅ few-shot 策展 + 反馈 |
| Agent 五层 | ✅ Context/Query/Logic/Action/Governance | SPI 插件 | Skills + MCP | AWEL + 多智能体 | ⚠️ 有 grounding/tools/action/权限，**无 Context 层、无硬收敛** |
| 反幻觉 | ✅ **架构性（看不到=编不出）** | 语义注入 | dry-run | — | ⚠️ prompt + 检索 + 校验 |
| 可视化 | ✅ | ✅ 自动选图 | ✅ Vega-Lite | ✅ GPT-Vis | ❌ **问数页仅表格** |
| 微调 | — | — | — | ✅ **DB-GPT-Hub（13B→82.5%）** | ❌ |

### 1.4 差距清单（本项目待补，按优先级）

| 编号 | 差距 | 对标 | 影响 | 优先级 |
|---|---|---|---|---|
| **G1** | **问数缺「语义执行层」**：LLM 直写物理 SQL，join/口径靠猜 | Palantir Object Query / SuperSonic S2SQL / WrenAI MDL | **最大失分源**（困难题/窗口/多表） | **P0** |
| **G2** | **scope 无硬收敛**：往 prompt 灌检索 schema，而非"只暴露授权对象/属性" | Palantir 五层 Governance | 反幻觉弱、token 浪费 | **P0** |
| **G3** | **无「当前对象上下文」注入**（选中对象 → agent 自动知道） | Palantir Context Layer | 多轮/上下文体验差 | **P1** |
| **G4** | 实例层无物化/索引，直连 PG；实例图 150 上限 | Palantir Object DB + Funnel | object set 操作慢、规模受限 | **P1** |
| **G5** | 问数结果不出图 | SuperSonic/WrenAI/DB-GPT | 体验级缺口 | **P1** |
| **G6** | 单方言（PG），无 transpile | WrenAI 20+ 源 | 外部数据源受限 | **P2** |
| **G7** | 多轮查询重写缺失 | SuperSonic query rewrite | 指代/追问弱 | **P2** |
| **G8** | 无反幻觉的架构保证 | Palantir | 编造风险 | 随 G1/G2 解决 |
| **G9** | 无微调路线 | DB-GPT-Hub | 长尾慢 | **不做**（见 §7） |

---

## 2. 结论先行

- **只需补 G1 + G2**（合并为一个工作流：语义执行层 + scope 收敛），就能拿到三家标杆最核心的正确性收益；且**本项目已有全部原料**（本体 + 实例层 + 权限），改造成本远低于从零造 wren-core / Calcite。
- G3/G4/G5 是体验与规模级增强，排在 G1 之后。
- G6/G7 视真实数据源需求再定；G9 明确不做。

**一条硬纪律（本项目既有教训）**：新增路径**默认关**，必须用留出法 A/B 验证后再开。`plan.py` 的两段式分解实测 **−7.55 分、错误率 +9.43%**，就是"让 LLM 多输出一层结构"翻车的先例——本方案的 IR 必须**用词汇表硬约束 + 严格降级**规避同类问题。

---

## 3. 设计方案

### 3.1 总体思路：三分支路由

问数主入口 `AiQueryService.ask` 由目前的两分支（metric 快路径 / NL2SQL 慢路径）扩展为三分支：

```
用户问题
   │
   ├─(1) 指标模板命中 ────────────────→ 【快路径】确定性 SQL（已有，秒级）
   │
   ├─(2) 命中本体对象且 IR 可覆盖 ────→ 【对象查询路径】LLM 出 IR → 语义执行（新增）
   │
   └─(3) 兜底 ────────────────────────→ 【慢路径】NL2SQL（已有，保留）
```

路由原则（确定性优先）：
1. 先试**指标模板**（0 LLM，秒级）。
2. 再试**对象查询**：若检索命中的本体对象能覆盖问题（有对应对象类型 + 属性），走 IR。
3. 任一环节失败/IR 不合法/执行报错 → **回退 NL2SQL**（绝不因新路径失败而答不出来）。

### 3.2 对象查询 IR（Object Query IR）

LLM 只输出这个结构，**不写 SQL**：

```json
{
  "object": "video_cameras",
  "filters": [
    {"field": "status", "op": "in", "value": ["ONLINE", "OFFLINE"]},
    {"field": "region", "op": "eq", "value": "华南"}
  ],
  "traverse": [
    {"link": "cam_has_alarms", "direction": "target",
     "filters": [{"field": "severity", "op": "eq", "value": "HIGH"}],
     "as": "alarms"}
  ],
  "group_by": [{"field": "region", "alias": "区域"}],
  "aggregations": [
    {"fn": "count", "field": "*", "alias": "告警数"},
    {"fn": "sum", "field": "duration", "alias": "总时长"}
  ],
  "order_by": [{"field": "告警数", "dir": "desc"}],
  "limit": 100
}
```

字段约束：
- `object` / `field` / `link` **必须**来自"授权 + 检索命中"的清单（§3.4），越界即判非法。
- `op` 取值固定枚举：`eq|ne|gt|gte|lt|lte|in|contains|is_empty|not_empty`（**复用本体已有的算子词表**，避免像视图筛选器那样两套词表打架）。
- `aggregations.fn` 取 `count|sum|avg|min|max`（对齐 `ONT_AGGREGATIONS`）。
- **单对象**查询（`limit=1` 且无聚合）→ 走 `instance_get`。

### 3.3 执行后端：复用本体实例层（零新增存储）

IR → 执行映射（全部复用现有函数，**不新造引擎**）：

| IR 部分 | 复用 | 现有 API |
|---|---|---|
| `filters` 单对象 | `instance_search(code, keyword, filters, limit, offset, principal)` | `ontology/service.py:2600` |
| `group_by` + `aggregations` | `instance_aggregate(object_code, group_by, aggs, limit, principal)` | `ontology/service.py:2808` |
| `traverse`（沿关系跳转） | `instance_pivot(object_code, key, link_id, limit, principal)` | `ontology/service.py` |
| 单对象读取 | `instance_get(code, key, principal)` | `ontology/service.py:2706` |
| 派生属性 | `compute_derived(...)` | `ontology/service.py:3623` |
| 权限 | `security.secure_sql` / `load_principal` | 已有，**实例层已内置** |

**为什么这样划算**：实例层已经解决了"物化与否、权限下推、列可见性、敏感字段"这些难题。IR 执行器只是一层"IR → 调用上述函数 → 拼结果集"的**薄封装**。

> ⚠️ 已知限制（如实标注）：实例层当前**只支持单对象类型 + 一层 pivot**。IR 的 `traverse` 若超过 1 跳或需要多对象类型联合聚合，需**降级到 NL2SQL**（第一版先不追求多跳聚合）。

### 3.4 LLM 角色与硬约束（吸取 plan.py 教训）

生成 IR 的 prompt 必须满足：

1. **词汇表只给"授权 + 检索命中"的子集**：注入的不是整个本体 schema，而是 `_semantic_tables` / `_recall_*` 命中的对象类型及其属性 + 关系。**这是对 Palantir "只暴露授权对象/属性" 的落地**，同时直接缓解 G2。
2. **只输出 JSON**，不写任何解释、不写 SQL。
3. **越界即丢**：解析后校验每个 `object`/`field`/`link` 是否在词表内；不在的一律剔除；`object` 不在词表 → 整条 IR 作废。
4. **严格降级**：IR 解析失败 / 校验失败 / 执行抛错 → 回退 `_nl2sql`（复用现有自纠错链路）。
5. **默认关 + 灰度**：设置项 `object_query_enabled`（默认 `false`），用留出法 A/B 验证后再开——**与 `two_stage_planning` 同一纪律**。

### 3.5 与现有链路的共存

- `ask()` 增加路由分支，**不改动** `_slow_path` / `_nl2sql`（保留为兜底）。
- 新增 `_object_query_path(question, session_id, datasource, auth, principal)`，返回与现有 `_answer()` 相同的响应结构（`path="object"`），前端无感。
- `AiQueryMessageModel.path` 增加取值 `"object"`；`confidence`：对象查询 = **0.95**（高于 NL2SQL 的 0.85，低于指标快路径的 1.0）。
- `evidence.source` 增加 `"本体对象查询"`。

### 3.6 治理与 scope 收敛（G2）

对齐 Palantir 五层 Governance 的"每层都有约束"：

| 层 | 本方案落地 |
|---|---|
| Context | 注入的是**检索命中的授权对象**，不是全 schema |
| Query | IR 的 `object/field/link` **白名单校验**，越界即丢 |
| Logic | 派生属性 / 本体函数走 `run_ontology_function`（已按调用者门控） |
| Action | 变更仍走 `ont_action__*` + 审批门禁（已有） |
| 治理 | 执行前 `load_principal`；实例层权限下推；`ai_call_logs` 留痕 |

**反幻觉的架构化**：IR **不能引用**不在授权清单里的对象/字段 → 与 Palantir "看不到就编不出" 同构。

### 3.7 Context 注入：当前对象上下文（G3）

为问数 / 助手增加"当前对象"参数（对齐 Palantir Retrieval Context 的 Fixed Object Set）：

- 前端从本体/实例页跳转问数时带 `object_code` + `object_key`。
- 后端 `instance_get` 取该对象 + 其关联数量，作为**确定性上下文**注入 prompt 头部（非 LLM 决定）。
- 助手的 `QUERY_DS_CONTEXT` 同款机制扩展一个 `QUERY_OBJECT_CONTEXT`。

### 3.8 可观测与评测

- 复用现有 `_recall_grounding`（召回表/字段）+ 新增 `ir` 字段（本次生成的 IR，供前端"查看对象查询"折叠展示，替代/并列 SQL 折叠）。
- 评测套件（`eval_runner` / `eval_metrics`）增加**分支维度**：`path=metric/object/nl2sql` 各自的准确率，便于验证 G1 的收益（对齐现有消融机制）。

### 3.9 其余缺口的小设计

**G4 实例物化/索引（P1）**
- 对高频对象类型提供"物化开关"：把 `instance_search/aggregate` 的常用组合落成**物化视图**或加**覆盖索引**，`index_status` 字段已存在，接上即可。
- 实例图 150 上限：分页/懒加载，或对已物化对象放宽。

**G5 自动出图（P1）**
- 由 IR/结果形态推断：`group_by` 有 1 维 + 1 聚合 → 柱/饼；`group_by` 有时间列 → 折线；否则表格。
- 前端复用 ECharts（项目已在 overview/logs/workflow 用）。

**G6 多方言（P2）**
- 慢路径 `_nl2sql` 的 system_prompt 里"PostgreSQL 查询助手"改为按 `datasource.type` 参数化的方言提示；外部源已支持 pg/mysql/sqlite，补 MySQL/SQLite 语法约束即可。

**G7 多轮重写（P2）**
- 仿 SuperSonic `QueryRewritingStrategy`：用 LLM 把"那上周呢"重写为完整问题（输入 = 当前问题 + 历史问题的映射 schema + 历史 SQL）。

---

## 4. 分期实施计划

### P0 — 语义执行层 + scope 收敛（核心，G1+G2）

| 交付物 | 说明 |
|---|---|
| `query/object_query.py` | IR 数据结构（pydantic）+ `parse_ir()` + `validate_ir(ir, allowed_objects)` + `render_prompt()` |
| `query/object_exec.py` | `execute_ir(ir, principal)` → 复用实例层；返回 `{columns, rows, sql_trace}` |
| `service.py` 路由 | `ask()` 三分支；新增 `_object_query_path()`；`path="object"`；严格降级 |
| 词表收敛 | IR prompt 只注入检索命中的授权对象/属性/关系 |
| 设置项 | `object_query_enabled`（默认 `false`）、`object_query_max_traverse_depth=1` |
| 前端 | 结果区可折叠展示"对象查询（IR）"；`path=object` 置信度角标 |
| 测试 | `tests/test_query_object.py`：IR 解析/越界丢弃/降级/权限 |

**验收标准**
1. `object_query_enabled=false` 时行为与现状**完全一致**（回归不破）。
2. 开启后，"统计每个区域的在线摄像头数"能生成合法 IR 并正确执行（group_by + count）。
3. IR 里出现词表外的对象/字段 → 被剔除/降级，**不产生错误结果**。
4. 对本体未覆盖的问题（如窗口函数），自动降级到 NL2SQL 且答案不劣化。
5. 留出法 A/B：对象查询覆盖的题集上 `data_accuracy` **不低于** NL2SQL 基线。

### P1 — 上下文注入 + 出图 + 实例索引（G3+G5+G4）

- 当前对象上下文（§3.7）
- 问数结果自动出图（§3.9 G5）
- 高频对象物化 + 覆盖索引（§3.9 G4）

### P2 — 多方言 + 多轮重写（G6+G7）

### P3 — （视需要）多跳 traverse 聚合

---

## 5. 验收的总口径

对齐本项目既有纪律：**任何新路径，先 A/B，再默认开**。P0 上线时 `object_query_enabled=false`；A/B 通过后才改默认。

---

## 6. 风险与取舍

| 风险 | 影响 | 应对 |
|---|---|---|
| LLM 输出 IR 时**幻觉对象/字段** | 中 | 词汇表硬约束 + 越界即丢 + 降级（plan.py 同款教训） |
| 实例层只支持单对象 + 1 跳 | 中 | 第一版明确限定；多跳降级 NL2SQL |
| 新增分支带来路由歧义（该走 object 还是 nl2sql？） | 中 | 规则优先：能生成合法 IR 才走 object，否则 nl2sql |
| 双路径维护成本 | 中 | object 路径只做"本体覆盖的常见形状"，其余全交 nl2sql |
| 与指标快路径语义重叠 | 低 | 快路径先判；object 路径只处理"非指标"问题 |

---

## 7. 明确不做

| 不做 | 理由 |
|---|---|
| 从零造 wren-core / Calcite 级编译器 | 成本极高；本项目在 Python 上做"IR + 实例层执行"已能达到同等正确性收益 |
| TypeScript/Python 函数沙箱 | 与"优先成熟第三方库"原则冲突（已在 `ontology-ultimate-plan.md` 列为非目标） |
| 微调路线（DB-GPT-Hub） | 需 GPU 训练基建，与当前"本机模型 + agno"路径不符 |
| 完整 Palantir Object DB / Funnel 双轨存储 | 我们是直连 PG；物化/索引按需做（G4），不引入独立存储服务 |

---

## 附：证据索引

| 结论 | 出处 |
|---|---|
| Palantir 对象查询 / 五层 Agent 架构 | `zerofuturetech` 五层拆解、palantir 官方 `ontology/overview`、`object-indexing/overview` |
| Palantir object backend（OMS/Object DB/OSS/Actions/Funnel） | PuppyGraph《Palantir Ontology: Architecture & Benefits》 |
| SuperSonic S2SQL → 物理 SQL（8 parser 链） | SuperSonic DeepWiki `3.4-sql-translation-and-optimization` |
| SuperSonic 规则+LLM 双解析 / 自一致性 / 记忆评审 | SuperSonic DeepWiki `4.2-nl2sql-parsing-strategies` |
| WrenAI MDL + wren-core 语义执行 | WrenAI 官方 `architecture`、Sudipta Pathak 技术拆解 |
| DB-GPT AWEL / 多智能体 / 微调 | DB-GPT DeepWiki、Sudipta Pathak 拆解与基准 |
| 本项目现状（问数/本体/实例层/差距） | `docs/superpowers/specs/2026-10-04-smart-query-design.md`、`docs/ontology-ultimate-plan.md`、`query/service.py`、`ontology/service.py` |
| 两段式分解 A/B 结论（−7.55 分） | `docs/superpowers/plans/2026-10-12-ai-query-closure-round2.md` |
