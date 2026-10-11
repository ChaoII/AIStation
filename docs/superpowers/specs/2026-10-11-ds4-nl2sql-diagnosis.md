# ds:4（燃煤外部库）NL2SQL 差的根因排查报告

> 触发：问数评测显示 **ds:4 准确率 25%**（system 100%），用户要求排查是
> 「语义层 / SQL 示例 / 反馈负样本 / 外键关联 / 其他工程化」哪一层的问题。
>
> 方法：systematic-debugging（先取证、再定位、后验证），全部结论都有可复现证据。

## 0. 结论先行

| 层 | 判定 | 关键证据 |
|----|------|----------|
| **其他工程化** | ❌ **直接根因** | 4 个 ds:4 指标模板**未加双引号**（`FROM FUEL_CB_COALBALANCE`）→ PG 折成小写 → `UndefinedTableError`；且 `ask()` 只 catch `CustomException`、`execute_select` 无 except → **异常逃逸，整题崩溃且不回退慢路径**（SQL 为空、0.4s、无 LLM 调用） |
| **语义层（指标）** | ⚠️ 有缺陷 | ds:4 仅 **4 个指标 / 331 张表**；且**匹配过宽**：「所有燃煤合同的**合同数量**合计」被匹配到 `total_settlement_qty`（**结算总量**，另一张表另一列）→ 语义错配；`avg_lf` 模板 `AVG("LF")` 在真库报 `avg(character varying)` —— **指标从未在真库验证过** |
| **SQL 示例（few-shot）** | ⚠️ 缺失 | `ai_query_fewshot`：system=57，**ds:4=0**。LLM 拿不到"大写表名要加引号"的范例 |
| **反馈负样本** | ⚠️ 完全未启用 | `ai_query_messages` 4534 条，**feedback 全为空、correct_sql 0 条**；反馈沉淀的 few-shot = 0 |
| **外键 / join 关联** | ⚠️ 见 §5 修订 | 燃煤域**已有 189 条**带字段映射的关系边；真正的问题是这些对象的 `datasource_id` 是 **NULL**（未打标），导致按数据源过滤时看不到 → 已修复，现 ds:4 关系边 **203** 条 |
| **资产层（表/字段元数据）** | ✅ 不是瓶颈 | 176 张 `FUEL*` 表 **100%** 有中文名/业务域/描述；`ai_query_schema` ds:4 331 表、194 有表注释 |
| **召回层** | ✅ 不是瓶颈 | `_recall_grounding` 对失败题**也返回了正确的表**（`FUEL_CB_COALCONTRACT` 等）。评测里 recall=0 是"崩溃导致没拿到 retrieved"的假象 |
| **本体层** | ⚠️ 半成品 | ds:4 对象 145 个、属性 925 个，但**别名 0 个**、**关系 0 条** |

### 但最重要的一条是：**这个 25% 不能作为任何一层的证据**

对 ds:4 的 50 道题**逐题跑金标 SQL** 审计结果：

| 类别 | ds:4 | system |
|------|------|--------|
| **有真实数据** | **4 道（8%）** | 31 道（62%） |
| 退化（单值 0） | 22 道（44%） | 18 道（36%） |
| 退化（空/全 NULL） | **24 道（48%）** | 1 道（2%） |

- `FUEL_CB_COALBALANCE` / `FUEL_CB_COALCONTRACT` / `FUEL_CB_COALBALANCEDETAIL` / `CMMS_CANVAS`
  的行数都是 **0**；只有 `DTXY_PMXX` 有 77 行。
- **92% 的 ds:4 题建在空表上**：`COUNT(*)` 得 0、`AVG()` 得 NULL，**任何 SQL 都能"答对"**。
- 出题时的「金标 SQL 必须真实执行且行数>0」这道闸门**挡不住它**——聚合查询在空表上
  仍返回 1 行（0 或 NULL）。

## 1. 直接根因：指标模板未加引号 + 异常不兜底（工程化）

### 复现（`scripts/repro_ds4_fail.py`）

```
Q: 所有燃煤合同的合同数量合计是多少？
  _recall_grounding → tables=['ont_FUEL_CB_COALCONTRACT', 'FUEL_CB_COALCONTRACT', ...]   ← 召回正确
  ask 抛错: UndefinedTableError: 关系 "fuel_cb_coalbalance" 不存在
  [SQL: SELECT SUM(BALANCEQTY) AS "结算总量" FROM FUEL_CB_COALBALANCE LIMIT 1000]
```

### 调用链（逐环确认）

1. `ask()`（`service.py:5371`）→ `_match_metric` **命中**（题 1 命中 `total_settlement_qty`，
   题 2/3 命中 `avg_contract_price`）。
2. `_execute_metric`（`:863`）→ `_execute_custom_ds_sql`（`:210`）：
   `validate_sql(sql, allowed)` —— 白名单**按原样比对**通过（`FUEL_CB_COALBALANCE` 在白名单里），
   **但不做任何标识符加引号/规范化**。
3. `executor.execute_select`（`executor.py:60`）—— **没有 `except`**，只有 `finally: dispose()`，
   驱动异常原样抛出。
4. `ask()`（`service.py:5395`）`except CustomException` —— **原始 `ProgrammingError` 不是
   `CustomException`，不被捕获** → 直接冒泡 → 整题失败。

**本该发生的是**：快路径失败 → 记录错误 → **回退慢路径**（`:5402` 的 `return await cls._slow_path(...)`
就是为这个写的，但只在 `CustomException` 时才会走到）。

### 假设验证（`scripts/verify_ds4_hypothesis.py`）

```
OK  SELECT SUM("BALANCEQTY") AS "结算总量" FROM "FUEL_CB_COALBALANCE"      ← 加引号即可跑通
OK  SELECT AVG("CONTRACTPRICE") AS "平均合同单价" FROM "FUEL_CB_COALBALANCE"
ERR SELECT AVG("LF") AS "平均干基全硫" FROM "DTXY_PMXX"
    → UndefinedFunctionError: 函数 avg(character varying) 不存在        ← 第二个缺陷：类型
```

`information_schema` 证实：`DTXY_PMXX.LF/RZ` 是 **character varying**（文本），
`FUEL_CB_COALBALANCE.BALANCEQTY/CONTRACTPRICE` 是 numeric。→ **`avg_lf`/`avg_rz` 两个指标
天生不可执行**，说明指标是"手写进去"而**从未在目标库执行验证**。

## 2. 语义层缺陷（有证据）

- 指标数量：ds:4 = **4**，system = 15；而 ds:4 有 331 张表 / 176 张 `FUEL*` 核心表。
- **匹配过宽（语义错配）**：`_match_metric("所有燃煤合同的合同数量合计是多少？")` →
  `total_settlement_qty`（结算总量）。合同**数量** ≠ 结算**量**，是不同表的不同列。
- 术语表 ds:4 = 6 条（合同单价/扣吨/热值/硫分/结算量/运损），其中 2 条**没有对应指标**。
- 本体：ds:4 对象 145、属性 925，**别名 0**、描述 145。

## 3. SQL 示例缺失（有证据）

`ai_query_fewshot` 按数据源：system=57，**ds:4=0**。
ds:4 的表名/列名是**大写且大小写敏感、必须加双引号**——这恰恰是最需要示例来示范的约定，
却一条示例都没有。（LLM 在 `CMMS_CANVAS` 那题靠自己猜对了引号，但这是运气不是保障。）

## 4. 反馈负样本完全未启用（有证据）

```
feedback=(空): 4534 条，带 correct_sql 0 条
反馈沉淀的 few-shot: 0
```

`ai_query_messages.feedback` 有字段、`QueryFeedbackRequest` 有接口、`feedback()` 有"沉淀"逻辑，
但**实际数据全空**：没有任何用户反馈，也没有任何"负样本 → few-shot"的沉淀产物。
→ 这条自我改进闭环**从未运转过**。

## 5. 外键 / join 关联（**本节结论已修订**）

### 修订：不是"没有关系边"，而是"关系边没打数据源标"

初版结论「ds:4 = 0 条关系」**是错的**——它来自 `WHERE o.datasource_id=4` 的过滤。
按**支撑表**重新统计：

```
FUEL*/CMMS* 对象按 ds: ds=NULL → 183          ← 燃煤域对象创建时没打 datasource_id
关系边中源对象是燃煤域表的: 189                ← 关系边**一直都在**，且带字段映射
样例: FUEL_CMCS_GOODSTRANSPORT.GOODSTYPEID → FUEL_CMCS_GOODSTYPE.ID
      FUEL_CMCS_INCOALBUNKER.INFURNACEID   → FUEL_CMCS_INFURNACE.ID
```

- 而且 `_ont_links()` 走的是本体统一语义接口 `semantic_context()`，**不按数据源过滤**
  → 这些关系边本来就能被问数用上。
- 真正缺的只是**归属标记**（以及少量目标库真实外键没导入）。

**修复**（`scripts/seed_ds4_joins.py`）：按"支撑表命中目标库真实表名"回填
`datasource_id`，并导入目标库 `information_schema` 的**真实外键**（两端都有本体对象的）。

**结果**：`ai_ont_object` ds:4 **145 → 332**；`ai_ont_link` 源对象 ds:4 **0 → 203**。

> 目标库实际有 **16 条真实外键**、290/331 张表有主键、1226 个 `*ID` 列
> —— 数据基础比预想的好；此前的"零"是**统计口径**造成的错觉。

## 6. 评测模块自身的效度缺陷（排查中发现，属于我上一轮交付的问题）

1. **`data_accuracy` 实际是"SQL 可执行率"，不是准确率**：
   `_lenient()`（`eval_runner.py:179`）在拿不到 `_gold_cols`/`_gold_rows` 时**退化为
   `not is_error and sql != ""`**；而 `_run_once` 传进去的 `case`（来自 `list_cases`）
   **从来不包含**这两个字段 → 于是**永远走退化分支**，**从不比对结果值**。
   → 上一轮报告的"数据准确率 92.5%"应读作"92.5% 的题产出了一条能跑通的 SQL"。
2. **出题闸门不足**：只校验"能执行 + 行数>0"，聚合在空表上返回 0/NULL 也算通过
   → 92% 的 ds:4 题是退化题。
3. **`semantic_accuracy` 分母不稳**：`expected_metric` 大量为空（出题模型常不填）。

## 7. 修复优先级建议

**P0（直接恢复可用性）**
1. `_execute_custom_ds_sql` / 指标模板：执行前对**目标库的表/列标识符加双引号**
   （或校验后按 schema 的真实大小写回写引号）——**只在"大小写敏感"的数据源上做**。
2. `ask()` 的快路径失败兜底：把 `except CustomException` 放宽为 `except Exception`
   （或让 `execute_select` 把驱动异常包装成 `CustomException`），确保**任何快路径失败都回退慢路径**。
3. 指标保存时**真库执行验证**（对齐测试集那道闸门）：不可执行/类型不符的指标不许启用。
   顺带修 `avg_lf`/`avg_rz`（文本列需 `AVG(NULLIF(LF,'')::numeric)`）。

**P1（恢复评测效度）**
4. `_run_once` 预取金标结果（`_gold_cols`/`_gold_rows`），让 `_lenient` 真正比对值；
   否则所有精度数字都不可信。
5. 出题闸门升级：聚合结果若为 **NULL / 全 0** 判为退化题，不入集（或标 `degenerate=true` 不参与精度统计）。

**P2（补齐语义层）**
6. ds:4 few-shot：至少给 5~10 条"大写表名 + 双引号"的范例（含单表聚合/联表/时间窗口各一）。
7. ds:4 本体关系：从 `ai_query_asset_columns.related_table` 或对目标库
   `information_schema` 的外键/命名约定（`XXXID` → `XXX.ID`）批量生成 join 边。
8. 指标匹配收紧：避免"合同数量"命中"结算量"这类跨语义命中。

## 8. 复现命令

```bash
cd backend
python scripts/diagnose_ds4.py                 # 各层证据一次性打印
python scripts/repro_ds4_fail.py               # 复现失败题的原始报错
python scripts/verify_ds4_hypothesis.py        # 验证"加引号即可跑通"与指标匹配错配
python scripts/audit_ds4_cases.py ds:4         # 测试集有效性审计（退化题占比）
python scripts/audit_ds4_cases.py system
```

---

## 9. 修复进展（本轮已落地，TDD）

### ✅ P0-1 大小写敏感数据源标识符加引号

新增 `app/plugin/module_ai/query/sql_quote.py::quote_schema_identifiers(sql, schema)`：
用 sqlglot 解析后把命中 schema 的表名/列名改写成**真实大小写 + 双引号**，
未命中（函数名/别名/未知表）原样保留；schema 为空或解析失败则原样返回。

接入点：`_execute_custom_ds_sql`（所有自定义数据源，含快/慢路径）。

**踩坑（已修）**：真库里**别的表有小写同名列**（`contractprice`），合并列池时把已写对的
`CONTRACTPRICE` 覆盖成小写 → 仍报「字段 contractprice 不存在」。改为
「大写键 → 真实名列表」不覆盖 + **精确大小写优先** + 单表查询按该表列名解析。

### ✅ P0-2 驱动异常兜底 + 回退慢路径

- `executor.execute_select`：驱动异常**包装成 `CustomException`**（原来裸抛）。
- `ask()` 快路径：`except CustomException` → **`except Exception`**，
  任何失败都「记录错误 → 回退慢路径」，不再整题崩溃。

### ✅ P0-3 回报的 SQL 必须是实际执行的那条

`_execute_custom_ds_sql` 回传加引号后的 SQL（原来展示的是未加引号的模板，排查会被误导）。

### ✅ P1-4 评测真正比对结果值

- 新增 `eval_runner._run_gold_sql()`：每轮**预取金标结果**（按题缓存），
  交给 `_lenient` 走 `lenient_match` 真比对。
- 修 `benchmark.lenient_match`：金标侧原来用 `str(v)`（`None → 'None'`），
  模型侧用 `_norm_cell`（`None → '∅'`）→ **NULL 永远不等**。改为两侧都 `_norm()`。
  （ds:4 有 48% 的题结果是 NULL，这条不修等于这些题永远判错。）

### 修复效果（12 题子集，真实运行）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| ds:4 准确率 | 25%（3 题崩溃） | **100%**（4/4） |
| system 准确率 | 100% | **87.5%**（7/8） |
| 口径 | 「SQL 跑通即算对」 | **真比对结果值** |

> ⚠️ system 从 100% 降到 87.5% 不是退化，是**指标变诚实**了：之前那条错答
> 因为"SQL 跑通了"被算对，现在被正确判错。
>
> ⚠️ **ds:4 的 100% 也不代表质量**：那 4 题里多数仍是**退化题**（金标为 NULL/0，
> 模型同样返回 NULL/0 就算"一致"）。要让它有意义，必须再做 P1-5。

### 待办（未做）

- **P1-5 退化题闸门**：出题时若金标聚合结果为 **NULL / 全 0**，判为退化题，
  不入集或不参与精度统计。（否则 ds:4 的数字始终虚高。）
- **P2-6 ds:4 few-shot**：至少 5~10 条（示范双引号 / 单表聚合 / 联表 / 时间窗口）。
- **P2-7 ds:4 join 边**：ds:4 目前 0 条关系、0 条 `related_table`、KG 仅 1 条。
- **P2-8 指标匹配收紧**：避免「合同**数量**」命中「结算**量**」这类跨语义命中
  （本轮 ds:4 唯一仍判错的那题就是它）。

---

## 10. 第二批修复（P1-5 / P2-6 / P2-7 / P2-8，已落地并验证）

| 项 | 做法 | 验证 |
|----|------|------|
| **P1-5 退化题闸门** | 新增 `is_degenerate_result()`（空/NULL/单值 0）；出题时打 `notes='degenerate'`；`summarize`/`group_by` **排除退化题**并新增 `degenerate_n`/`all_total` | 回填后 **100 题里 65 题是退化题**；全量跑 `total=35, degenerate_n=65` ✓ |
| **P2-8 指标匹配收紧** | 去掉「数量/多少/类型/分布」这类**通用词**加分；改为**指标自身用词**（名称/描述的中文二元组，名称权重 3×、描述 1×）+ 术语 + 时间维度；设最低分门槛 `_MIN_METRIC_SCORE=4`，并允许"时间维度正好对上"单独命中 | 5 条纯逻辑测试；「合同数量合计」不再命中「结算总量」✓ |
| **P2-6 ds:4 few-shot** | `scripts/seed_ds4_fewshots.py`：9 条示例，**每条先在目标库执行验证**，跑不通就跳过 | ds:4 few-shot **0 → 9**（单表计数/分组/去重/联表/时间窗口/指标口径各覆盖） |
| **P2-7 ds:4 join** | `scripts/seed_ds4_joins.py`：回填 `datasource_id` + 导入目标库真实外键 | 关系边 **0 → 203**；对象 ds:4 **145 → 332** |

### 全量真实基线（100 题，修复后）

```json
{"total": 35, "all_total": 100, "degenerate_n": 65, "data_accuracy": 0.5714,
 "semantic_accuracy": 0.1143, "fast_rate": 0.6571, "recall_at_k": 0.3429,
 "avg_ms": 33.5, "p50_ms": 4.0, "p95_ms": 235.0, "error_rate": 0.0}
```

| 维度 | 数字 | 读法 |
|------|------|------|
| **error_rate** | **0.0** | P0 修复彻底：不再有整题崩溃 |
| 数据准确率 | **57.1%**（20/35） | **这才是诚实基线**（此前"92.5%"是"SQL 跑通率"） |
| 快路径指标 | **90.9%**（10/11） | 指标快路径是可靠的 |
| **占比 / 窗口函数 / 多维报表 / 排名TopN** | **0% / 16.7% / 0% / 50%** | **真正的短板在这里**——复杂形式的生成质量 |
| ds:4 | 100%（4/4） | 但只有 4 题有真实数据，样本太小，不足以下结论 |
| system | 51.6%（16/31） | 非退化题多为占比/窗口/多维，正是难的那批 |

> **结论修正**：ds:4 的"差"= ① 工程化崩溃（已修，error 0）+ ② 题集 92% 退化（已隔离）。
> 修完之后暴露出的**真正长期短板**是 **system 源上复杂形式（占比/窗口函数/多维报表）的生成质量**，
> 而不是语义层/示例/反馈/外键 —— 这些层各有缺陷但都不是当前精度的主因。

### 仍未做

- **反馈闭环**：4534 条消息里 **0 条反馈**、0 条沉淀 few-shot（机制在，但从未被使用）。
- **ds:4 指标仅 4 个 / 331 表**：且 `avg_lf`/`avg_rz` 因列是**文本**而不可执行（需 `AVG(NULLIF(LF,'')::numeric)`）。
- **题集**：65% 退化题仍在库里（已标记、不参与统计，但若要扩集应补**有数据**的题）。

---

## 11. 第三批：表范围收敛 + 指标扩充 + 评测集补样 + 缺数据清单

### 11.1 表范围：331 → **184 张关键业务表**（排除 119 张系统/技术表）

**问题**：自定义数据源的 `_ds_schema_map` 读**全部同步表**（331 张），
把 `SYS_*`/`_BAK`/`JIMU_*`/`OPS_*` 等技术表一起塞进检索与 prompt —— 污染召回。

**盘点**（`scripts/ds4_table_scope_report.py`）：

| 类别 | 表数 | 有数据 | 已纳入资产 | 有本体对象 |
|------|------|--------|-----------|-----------|
| 业务（FUEL_/CMMS_/DTXY_/FR_/RPT_/…） | **192** | **99** | 184 | 192 |
| 技术/系统（SYS_/_BAK/_LOG/JIMU_/OPS_/加密表） | 92 | 46 | 46 | 2 |
| 其它 | 27 | 9 | 9 | 0 |

**收敛**（`scripts/curate_ds4_scope.py`）：`ai_query_assets.included` 只留业务表；
非业务表的本体对象 `enabled=false`。

**让检索真正生效**（TDD，`tests/test_ds4_scope.py`）：`list_ds_schema(id, included_only=True)`
+ `_ds_schema_map` 改用它。

**验证**：同步表 331 → 纳入 **184**；检索映射 **184 张、0 张系统表**；召回只返回业务表。

### 11.2 指标：4 → **67 个**（只建有数据的表，逐条执行验证）

`scripts/seed_ds4_metrics.py`：对有数据的 99 张业务表
生成「条数」指标（40 个）+ 数值列「合计」指标（23 个），**每条先在目标库执行**，
结果非 NULL 才入库（65 个计划里 63 个通过）。

> 原有 4 个指标里有 3 个建在 **0 行表**上（`FUEL_CB_COALBALANCE` 等）→ 恒返回 NULL，
> 这也是"指标快路径没用"的原因之一。

### 11.3 评测集：ds:4 50 → **110 道**（新增 60 道**非退化**题）

`scripts/seed_eval_from_metrics.py`：用**已验证过的指标**反推问句
（「<指标名>是多少？」→ 金标 = 指标模板），天然非退化。
新增 60 道（2 道已存在、2 个指标不可执行、3 个结果退化被跳过）。

### 11.4 缺数据清单（交给人工补数）

`docs/ds4-missing-data.md`（由 `scripts/ds4_missing_data_report.py` 生成）：
- 业务表 192，其中 **0 行 93 张**、有数据 99 张；
- 按子域分组（采购结算 / 化验煤质 / 采样制样 / 煤场库存 / 入炉耗用 / 运输计量 / 计划报表 / 组织基础）；
- 附补数优先级：**采购与结算**（现有 3 个指标全建在这批空表上）＞ 化验煤质 ＞ 煤场库存 ＞ 计划报表。

### 11.5 新增脚本一览

| 脚本 | 作用 |
|------|------|
| `ds4_table_scope_report.py` | 表范围盘点（业务/技术、行数、是否纳入） |
| `curate_ds4_scope.py` | 收敛 included 范围 + 输出缺数据清单 |
| `ds4_missing_data_report.py` | 生成 `docs/ds4-missing-data.md` |
| `seed_ds4_metrics.py` | 批量播种可执行指标 |
| `seed_eval_from_metrics.py` | 用指标生成非退化评测题 |
| `seed_ds4_joins.py` / `seed_ds4_fewshots.py` | 关系边归属回填 + 验证过的 few-shot |

---

## 12. 架构边界：本体 ↔ 问数 怎么"有机结合"

### 12.1 现状（改造前）：**双向直连**

- **问数 → 本体（方向正确，接口调用）**：`object_table_map()` / `semantic_context()` /
  `context_block(only_tables=召回表集)` / `_secure_ont_sql()`
- **本体 → 问数（方向反了，直读问数的表）**：
  `ontology/semantic.py` 读 `ai_query_concept`、读/写 `ai_query_asset_columns.sensitive`。
  代码注释自己都写着"历史遗留：两套并行标记，实测已不一致（本体 11 vs 问数 2）"。

### 12.2 边界（改造后）

| 层 | 拥有什么 | 归属 |
|----|----------|------|
| **数据目录** | 表/字段中文名、业务域、敏感标记、**范围(included)**、业务概念 | 共用资产，单一真源 |
| **本体** | 对象/属性/**关系(join)**/权限策略/支撑表映射 | 本体 |
| **问数资产** | 指标、术语、few-shot | 问数 |
| **问数运行时** | 检索、prompt、LLM、SQL 校验执行、评测 | 问数 |

**唯一该有的耦合点**：`context_block(only_tables=召回表集)`
—— **问数决定"看哪些表"，本体负责"这些表在业务上是什么"**。

### 12.3 已做的重构

新增 `app/plugin/module_ai/catalog.py`（共享目录接口）：
`list_concepts()` / `list_sensitive_columns()` / `mark_sensitive()`（幂等）/ `included_tables()`。
本体三处直读/直写**全部改走它**，并加**回归守卫测试**
（扫 `ontology/*.py`，出现 `FROM|UPDATE|JOIN ai_query_` 即失败）。
行为不变：187 passed。

### 12.4 顺带纠正一个错误认知

`ai_ont_object.enabled` 是**装饰性的** —— `semantic_context` 不按它过滤，
所以 §11.1 里"把非业务表的本体对象 enabled=false"其实**没起作用**；
真正的范围闸门是 `ai_query_assets.included`（检索已按它过滤）。

---

## 13. 硬形式出题一直落空的两个真 bug（已修）

现象：`--generation-only --forms=联表,占比,…` 跑完只加了 1 道联表题，日志全是
"LLM 未产出可解析用例"。

| bug | 证据 | 修复 |
|-----|------|------|
| **`max_tokens=4000` 被推理吃光** | 联表/占比的**原始输出长度 = 0**；窗口函数那次是被**截断**的 JSON | 提到 **8000**；空正文时打印 `finish_reason`/`usage` 留痕 |
| **`parse_cases` 不会救截断 JSON** | 738 字合法开头 → 解析出 **0 条** | 新增 `_salvage_objects()`：花括号**栈**配平，救回前面完整对象（TDD） |

修后复测：联表/占比/窗口函数 **各解析出 2 条**（原 0）。
题集随之扩容：占比 8→**14**、业务黑话 9→**12**、窗口函数 7→**12**、
排名TopN 2→**7**、多维报表 1→**4**、联表 1→**2**。

