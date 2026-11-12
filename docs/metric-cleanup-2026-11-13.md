# 指标体检处置清单（2026-11-13，ds:6）

**数据来源**：`GET /ai/query/metrics/audit?datasource=ds:6`（扫描该数据源全部 200 道题）。
167 个启用指标中 **31 个可疑**，全部是自动生成痕迹（表名 + 字段码 + 聚合后缀）。
本清单只做**分类与建议**，处置可在界面「问数设置 → 治理体检」逐条操作，
也可用 `scripts/apply_metric_plan.py` 按计划文件批量执行。

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

## 二、建议改名（17 条：口径正确，只是名字是机器拼的）

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

## 三、需业务确认（4 条：字段含义不明，脚本跳过）

| 原指标名 | 待确认点 | 两种处置 |
|---|---|---|
| 配煤方案主表STANDQTY合计 | STANDQTY 是「标准煤量」还是「标准值/阈值」 | 标准煤量 → 改名「配煤方案标准煤量合计」；阈值 → 停用 |
| 配仓方案STANDQTY合计 | 同上（同一字段） | 同上 |
| 入厂入炉热值差月报RL_QTY_1_1合计 | `RL_QTY_1_1` 是报表列编号，含义未知 | 确认后改名「入厂入炉热值差月报·<业务名>」；若只是列占位 → 停用 |
| 入炉煤质量分析月报表QTY1合计 | `QTY1` 含义未知 | 同上 |

## 四、风险与验证纪律（别跳过）

1. **改名会改变指标匹配**：`match_metric` 与护栏（兄弟限定词、跨表竞争别名）都看指标名。
   例如把「煤场进煤记录(流水)QTYIN合计」改成「煤场进煤量合计」后，指标名里不再出现表中文名，
   可能被「跨表竞争别名」规则拦住 → 快路径不命中。
2. **所以改名必须回归**（顺序固定）：
   ```bash
   cd backend
   uv run python scripts/run_eval_once.py --dataset=holdout-v2 --datasource=ds:6   # 基线 97.30%
   uv run python scripts/run_eval_once.py --dataset=fuel-v2   --datasource=ds:6   # 基线 99.05% / fast 31.43%
   ```
   任一项下降 → 只回滚**改名**（停用不受影响，因为停用的都是答错的指标）。
3. **停用是改善而不是删数据**：只关 `enabled`，指标与口径全在，随时可在指标页重新启用。
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
`action=confirm` 的 4 条永远跳过，等业务确认后改计划文件再跑。
