# 问数权限模型重构——统一策略引擎 + SQL 收口 设计稿

> 日期：2026-11-06
> 范围：`backend/app/plugin/module_ai/query/` + `backend/app/plugin/module_ai/ontology/security.py`
> 状态：设计待评审（未动代码）

## 1. 背景

### 1.1 现状（2026-11-06 代码核查）

问数链路的权限由**三套互不相通的机制**拼成，判定发生在两个不同的地方：

| 层 | 现有实现 | 判定位置 |
|---|---|---|
| 表 | `ai_query_assets.included`（全局白名单）+ 数据域成员表 + `ai_access_rule`（角色→`allowed_tables`） | `_allowed_for_user()` → `validate_sql()`
| 列 | `ai_query_asset_columns.sensitive` | `_ont_sql_violations()`
| 行 | 无 | ——
| 行（仅本体对象） | `ai_ont_row_policy` + `visible_properties()` | `ontology/security.py` → `object_exec.py`

### 1.2 已确认的缺陷（均有代码或实验支撑）

1. **`SELECT *` 绕过列级 ACL**（安全漏洞）。
   `_sql_query_scope()` 用 `sqlglot` 取 `exp.Column`，而 `select * from t` 解析出 `columns=[]`
   （实测：`t.*` 得到名为 `*` 的列），`_ont_sql_violations()` 里 `c in cols` 永远不命中 →
   敏感列随结果返回。`validate_sql()` 不禁止 `*`。
2. **行级策略只作用于对象查询**。`filter_instances()` 的调用点只有 `ontology/service.py`
   与 `query/object_exec.py`；自由 SQL（ask / agent / 报表）不注入任何行过滤。
   同一份数据，两个入口给出不同结果。
3. **默认放行**。`_allowed_for_user()` 在"没有数据域、也没有 ABAC 规则"时 `return base`
   （全表）；而 `_can_see_sensitive(None)` 又返回 False —— 半开半关。
4. **异步执行没有主体**。多处 `auth=None`（评测、导出、委托执行），落到
   `_allowed_for_user(None)` 就是全表白名单。
5. **生成前上下文不裁剪**。`_build_schema_context()` 使用 `_system_schema()`（全局），
   模型能看到用户无权查询的表/列，生成后才被拒，界面表现为"问完才报无权限"。
6. **判定分散、规则不同**。表级与列级各自实现，优先级隐式（域 > ABAC > 资产白名单）。
7. **派生资产不复核**。报表、指标、评测金标、查询缓存、会话历史保存的是结果文本，
   换主体打开不会按新主体重判。
8. **无审计、无解释**。`security_audit()` 只是看板评分，拒绝不落库。
9. **只有一个数据库账号**。连接外部库用的是服务账号，借不到 PG/MySQL 自身的 RLS，
   所有执行期兜底**只能靠应用层改写 SQL**。

### 1.3 外部参照

- **Palantir**：object/property security policies 覆盖 cell-level（对象=行、属性=列）；
  另有 data source policies（数据集权限 / restricted views 做行级 / MDO 做列级）。
  关键边界：粒度行列控制是 **read-time only**，不传播到下游与导出；要传播必须挂 **marking**。
- **Snowflake Cortex Analyst**：生成的 SQL **以调用者 role 执行**；语义模型里未定义的表列
  模型根本看不到；行访问策略 / 掩码策略在执行期兜底。
- **Databricks Genie**：按每个用户的 Unity Catalog 权限执行；row filter / column mask；
  新版本支持按请求属性的 ABAC。
- 共性：① 执行引擎兜底，不靠模型自觉；② 生成前上下文按权限裁剪；
  ③ 表/行/列分层，列可"脱敏"而非仅拒绝；④ 默认拒绝 + 可解释 + 审计。

### 1.4 结论

只补"行级策略下推"（方案一）是**必要但不充分**：它关闭最危险的语义断层，但默认放行、
`*` 绕过、异步身份、派生资产、审计仍然存在。本设计采纳**统一模型**，并把方案一作为
其中的一个阶段交付。

## 2. 目标与非目标

### 2.1 目标

1. **单一真相**：一处定义策略，所有入口（问数、智能体、应用、工作流、定时任务、报表、
   指标、对象查询、导出、评测）使用同一套判定。
2. **默认拒绝**：没有显式 allow 的表/列不可查；不可判定时一律拒绝（fail-closed）。
3. **行级可执行**：策略表达式编译成 SQL 谓词，在基表引用处生效（单表 / join / 聚合 /
   子查询 / CTE / union 都覆盖），不依赖提示词。
4. **列级可脱敏**：除 allow/deny 外支持 mask（部分掩码 / 空值替换 / 取整），
   `SELECT *` 展开后逐列判定。
5. **上下文裁剪**：生成前只提供有权表列，并在提示词中声明约束，减少"生成完才被拒"。
6. **可解释、可审计**：每次判定落库（谁、哪个入口、什么 SQL、放/拒、哪条策略、为什么），
   提供 explain 接口与治理看板。
7. **派生资产不越权**：报表、指标、评测、缓存按阅读者重判；缓存按主体分桶。

### 2.2 非目标（YAGNI）

- 不做多租户隔离（Principal 保留 `attrs` 扩展位，将来加不推翻模型）。
- 不做 purpose-based access control（用途约束）。
- 不依赖数据库引擎的 RLS / 列加密（服务账号模型下不可用）。
- 不做行级**写**权限：写回仍走本体 action 权限（`check_action_allowed`）。
- 不做跨库联邦查询的权限推导。

## 3. 概念模型

```
Principal（主体）
  user_id, is_superuser, roles[], attrs{dept_id, mine_id, ...}, entry

Resource（资源）
  datasource | table | view | object | column

Policy（策略）
  effect: allow | deny | mask
  subject: everyone | role:<code> | user:<id> | attr:<name> == <value>
  resource: 表/视图/对象（+ 可选列清单）
  condition: 行级表达式（仅 allow 用）
  mask_expr: 掩码表达式（仅 mask 用）
  marking: 可选标记名（用于下游传播）

Decision
  permit | deny(reason, policy_ids) | rewrite(sql, applied[])
```

### 3.1 两类策略，两种传播语义（取自 Palantir 的教训）

| 类别 | 例子 | 生效范围 | 是否传播到派生/导出 |
|---|---|---|---|
| **读时过滤**（granular） | 行策略、列 allow/deny/mask | 查询期 | **否**（必须显式处理导出） |
| **标记**（marking） | `sensitive`、`PHI` | 全链路 | **是**（报表/指标/导出/血缘继承） |

迁移时把现有 `sensitive` 列标记归入 marking 类，以保证导出路径不会绕过。

### 3.2 优先级（显式，不再隐式）

1. `deny` 永远优先于 `mask`，`mask` 优先于 `allow`。
2. 同一 effect 内：主体具体性 `user > attr > role > everyone`。
3. 同具体性按 `priority` 降序；仍并列则取更严格者。
4. 超级管理员绕过一切策略，但**每次绕过都记审计**。
5. 无任何 `allow` 覆盖 → 拒绝（默认拒绝）。

## 4. 数据模型

新表（启动幂等建表，沿用 `_ensure_query_tables` 的方式，不走 alembic autogenerate）：

```sql
CREATE TABLE ai_policy (
  id            BIGSERIAL PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  description   VARCHAR(255) DEFAULT '',
  enabled       BOOLEAN NOT NULL DEFAULT true,
  priority      INTEGER NOT NULL DEFAULT 100,
  resource_kind VARCHAR(16)  NOT NULL,      -- table | view | object | datasource
  resource_code VARCHAR(160) NOT NULL,      -- 表名 / 视图名 / 对象码
  effect        VARCHAR(8)   NOT NULL,      -- allow | deny | mask
  subject_kind  VARCHAR(16)  NOT NULL,      -- everyone | role | user | attr | domain
  subject_value VARCHAR(160) DEFAULT '',    -- 角色码 / 用户 id / 属性表达式 / 数据域 code
  condition     TEXT         DEFAULT '',    -- 行级表达式（allow）
  columns       JSONB        DEFAULT '[]',  -- 列清单；空 = 整表
  mask_expr     TEXT         DEFAULT '',    -- 掩码表达式（mask）
  marking       VARCHAR(60)  DEFAULT '',    -- 标记名（传播用）
  created_time  TIMESTAMP DEFAULT now(),
  updated_time  TIMESTAMP DEFAULT now(),
  is_deleted    BOOLEAN DEFAULT false
);
```

审计表：

```sql
CREATE TABLE ai_query_access_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     INTEGER,
  entry       VARCHAR(32),        -- ask|agent|app|workflow|cron|report|metric|object|export|eval
  datasource  VARCHAR(120),
  sql_hash    CHAR(64),
  sql_preview TEXT,               -- 截断 2KB，敏感字面量打码
  decision    VARCHAR(8),         -- permit | deny
  reason      VARCHAR(255),
  policy_ids  JSONB DEFAULT '[]',
  rewrite     JSONB DEFAULT '[]', -- 实际施加的改写（行/列/掩码）
  elapsed_ms  INTEGER,
  created_time TIMESTAMP DEFAULT now()
);
```

### 4.1 旧数据迁移（幂等 backfill）

| 旧机制 | 迁移为 |
|---|---|
| `ai_query_assets.included=false` 的表 | 不迁移（这是"目录是否对外"，不是权限） |
| `ai_data_domain.tables` + 成员 | 一条 `allow`，`subject_kind=domain`、`subject_value=<域 code>`（成员关系仍由域本身维护，策略只引用） |
| `ai_access_rule.allowed_tables` | `allow`（subject=`role:<value>`），`sensitive_ok` → 列 `mask`/`allow` 策略 |
| `ai_query_asset_columns.sensitive` | `deny` 列策略 + `marking=sensitive` |
| `ai_ont_row_policy` | `allow` 行策略（`condition` 原样搬迁，表达式语法对齐） |

迁移器写入 `ai_policy_migration` 记录（旧表 → 新策略 id），重复执行不产生重复策略。
旧表保留只读，直到 `POLICY_ENGINE=enforce` 稳定后再下线。

## 5. SQL 编译（核心）

### 5.1 处理流程

```
parse(sqlglot) → 解析表/列/CTE/子查询
   → 表级判定（allow/deny；视图按血缘展开到基表）
   → 行策略包装（每个基表引用）
   → 列投影改写（* 展开 → 逐列判定 → mask）
   → 重新生成 SQL（保留参数绑定）
   → 无法解析 / 未知函数 / 动态 SQL → deny(fail-closed)
```

### 5.2 行策略

- 表达式限定安全子集：`= != > >= < <= IN LIKE IS NULL AND OR NOT 括号`，右侧可为
  字面量或 `$user.id / $role.* / $attr.<name>`；**禁止子查询、函数调用、字符串拼接**。
- 编译：表引用 `FROM t AS x` 改写为 `FROM (SELECT * FROM t WHERE <pred>) AS x`。
  join / 子查询 / CTE 内的引用同样处理。
- 属性缺失（如用户没有 `mine_id`）→ 视为条件不成立 → 该表 deny，不是忽略条件。
- 性能：包装会阻止部分谓词下推；要求被策略覆盖的表在策略列上有索引，
  上线前用 `EXPLAIN` 抽查 3 条典型查询（单表 / join / 聚合）。

### 5.3 列策略

- 先把 `*` / `t.*` 展开为真实列（来自 schema 元数据）；展开失败 → deny。
- 逐列判定：deny → 该列不可出现在投影/条件/排序中；mask → 投影替换为 `mask_expr`
  （白名单函数：`NULLIF`、`LEFT`、`REPLACE`、`ROUND`、`CASE`）。
- 敏感列出现在 `WHERE` / `GROUP BY` / `ORDER BY` 时按 deny 处理（防止"用条件反推值"）。
  `mask` 只作用于**投影**，不代表允许拿它做条件；需要按敏感列筛选时必须单独配置
  `allow` 列策略，并在审计里标注。
- `COUNT(*)` 允许；对敏感列做聚合（`SUM/AVG/MAX/MIN`）默认 deny，可被显式 `mask` 策略放开。

### 5.4 视图与血缘

- 视图引用：用 `ai_query_lineage` 找基表；把基表的行条件按列映射套到视图列上。
- 单层视图在 P2 支持；多层/物化视图在 P5。无法映射 → deny。
- 标记类（`marking`）沿血缘传播；导出/报表继承标记（已在 `lineage.py` 有敏感传播一格，
  此处扩展为通用标记）。

### 5.5 允许清单（防绕过）

- 只允许 `SELECT`；`WITH`（CTE）允许但不允许递归。
- 禁止：`INTO`、`COPY`、`pg_*` 系统表、`information_schema`、外部扩展函数。
- 解析器版本与方言白名单写死；新增方言需补回归用例。

## 6. 上下文投影（生成前）

- `_build_schema_context()` 改为接收 `Principal`：
  只召回该主体有 `allow` 的表与列；`mask` 列以"不可见，需申请"呈现；
  指标/术语/样例同样过滤（指标绑定到无权表 → 不出现）。
- 提示词追加一段确定性约束：
  「你只能查询以下表；涉及行级限制的表系统会自动追加过滤条件，不要试图绕过。」
- 目的：把"生成后被拒"降为"根本不会生成"，同时避免 schema 名称泄露给无权用户。

## 7. 执行网关（唯一收口）

```python
# 所有入口只走这一个函数
decision = await QueryGuard.prepare(sql, principal, entry=...)
if not decision.permit:
    audit(...); raise CustomException(decision.reason)
sql = decision.sql
```

| 入口 | 今日身份 | 改造后 |
|---|---|---|
| `ask` / `ask_stream` | auth | Principal(auth.user) |
| agent 工具 / app 运行 | auth 或 None | 发起者 Principal；无发起者 → deny |
| workflow 节点 | auth 或 None | 同上 |
| cron | None | **owner Principal**（创建者**当前**的权限；创建者停用/删除 → deny），审计标注 `entry=cron` |
| 报表 / 指标渲染 | auth | 阅读者 Principal |
| 导出 / 下载 | auth | 阅读者 + 标记校验 |
| 评测 / 金标执行 | None | 管理员 Principal（`entry=eval`），审计标记 |
| 对象查询 | auth | Principal + 现有对象策略 |

**禁止 `auth=None`**：网关层遇到无主体直接 deny 并记录（`reason="missing principal"`）。

## 8. 审计与解释

- 每次 `prepare()` 写一条 `ai_query_access_log`（放行也写，便于回溯）。
- `GET /ai/query/access/explain?table=&column=&user_id=` 返回判定链：
  命中的策略、被哪条 deny、缺哪个属性、是否 superuser 绕过。
- 治理看板增加两页：拒绝 Top（按用户/表/入口）、策略命中分布。
- 留存期挂到现有清理任务（默认 90 天）。

## 9. 派生资产与缓存

- 查询缓存 key 增加 `scope_hash`（主体 + 策略版本指纹），不同主体不复用结果。
  定义：`sha256(user_id | 排序后的角色码 | 排序后的 attrs | max(ai_policy.updated_time))`，
  策略一改，指纹变化，旧缓存自然失效。
- 报表/指标：渲染时按阅读者重跑 `QueryGuard`（模板 SQL 也要编译），不得直接复存结果。
- 会话历史：本人回放；他人（含管理员）查看时按其自身权限过滤或显示"部分内容不可见"。
- 评测金标：执行时用管理员主体，但**结果只用于评测，不回流给普通用户**。

## 10. 迁移与灰度

开关 `POLICY_ENGINE`：

| 值 | 行为 |
|---|---|
| `legacy` | 完全走旧逻辑（回退用） |
| `shadow`（默认上线值） | 旧逻辑决策生效；新引擎并行判定，差异写 `ai_policy_shadow_diff` |
| `enforce` | 新引擎决策生效，旧逻辑只读 |

灰度顺序：`ask` → `agent/app` → `cron` → `report/metric` → `export`。
每一步的单入口可独立切回 `legacy`。

**默认拒绝的落地靠"祖父条款"**：backfill 把现有域/ABAC 规则转成显式 `allow`，
因此切换瞬间不会锁死现有用户；差异由 shadow 报告逐条确认。

## 11. 阶段与验收

每个阶段单独出一份实施计划、单独评审、单独上线（一份 spec 不拆成一个大 PR）：

- **计划 A（核心）**：P0 止血 + P1 策略模型 + P2 SQL 编译器 —— 做完即具备"默认拒绝 + 行/列可控"的完整能力；
- **计划 B（体验与运维）**：P3 上下文投影 + P4 全入口网关与解释；
- **计划 C（生命周期）**：P5 派生资产、导出、多层视图。

| 阶段 | 交付 | 验收（可测） |
|---|---|---|
| **P0 止血** | ① 含敏感列的表一旦出现 `*` / `t.*` 直接拒绝（保守，P2 再做精确展开）；② `auth=None` 网关拒绝；③ 审计表 + shadow 记录；④ 确认并收紧 `_execute_sql` 旁路（仅超管 + 留痕） | 3 条 exploit SQL（`*`、`t.*`、`COUNT(*)` 变体）被拦；无 `auth=None` 落库为 permit |
| **P1 模型** | `ai_policy` + 判定引擎 + backfill + shadow 对比 | 对最近 500 条真实 SQL 双跑，差异逐条有解释；backfill 幂等 |
| **P2 编译器** | 行包装、列投影、mask、视图单层、fail-closed | 绕过回归集 ≥12 条全拦（star/alias/cte/union/subquery/join/function/view/注释/引号/大小写/动态 SQL）；EXPLAIN 性能抽查通过 |
| **P3 上下文** | schema/指标/术语裁剪 + 提示词约束 | 无权表列不出现在 prompt（自动断言）；生成后拒绝率下降 ≥50% |
| **P4 网关** | 全入口接入 + explain + 看板 | 每个入口各 1 条用例，均能回答"为什么放/拒" |
| **P5 派生** | 报表/指标/缓存分桶、导出标记、多层视图 | 换主体打开同一报表结果一致且不越权；导出按标记拦截 |

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| 行策略包装导致查询变慢 | 策略列建索引；上线前 EXPLAIN 抽查；必要时把谓词合并到外层 WHERE |
| sqlglot 对方言覆盖不足 | fail-closed + 方言白名单 + 回归集；解析失败按 deny 处理 |
| 默认拒绝锁死存量用户 | shadow 双跑 + 祖父条款 backfill + 单入口灰度 |
| 视图/物化视图映射不准 | 先单层、再血缘递归；映射不了直接 deny |
| 掩码表达式被滥用 | 掩码函数白名单；`mask_expr` 只允许由管理员配置，不接收用户输入 |
| 审计表膨胀 | 90 天清理 + `sql_preview` 截断 + 只存 hash 不存全量 |

## 13. 为什么不引第三方策略引擎

OPA / Cedar 能把"策略求值"标准化，但**它们不生成 SQL 改写**；本项目的难点在
"把策略编译成 SQL"（sqlglot 已在用），而不是布尔求值。引入第二个引擎会增加部署与
运维面（sidecar / bundle 分发），收益不匹配。策略 DSL 保持小而可审计，编译器是我们自己的。

## 14. 附录：关键代码位置

- 表级：`query/service.py::_allowed_for_user` / `_domain_tables_for_user` / `validate_sql`
- 列级：`query/service.py::_ont_sql_violations` / `_sql_query_scope` / `_sensitive_asset_cols`
- 敏感放行：`query/service.py::_can_see_sensitive`（ABAC `sensitive_ok`）
- 行级（对象侧）：`ontology/security.py::filter_instances` / `row_allows` / `visible_properties`
- 执行收口：`query/service.py::_execute_one`；旁路 `_execute_sql`（备份/导出，需确认仅超管可用）
- 上下文：`query/service.py::_build_schema_context`（`_system_schema()`）
- 血缘：`query/lineage.py`（表级/列级、敏感传播）
- 普通角色/属性来源：`sys_user`、`sys_role`、`_user_role_codes`
