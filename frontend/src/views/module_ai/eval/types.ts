/** 问数评测（NL2SQL Eval）类型定义。字段口径与后端 `eval_metrics.py` / `eval_set.py` 对齐。 */

export interface EvalCase {
  id: number;
  question: string;
  gold_sql: string;
  datasource: string;
  difficulty: string;
  form: string;
  scenario: string;
  expected_metric?: string;
  verified?: boolean;
  enabled?: boolean;
  created_time?: string;
}

/** 总览指标（后端 `summarize`）。 */
export interface EvalSummary {
  total: number;
  /** 全部题数（含退化题） */
  all_total?: number;
  /** 退化题数（金标为空/NULL/单值 0）：**不计入精度分母** */
  degenerate_n?: number;
  data_accuracy: number;
  semantic_accuracy: number;
  fast_rate: number;
  recall_at_k: number;
  avg_ms: number;
  p50_ms?: number;
  p95_ms?: number;
  error_rate: number;
  /** 指标题（快路径能答）：考的是"指标枚举" */
  metric_total?: number;
  metric_accuracy?: number;
  /** 生成题（指标答不了）：考的是"模型把自然语言推理成 SQL" */
  generation_total?: number;
  generation_accuracy?: number;
  k?: number;
}

/** 逐题结果行（后端 `load_results`）。 */
export interface EvalResultRow {
  testcase_id: number;
  question: string;
  ok: boolean;
  is_error: boolean;
  path: string;
  metric_key: string;
  expected_metric: string;
  sql: string;
  n_rows: number;
  took_ms: number;
  gold_match: boolean;
  recall: number;
  /** JSON 字符串：`{expected: string[], recalled: string[]}` */
  recall_hit: string;
  /** JSON 字符串：本体物化表名数组 */
  ontology_used: string;
  difficulty: string;
  form: string;
  scenario: string;
  datasource: string;
}

/** 分维度聚合行（后端 `group_by`）。 */
export interface EvalGroupRow {
  total: number;
  correct: number;
  accuracy: number;
}

export interface EvalReport {
  summary: EvalSummary;
  by_difficulty: Record<string, EvalGroupRow>;
  by_scenario: Record<string, EvalGroupRow>;
  by_form: Record<string, EvalGroupRow>;
  by_datasource: Record<string, EvalGroupRow>;
  results: EvalResultRow[];
}

export interface EvalRunProgress {
  run_id: string;
  status: "running" | "done" | "error";
  mode?: string;
  total: number;
  done: number;
  current?: string;
  summary?: EvalSummary | null;
  error?: string;
}

export interface EvalRunItem {
  run_id: string;
  mode?: string;
  status?: string;
  total?: number;
  done?: number;
  started_at?: string;
  summary?: EvalSummary | null;
}

export interface EvalAblationReport {
  run_id: string;
  status: "running" | "done" | "error";
  groups?: string[];
  current?: string;
  table?: Record<string, EvalSummary & { delta_data_accuracy?: number; delta_avg_ms?: number }>;
  error?: string;
}

/** 8 个消融开关 → 展示名（存放 i18n key 后缀，展示时用 t('ai_workflow.' + label) 取）。 */
export const ABLATION_KEYS: { key: string; label: string }[] = [
  { key: "recall_enabled", label: "eval_ablRecall" },
  { key: "agno_semantic_enabled", label: "eval_ablSemantic" },
  { key: "kg_enabled", label: "eval_ablKg" },
  { key: "agno_tool_agent", label: "eval_ablTool" },
  // 诚实命名：它只在提示词里加一条「先判断单表/联表/嵌套」，**不是真分解**
  // （真分解是 two_stage_planning：先出执行计划再写 SQL；修复 _cfg_bool 后重测 B 半 A/B：
  //  **−7.55 分 + 错误率 0→9.4%**（计划诱发表名幻觉）→ **保持默认关**）
  { key: "decomposed_planning", label: "eval_ablPlan" },
  { key: "empty_self_correct", label: "eval_ablSelfCorrect" },
  { key: "fewshot_auto_curate", label: "eval_ablFewshot" },
  { key: "enum_hint_enabled", label: "eval_ablEnum" },
];

// 难度/形式：数组元素为发送给后端的原始枚举值（数据），展示时用下面的 key 经 i18n 翻译。
export const DIFFICULTIES = ["简单", "中等", "困难"];

export const FORMS = [
  "单维统计",
  "多维报表",
  "时间窗口",
  "占比",
  "排名TopN",
  "窗口函数",
  "去重",
  "嵌套子查询",
  "业务黑话",
  "快路径指标",
];

// 与 DIFFICULTIES / FORMS 顺序一一对应，返回 i18n key 后缀（不含 ai_workflow. 前缀）。
export const DIFFICULTY_KEYS = ["eval_diff_easy", "eval_diff_medium", "eval_diff_hard"];

export const FORM_KEYS = [
  "eval_form_single",
  "eval_form_multi",
  "eval_form_timewin",
  "eval_form_ratio",
  "eval_form_topn",
  "eval_form_windowfn",
  "eval_form_distinct",
  "eval_form_nested",
  "eval_form_jargon",
  "eval_form_fast",
];

/** 难度原始值 → i18n key 后缀（找不到则回退未知）。 */
export function diffKey(d: string): string {
  const i = DIFFICULTIES.indexOf(d);
  return i < 0 ? "eval_diff_default" : DIFFICULTY_KEYS[i];
}

/** 形式原始值 → i18n key 后缀（找不到则回退未知）。 */
export function formKey(f: string): string {
  const i = FORMS.indexOf(f);
  return i < 0 ? "eval_form_default" : FORM_KEYS[i];
}

/** 难度 → el-tag 类型。 */
export function difficultyTag(d: string): "success" | "warning" | "danger" | "info" {
  if (d === "困难") return "danger";
  if (d === "中等") return "warning";
  if (d === "简单") return "success";
  return "info";
}

/** 百分比展示（后端返回的是 0~1 小数）。 */
export function pct(v: number | undefined | null): string {
  if (v === null || v === undefined) return "-";
  return `${(v * 100).toFixed(1)}%`;
}
