# 留出集 v1（holdout-v1）

> 目的：给一个**没被调优过**的准确率。现有 105 题里 57 道能找到近似 few-shot、4 道原题就在
> 示例库、5 道 gold 与指标模板相同、3 道 gold 事后改过 —— 那 99% 只能当「样本内上限」。
> 本文件由 `backend/scripts/seed_holdout_set.py` 生成/维护，题目清单以脚本为准。

## 一、冻结条款（写死，后续不许破）

1. **只用没被污染的表**：不出现在任何 `gold_sql` / 指标 `sql_template` / few-shot `sql` 里，
   也不是 `seed_*` 脚本造过数据的表（数据是副本库自带的真实行）。
2. 题目**不进 few-shot**、不建指标、不加术语；跑之前冻结规则/指标/术语。
3. 跑完**不许按错题反改**。要修只能修「通用缺陷」，且必须用别的表验证，不能针对这几道题改。
4. 金标一律带 `ISDELETED = false`（问「已删除」的除外），与平台软删口径一致。

## 二、数据与规模

| 项 | 值 |
|----|----|
| 数据源 | `ds:6`（本地副本 `ezdcs_yuanmei`） |
| 数据集标记 | `dataset = 'holdout-v1'`（`ai_query_testcase`） |
| 题量 | **47** |
| 覆盖表 | **11 张**（均为副本库自带、从未被 gold/few-shot/指标引用） |
| 题目指纹 | `ddaf882848def329`（题面排序后 sha1 前 16 位，用于证明「跑的是同一套题」） |
| 难度 | 简单 27 / 中等 17 / 较难 3 |
| 题型 | 计数 9、分组聚合 9、条件筛选 8、求和 6、去重 6、单维聚合 5、时间窗口 3、排序 1 |

覆盖表：`FUEL_CMCS_STATION`、`FUEL_CMCS_ASSAYCHECKSUGGESTION`、`FUEL_MIX_LOADPLANDETAIL`、
`FUEL_CMCS_TRANSPORTPLANDETAIL`、`FUEL_CMCS_PURCHASEPLANDETAIL`、`FUEL_STG_FUELSTORAGEAREA`、
`FUEL_MIX_BUNKERREALTIME`、`FUEL_CMCS_TRANSPORTPLAN`、`FUEL_CMCS_BELTMODEL`、
`FUEL_STG_CONTROLLOG_CHANGEHISTORY`、`FUEL_STG_DAYCOALINFO`。

## 三、怎么跑

```bash
cd backend
# 1) 只校验金标（不写库）：逐条执行，确认没有空结果/全空值
uv run python scripts/seed_holdout_set.py --check
# 2) 落库（幂等，按 (datasource,question) upsert）
uv run python scripts/seed_holdout_set.py --apply
# 3) 跑留出集（平台默认口径：few-shot + 快路径；示例库经验证不含这些表）
uv run python scripts/run_eval_once.py --run-limit=50 --dataset=holdout-v1 --datasource=ds:6
```

## 四、泄漏检查（每次 `--apply` 都会做）

- **原题命中 0 条**：47 道题面都不在 few-shot 里。
- **示例 SQL 用到留出集的表 0 条**：按 `FROM/JOIN` 后的表名比对（不按问句相似度——
  这些题都是「X 一共有多少条」这类通用句式，相似度判会大量误报，实测 16/47）。

## 五、结果

**29 / 47 = 61.7%**（原生 run `ev_9f7300c28f50`，平台默认口径；冻结基线，未按错题做任何调优）

| 维度 | 结果 |
|------|------|
| 难度 | 简单 20/27（74.1%）、中等 6/17（35.3%）、较难 3/3（100%） |
| 题型 | 求和 6/6、条件筛选 6/8、去重 4/6、时间窗口 2/3、计数 5/9、单维聚合 2/5、分组聚合 3/9、排序 1/1 |

> 对照：同一套题的样本内口径是 97~99%。差 35 个点不是模型突然变笨，而是
> **样本内那 105 题的表都被描述过/被示例覆盖过**，而这里 11 张表从来没进过提示词。

### 失败归类（18 条）

| 类别 | 条数 | 典型现象 |
|------|------|----------|
| **指标快路径误劫持**（真缺陷，最严重） | 4 | 「装车计划明细有多少条」被绑定的 `FUEL_CMCS_PURCHASEPLANDETAIL.count(ID)` 抢走；「皮带型号」→ `FUEL_CMCS_BELT.count(ID)`；「运输计划平均煤量」→ `...avg(CARCOUNTS)`。错得很自信：fast 路径不出 SQL，直接给错数 |
| **表/字段语义消歧弱**（真缺陷） | 5 | `FUEL_CMCS_ASSAY` vs `ASSAYCHECKSUGGESTION`；`FUEL_CMCS_PLANDAY` vs `FUEL_STG_DAYCOALINFO`；`FUEL_CMCS_BELT` vs `BELTMODEL`；按 ID 分组而不是名称 |
| **健壮性**（真缺陷） | 3 | 2 条生成空 SQL 报错；1 条不该澄清却走了澄清 |
| **SQL 细节**（真缺陷） | 2 | 分组时把 NULL 当成一组（金标要求排除）；用 `STATIONID` 关联而不是 `DEPOSITSITENAME` |
| **我方出题/金标不严谨**（不是产品的错） | 4 | ①「取前 3 个排序号」题面没写并列时按排序号升序，金标却加了 tie-break；②「平均完成率」可指 `COMPLETIONRATE` 字段或 `完成量/采购量` 计算（两值 21.53 vs 144.48）；③「多少个不同机组」按 ID 是 9、按名称是 6；④「按皮带统计」金标返回 UUID，不如模型返回的皮带名 |

**结论**：产品真实短板集中在 **「这张表/这个字段到底指什么」**（消歧与业务语义），
而不是 SQL 语法——这正好是本体/资产描述/术语该解决的问题，而不是加 few-shot 能解决的。

### 后续纪律

- 上面 4 条「我方不严谨」的题**不许**用来判产品；修正题面后应进 v2，而不是拿来给 v1 改分。
- 修任何通用缺陷后重跑 v1 必须标注「题目已看过」，不能与 61.7% 的冻结基线混为一谈。


## 六、判读规则

- 留出集分数**不应**低于公平口径（97~99%）太多。若明显偏低，先看是「表不认识」还是「口径不懂」：
  - 大量 `no such table` / 选错表 → schema 召回问题（该修检索/资产描述，不是加 few-shot 原题）；
  - 选对表但聚合/筛选写错 → 生成规则或字段语义问题；
  - 结果对但列名/顺序不同 → 比对口径问题（先确认真错还是误判）。
- 任何一次「针对留出集」的修复都会让这套题失效，必须另建 v2 重来。
