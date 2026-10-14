# 智能问数「语义执行层」P2 实施计划

> 依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.9、§4
> 前置：**P0/P1 已上线**（对象查询 + 上下文 + 出图 + 索引）
> 范围：G6 多方言（SQL 层）+ G7 多轮查询重写
> 纪律：两项独立开关、默认关、A/B 后开

---

## 0. 开工前取证（已核实）

| 事项 | 事实 | 位置 |
|---|---|---|
| 系统提示词**硬编码 PostgreSQL** | `"你是 PostgreSQL 数据库查询助手…（日期用 CURRENT_DATE / date_trunc，别用 CURDATE）"` | `query/service.py:6019`（`_nl2sql`）、`service.py:6169`（`ask_stream`） |
| 自定义数据源大写标识符提示 | 对 `FUEL_*` 类数据源追加"必须双引号引用"说明 | `query/service.py:7322` |
| 数据源类型 | `AiQueryDatasourceModel.type`：`postgres/mysql/sqlite/file/api` | `query/model.py:11` |
| 自定义源执行 | `_execute_custom_ds_sql(ds_id, sql, auth)` / `_ds_schema_map(datasource)` | `query/service.py` |
| 连接与方言 | `build_engine()` / `_dialect()` / `execute_select()` | `query/executor.py`、`ontology/service.py` |
| SQL 校验 | `validate_sql(sql, allowed, question)`（禁 DDL/DML/多语句 + 白名单） | `query/service.py` |
| 会话消息 | `AiQueryMessageModel`（含 `question / sql / summary / path / datasource`）；`list_messages(session_id)` | `query/model.py:219`、`service.py` |
| **当前未用多轮历史生成** | `_nl2sql` 的 `user_msg = question`（+ `prev_error`），**没有带上一轮问句/SQL** | `query/service.py:6026` |
| 对象查询 IR 生成 | `_object_query_path()`（P0 新增） | `query/service.py` |

---

## 1. 交付物清单

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| 1 | `backend/app/plugin/module_ai/query/dialect.py` | 新增 | 方言提示词模板（pg / mysql / sqlite）+ 由 `datasource.type` 解析（纯逻辑） |
| 2 | `backend/app/plugin/module_ai/query/service.py` | 改 | `_nl2sql` / `ask_stream` 用 `dialect.py` 生成 system_prompt；增多轮重写 |
| 3 | `backend/app/plugin/module_ai/query/rewrite.py` | 新增 | 多轮查询重写（仿 SuperSonic `QueryRewritingStrategy`）：历史 → 完整问题（纯逻辑 + 一次 LLM 调用封装） |
| 4 | `backend/tests/test_query_dialect.py` | 新增 | 方言提示词选择/外部源（mysql/sqlite）断言 |
| 5 | `backend/tests/test_query_rewrite.py` | 新增 | 重写触发条件 / 降级 / 不越权 |

---

## 2. 任务分解

### T1 — 多方言（G6）

**目标**：把"PostgreSQL 专用提示词"改为**按数据源方言参数化**，让自定义 MySQL/SQLite 源也能正确生成 SQL。

1. `query/dialect.py`（纯逻辑）：

   ```python
   DIALECTS = {
     "postgres": {
       "name": "PostgreSQL",
       "rules": ["日期用 CURRENT_DATE / date_trunc / INTERVAL，别用 CURDATE/NOW(3)",
                 "字符串拼接用 ||", "分页用 LIMIT n OFFSET m",
                 "标识符大小写敏感时用双引号"],
     },
     "mysql": {
       "name": "MySQL",
       "rules": ["日期用 CURDATE() / DATE_FORMAT / DATE_SUB，别用 date_trunc",
                 "字符串拼接用 CONCAT()", "分页用 LIMIT n OFFSET m",
                 "标识符用反引号包裹"],
     },
     "sqlite": {
       "name": "SQLite",
       "rules": ["日期用 date('now') / strftime，不要用 CURRENT_DATE 的函数式写法",
                 "字符串拼接用 ||", "分页用 LIMIT n OFFSET m",
                 "无 date_trunc；按需用 strftime 或 substr 截断"],
     },
   }

   def resolve_dialect(datasource_type: str) -> dict:   # 未知类型 → 回退 postgres
   def build_system_prompt(dialect: dict, rules: list[str], schema_ctx: str, extra: str = "") -> str:
   ```

2. `_nl2sql` / `ask_stream`：`system_prompt = build_system_prompt(resolve_dialect(ds_type), ...)`，替换硬编码串。
   - `ds_type` 从数据源解析：`system` → postgres；`ds:{id}` → `AiQueryDatasourceModel.type`；`file/api` → 回退 postgres 并提示"该源为模板化数据，请用标准 SQL"。
3. **保留**现有"大写标识符需双引号"的特例补充（`service.py:7322`），按方言并入。
4. `validate_sql` 的白名单/只读校验**不改**（跨方言通用）。

**验收**
1. 系统数据源 → 提示词含 PostgreSQL 规则（回归不变）。
2. `mysql` 源 → 提示词含 `CURDATE()` / `CONCAT()` / 反引号；**不含** `date_trunc`。
3. `sqlite` 源 → 含 `strftime`；不含 `date_trunc`/`CURDATE`。
4. 未知类型 → 回退 PostgreSQL，不报错。

### T2 — 多轮查询重写（G7）

**目标**：仿 SuperSonic `NL2SQLParser` 的 query rewriting——把"那上周呢 / 换成华东呢"重写成**自包含**的问题，再交给生成。

1. `query/rewrite.py`：

   ```python
   REWRITE_RULES = ("保留实体/指标/维度/取值/时间范围；只输出重写后的问题，不要解释")

   def needs_rewrite(question: str, history: list[dict]) -> bool:
       """仅当"当前问题看起来不自包含"且"有历史"时才重写：
          - 疑问代词/指代：这、那、它、上面、刚才、换成、改成、还有、呢
          - 或极短句（<= 6 字）
          - 无历史 → False（省钱、避免无谓调用）"""

   def build_rewrite_prompt(question, history: list[dict]) -> str:
       """history = [{question, sql, datasource}]（取最近 N 轮，N=2"""
   ```

2. `_nl2sql`（及 `ask` 主入口）：若 `needs_rewrite` → 一次 LLM 调用得 `rewritten`；**校验**：
   - 结果为空 / 与原文相同 / 超长 → 用原问题（降级）；
   - 重写后的问题**重新走一遍路由**（可能命中指标快路径或对象查询）——避免"重写后直接进 NL2SQL"。
3. **历史来源**：`_load_recent(session_id, n=2)` 读 `AiQueryMessageModel`（`question` + `sql`），只取**成功**的消息。
4. **越权防护**：重写不得引入用户无权访问的对象/表；重写后仍走 `_allowed_for_user` + 对象白名单校验。

**验收**
1. "那上周呢"（有历史）→ 重写为自包含问题；无历史 → 不重写。
2. 重写失败/超长 → 用原问题（不降级答案质量）。
3. 重写后能命中指标快路径或对象查询（不是硬进 NL2SQL）。
4. 重写不产生越权对象。

---

## 3. 关键约定

1. **开关**：`multi_dialect_enabled`（默认 `true`，因为只是把硬编码参数化，风险低）、`query_rewrite_enabled`（默认 `false`，需 A/B）。
2. **降级**：方言未知 → postgres；重写失败 → 原问题。
3. **重写后重走路由**，不要直接进 NL2SQL（否则会绕过 P0 的对象查询收益）。
4. **成本控制**：`needs_rewrite` 严格判定，避免每轮都多一次 LLM 调用（对齐本项目"多一次 LLM 调用要证明值"的纪律）。

---

## 4. 验收标准（P2 整体）

| # | 验收项 | 方法 |
|---|---|---|
| 1 | 方言提示词按源切换 | `test_query_dialect.py` |
| 2 | 系统源行为不变 | 回归 `tests/test_query*.py` |
| 3 | 重写触发条件严格 | `test_query_rewrite.py`：`needs_rewrite` 正反例 |
| 4 | 重写后重走路由 | e2e：重写结果命中对象查询 |
| 5 | 关闭 `query_rewrite_enabled` 时零影响 | 回归全绿 |
| 6 | 提交前全量 | `uv run pytest -q -n 4` |

---

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| 方言规则写错 → 生成的 SQL 更差 | 先只做 pg/mysql/sqlite 三档；每个档位带 A/B |
| 重写引入幻觉/越权 | 重写后仍走全部校验（白名单/权限/对象词表） |
| 每轮多一次 LLM → 变慢 | `needs_rewrite` 严格；仅在"看起来不自包含"时触发 |
| 重写改变原意 | 结果与原文相同/空 → 用原问题 |

---

## 6. 明确不做（P2 范围外）

- 完整 SQL transpile（WrenAI 式 sqlglot 方言转换）——本项目只做**提示词级方言适配**，不做 AST 级 transpile
- 多跳 traverse → P3
- 微调路线 → 始终不做
