# 智能问数「语义执行层」P1 实施计划

> 依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.7/§3.9、§4
> 前置：**P0 已上线且 A/B 通过**（`object_query_enabled` 已可开）
> 范围：G3 当前对象上下文 + G5 自动出图 + G4 实例索引/规模 + `ask_stream` 流式对象查询
> 纪律：每项**独立开关**、默认关、A/B 后开

---

## 0. 开工前取证（已核实）

| 事项 | 事实 | 位置 |
|---|---|---|
| 索引模块**已存在且是真的** | `build_index` 真执行 `CREATE INDEX`；状态机 `not_started/building/ready/failed/stale`；瞬时失败 5 分钟自动重试；`suggest_indexes` / `apply_suggestions` / `build_all` / `retry_due_indexes` | `ontology/indexing.py`（整文件） |
| 索引状态回写对象 | `_sync_object_index_status(object_code)` → `ai_ont_object.index_status` | `ontology/indexing.py:341` |
| 单实例读取（上下文注入用） | `instance_get(object_code, key, principal=None, scenario_code="")` | `ontology/service.py:2706` |
| 请求体 | `QueryAskRequest`（`question / session_id / datasource / force_slow`） | `query/schema.py` |
| 控制器 | `POST /query/ask`、`POST /query/ask/stream` 均只透传上述字段 | `query/controller.py:40/56` |
| 助手数据源上下文 | `QUERY_DS_CONTEXT: ContextVar[str]` | `assistant/tools.py:16` |
| 会话消息 | `AiQueryService.list_messages(session_id)` | `query/service.py` |
| 设置默认值 | `get_settings()` 内含默认 dict（如 `"schema_top_k": "16"`）；`save_setting(key, value, remark, auth)` | `query/service.py:5254`、`controller.py:1433` |
| 前端图表库 | 项目已用 `vue-echarts`（overview / logs / workflow） | `frontend/src/views/module_ai/*` |
| 流式事件 | `ask_stream()` 产出 `meta/reasoning/tool/sql_delta/sql_final/result/done/error` | `query/service.py:6122` |

---

## 1. 交付物清单

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| 1 | `backend/app/plugin/module_ai/query/schema.py` | 改 | `QueryAskRequest` 增 `object_code` / `object_key`（可选） |
| 2 | `backend/app/plugin/module_ai/query/controller.py` | 改 | `ask` / `ask_stream` 透传 `object_code/object_key` |
| 3 | `backend/app/plugin/module_ai/query/service.py` | 改 | `_object_context()` 注入；`ask`/`ask_stream` 签名扩展；`ask_stream` 增对象查询分支 |
| 4 | `backend/app/plugin/module_ai/assistant/tools.py` | 改 | 增 `QUERY_OBJECT_CONTEXT` contextvar，`ai_query` 读取 |
| 5 | `backend/app/plugin/module_ai/query/chart.py` | 新增 | 由 IR/结果形态推断图表类型（纯逻辑） |
| 6 | `backend/app/plugin/module_ai/ontology/indexing.py` | 改 | 增"按访问热度自动建索引"的入口（复用 `suggest_indexes`/`apply_suggestions`） |
| 7 | `frontend/src/views/module_ai/query/index.vue` | 改 | 结果区自动出图；接收 `object_code/object_key`；展示对象上下文条 |
| 8 | `frontend/src/views/module_ai/ontology/...`（实例探索器） | 改 | 加「去问数验证」入口（带 `object_code/object_key` 跳 `/ai/query`） |
| 9 | `backend/tests/test_query_object_context.py` | 新增 | 上下文注入 / 图表推断单测 |

---

## 2. 任务分解

### T1 — 当前对象上下文注入（G3）

**对齐 Palantir Context Layer**：用户在某对象上，agent 自动知道"当前对象"，不由 LLM 决定。

1. `QueryAskRequest` 增可选 `object_code` / `object_key`；控制器透传。
2. `AiQueryService._object_context(object_code, object_key, principal) -> str`：
   - `instance_get` 取该实例 + `list_links` 统计各关系对端数量；
   - 渲染成确定性文本块（**非 LLM 决定**），注入 `_build_schema_context` 头部：
     ```
     【当前对象】摄像机 #1（video_cameras）
     区域：华南；状态：ONLINE；告警记录：12 条
     ```
   - 取不到 → 静默跳过（**不报错、不阻断**）。
3. 助手侧：`assistant/tools.py` 增 `QUERY_OBJECT_CONTEXT`（与 `QUERY_DS_CONTEXT` 同款），`ai_query` 调用时带上；由会话/应用变量设置。
4. 前端：本体实例探索器加「去问数验证」，跳 `/ai/query?object_code=...&object_key=...`；问数页显示"当前对象"条（可关闭）。

**验收**
1. 带 `object_code/object_key` 提问 → prompt 里出现【当前对象】块（打桩 LLM 断言）。
2. 传了不存在的 key → 静默跳过，查询照常。
3. 助手 `ai_query` 在设置对象上下文后能感知。

### T2 — 自动出图（G5）

1. `query/chart.py`（纯逻辑）：
   ```python
   def infer_chart(ir: dict | None, columns: list, rows: list) -> dict:
       """→ {"type": "bar|line|pie|table", "x": 列名, "series": [列名], "reason": "..."}"""
   ```
   规则：`group_by` 有 1 维 + 1 个聚合 → 柱/饼（基数 ≤ 8 用饼）；`group_by` 含时间列（date/datetime）→ 折线；多聚合 → 多系列柱；否则表格。
2. `_answer()` 返回体加 `chart` 字段（后端推断，前端渲染）。
3. 前端问数页：结果区在表格上方渲染 `vue-echarts` 图（默认折叠，可切换表格/图表）。
4. **遵循项目 UI 规范**：Element Plus 原生 + `--el-*`；完成后截图读图核对。

**验收**
1. 分组计数题 → `type=bar`；时间分组 → `type=line`。
2. 明细题 → `type=table`（不出图）。
3. 前端图/表可切换。

### T3 — 实例索引自动化 + 实例图规模（G4）

> 索引模块已存在，本任务只做**接线与自动化**，不新建索引体系。

1. **热度驱动自动索引**：对象查询命中某对象类型时，累计计数（复用 `ai_call_logs` 或轻量计数）；超过阈值 → 调 `indexing.apply_suggestions(object_code, only_high=True)`（后台，不阻塞问答）。
2. **索引就绪度提示**：对象查询路径若走了未建索引的过滤字段，在 `evidence` 里给"建议建索引"提示（温和，不拦）。
3. **实例图规模**：`POST /ontology/instance/graph` 现 150 节点上限 → 改**分页/懒加载**（每页 N 节点 + "继续扩展"），不改一次性总量语义。
4. （可选）高频对象类型的聚合 → 物化视图（仅当实测有性能问题再上，**不预设**）。

**验收**
1. 连续问同一对象超阈值 → 该对象主键/常用过滤字段自动出现 ready 索引。
2. 自动建索引失败不阻断问答。
3. 实例图能分页扩展，不在 150 处静默截断。

### T4 — 流式对象查询（`ask_stream`）

> P0 为控范围未改流式；P1 补齐，保证两条路径体验一致。

1. `ask_stream()` 头部（`meta` 之后）插入对象查询判定：
   - 能出合法 IR → 产出 `type="ir"`（IR 内容）→ `type="sql_delta"`/`type="result"` 复用现有事件 → `done`，`path="object"`；
   - 不能 → 落到现有流式 NL2SQL。
2. `ask_stream` 签名增 `object_code/object_key`（上下文）。

**验收**
1. 流式提问命中对象查询 → 前端收到 `ir` 事件并可折叠展示。
2. 未命中 → 流式行为与现状**逐位一致**。

---

## 3. 关键约定

1. **每个能力独立开关**：`object_context_enabled`（上下文注入）、`auto_chart_enabled`（出图）、`auto_index_enabled`（自动索引）——**均默认关**，A/B 后才开。
2. **上下文是确定性注入**，不交给 LLM 决定是否检索（对齐 Palantir）。
3. **不阻断**：上下文取不到、建索引失败、出图推断失败 → 全部静默降级，不影响答案。
4. **复用**：索引用 `indexing.py` 现成函数；图表用项目已有 `vue-echarts`。

---

## 4. 验收标准（P1 整体）

| # | 验收项 | 方法 |
|---|---|---|
| 1 | 关闭全部新开关时零影响 | `pytest tests/test_query*.py` 全绿 |
| 2 | 对象上下文注入生效且不阻断 | 单测（打桩 LLM） |
| 3 | 自动出图类型正确 | `test_query_object_context.py` 图表推断断言 |
| 4 | 自动索引不阻断问答 | e2e：建索引失败仍正常返回 |
| 5 | 流式两条路径 | e2e：`ir` 事件 / 降级路径 |
| 6 | 前端可解释 + 视觉一致 | Playwright 截图读图核对 |
| 7 | 提交前全量 | `uv run pytest -q -n 4` 全绿 |

---

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| 自动建索引锁表 / 拖慢 | 后台异步、仅 high 优先级、失败不阻断 |
| 出图推断错导致误导 | 默认折叠为表格；图类型附 `reason`；可切换 |
| 上下文注入增加 token | 上下文块**截断**（只带关键属性 + 关系计数） |
| 流式改造回归 | 未命中路径必须与现状逐位一致（回归测试守住） |

---

## 6. 明确不做（P1 范围外）

- 多方言（G6）、多轮重写（G7）→ P2
- 多跳 / 集合级 traverse 聚合 → P3
- 独立对象存储服务（Palantir Object DB / Funnel 双轨）→ 始终不做（`object_query_exec.py` 走实例层）

---

## ✅ P1 完成记录（2026-10-14）

> ⚠️ **范围调整**：使用方要求「自动出图先不着急」→ **T2（G5 出图）本轮不做**。
> 本轮完成 **T1（G3 上下文注入）+ T3（G4 自动建索引/规模）+ T4（ask_stream 对象查询）**。

### 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `query/schema.py` | 改 | `QueryAskRequest` 增 `object_code` / `object_key` |
| `query/controller.py` | 改 | `ask` / `ask_stream` 透传当前对象；`/eval/report` 增 `by_path` |
| `query/service.py` | 改 | `_OBJECT_CTX`（ContextVar）+ `_object_context_block` + `_object_spec_for`（重构）+ `_maybe_auto_index` / `_auto_index` + `_ir_runtime`；`ask`/`ask_stream` 增上下文参数与流式对象查询分支 |
| `assistant/tools.py` | 改 | 增 `QUERY_OBJECT_CONTEXT`，`ai_query` 读取 |
| `query/eval_metrics.py` | 改 | 增 `object_rate` |
| `frontend/.../query/index.vue` | 改 | 「当前对象」横幅（可关闭）+ 设置面板增两项（含文本类型）+ 上下文随请求下发 |
| `frontend/.../api/module_ai/query.ts` | 改 | `queryAsk` 收 `object_code` / `object_key` |
| `frontend/.../ontology/components/OntInstanceExplorer.vue` | 改 | 实例行「问数」按钮 → 带 `object_code/object_key` 跳问数 |
| `tests/test_query_object_e2e.py` | 改 | +8 例：上下文注入、参数透传、流式 ir 事件、自动建索引（含失败回滚） |
| `tests/test_query_object.py` | 改 | +1 例：单对象详情**隐藏凭证列** |

### 验收实测

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 全部新能力默认关时零影响 | ✅ `-k query` **300 passed, 1 skipped** |
| 2 | 当前对象上下文注入生效 | ✅ 真机：`object_code=video_cameras, object_key=1` + 「它现在什么状态」→ `path=object`、IR 里被**自动补上** `"object_key":"1"` |
| 3 | 上下文取不到不阻断 | ✅ 单测：无 code / 不存在的对象 → 空串 |
| 4 | 流式对象查询 | ✅ 单测：`meta → ir → result → done`（`path=object`） |
| 5 | 自动建索引按阈值触发且只建一次 | ✅ 单测：阈值前不触发、达阈值触发、后续不重复；**失败回滚占位**可重试 |
| 6 | 实例图规模 | ✅ 复核：`instance_graph` 已有 `truncated` 标志（cap 400）并在 `msg` 里说明，**无需改** |
| 7 | 前端可解释 + 无报错 | ✅ 浏览器实测：横幅渲染、设置面板新项齐全、**控制台无报错** |
| 8 | 类型检查 | ✅ `module_ai` 0 错误（13 条既有问题不在本模块） |

### 期间发现并修复的缺陷（3 条，均非计划内）

1. **凭证列进了聊天答案**：单对象详情返回了 `password` / `username` / rtsp 地址等，且会**落进 `ai_query_messages.rows`（会话历史）**。修：`get` 分支复用本体既有的敏感名启发式（与写回白名单同源）过滤，并在 `note` 里说明隐藏了哪些列。
2. **`TimeoutError` 的 `str()` 是空串** → 日志只有「IR 生成失败 」，完全看不出是超时（实测排查了半天）。修：日志打**异常类型**。
3. **IR 超时设置过紧**：先设 30s 导致频繁降级；改回 60s。

### 关键实测数据：**agno 包装让 IR 调用严重变慢**（重要，供后续决策）

同一提示词、同一模型（`LLM-284B-MXFP4`）的对照：

| 调用方式 | 耗时 |
|---|---|
| 裸 `AsyncOpenAI` | **11 ~ 19s** |
| 经 agno `Agent.arun` | **29 ~ 65s**（长尾 >60s → 超时降级） |

这与 `_nl2sql` 注释里记载的「agno 内部还可能重试/多段请求」一致。

**不同模型的 IR 耗时**（均经 agno）：

| 模型 | 耗时 |
|---|---|
| `deepseek-v4.1-flash` | **≈4.4s** |
| `LLM-27B-FP8` | **≈8.9s** |
| `LLM-284B-MXFP4`（默认） | **≈29.4s**（长尾 >60s） |

**因此新增了 `object_query_model` 设置**（留空 = 与 NL2SQL 同源；可填模型名或 id）。
实测指定 `LLM-27B-FP8` → **15s 内命中 `path=object`**（对比 284B 的 86s 降级）。

### 偏离与待办（如实标注）

- **`object_query_model` 已还原为空**（= 默认 284B），按使用方「模型就用 LLM-284B-MXFP4」的要求。
  ⚠️ 但实测 284B 下本功能**不稳定**（29s 均值、长尾 >60s 会降级），建议在「问数设置 → 对象查询 · IR 模型」里填 `LLM-27B-FP8`。
- **`object_query_auto_index_enabled` 默认关**，未在真机上跑到阈值 20 次，仅单测覆盖。
- **自动出图（G5）未做**（使用方要求暂缓）。
- **实例图分页/懒加载未做**：复核发现 `truncated` 已具备、cap 到 400，判定当前无需改。
- `_allowed_objects_for_query` 对每个候选对象调用 `_instance_meta`（含反射），实测占 ~10s —— 有优化空间（未做）。
