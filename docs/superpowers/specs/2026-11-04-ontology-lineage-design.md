# 本体血缘与影响分析（第一步：表级）— 设计

日期：2026-11-04
状态：待评审
范围：`module_ai/query` 的数据资产血缘；为 `module_ai/ontology` 的治理能力提供数据基础

## 1. 背景

治理方向选的是「血缘 / 影响分析 / 敏感标记」。实测发现**功能都在、数据几乎没有**：

| 项 | 现状 |
|---|---|
| 影响分析接口 `/assets/{table}/impact` | 有 |
| 血缘传播 `/assets/{table}/lineage` | 有 |
| 前端血缘图（`OntDecisionView`） | 有 |
| 血缘实际覆盖 | **75 / 15327 列 = 0.5%** |
| 资源 ACL | 1 条 |

根因不是"没写"，是**血缘只有一条产生途径：人工维护的外键字段**
（`ai_query_asset_columns.related_table`），而燃料库几乎没有真实外键约束。

### 只读探测（2026-11-04，ds:4）

331 张表 / 7021 列，三种自动来源 + 使用血缘的结果：

| 来源 | 覆盖列 | 说明 |
|---|---|---|
| 视图依赖（`information_schema.views` + sqlglot） | 355 | 20 个视图，最大来源 |
| 命名约定（`XXXID` → 表 `*XXX`） | 246 | 仅"唯一匹配"才计入 |
| 使用血缘（指标 / 报表 / 历史问数 SQL） | 73 | 列名匹配过糙，明显低估 |
| 数据库真外键 | 29 | 全库只有 16 条 FK 约束 |
| **合计（去重）** | **678 列 = 9.7%** | 表级：181 / 331 = **54.7%** |

结论：**表级血缘零维护就能到 54.7%，足够支撑"改这张表会影响谁"；
列级只有 9.7%，瓶颈在 SQL 列解析太糙 —— 那是第二步。**

## 2. 目标与非目标

**目标（第一步）**

1. 血缘自动产生并落库，`schema 同步时重算`，无需人工维护
2. 表级影响分析可用：给定一张表，能答出"哪些指标 / 报表 / 视图 / 对象 依赖它"
3. 覆盖率可见：多少表/列有血缘、按来源分布
4. 全程可回退（一个开关），不改变既有接口的返回结构（只增字段）

**非目标（第一步不做）**

- 列级 SQL 深度解析（`SELECT *` 展开、别名、CTE）—— 第二步，凭第一步数据再定
- 敏感字段沿血缘自动传播与强制脱敏 —— 第二步
- 前端血缘图重做 —— 复用现有图，只加覆盖率看板
- 跨数据源血缘 —— 单数据源内成立即可

## 3. 数据模型

新表（插件表，`CREATE TABLE IF NOT EXISTS`，不走 alembic —— 与
`ai_query_kg_relation` 一致，避免 autogenerate 误删历史表）：

```sql
CREATE TABLE IF NOT EXISTS ai_query_lineage (
    id            BIGSERIAL PRIMARY KEY,
    datasource    VARCHAR(64)  NOT NULL,          -- ds:4
    kind          VARCHAR(16)  NOT NULL,          -- fk | view | name | usage
    src_table     VARCHAR(128) NOT NULL,
    src_column    VARCHAR(128),                   -- NULL = 表级
    dst_table     VARCHAR(128),                   -- usage 边为 NULL
    dst_column    VARCHAR(128),
    ref_kind      VARCHAR(16),                    -- usage: metric | report | ask | object
    ref_key       VARCHAR(255),                   -- 指标 key / 报表 key / 会话 id
    confidence    REAL         NOT NULL DEFAULT 1.0,
    is_deleted    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_time  TIMESTAMP    NOT NULL DEFAULT now(),
    updated_time  TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_query_lineage
  ON ai_query_lineage (datasource, kind, src_table,
                       COALESCE(src_column,''), COALESCE(dst_table,''),
                       COALESCE(dst_column,''), COALESCE(ref_key,''));
CREATE INDEX IF NOT EXISTS ix_ai_query_lineage_src ON ai_query_lineage (datasource, src_table);
CREATE INDEX IF NOT EXISTS ix_ai_query_lineage_dst ON ai_query_lineage (datasource, dst_table);
```

**边的方向统一为 `src → dst`**（"上游 → 下游"）：

| kind | src | dst | 置信度 |
|---|---|---|---|
| `fk` | 子表.外键列 | 父表.被引用列 | 1.0 |
| `view` | 视图.列 | 基表.同名列 | 0.9 |
| `name` | 表.`XXXID` | 候选表.`ID` | 0.6 |
| `usage` | 表.列 | NULL（用 `ref_kind/ref_key` 表示"被谁用"） | 1.0 |

`name` 只收**唯一匹配**：`INFACTORYBATCHID` 去掉 `ID` 后若只有一张表以其结尾才计入，
避免 `ID`/`USERID` 这类通用列乱连（实测唯一匹配命中 246 条，多匹配全部丢弃）。

## 4. 重算流程

`module_ai/query/lineage.py`：

```python
async def rebuild_lineage(datasource_id: int) -> dict:
    """幂等：先按 datasource 清空，再按四个来源重建。返回各来源条数。"""
```

- **触发点 1**：`sync_datasource_schema()` 末尾调用（同步 331 张表本来就要几秒，
  血缘重算是同一量级；失败只记 warning，**不能让同步失败**）
- **触发点 2**：手动 `POST /ai/query/lineage/rebuild?datasource=ds:4`（运维/首次回填）
- **触发点 3**：指标/报表保存后**不重算全量**（太贵）。`rebuild_lineage` 本身会把
  `usage` 边一起算出来；新增的指标/报表要等下次同步或手动 rebuild 才进血缘。
  第一步接受这个延迟，不做增量。

成本实测（只读探测）：331 表 + 20 视图 + 146 指标 + 3000 条历史 SQL ≈ 10 秒级。

## 5. 接口改造

### 5.1 影响分析（只增字段，不破坏既有返回）

`GET /ai/query/assets/{table_name}/impact` 增加：

```json
{
  "lineage": {
    "upstream":   [{"table": "...", "kind": "fk", "confidence": 1.0}],
    "downstream": [{"table": "...", "kind": "view", "confidence": 0.9}],
    "used_by":    [{"ref_kind": "metric", "ref_key": "sum_fuel_xxx", "kind": "usage"}],
    "sensitive_columns": ["COALMONEY"]
  }
}
```

`sensitive_columns` 的定义：该表被标敏感的列，来源是两处元数据的并集 ——
`ai_query_asset_columns.sensitive` 与 `ai_ont_property.sensitive`（后者按
`ai_ont_object.backing_table` 关联到本表）。**第一步只"展示"，不传播、不阻断**。

开关 `lineage_enabled`（默认 **false**，与项目"新开关先给入口与默认值"一致）：
关闭时返回空数组，旧字段（`metrics` / `incoming_relations` / `object_links`）保持原样。
第一步交付后人工核对 3 张表再决定是否默认开启。

### 5.2 覆盖率

`GET /ai/query/lineage/coverage?datasource=ds:4`

```json
{"tables_total": 331, "tables_with_edges": 181, "columns_total": 7021,
 "columns_with_edges": 678, "by_kind": {"view": 355, "name": 246, "usage": 73, "fk": 29}}
```

前端：在现有血缘图页签旁加一行统计（不新做页面）。

## 6. 数据质量规则

1. **宁缺勿错**：命名约定只收唯一匹配；视图同名匹配才计入；解析失败的 SQL 直接跳过并计数。
2. **不覆盖人工数据**：`ai_query_asset_columns.related_table` 保持人工权威；
   血缘表只读产出，不写回人工字段。
3. `usage` 边的 `ref_key` 对历史问数取 `ai_query_messages.id`，前端能点回原问题。

## 7. 测试

| 类型 | 内容 |
|---|---|
| 单测 | 四个来源各一条（构造最小 schema + SQL）；唯一匹配/多匹配丢弃；幂等（跑两次条数不变）；SQL 解析失败不抛 |
| 单测 | 影响分析在读开关关闭时返回空 lineage、旧字段不变 |
| 集成 | `rebuild_lineage(4)` 后 `coverage` 数字 > 0；表级覆盖 ≥ 50%（与探测一致） |
| 冒烟 | 现有 `query_smoke.py` 不受影响（不碰问数主链） |

## 8. 风险与回滚

| 风险 | 处理 |
|---|---|
| 血缘连错，影响分析给错答案 | 置信度 + `kind` 全部展示；开关默认关；人工核对后再开 |
| 同步变慢 | 重算 try/except；失败仅 warning；必要时挪到 BackgroundTasks |
| 表无人维护变脏 | 幂等重建（每次全量覆盖），不做增量累积 |

回滚：`lineage_enabled=false` 即恢复旧行为；彻底删除只需 `DROP TABLE ai_query_lineage`，
不涉及既有表结构。

## 9. 验收标准

1. `POST /lineage/rebuild?datasource=ds:4` 返回各来源条数，总边数 > 500
   （探测口径：678 个被覆盖列，边数按「列×来源」计，必然更多）
2. `GET /lineage/coverage?datasource=ds:4`：`tables_with_edges / tables_total ≥ 50%`
3. 任取 3 张业务表（如 `FUEL_CMCS_INFACTORYBATCH`、`FUEL_REPORT_DAYINOUTSTORAGE`、
   `DTXY_GYSKDGX`），影响分析能答出"依赖它的指标/视图/问数"，人工核对无误
4. 开关关闭时，接口返回与改造前**完全一致**
5. 单测全绿；`query_smoke.py` 完整模式通过
