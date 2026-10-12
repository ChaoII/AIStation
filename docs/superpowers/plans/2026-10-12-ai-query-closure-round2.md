# 问数闭环补全（第二轮）— 计划

> 用户要求：**逻辑连贯 / 完善 / 闭环**，且**界面友好、美观**。
> 前置：`docs/superpowers/specs/2026-10-11-ai-query-report-and-clarify-design.md`（§10 已 A/B 结论）。

## 取证结论（本轮开工前）

| 缺口 | 证据 | 性质 |
|---|---|---|
| 报表**参数永远为空** | `submitSaveReport` 只发 `key/name/sql/columns`，**不发 params** → 库里 `params=[]` → 运行弹窗永远显示"该报表无需参数"（表单是死的） | 半接线 |
| 参数**无定义、无校验** | `_render_template` 只做正则替换；缺参数时 `m.group(0)` 原样留下 `{key}` → 直接把 `{key}` 发给数据库（语法错/注入面） | 逻辑不闭环 |
| 「本轮召回的表」**看不到** | 前端只读 `m.evidence.retrieved_tables`（快路径恒空、历史消息无该字段）；而**落库的** `m.grounding.retrieved.tables` 没被用 | 半接线 |
| 本体 ↔ 问数**只有单向** | 问数提示语说"复用本体语义/权限"，但**没有**跳到本体的入口；本体页也没有"去问数验证" | 闭环缺口 |

## 任务

### A. 报表参数闭环（后端为主）
1. `report.py` 新增 `extract_params(sql_template)`：从 `{key}` 抽取参数定义
   `{key,label,type,required,default}`；类型推断（数值比较/`LIMIT` 上下文 → `number`，否则 `text`）。
2. `upsert_report`：`params` 为空时**自动抽取**并落库（人工可覆盖）。
3. `run_report`：**运行前校验**（缺必填 / 空值 / 类型不符 → 明确报错）；
   渲染后**兜底检查**残留 `{key}` → 报错，绝不把 `{key}` 发给数据库。
4. 前端报表页：参数**定义编辑器**（增删改 key/label/type/required/default），
   运行弹窗按 `type` 渲染 `el-input-number` / `el-date-picker` / `el-input`，必填标记。

### B. 问数 ↔ 本体 双向可见（前端）
5. `recalledOf(m)` 改为优先读**落库的** `m.grounding.retrieved.tables`，兼容 `m.evidence`；
   另显示 `m.grounding.ontology_used`（本体对象）。
6. 问数页提示语加「查看本体」链接；本体页加「去问数验证」入口 → **双向闭环**。

### C. 界面
7. 统一用 Element Plus 原生组件与 `--el-*` 变量；不写死字号/主题色；弹窗宽度 520/720 档位。

### D. 验证
8. 单测：`extract_params` / 参数校验 / 残留占位兜底（`PYTEST_NO_APP=1` 快速跑）。
9. 回归：`test_query_report.py` + `test_query*.py`。
10. `pnpm run type-check` + Playwright 截图**读图**核对（问数页 / 报表页 / 参数弹窗）。

## 明确不做（避免范围膨胀）
- 不做"从字面量自动猜参数"（魔法，易错）。
- 不改动已 A/B 否掉的两个方案（错题沉淀、两段式分解）。
