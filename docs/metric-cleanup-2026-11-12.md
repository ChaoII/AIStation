# 指标清洗清单（2026-11-12，只读审计）

数据源 `ds:6`，启用指标 167 个；有自动生成痕迹 31 个。
标记为「建议」的动作需要人工确认后再执行（不改数据也能先看影响面）。

| # | 指标名 | key | 绑定表/对象 | 问题 | 抢答的留出题 | 建议 |
|---|--------|-----|-------------|------|--------------|------|
| 1 | 配煤方案结果明细表STOQTY合计 | `sum_fuel_mix_coalschemereusltdetail_stoqty` | FUEL_MIX_COALSCHEMEREUSLTDETAIL | 名字里带字段码、「表名+聚合」拼装、名字过长 | 配煤方案分仓里灰分上限（AD_MAX；配煤结果的混煤量（MIXCOALQ） | **停用** |
| 2 | 机组信息表DESIGNVALUE合计 | `sum_fuel_mix_genset_designvalue` | FUEL_MIX_GENSET | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 3 | 分仓计量机组实时数据表FACELECRATE合计 | `sum_fuel_mix_gensetrealtime_facelecrate` | FUEL_MIX_GENSETREALTIME | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 4 | 机组原煤仓表MAXAMOUNT合计 | `sum_fuel_mix_rawcoalbunker_maxamount` | FUEL_MIX_RAWCOALBUNKER | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 5 | 机组工况运行设置主表COALCONSUMP合计 | `sum_fuel_mix_runsetting_coalconsump` | FUEL_MIX_RUNSETTING | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 6 | 日入炉煤统计报表ORDERNUMBER合计 | `sum_fuel_report_incoalbunker_ordernumber` | FUEL_REPORT_INCOALBUNKER | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 7 | 日入厂分场统计报表ORDERNUMBER合计 | `sum_fuel_report_infactorystorage_ordernumber` | FUEL_REPORT_INFACTORYSTORAGE | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 8 | 入厂煤堆放信息表TOTALQTY合计 | `sum_fuel_stg_deposit_totalqty` | FUEL_STG_DEPOSIT | 名字里带字段码、「表名+聚合」拼装、名字过长 | — | 改名 |
| 9 | FUEL_CMCS_ASSAYCHECK条数 | `count_fuel_cmcs_assaycheck` | FUEL_CMCS_ASSAYCHECK | 名字里带字段码、名字过长 | — | 改名 |
| 10 | FUEL_CMCS_INFACTORYPLAN条数 | `count_fuel_cmcs_infactoryplan` | FUEL_CMCS_INFACTORYPLAN | 名字里带字段码、名字过长 | — | 改名 |
| 11 | FUEL_CMCS_INSILOHISTORY条数 | `count_fuel_cmcs_insilohistory` | FUEL_CMCS_INSILOHISTORY | 名字里带字段码、名字过长 | — | 改名 |
| 12 | FUEL_REPORT_DAYCOALSTORAGELEDGER条数 | `count_fuel_report_daycoalstorageledger` | FUEL_REPORT_DAYCOALSTORAGELEDGER | 名字里带字段码、名字过长 | — | 改名 |
| 13 | FUEL_STG_CONTROLLOG条数 | `count_fuel_stg_controllog` | FUEL_STG_CONTROLLOG | 名字里带字段码、名字过长 | — | 改名 |
| 14 | FUEL_STG_INVENTORYREPORTDETAIL条数 | `count_fuel_stg_inventoryreportdetail` | FUEL_STG_INVENTORYREPORTDETAIL | 名字里带字段码、名字过长 | — | 改名 |
| 15 | 评价规则执行明细ORDERNUMBER合计 | `sum_fuel_mix_appraisesettingdetail_ordernumber` | FUEL_MIX_APPRAISESETTINGDETAIL | 名字里带字段码、名字过长 | — | 改名 |
| 16 | 配煤方案主表STANDQTY合计 | `sum_fuel_mix_coalscheme_standqty` | FUEL_MIX_COALSCHEME | 名字里带字段码、「表名+聚合」拼装 | — | 改名 |
| 17 | 负荷计划表TOTALELEC合计 | `sum_fuel_mix_loadplan_totalelec` | FUEL_MIX_LOADPLAN | 名字里带字段码、「表名+聚合」拼装 | — | 改名 |
| 18 | 机组工况运行设置煤仓煤质要求ORDERNUM合计 | `sum_fuel_mix_runsettingbunkerdetail_ordernum` | FUEL_MIX_RUNSETTINGBUNKERDETAIL | 名字里带字段码、名字过长 | — | 改名 |
| 19 | 机组工况运行设置负荷煤质明细MINVALUE合计 | `sum_fuel_mix_runsettingdetail_minvalue` | FUEL_MIX_RUNSETTINGDETAIL | 名字里带字段码、名字过长 | — | 改名 |
| 20 | 配仓方案-煤种信息QTYHAVE合计 | `sum_fuel_mix_storeschemestorage_qtyhave` | FUEL_MIX_STORESCHEMESTORAGE | 名字里带字段码、名字过长 | — | 改名 |
| 21 | FUEL_REPORT_DAYCOALSTORAGELEDGERQTY合计 | `sum_fuel_report_daycoalstorageledger_qty` | FUEL_REPORT_DAYCOALSTORAGELEDGER | 名字里带字段码、名字过长 | — | 改名 |
| 22 | 每日耗用量及存煤量TOTALUSEQTY合计 | `sum_fuel_report_dayinoutstorage_totaluseqty` | FUEL_REPORT_DAYINOUTSTORAGE | 名字里带字段码、名字过长 | — | 改名 |
| 23 | 入厂入炉热值差月报RL_QTY_1_1合计 | `sum_fuel_report_infacinfurqcaldiff_rl_qty_1_1` | FUEL_REPORT_INFACINFURQCALDIFF | 名字里带字段码、名字过长 | — | 改名 |
| 24 | 入炉煤质量分析月报表QTY1合计 | `sum_fuel_report_infurnacequality_qty1` | FUEL_REPORT_INFURNACEQUALITY | 名字里带字段码、「表名+聚合」拼装 | — | 改名 |
| 25 | 煤场进煤记录(流水)QTYIN合计 | `sum_fuel_stg_allinmiddle_qtyin` | FUEL_STG_ALLINMIDDLE | 名字里带字段码、名字过长 | — | 改名 |
| 26 | 煤场取煤记录(流水)QTYOUT合计 | `sum_fuel_stg_alloutmiddle_qtyout` | FUEL_STG_ALLOUTMIDDLE | 名字里带字段码、名字过长 | — | 改名 |
| 27 | 化验主表记录数 | `FUEL_CMCS_ASSAY_count_ID` | FUEL_CMCS_ASSAY | 「表名+聚合」拼装 | — | 改名 |
| 28 | DTXY_GYSKDGX条数 | `count_dtxy_gyskdgx` | DTXY_GYSKDGX | 名字里带字段码 | — | 改名 |
| 29 | DTXY_QYXX条数 | `count_dtxy_qyxx` | DTXY_QYXX | 名字里带字段码 | — | 改名 |
| 30 | 配仓方案STANDQTY合计 | `sum_fuel_mix_storescheme_standqty` | FUEL_MIX_STORESCHEME | 名字里带字段码 | — | 改名 |
| 31 | 皮带操作记录COUNT合计 | `sum_fuel_stg_beltoperation_count` | FUEL_STG_BELTOPERATION | 名字里带字段码 | — | 改名 |

## 汇总

- 有留出题被抢答的指标：**1 个**（优先停用/改名）
- 仅命名不规范的指标：30 个（可批量改名）
