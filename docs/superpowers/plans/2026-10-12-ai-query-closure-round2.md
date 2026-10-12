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

## 追加：`decomposed_planning` 名不副实的闭环（2026-10-12）

**取证**：
| 开关 | 实际行为 | 结论 |
|---|---|---|
| `decomposed_planning`（默认**开**，UI 旧标签「分解式规划」） | **只在提示词里加一条**「先判断单表/联表/嵌套」，**不做真分解** | 名字夸大 |
| `two_stage_planning`（默认关） | **真分解**：`plan.py` 先出执行计划（JSON）→ 再据计划写 SQL，失败自动降级 | ⚠️ 旧 A/B 结论**作废**（见下） |

**决策**：真分解**已经存在且已被 A/B 判负**，不再造第三个分解（重复开已被禁止）。改为：
1. **改诚实名**：前端标签「分解式规划」→「**规划提示（单表/联表/嵌套）**」；
2. **注册表注释写实**：`decomposed_planning` 注明"仅提示词一条规则，**非真分解**"；
   `two_stage_planning` 注明"两段式**真分解**；旧 A/B 结论已作废（开关曾不生效）→ 待重测"；

## ⚠️ 本轮附带挖到并修掉的**真 bug**：`_cfg_bool` 让 default=False 的开关全部失效

**症状**：`two_stage_planning=true` + 多步题 → 规划阶段**从不被调用**（打桩验证：`_nl2sql` 被调用、SQL 生成成功，但 `plan` 桩 0 次）。

**根因**（`service.py`）：
```python
def _cfg_bool(cls, cfg, key, default=True):
    v = str(cfg.get(key, "true")).strip().lower()
    if v in ("0","false","no","off",""): return False
    return default          # ← 值为真时返回的是 default，不是 True
```
→ **凡是以 `default=False` 读取的开关永远不可能为真**：`two_stage_planning`、`agno_tool_agent`
（后者=工具化 Agent 多轮往返，也一直是死的）。

**修复**：显式值优先，只有 key 缺失/为空才回落 `default`。

**影响面审计**：库里 `two_stage_planning=false`、`agno_tool_agent=false`
（`scripts/_check_switch_values.py`）→ 修复**不改变当前默认行为**。

**连带勘误**：spec §10 里"两段式分解 −3.78 分"的 A/B 结论**作废**——当时开关根本没生效，
测的是噪声；需重测（默认关仅代表"未验证"）。

**防回归**：`test_cfg_bool_honours_explicit_true_even_with_default_false`（4 条断言）+ 打桩 e2e
（`scripts/_diag_two_stage.py`：桩掉规划 LLM，断言"规划阶段被调用=True"）。

**连带影响（诚实记录）**：消融清单里的 `agno_tool_agent` 也是以 `default=False` 读取的 →
它的"关"态**一直是默认态**，所以历史消融中该维度是 **baseline vs baseline**（"无差异"是假的）。
修复后该维度才有意义；其余 6 个以 `default=True` 读取的维度（关掉即测）不受影响。

3. **修陈旧文档**：`plan.py` docstring 原写 `decomposed_planning=true`（错）→ 改为 `two_stage_planning=true`；
4. **防回归测试**（`tests/test_query_eval.py`）：
   - `plan` 模块只能挂在 `two_stage_planning` 分支下；`decomposed_planning` 不得与真分解同现；
   - 注册表注释必须写明"提示"与 A/B 结论；
   - `plan.is_multistep` 严格触发（简单题不触发）+ `parse_plan` 容错；
5. **前后端接线守卫**：消融开关清单（后端 `ABLATION_KEYS` ↔ 前端 `ABLATION_KEYS`）必须一致。

真分解的开启方式（保留可复测）：`run_eval_once.py --config two_stage_planning=true`
或设置项 `two_stage_planning=true`。

