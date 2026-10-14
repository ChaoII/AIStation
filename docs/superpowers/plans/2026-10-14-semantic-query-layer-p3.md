# 智能问数「语义执行层」P3 实施计划

> 依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.3、§4
> 前置：**P0/P1/P2 已上线**
> 范围：把 IR 的 `traverse` 从"单对象 1 跳"升级为**集合级多跳 + 在关联集上聚合**（对齐 Palantir Object Query Pattern 2/3）
> 纪律：默认关、A/B 后开；本阶段是"视需要"的进阶，**先用真实题集证明缺口再开工**

---

## 0. 开工前取证（已核实）

| 事项 | 事实 | 位置 |
|---|---|---|
| **当前 traverse 是逐个实例的** | `instance_pivot(object_code, key, link_id, limit, principal)` 需要**具体 key** | `ontology/service.py:2889` |
| P0 的 IR 限制 | `traverse` 只支持单对象 1 跳；多跳直接降级 NL2SQL | `plan/object_query` P0 约定 |
| 实例图已有 1–3 步扩展 | `POST /ontology/instance/graph`（真实行为节点、关系为边、1–3 步 Search Around）——**但它是可视化用途，不是结果集** | `ontology/service.py`、P4 记录 |
| 派生属性可算 | `compute_derived(object_code, key, prop_code, ...)`：沿 link 链（≤3 层）+ 9 种聚合 | `ontology/service.py:3623` |
| 单对象聚合 | `instance_aggregate(object_code, group_by, aggs, filters, limit, principal)`（**行策略下推成 WHERE**） | `ontology/service.py:2808` |
| 行级策略 SQL | `row_filter_sql(object_code, principal, cols, quote) -> {ok, where, ...}` | `ontology/security.py:887` |
| 跨域图遍历（schema 级） | `agno_kg.traverse(start, hops)`（Apache AGE，**数据/知识图谱**，非实例） | `query/agno_kg.py` |

**结论**：多跳/集合级 traverse **缺的是"设置级接口"**——现有 `instance_pivot` 是逐条的，`instance_graph` 是可视化的。P3 需在**实例层新增一个"设置级 traverse"函数**，并在 IR 层放开 hops。

---

## 1. 交付物清单

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| 1 | `backend/app/plugin/module_ai/ontology/service.py` | 改 | 新增 `instance_traverse(...)`（设置级、双向、多跳、可聚合、带两侧权限） |
| 2 | `backend/app/plugin/module_ai/query/object_query.py` | 改 | IR `traverse` 支持 `hops`（1–3）；`validate_ir` 放开多跳校验 |
| 3 | `backend/app/plugin/module_ai/query/object_exec.py` | 改 | `traverse` → `instance_traverse`；支持"在关联集上聚合" |
| 4 | `backend/app/plugin/module_ai/query/object_exec.py` | 改 | IR 支持 `derived_property`（走 `compute_derived`） |
| 5 | `backend/tests/test_ontology_traverse.py` | 新增 | 设置级 traverse：双向 / 多跳 / 两侧权限 / 聚合 |
| 6 | `backend/tests/test_query_object_multihop.py` | 新增 | 多跳 IR 执行 / 降级边界 |

---

## 2. 任务分解

### T1 — 实例层：设置级 traverse（`instance_traverse`）

**目标**：一条 SQL 完成"A 集合 → 沿关系 → B 集合（可多跳、可聚合、两侧权限都生效）"。

```python
async def instance_traverse(
    object_code: str,              # 起点对象类型
    filters: dict | None = None,   # 起点过滤（同 instance_search 词表）
    link_id: int = 0,              # 走哪条关系（1 跳；多跳由调用方串行拼接）
    direction: str = "auto",       # auto|source|target
    target_filters: dict | None = None,  # 对端过滤
    group_by: str = "",            # 对端分组
    aggs: list[dict] | None = None,      # 对端聚合
    limit: int = 100,
    principal: Any = None,
) -> dict:  # {ok, items|series, columns, count, link, hops, ...}
```

实现要点：

1. **优先单条 JOIN SQL**（而非 N 次 pivot）：`起点表 s JOIN 对端表 t ON s.source_field = t.target_field`（按 `join_method` 与方向决定），
   起点条件与对端条件分别下推；
2. **两侧行级策略都必须下推**：分别调 `security.row_filter_sql(object_code/其他)`，把 `where` 合进 JOIN 的 `ON`/`WHERE`（**过滤在聚合之前**，沿用 `instance_aggregate` 的做法）；
3. **列级掩码**：对端列也要按 `hidden_columns` 处理（沿用 `filter_instances` 语义）；
4. **join_method 三态**：`foreign_key` 直接 JOIN；`dataset`（多对多连接表）需先接连接表；`object_type`（中间对象）需两跳；
5. **多跳**：hops > 1 时由调用方**串行拼接**（每次用上一步结果的 keys 作为下一步输入），并在每步做权限校验；
6. **失败语义**：对象未物化 / 关系不存在 / 方向不匹配 → `ok=False`（→ 降级）。

**验收**
1. 正向 + 反向 traverse 都返回正确集合（复用 P4 `test_ontology.py` 的双向夹具）。
2. 起点有行级策略时，**起点与被连表两侧**都按策略过滤（构造只允许看部分行的主体）。
3. `group_by + aggs` 时返回 series（等价于"关联集上的分组聚合"）。
4. 多对多（`join_method=dataset`）能走连接表。
5. 未物化/关系不存在 → `ok=False`。

### T2 — IR 放开多跳 + 接线

1. `object_query.py`：
   - `traverse` 项增 `"hops": int`（默认 1，上限 `object_query_max_traverse_depth`，默认仍 **1**，P3 开时可调 2–3）；
   - `validate_ir` 对 `hops > max_depth` → 剔除该项（不整条作废），并记录 reason。
2. `object_exec.py`：
   - `traverse` → 串行调 `instance_traverse`（逐跳）；
   - 支持"**在 traverse 结果上聚合**"：IR 的 `group_by`/`aggregations` 若标注 `on: "traverse"` → 在末跳结果上 `instance_aggregate`（或让 `instance_traverse` 直接带 `group_by/aggs` 一次完成）。
3. **IR 的 `derived_property`**：LLM 可请求某派生属性 → 走 `compute_derived`（仅单对象，逐实例）。

**验收**
1. 2 跳 IR（如"摄像机的告警里，严重级别为高的有多少"）→ 正确结果。
2. `hops` 超上限 → 该项被剔除（其余保留），不整条失效。
3. 派生属性查询 → 正确值（复用 `test_ontology` 的派生夹具）。

### T3 — 评测与边界

1. 评测集新增**多跳/关联聚合**分类；`eval_metrics` 的 `path` 维度下再分 `hops`。
2. A/B：`object_query_max_traverse_depth=1`（基线）vs `3`（实验），唯一变量。

**验收**：能输出"多跳题集上 1 跳 vs 3 跳"的准确率与延迟对比。

---

## 3. 关键约定

1. **两侧权限都必须下推**（起点 + 对端），否则 traverse 会绕权限——这是本阶段**最大的安全风险点**（历史上有 `_render_chart` 绕行策略的先例）。
2. **过滤在聚合之前**（JOIN → WHERE → GROUP BY），沿用 `instance_aggregate` 的既有做法。
3. **多跳是串行拼接**，每跳独立权限校验；任何一跳失败 → 整条 `ok=False`（降级）。
4. **默认 1 跳不变**：`object_query_max_traverse_depth` 默认仍 `1`，只有 A/B 证明多跳有收益才调高。
5. **不新建存储**：全部基于实例层的真实表 JOIN。

---

## 4. 验收标准（P3 整体）

| # | 验收项 | 方法 |
|---|---|---|
| 1 | 设置级 traverse 正确（正/反向） | `test_ontology_traverse.py` |
| 2 | **两侧行级策略都生效** | 构造受限主体，断言两侧行数 |
| 3 | 关联集上聚合正确 | group_by + aggs 断言 |
| 4 | 多跳 IR 可执行 | `test_query_object_multihop.py` |
| 5 | 超限降级、不整条失效 | 单测 |
| 6 | 默认 1 跳时行为与 P2 一致 | 回归全绿 |
| 7 | A/B 可跑 | 脚本输出 1 跳 vs 3 跳对比 |
| 8 | 提交前全量 | `uv run pytest -q -n 4` |

---

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| **traverse 绕行级策略** | 两侧都下推 `row_filter_sql`；专门写回归测试（§4-2） |
| 多跳延迟高 | 上限 3；每跳 LIMIT；串行拼接可缓存中间 keys |
| 多对多/中间对象 join 复杂 | 按 `join_method` 分派；不支持的类型直接 `ok=False` 降级 |
| 多一次 LLM 输出（hops）反而变差 | 沿用 P0 纪律：词汇表约束 + 严格降级 + A/B |

---

## 6. 明确不做（P3 范围外）

- 任意深度图遍历（>3 跳）——实例层保持 ≤3
- traverse 结果再 traverse 的**任意链式组合**（只做线性多跳）
- 独立图数据库/对象存储（Palantir Object DB 式）——始终不做
- 微调路线——始终不做

---

## 附：P0–P3 与三家标杆的对应

| 本计划 | 对应 Palantir | 对应 SuperSonic | 对应 WrenAI |
|---|---|---|---|
| P0 对象查询 + scope 收敛 | Object Query Tool + Governance | S2SQL 语义执行 | MDL 语义模型 |
| P1 上下文注入 | Retrieval Context（固定对象集） | 多轮上下文 | — |
| P1 自动出图 | — | 自动选图 | Vega-Lite |
| P1 实例索引 | Object Storage + Funnel | — | — |
| P2 多方言 | — | JDBC 多库 | 20+ 源 transpile |
| P2 多轮重写 | — | Query Rewriting | — |
| P3 多跳 traverse | Pattern 2（根因分析） | — | — |
| P3 关联集聚合 | Pattern 3（概览聚合） | — | — |
