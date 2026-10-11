# ds:4（燃煤外部库）缺数据清单

> 由 `backend/scripts/ds4_missing_data_report.py` 生成（表行数取自目标库实时统计）。
> 用途：把「业务表但 0 行」的表交给人工补数 —— 空表会让评测题退化为「任何 SQL 都算对」，指标也不可用。

## 总览

- 目标库表（base table）：**311**
- 业务表：**192**，其中有数据 **99**、**0 行 93**
- 已移出范围的技术/系统表：**119**

## 已移出范围（技术/系统表，不参与检索）

`SYS_*`、`EFMigrationsHistory`、`*_BAK/_LOG/_HISTORY`、`JIMU_*`、`OPS_*`、`QUALITYENCRYPT`、`QUANTITYENCRYPT` 等 —— 详见 `python scripts/ds4_table_scope_report.py --csv out.csv`。

## 缺数据（业务表 0 行，按子域）

### 入炉与耗用（1 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_INFURNACEHISTORY` | 入炉煤历史 |

### 其它业务（10 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_APPLETCONFIG` | 小程序参数配置 |
| `FUEL_CMCS_APPREMOTECONTROLCMD` | 程序远程控制命令 |
| `FUEL_CMCS_CONFIRMOPERATIONLOG` | 操作日志确认记录表 |
| `FUEL_CMCS_INFACTORYBATCHEDIT` | 入厂煤批次信息主表(超级修改记录表) |
| `FUEL_CMCS_SUPEREDITAPPLY` | 超级修改申请表 |
| `FUEL_CMCS_TRAINTYPE` | 火车车型管理 |
| `FUEL_INF_QCJXCYUNLOADCMD` | 汽车采样机接口-卸样命令 |
| `GEN_JSONCONFIG` |  |
| `GEN_JSONOBJECT` |  |
| `RPT_INDEX` | 报表指标 |

### 化验与煤质（8 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_ELEMENTASSAY` | 元素分析仪化验指标标准数据表 |
| `FUEL_CMCS_HEATASSAY` | 标准量热仪数据 |
| `FUEL_CMCS_MOISTUREASSAY` | 水分仪化验指标标准数据表 |
| `FUEL_CMCS_PROXIMATEASSAY` | 工分仪化验指标标准数据表 |
| `FUEL_CMCS_SULFURASSAY` | 测硫仪化验指标标准数据表 |
| `FUEL_CMCS_TEMPERATUREBARHISTROY` | 红外测温仪历史数据 |
| `FUEL_CMCS_TEMPERATUREERRORIMAGE` | 红外测温仪图片 |
| `FUEL_MIX_HEATEFFICIENCY` | 锅炉热效率计算 |

### 煤场与库存（16 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_OUTCOALBUNKER` | 出仓煤记录 |
| `FUEL_MIX_COALCONFIGCALC` | 配煤数据计算主表 |
| `FUEL_MIX_COALCONFIGCALCDETAIL` | 配煤数据计算-分炉明细表 |
| `FUEL_MIX_COALCONFIGCALCSTORAGEDETAIL` | 配煤数据计算-存煤明细表 |
| `FUEL_MIX_MUTERCOALSETTING` | 配仓方案-互斥煤种 |
| `FUEL_MIX_RAWCOALBUNKERSETTING` | 机组加仓方案设置 |
| `FUEL_STG_CONTROLLOG_CHANGEHISTORY` | 控制日志变更历史 |
| `FUEL_STG_DLJCMD` | 斗轮机执行计划主表 |
| `FUEL_STG_FUELEARLYWARNING` | 煤场预警主表 |
| `FUEL_STG_FUELEARLYWARNINGDETAIL` | 煤场预警明细 |
| `FUEL_STG_FUELTRANSFER` | 煤场移库表 |
| `FUEL_STG_OUTMINQTY` | 煤场最小刻度取煤记录（暂不使用） |
| `FUEL_STG_PMYCMDRESULT` | 盘煤仪执行计划执行结果表 |
| `FUEL_STG_RATIOINFO` | 配比信息 |
| `FUEL_STG_STORAGETOSILODETAIL` | 煤场入筒仓指令明细 |
| `FUEL_STG_WARNMESSAGE` | 煤场预警信息 |

### 组织与基础（9 张）

| 表名 | 表注释 |
|------|--------|
| `CMMS_CANVAS` | 组态画面 |
| `CMMS_CANVASCLASSIFICATION` | 组态画面分类 |
| `CMMS_CANVASCOMPONENT` | 组态画面所引用的组件 |
| `CMMS_COMPONENT` | 组件 |
| `CMMS_COMPONENTCLASSIFICATION` | 组件分类 |
| `CMMS_FACILITY` | 设备设施信息 |
| `EQUIPMENT` |  |
| `FR_PERSONNELINFO` | 人脸识别-人员信息 |
| `FR_PERSONNELPHOTO` | 人脸识别-人员照片 |

### 计划与报表（8 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_PLANDAY` | 日计划主表 |
| `FUEL_CMCS_PLANDAYDETAIL` | 日计划明细表 |
| `FUEL_CMCS_PLANMONTH` | 月计划主表 |
| `FUEL_CMCS_PLANMONTHDETAIL` | 月计划明细 |
| `FUEL_CMCS_PLANYEAR` | 年计划主表 |
| `FUEL_CMCS_PLANYEARDETAIL` | 年计划明细 |
| `RPT_REPORT` |  |
| `RPT_REPORTCLASSIFICATION` |  |

### 运输与计量（12 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_AUTOTRUCK` | 车辆登记管理 |
| `FUEL_CMCS_CARBLACKLIST` | 车辆黑名单 |
| `FUEL_CMCS_EPCCARD` | 标签卡 |
| `FUEL_CMCS_GOODSTRANSPORT` | 汽车入厂记录表(其他物资) |
| `FUEL_CMCS_GOODSTYPE` | 汽车智能化-物资类型 |
| `FUEL_CMCS_SIGNALDATA` | 实时信号表 |
| `FUEL_CMCS_TRAINWEIGHTRECORD` | 火车车厢入厂记录表 |
| `FUEL_CMCS_TRANSPORTEDIT` | 入厂煤批次明细表(超级修改记录表) |
| `FUEL_CMCS_TRANSPORTPICTURE` | 汽车入厂图片 |
| `FUEL_CMCS_TRUCKINFACTORYWAY` | 车辆入场路线 |
| `FUEL_CMCS_TRUCKINFACTORYWAYDETAIL` | 车辆入场路线明细 |
| `FUEL_CMCS_UNFINISHTRANSPORT` | 未完成运输记录表 |

### 采样制样（14 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CMCS_MAKEDETAIL` | 制样单明细表 |
| `FUEL_CMCS_RCCOALSAMPLING` | 煤样抽检信息 |
| `FUEL_CMCS_RLSAMPLINGDETAIL` | 入炉煤采样明细表 |
| `FUEL_CMCS_SAMPLEBARREL` | 样桶管理 |
| `FUEL_CMCS_SAMPLECLEAR` | 智能存样柜销样主表 |
| `FUEL_CMCS_SAMPLECLEARDETAIL` | 智能存样柜销样明细表 |
| `FUEL_CMCS_SAMPLEINPUT` | 智能存样柜--存样记录 |
| `FUEL_CMCS_SAMPLEINPUTHISTORY` | 智能存样柜--存样柜存取历史记录 |
| `FUEL_CMCS_SAMPLETAKE` | 智能存样柜--取样主表记录 |
| `FUEL_CMCS_SAMPLETAKEDETAIL` | 智能存样柜--取样明细记录（智能存样柜是同步过来的，数据根据编码查询，不根据ID查询） |
| `FUEL_INF_BELTSAMPLEUNLOADCMD` | 皮带采样机接口-卸样命令 |
| `FUEL_INF_EQUINFSAMPLEBARREL` | 第三方设备接口 - 实时集样罐表 |
| `FUEL_INF_MAKERCONTROLCMD` | 制样接口 - 制样命令 |
| `FUEL_INF_MAKERPLAN` | 全自动制样接口 - 制样计划 |

### 采购与结算（15 张）

| 表名 | 表注释 |
|------|--------|
| `FUEL_CB_COALBALANCE` | 燃煤采购结算主表 |
| `FUEL_CB_COALBALANCEDETAIL` | 燃煤采购结算明细表 |
| `FUEL_CB_COALBALANCEDETAILBATCH` | 燃煤采购结算明细批次信息表 |
| `FUEL_CB_COALCONTRACT` | 燃煤合同主表 |
| `FUEL_CB_COALCONTRACTQUALITY` | 合同煤质约束表 |
| `FUEL_CB_CONTRACTTEMPITEM` | 量价条款主表 |
| `FUEL_CB_CONTRACTTEMPITEMZONE` | 量质考核条款明细 |
| `FUEL_CB_QUALITYSETTING` | 合同结算煤质指标表 |
| `FUEL_CMCS_BUYFUELTRANSPORT` | 汽车智能化-入厂煤运输记录 |
| `FUEL_CMCS_BUYFUELTRANSPORTDEDUCT` | 汽车智能化-扣吨记录 |
| `FUEL_CMCS_MZSTORAGEQTYSET` | 煤种存煤警报线 |
| `FUEL_CMCS_OPTSUPPLIERHISTORY` | 寻优供应商可供煤炭信息历史 |
| `FUEL_CMCS_PURCHASEMONTH` | 采购寻优主表 |
| `FUEL_CMCS_PURCHASEMONTHDETAIL` | 采购寻优明细 |
| `FUEL_CMCS_PURCHASEMONTHINFURNACE` | 采购寻优 煤场入炉明细 |

## 补数优先级建议

1. **采购与结算**（`FUEL_CB_COALBALANCE` / `FUEL_CB_COALCONTRACT` 等）——现有 4 个指标里有 3 个直接建在这些表上，全为 0 行，指标目前返回 NULL；这也是评测集里「平均合同单价/结算总量」等题的来源。
2. **化验与煤质**（`FUEL_CMCS_FUELQUALITY` 等）——`avg_lf`/`avg_rz` 两个指标依赖的`DTXY_PMXX` 有 77 行但 `LF/RZ` 是**文本**列，需要补可数值化的数据或改指标口径。
3. **煤场与库存 / 入炉与耗用**（`FUEL_CMCS_INCOALHISTORY` 已有 118 万行，但 `FUEL_CMCS_INCOALBUNKER` 之外的明细多为空）——库存/耗用类问题的数据基础。
4. **计划与报表**——计划/报表类问题（月报/日报）几乎全空。

## 有数据的业务表（Top 20，评测与指标的可用基础）

| 表名 | 行数 |
|------|------|
| `FUEL_CMCS_INCOALHISTORY` | 1,189,438 |
| `FUEL_SIS_BELTSIGNALDATA` | 55,557 |
| `FUEL_CMCS_INCOALBUNKER` | 41,721 |
| `FUEL_STG_ALLOUTMIDDLE` | 26,498 |
| `FUEL_STG_BELTOPERATION` | 16,774 |
| `FUEL_REPORT_DAYCOALSTORAGELEDGER` | 13,284 |
| `FUEL_CMCS_INFURNACEDETAIL` | 13,005 |
| `FUEL_REPORT_INCOALBUNKER` | 6,744 |
| `FUEL_CMCS_TRANSPORT` | 5,849 |
| `FUEL_STG_ALLINMIDDLE` | 5,710 |
| `FUEL_STG_INMINQTY` | 4,389 |
| `FUEL_CMCS_INSILOHISTORY` | 4,053 |
| `FUEL_REPORT_DAYINOUTSTORAGE` | 3,702 |
| `FUEL_STG_CONTROLLOGDETAIL` | 3,313 |
| `FUEL_STG_STORAGETOSILO` | 2,973 |
| `FUEL_CMCS_MAKE` | 2,851 |
| `FUEL_CMCS_FUELQUALITY` | 2,844 |
| `FUEL_CMCS_ASSAY` | 2,527 |
| `FUEL_STG_DEPOSIT` | 2,269 |
| `FUEL_CMCS_INFURNACE` | 1,558 |
