# 指标体检处置清单（2026-11-13，ds:6）

**数据来源**：`GET /ai/query/metrics/audit?datasource=ds:6`（扫描该数据源全部 200 道题）。
167 个启用指标中 **31 个可疑**，全部是自动生成痕迹（表名 + 字段码 + 聚合后缀）。
**执行状态（2026-11-13，全部完成）**：① 停用 10 条 —— **已执行**；② 改名 21 条 —— **已执行，两轮回归均 0 翻转**；③ 待确认 2 条 —— **已按库注释定名并改名**（不再是待确认）。
处置后体检：启用指标 157 个，**可疑 0、抢答 0、悬空引用 0**。
处置也可在界面「问数设置 → 治理体检」逐条操作，或用 `scripts/apply_metric_plan.py` 按计划文件批量执行（幂等，重复跑会跳过已停用的）。

计划文件：`backend/scripts/plans/metric_plan_2026-11-13.json`（31 条，含 reason）。

## 一、建议停用（10 条：聚合口径没有业务意义）

| 原指标名 | 为什么停用 |
|---|---|
| 配煤方案结果明细表STOQTY合计 | 明细表按行重复，SUM 库存量会重复累加；**也是唯一抢答题**（问「分仓灰分上限>20 有多少条」被它接走） |
| 机组信息表DESIGNVALUE合计 | DESIGNVALUE 是设计值，求和无意义 |
| 分仓计量机组实时数据表FACELECRATE合计 | 率值（负荷率）不能相加，要就该改 avg |
| 机组原煤仓表MAXAMOUNT合计 | 上限值求和无意义 |
| 日入炉煤统计报表ORDERNUMBER合计 | 单据号求和是无效数字；要「单据数」应新建 count 指标 |
| 日入厂分场统计报表ORDERNUMBER合计 | 同上 |
| 评价规则执行明细ORDERNUMBER合计 | 序号/单据号求和 |
| 机组工况运行设置煤仓煤质要求ORDERNUM合计 | 序号求和 |
| 机组工况运行设置负荷煤质明细MINVALUE合计 | 下限值求和 |
| 皮带操作记录COUNT合计 | 对计数字段 SUM 是重复计数；要次数就用 `count(*)` |

## 二、建议改名（21 条：口径正确，只是名字是机器拼的）

| 原指标名 | 建议名 |
|---|---|
| 机组工况运行设置主表COALCONSUMP合计 | 机组工况设置耗煤量合计 |
| 入厂煤堆放信息表TOTALQTY合计 | 入厂煤堆放总量 |
| FUEL_CMCS_ASSAYCHECK条数 | 入厂煤化验记录条数 |
| FUEL_CMCS_INFACTORYPLAN条数 | 入厂计划明细条数 |
| FUEL_CMCS_INSILOHISTORY条数 | 筒仓煤量历史记录数 |
| FUEL_REPORT_DAYCOALSTORAGELEDGER条数 | 日煤场存煤台账记录数 |
| FUEL_STG_CONTROLLOG条数 | 燃料运行交接班日志条数 |
| FUEL_STG_INVENTORYREPORTDETAIL条数 | 库存报告明细条数 |
| 负荷计划表TOTALELEC合计 | 负荷计划总电量合计 |
| 配仓方案-煤种信息QTYHAVE合计 | 配仓方案现有煤量合计 |
| FUEL_REPORT_DAYCOALSTORAGELEDGERQTY合计 | 日煤场存煤量合计 |
| 每日耗用量及存煤量TOTALUSEQTY合计 | 每日耗用量合计 |
| 煤场进煤记录(流水)QTYIN合计 | 煤场进煤量合计 |
| 煤场取煤记录(流水)QTYOUT合计 | 煤场取煤量合计 |
| 化验主表记录数 | 化验主表单据数（与「入厂煤化验记录条数」区分：两张不同表） |
| DTXY_GYSKDGX条数 | 供应商矿点关系条数 |
| DTXY_QYXX条数 | 区域信息条数（**先在资产页给该表补中文名**「区域信息表」，现在 alias 等于表名） |
| 配煤方案主表STANDQTY合计 | 配煤方案标煤耗量合计（库注释：STANDQTY = 标煤耗煤量） |
| 配仓方案STANDQTY合计 | 配仓方案标煤耗量合计（同上，同一字段） |
| 入厂入炉热值差月报RL_QTY_1_1合计 | 一期#1原煤量合计（库注释：RL_QTY_1_1 = 一期#1原煤量(t)） |
| 入炉煤质量分析月报表QTY1合计 | 一期#1机给煤量合计（库注释：QTY1 = 一期#1机给煤量） |

## 三、字段含义的确认来源（不再靠猜）

两条「报表列编号」字段的**库注释**直接给出答案（ds:4 原始库与 ds:6 副本一致）：

| 表.字段 | 注释原文 | 样例值（ds:6 / ds:4） | 采用的指标名 |
|---|---|---|---|
| `FUEL_MIX_COALSCHEME.STANDQTY` | 标煤耗煤量 | 0.0 / 0.0 | 配煤方案标煤耗量合计 |
| `FUEL_MIX_STORESCHEME.STANDQTY` | 标煤耗煤量 | 2880.0 / 2880.0 | 配仓方案标煤耗量合计 |
| `FUEL_REPORT_INFACINFURQCALDIFF.RL_QTY_1_1` | 一期#1原煤量(t) | 2131 / 1894 | 一期#1原煤量合计 |
| `FUEL_REPORT_INFURNACEQUALITY.QTY1` | 一期#1机给煤量 | 0.0 / 0.0 | 一期#1机给煤量合计 |

教训：**字段含义优先查库注释**（`col_description`），比问人快且不会记错；查不到再问业务。

## 三点五、处置过程中发现并修掉的匹配漏洞

停用 `sum_fuel_mix_coalschemereusltdetail_stoqty` 后重新体检，同一句
「配煤方案分仓里灰分上限（AD_MAX）大于 20 的有多少条？」又被
`sum_fuel_mix_coalscheme_standqty`（SUM(标煤量)）抢答 —— 说明问题不在某一条指标，
而在护栏漏放：

- `match_metric` 里本来就有「问多少条 → 非计数指标不参战」这条，但条件是
  `rowcount_asked and not physical_qty`；只要句子里顺带出现一个物理量词
  （灰分/耗用/总量…）就被放行。**「多少条」是显式计数诉求，比顺带的物理量词更具体**，
  已去掉这个放行条件。
- 自动生成的计数指标有 `FUEL_CMCS_ASSAY_count_ID` 这类命名，`is_rowcount_metric`
  原来只认 `count_` 前缀 / `_count` 后缀，认不出中缀 `_count_`、「计数」「总数」后缀，
  已补齐（这决定物理量问句能否正确排除计数指标）。

回归用例：`tests/test_query_metric_guard.py::test_count_question_is_not_hijacked_by_sum_metric`
（计数问句不被 SUM 抢）与 `::test_rowcount_metric_recognised_by_generated_key_shapes`。
实测同一批问句：「煤场进煤总量是多少」仍走 `SUM(QTYIN)`，「入厂煤批次一共有多少条」
走 count 指标，两条「多少条」改走 SQL。

## 四、风险与验证纪律（别跳过）

1. **改名会改变指标匹配**：`match_metric` 与护栏（兄弟限定词、跨表竞争别名）都看指标名。
   例如把「煤场进煤记录(流水)QTYIN合计」改成「煤场进煤量合计」后，指标名里不再出现表中文名，
   可能被「跨表竞争别名」规则拦住 → 快路径不命中。
2. **所以改名必须回归**（顺序固定）：
   ```bash
   cd backend
   uv run python scripts/run_eval_once.py --dataset=holdout-v2 --datasource=ds:6 \
     --run-limit=1000 --ablation-limit=0     # 基线 97.30%
   uv run python scripts/run_eval_once.py --dataset=fuel-v2 --datasource=ds:6 \
     --run-limit=1000 --ablation-limit=0     # 当前 78 题 100%
   ```
   任一项下降 → 只回滚**改名**（停用不受影响，因为停用的都是答错的指标）。
   本次 19 条改名实测 **0 翻转**，故未回滚。
3. **停用是改善而不是删数据**：只关 `enabled`，指标与口径全在，随时可在指标页重新启用。
   本批 10 条已停用，停用 + 护栏修复后复跑（2026-11-13）：
   - **holdout-v2**：36/37 = **97.30%**，快路径 8.11%（与基线一致）；
   - **fuel-v2**：当前启用 78 题（原 105 题里 27 题已停用）**78/78 = 100%**，快路径 12.82%；与基线 `ev_852e82a95756` **同口径（同一批 78 题）对比 0 翻转**。
   - **改名后再跑一遍**（`ev_706b3b50eec5` / `ev_8d2ebea9dc42`）：两个数据集 **逐题 0 翻转、指标命中 0 变化**，数字与改名前完全一致 —— 因为匹配证据主要来自表别名与描述，指标名的业务词只是辅助。
   - **二轮改名（标煤耗量 + 两条一期机组字段）再跑**（`ev_3daa3ffb8584` / `ev_41821f3400ee`）：同样 **0 翻转、0 命中变化**（97.30% / 100% 不变）。
   复跑命令：`run_eval_once.py --dataset=<ds> --datasource=ds:6 --run-limit=1000 --ablation-limit=0`
   （`--run-limit` 是在全库 891 题里截前 N 再过滤，给小值会漏题；消融默认 20 题，不测就置 0。）
4. **`DTXY_QYXX` 的资产中文名缺失**属于资产治理项，与改名同批做（否则新名「区域信息条数」
   在界面上仍然对不上表）。

## 五、执行方式

```bash
cd backend
# 预演（默认，不写库）
uv run python scripts/apply_metric_plan.py --plan scripts/plans/metric_plan_2026-11-13.json

# 只停用（风险最低，先做这一批）
uv run python scripts/apply_metric_plan.py --plan scripts/plans/metric_plan_2026-11-13.json --apply --only disable

# 改名（做完必须跑上面的回归）
uv run python scripts/apply_metric_plan.py --plan scripts/plans/metric_plan_2026-11-13.json --apply --only rename
```

脚本会校验：指标存在且启用、新名不与现有指标重名、计划内新名互不重复；任一不满足整体不写库。
`action=confirm` 的 2 条永远跳过，等业务确认后改计划文件再跑。
