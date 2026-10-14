# 接入一个真实业务库（燃煤业务库 EZDCSZHMC）

本篇记录把**外部 PostgreSQL 业务库**接进问数 + 本体的完整过程、踩到的坑、以及现状。
它同时是一份**接新库的操作手册**——照这个顺序做，能避开我们踩过的所有坑。

## 一、这次接的是什么

| 项 | 值 |
|---|---|
| 数据源编码 | `ezdcs_pg` |
| 显示名称 | 燃煤业务库 |
| 主机 / 端口 | `172.168.100.214:5433` |
| 数据库 | `EZDCSZHMC`（**不是** `EZDCSTHMC`，截图里那个是错字，连不上） |
| 版本 | PostgreSQL 18.4 (Windows) |
| 规模 | **311 张表 / 331 个可查对象 / 7000+ 字段** |
| 业务 | 燃煤采购结算、煤款、化验、购煤运输、设备（CMMS/CMCS） |

## 二、接进来的完整链路

```
① 注册数据源         POST /ai/query/datasources/save
② 同步表结构（含注释） POST /ai/query/datasources/{id}/sync-schema
③ 批量导入本体        POST /ai/query/ontology/import-from-ds/batch
④ 问数                POST /ai/query/ask  {"question": "...", "datasource": "ds:4"}
```

**实测结果**：问「化验表里有多少条记录」→
`SELECT COUNT(*) AS 记录数 FROM "FUEL_CMCS_ASSAY"` → **2527 行**（真实数据）。

## 三、关键认知：**中文注释才是语义**

这个库的表名列名**全是英文缩写**：

| 表 / 列 | 注释（业务含义） |
|---|---|
| `FUEL_CB_COALBALANCE` | **燃煤采购结算主表** |
| `FUEL_CB_COALCONTRACT` | 燃煤合同主表 |
| `FUEL_CMCS_ASSAY` | 化验表 |
| `COALMONEY` | **煤款金额** |
| `COALPRICE` | 含税煤款单价 |
| `BALANCEQTY` | 结算数量 |
| `MARGINQTY` | 盈亏量 |

中文问题（"煤款金额是多少"）**只可能靠注释匹配到 `COALMONEY`**。
不读注释，模型只能瞎猜——实测它编出了 `coal_amount`、`coal_balance`
这种**根本不存在的表名列名**，问数必然答错。

**结论：接一个中文业务库，注释就是本体的语义来源，不是"锦上添花"。**

## 四、这轮修掉的 6 个缺陷

| # | 缺陷 | 后果 |
|---|---|---|
| 45 | `introspect_schema` 的 Postgres 分支把 **`column_default`（默认值）当成注释** | 注释**从来没被读过**，本体属性名全是英文，模型只能编列名 |
| 46 | 导入本体时**不写 `datasource_id` / `backing_table`** | 本体只知道"有这么个对象"，问数不知道去哪儿查数据 |
| 47 | 导入时用**英文列名同时当 code 和 name** | 本体零中文语义 |
| 48 | `_build_schema_context` 对**自定义数据源完全不加表结构** | 模型对 ds:{id} 一张表一个字段都不知道 |
| 49 | `_relevant_tables` 打分**只取 `(` 前的英文名** | 中文注释不参与检索，永远命中不了 |
| 50 | `execute_select` 不返回 `took_ms`，调用方裸取 `res["took_ms"]` | 外部数据源问数**必然 KeyError → 400** |
| 51 | 控制器把模块级函数 `test_datasource_conn` 当类方法调 | 页面上「测试连接」按钮**一直是坏的**（AttributeError） |

## 五、现在能做到什么

| 能力 | 状态 |
|---|---|
| 数据源注册 / 测试连接 | ✅（「测试连接」本轮才修好） |
| 表结构同步（表注释 + 列注释） | ✅ 331 张 |
| 导入本体（对象名 = 表注释，属性名 = 列注释） | ✅ 331 对象 / 8522 属性，**194 个拿到中文名** |
| 问数按问题检索相关表（331 张里挑 top_k） | ✅ 中文注释参与打分 |
| 远端只读执行（白名单 + 只读校验） | ✅ 实测 2527 行真实数据 |
| 问数答案人话化 / 列头中文化 | ✅ |

## 六、已知边界（诚实说明）

- **194 / 331 个对象有中文名**，其余表本身没写表注释，对象名只能退回英文表名。
- **本体的实例层（对象视图、实例检索）对远端对象是"未物化"状态**：
  导入时会建一张本地空镜像表 `ont_{table}`，数据**不在**本地。
  远端对象的实例浏览目前**没有做**——本体的实例能力仍只对本地表有效。
- **远端对象没有行级/列级权限策略**。`secure_sql` 的重写只作用于本地本体表；
  `ds:{id}` 走的是 `_execute_custom_ds_sql`，只做白名单 + 只读校验。
  **给这个库配数据权限目前做不到**，只有数据源级的角色授权（`_assert_ds_access`）。
- **检索是关键词打分，不是语义检索**。中文注释命中权重最高，但表述差异大时
  （问"拉了多少煤"而注释写"结算数量"）仍会漏。这需要别名/术语表补充。
- **311 张表的业务关系（外键）没有导入成本体 link**，跨表联查只能靠模型自己判断。
- **没有做表的业务分组/分层**，问数面对 331 张表时检索质量会随库的规模下降。
- `FUEL_CB_COALBALANCE` 这张主表**本身是空的**（0 行），不是接入问题。

## 七、接新库的标准动作（照做即可）

```bash
# 1) 注册（注意数据库名要跟服务端 pg_database 对一遍，别信截图）
POST /api/v1/ai/query/datasources/save
  {"name":"...","code":"...","type":"postgres","host":"...","port":5433,
   "database":"...","username":"...","password":"...","read_only":true}

# 2) 确认连接（这一步会真的连一次）
POST /api/v1/ai/query/datasources/{id}/test

# 3) 同步表结构（含中文注释，务必在导入本体之前）
POST /api/v1/ai/query/datasources/{id}/sync-schema

# 4) 导入本体
POST /api/v1/ai/query/ontology/import-from-ds/batch
  {"datasource_id": <id>, "include_technical": false}

# 5) 抽查：本体对象名是不是中文、属性名是不是中文
SELECT code, name FROM ai_ont_object WHERE datasource_id=<id> AND is_deleted=false LIMIT 10;
SELECT code, name FROM ai_ont_property WHERE object_code='<表名>' AND is_deleted=false LIMIT 10;

# 6) 问一句真实的业务问题，确认 SQL 用的是**真实表名**而不是编的
POST /api/v1/ai/query/ask  {"question":"...", "datasource":"ds:<id>"}
```

**第 5 步不能跳**：如果对象名/属性名还是英文，说明注释没同步到，
后面问数一定答错——先回去查 `ai_query_schema` 里的 `comment` 字段。

## 八、下一步该做什么（按性价比排序）

1. **给远端对象补别名/术语表**——把"拉了多少煤"这类口语映射到 `BALANCEQTY`，
   直接提升检索命中率，成本最低。
2. **远端对象的实例浏览**——现在本体 UI 里点这些对象是空的（未物化），
   要么明确标注"远端对象，不支持下钻"，要么接上远端查询。
3. **导入外键关系成本体 link**——311 张表的联查现在全靠模型猜。
4. **远端对象的权限策略**——目前完全没有，是安全上的真实缺口。
