# 问数评测模块（Eval）设计

- 日期：2026-10-11
- 状态：**待评审**
- 范围：测试集维护 + 执行/进度 + 路径观测 + 分维度报表 + 消融测试 + 前端页面

## 一、背景与目标

现在只有「跑基准」的一键脚本（`benchmark.py` + `benchmark_runner.py`：`POST /benchmark/run`、
`GET /benchmark/status`），题集写死在代码里（20 快 + 98 慢），**无法维护、无维度、
看不到路径、不能消融**。

**目标**：把评测做成一个**可维护、可观测、可消融**的模块：

1. **测试集持久化**：100 题（难度/场景/形式/数据源 + 金标 SQL），可增删改、可批量导入。
2. **执行与进度**：后台跑，前端看到进度（done/total）、当前题、逐题状态。
3. **路径观测**：每题记录 **走哪条路（fast/slow）、命中哪个指标、召回哪些表、
   用到哪些本体表、生成的 SQL、耗时、重试/自纠错、工具调用**。
4. **结果与维度**：数据精度 / 语义精度 / 快路径命中率 / 召回命中率(Recall@k) /
   平均·P50·P95 耗时，并**按难度/场景/形式分组**。
5. **消融测试**：同一题集在 8 个开关的不同组合下跑，输出**对照表 + 增量**，
   回答「本体 / 召回 / KG / few-shot / 工具化 Agent 各值多少」。

## 二、现状（可复用 vs 缺口）

| 已有 | 位置 |
|---|---|
| 后台运行 + 进度模式（`_RUNS` 字典 + status 轮询） | `query/benchmark_runner.py` |
| 题集与宽松比对（结果数据级） | `query/benchmark.py`（`GOLDEN` / `NL2SQL_GOLDEN` / `lenient_match`） |
| 召回评测 Recall@k | `query/recall_eval.py` |
| **路径信息已在 ask 返回体里** | `path` / `metric` / `retrieved` / `ontology_used` / `sql` / `took_ms` / `cached` / `is_error`（`service.py:5563,5873,7026`） |
| 配置开关（可直接做消融维度） | `ai_query_settings`：`recall_enabled` / `agno_semantic_enabled` / `kg_enabled` / `agno_tool_agent` / `decomposed_planning` / `empty_self_correct` / `fewshot_auto_curate` / `enum_hint_enabled` |

**缺口**：题集不可维护、无维度与分组、无逐题 trace 落库、无消融、无前端页面。

## 三、数据模型

### 3.1 `ai_query_testcase`（测试集，可维护）

| 列 | 说明 |
|---|---|
| `question` | 问题文本 |
| `gold_sql` | 金标 SQL（数据级比对的基准） |
| `datasource` | `system` / `ds:4` |
| `difficulty` | `简单` / `中等` / `困难` |
| `scenario` | 安防 / 训练 / 模型调用 / 标注 / 用户 / 燃煤采购 / 化验 / 皮带 / 运输 / 掺配 … |
| `form` | 单维统计 / 多维报表 / 联表 / 时间窗口 / 占比 / 排名TopN / 窗口函数 / 去重 / 嵌套子查询 / 快路径指标 / 业务黑话 |
| `expected_metric` | 期望命中的指标 key（快路径题；可空） |
| `tags` | jsonb |
| `verified` / `last_verified_at` / `notes` | 金标是否执行通过 + 时间 + 备注 |
| `enabled` / 审计字段 | 与其他表一致 |

唯一键：`(datasource, question)`。

### 3.2 `ai_query_testrun`（一次运行）

`run_id` / `mode`(`full`|`filter`|`ablation`) / `filter`(jsonb) / `config`(jsonb，覆盖的开关)
/ `status`(`running`|`done`|`error`) / `total` / `done` / `started_at` / `finished_at`
/ `summary`(jsonb，聚合指标) / `ablation_group`(varchar，消融组名)。

### 3.3 `ai_query_testresult`（逐题结果 + 路径 trace）

`run_id` / `testcase_id` / `question` / `ok` / `is_error` / `path`(fast|slow)
/ `metric_key` / `sql` / `n_rows` / `took_ms` / `gold_match`(bool)
/ `recall_hit`(jsonb: `{expected_tables, recalled, hit}`) / `ontology_used`(jsonb)
/ `tool_calls`(jsonb) / `retries`(int) / `trace`(jsonb，原始 `ask` 返回的关键字段)。

## 四、题目生成与校验（100 题）

1. 取每张候选表的 schema（表名/中文名/关键字段中文名）+ 该源指标 + 术语 + 本体别名，
   按 **难度/场景/形式** 分批让 LLM 产出 `[{question, gold_sql, difficulty, scenario, form}]`。
2. **执行校验**：`gold_sql` 在对应数据源上实际执行（system 走本地、`ds:4` 走连接器）：
   - 执行成功且 `行数 > 0` → `verified=true` 收录；
   - 失败或空 → 丢弃（记录原因，不入集）。
3. 目标规模：**100 题**（系统库 ~55 + 燃煤库 ~45），三档难度与多形式覆盖；
   生成到够数为止（分轮次 + 去重）。
4. 输出报告：各维度题数分布 + 校验通过率。

## 五、执行器与进度

- `POST /ai/query/eval/run`：按 `filter`（数据源/难度/场景/形式/标签）选题 → 建 run →
  **后台任务**逐题执行（复用 `AiQueryService.ask`），实况写 `ai_query_testresult` 并更新
  `done`；`GET /ai/query/eval/status?run_id=` 返回进度与当前题。
- 每题记录 trace（见 3.3），包含 `path`/`metric`/`retrieved`/`ontology_used`/`sql`/
  `took_ms`/`retries`/`tool_calls`。
- 数据级精度沿用 `lenient_match`（与金标结果比对）。

## 六、指标与分维度报表

- 总览指标（口径明确）：
  - **数据精度**：`lenient_match(金标结果, 实际结果)` 且非错误 → 占总题数比例。
  - **语义精度**：带 `expected_metric` 的题中，实际 `metric_key` == 期望的比例
    （不带期望的题不计入分母）。
  - **快路径命中率**：`path == "fast"` 的比例。
  - **Recall@k**：从 `gold_sql` 抽表作为 ground truth，看实际 `retrieved` 命中比例；**k 取 8**
    （与 `recall_eval.py` 默认一致，可配）。
  - **耗时**：平均 / P50 / P95（ms）；另给错误率与超时率。
- **分组**：按 `difficulty` / `scenario` / `form` / `datasource` 输出「题数 / 正确数 / 精度」。
- `GET /ai/query/eval/report?run_id=` 返回总览 + 分组 + 逐题明细（含 trace）。

## 七、消融测试

- 维度（8 个开关，逐个「关掉 vs 全开」对照）：`recall_enabled`、`agno_semantic_enabled`、
  `kg_enabled`、`agno_tool_agent`、`decomposed_planning`、`empty_self_correct`、
  `fewshot_auto_curate`、`enum_hint_enabled`。
- 实现：临时覆盖 `ai_query_settings`（并清 `_SETTINGS_CACHE`）→ 跑一轮 → **恢复**；
  因配置是全局的，**消融必须串行**（一组跑完再跑下一组），避免互相污染。
- 输出：`{组名: 指标}` 对照表 + 相对基线的**增量**（精度/耗时/召回）。

## 八、接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET/POST/PUT/DELETE | `/ai/query/eval/cases` | 测试集 CRUD（含批量导入/启用停用） |
| POST | `/ai/query/eval/generate` | LLM 生成 + 校验（后台，返回 run_id 复用 status） |
| POST | `/ai/query/eval/run` | 启动一轮 |
| GET | `/ai/query/eval/status?run_id=` | 进度 |
| GET | `/ai/query/eval/report?run_id=` | 结果 + 分组 + 逐题 trace |
| POST | `/ai/query/eval/ablation` | 启动消融（串行多组） |
| GET | `/ai/query/eval/runs` | 历史运行列表 |

## 九、前端页面

`/ai/eval`（与既有页面同风格：Element Plus 原生组件、`--el-*`、单根、无自造样式）：

1. **测试集**：表格（问题/数据源/难度/场景/形式/校验状态）+ 搜索筛选 + 新增/编辑弹窗 +
   批量导入 + 「生成 100 题」按钮。
2. **运行**：筛选器 + 运行按钮 + **进度条**（done/total + 当前题）+ 逐题状态表（局部刷新，不整表重拉）。
3. **结果**：指标卡片（`el-statistic`）+ 分维度表 + 逐题明细（可展开看 trace：路径/指标/召回表/本体表/SQL）。
4. **消融**：对照表（组名 × 指标）+ 增量列。

## 十、验收标准

- **100 题**入库：`verified=true` 占比 ≥ 90%，且系统库/燃煤库两源都覆盖。
- 一轮「全量」运行：界面能看到进度 → 结果 → 逐题 trace；
  报表给出总览 + 至少 3 个维度的分组。
- **消融**：至少 3 组（全开 + 关召回 + 关本体）产出对照表与增量。
- 单测：测试集 CRUD、金标表抽取（Recall@k）、消融配置覆盖**与恢复**、分组聚合。
- 回归：全量 pytest 不新增失败；改动文件 ruff 干净。

## 十一、分阶段

1. 数据模型 + 测试集 CRUD + LLM 生成与校验 → **100 题落库**。
2. 执行器 + 进度 + trace + 报表。
3. 消融（8 开关串行对照）。
4. 前端页面。
5. （可选）把 `benchmark.py` 的题集迁移进测试集表，旧接口保留兼容。

## 十二、风险与边界

| 风险 | 缓解 |
|---|---|
| LLM 生成的金标 SQL 错/不可执行 | **强制执行校验**，不过不入集；保留 `verified` 标记 |
| 100 题生成耗时/成本 | 分轮次 + 批量提示；执行校验便宜（无 LLM） |
| 消融串行耗时长 | 支持按 `filter` 缩小（如只跑 30 题）先看趋势 |
| 配置全局污染 | 每组跑完**恢复**原配置并清缓存；单测覆盖恢复逻辑 |
| 与既有 benchmark 重复 | 复用 `lenient_match`/`ask`，旧脚本保留；阶段 5 再合并 |

**不做**：不做多轮对话式评测；不做模型间横向对比（本轮只评测问数管线本身）；
不改 `ask`/`stream` 的对外行为。
