# 问数语义的「家」：哪些能配、哪些还写死在代码里

> 原则见 `AGENTS.md`「工程原则：语义/口径不写死在代码里」。
> 一句话判定：**改一条业务口径如果需要发版，它就放错了位置。**

## 一、已经可以维护（改库即可，无需发版）

| 内容 | 维护位置 | 已验证 |
|------|----------|--------|
| 业务术语 / 同义词（含字段级：全水分→`DTXY_PMXX.QSF`） | `ai_query_dictionary` | ✅ 全水分/热值/运损修复 |
| 指标口径（含绑定型 `object_code`+`agg_fn`） | `ai_query_metrics` | ✅ 库存 234,938 吨 |
| 表/字段业务含义、别名、枚举 | `ai_query_assets`、`ai_query_asset_columns` | ✅ 回填 17 张表中文名 |
| 对象/属性/关系/业务函数 | `ai_ont_object`/`property`/`link`/`action` | ✅ 本体页维护 |
| 表间关联/影响面 | `ai_query_lineage`（同步 schema 时重建） | ✅ 血缘页 |
| 提示词书写规范（别名/格式/占比/Top-N 空值） | `ai_query_prompt_rules` | ✅ 设置页「生成规则」 |
| 示例问答 | `ai_query_fewshot` | ✅ 评测/示例库 |
| **软删列名 + "已删除"说法** | `ai_query_datasources.filter_rules.softdelete`（`column` / `deletion_hints`） | ✅ 2026-11-12 迁移，默认 `ISDELETED`；单测 `test_query_softdelete_config.py` |
| 开关 / 阈值 / 实体映射 | `ai_query_settings` | ✅ 设置面板 |
| 权限（表/行/列/模块） | `ai_policy*` | ✅ `eval_permissions.py` 16/16 |

软删迁移的代码形态：`softdelete.apply_softdelete_policy(question, sql, schema_map, rules)`
（纯逻辑，规则来自数据源）→ 入口只有一处 `rewrite_generated_sql`，`execute_ops` 与
`assetio_ops` 不再各写一份。

## 二、还在代码里（按建议顺序迁移）

| 优先级 | 内容 | 现在在哪 | 建议去处 | 风险 |
|--------|------|----------|----------|------|
| P1 | **方言语法提示 + 时间口径**（"上周/本月"的 SQL 写法） | `dialect.py::DIALECTS` / `time_rules()` | 数据源 `filter_rules.dialect`（或 `ai_query_settings.dialect_time_rules` JSON） | 中：直接影响时间类问答，需按方言 A/B |
| P2 | **问句语言启发式**（计数诉求、物理量、排序、分组、全量列举、"多少条/多少笔"） | `metric_rules.py` 的 `COUNT_INTENT_RE` / `PHYSICAL_QTY_RE` / `ROWCOUNT_ASK_RE` / `ORDER_WORD_RE` / `AGG_NOUN_RE` / `GROUPING_RE`；`question_rules.py` 的 `LISTING_RE` / `COUNT_OVERRIDE_RE` / `TOP_N_RE` / `AGG_OVER_GROUPS_RE` / `ALL_LIST_HINTS` | `ai_query_settings.query_language_rules`（JSON：正则 + 词表），代码保留默认 | 高：牵动路由与快路径，必须先做 v2 基线再改 |
| P3 | 实体名词→表 默认映射 | `seed_data.py::_ENTITY_TABLE`（可被 `settings.entity_map` 覆盖） | 术语表（entity 类型）或保留为**种子**并注明 | 低：已有覆盖通道 |
| P4 | 敏感列默认集 | `allowlist.py` | 数据源 `filter_rules` 或策略表 | 中：涉及脱敏，改动要先跑权限评测 |
| P5 | 指标/术语/few-shot 的默认种子（`_SYSTEM_METRICS` 等） | `seed_data.py` | **保留为种子**（只在空库播种，之后以库为准） | 低：不算硬编码口径 |

## 三、明确留在代码里的（不是缺陷）

- **安全护栏**：`dialect.CORE_RULES`（只读 SELECT / 必须 FROM / 只用给定表）、
  `sqlguard.FORBIDDEN_RE`（禁 DDL/DML）、白名单校验、fail-closed 逻辑。
- **协议/错误处理**：重试、降级、超时、SSE 帧格式。
- **上表各项的默认值**：必须存在，且必须能被库里的配置覆盖（有单测）。

## 四、迁移模板（每迁一项照做）

1. 先把**默认值**从代码挪到一个函数（如 `softdelete_rules(None)`），保证行为不变；
2. 从正确的表/配置读覆盖（旧 JSON 不要求重存：逐键合并）；
3. 加单测：`默认生效` + `覆盖生效` + `坏配置回落默认`；
4. 跑 `pytest -k "query"` + `query_golden_smoke.py`；
5. 跑 105 题回归（准确率、快路径占比不降）后再提交。
