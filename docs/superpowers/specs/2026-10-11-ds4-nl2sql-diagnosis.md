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
| **外键 / join 关联** | ⚠️ ds:4 为零 | `ai_ont_link` 222 条**全部属于 system 对象，ds:4 = 0**；`ai_query_kg_relation` 全库仅 **1** 条；`ai_query_asset_columns.related_table` 里 `FUEL*` 表 **0** 条 |
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

## 5. 外键 / join 关联：ds:4 为零（有证据）

```
ai_ont_object 按 ds: ds=4 → 145, ds=NULL → 271
ai_ont_link   按源对象 ds: ds=NULL → 222, ds=4 → (无)      ← ds:4 一条关系都没有
ai_query_kg_relation 总数: 1
ai_query_asset_columns.related_table 里 FUEL* 表: 0 条
```

- ds:4 **没有任何 join 元数据**（本体关系 0、资产 `related_table` 0、KG 1）。
- 本次 3 道失败题都是**单表聚合**，所以 join 缺失**不是这 3 题的原因**；
  但它会让**多表题**（占比/多维报表/时间窗口联表）无从下手。

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
