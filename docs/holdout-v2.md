# 留出集 v2（holdout-v2）与「资产描述注入」A/B

> v1 见 `docs/holdout-v1.md`。v2 的目的不是再刷个分，而是给一个**能归因的对照实验**：
> 在「从没被题目/示例/指标用过」的表上，把资产目录里的中文名/描述注入提示词，到底有没有用。

## 一、数据集

| 项 | 值 |
|----|----|
| 数据源 | `ds:6` |
| 数据集标记 | `dataset = 'holdout-v2'` |
| 题量 | **37** |
| 覆盖表 | **12 张**：`FUEL_STG_FUELADJUSTMENT`、`FUEL_STG_STORAGEINITIALIZEDETAIL`、`FUEL_CMCS_FACTORYCOSTYEARDETAIL`、`FUEL_CMCS_FACTORYCOSTPOINT`、`FUEL_MIX_COALSCHEMEBUNKER`、`FUEL_CMCS_SUPPLIERQUALITYLIMIT`、`FUEL_MIX_COALSCHEMERESULT`、`FUEL_CMCS_ASSAYRECHECK`、`FUEL_STG_STORAGEINITIALIZE`、`FUEL_CMCS_PURCHASEPLAN`、`FUEL_CMCS_TRANSPORTTYPE`、`FUEL_STG_INVENTORYREPORT` |
| 题目指纹 | `4f66ce3c4b93f137` |
| 泄漏检查 | 原题命中 0；few-shot 示例 SQL 未使用这些表 0 |

> 这批表都很小（2~29 行），所以题目偏「口径 / 关联 / 空值」而非大数据量聚合。
> 生成/校验：`scripts/seed_holdout_set.py --dataset holdout-v2 --check|--apply`。

## 二、A/B 设计

| 臂 | 配置 | run |
|----|------|-----|
| **A 基线** | 资产目录已有中文名/描述，但**不注入**（`schema_asset_meta_enabled=false`，历史默认） | `ev_fac3da9aad46` |
| **B +描述注入** | 同一批题，打开注入（`schema_asset_meta_enabled=true`） | `ev_2e1e5ae431c7` |

两臂之间只改这一个开关；跑之前先补了 17 张缺描述的表（一般性回填，不是针对 v2 挑表）。

## 三、结果：**零翻转**

| 指标 | A | B |
|------|----|----|
| 数据准确率 | 21 / 37 = **56.76%** | 21 / 37 = **56.76%** |
| fixed / regressed / same | — | **0 / 0 / 37** |
| SQL 有变化 | — | 22/37 完全一致，15 条变了 |

**结论：注入资产中文名/描述没有带来任何一道题的翻转**（改写了 15 条 SQL，但结果对错不变）。
这与历史记录里「`schema_asset_meta_enabled` 开 vs 关无差异」的配对实验一致。

> 注意：这只证明「把描述塞进提示词」无效，**不等于**「业务语义没用」。
> 失败原因里，模型确实是因为「不知道这张表是什么」而选错表；问题在于**选表发生在召回阶段**，
> 提示词里出现描述时表已经选错了——描述来得太晚。

## 四、A 臂 16 条失败归因

| 类别 | 条数 | 现象 |
|------|------|------|
| **指标快路径误劫持** | 6 | 「配煤方案分仓明细」→ `配煤方案数量`；「供应商煤质限制」→ `供应商数量`；「配煤结果」→ `配煤方案…`；且指标 SQL 不带 `ISDELETED`（计数 5 vs 4） |
| **表消歧失败** | 7 | 「期初库存明细」→ `INVENTORYREPORTDETAIL`（应为 `STORAGEINITIALIZEDETAIL`）；「成本项目」→ `FACTORYCOSTYEAR` / `SYS_CODES` / `JIMU_DICT_ITEM`；「期初库存主表」→ 明细表 |
| 我方金标过严 | 1 | 「取前 3 个单据号」题面没写并列规则，金标加了 tie-break |
| 其它 | 2 | 空 SQL / 聚合口径不同 |

**真正的短板是两件事**：
1. **指标匹配把「通用词重合」当成「同一张表」**（计划/明细/数量/供应商）→ 快路径直接给错数，且不经过软删口径；
2. **召回阶段分不清同族表**（主表/明细、方案/方案明细、年份/项目），提示词里的描述救不回来。

## 五、下一步（C 臂）

1. **指标护栏**：绑定型指标（绑定到某张表的 count/avg）必须与问句在**该表的中文名/别名**上有重合，否则不参与快路径；通用词（计划/明细/数量/条数/记录/表/平均…）不算证据。
2. **软删口径**：指标快路径的 SQL 也要补 `ISDELETED = false`（现在只有慢路径补）。
3. 表消歧要**在召回层**解决（别名/描述参与检索打分），不是往提示词里加字。

验证纪律：v1 不复跑；v2 的 A/B 已完成并冻结；C 臂改完用 v2 复跑 + 105 题回归，结果标注「v2 题目已看过」。
