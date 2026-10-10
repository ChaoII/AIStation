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
  data_accuracy: number;
  semantic_accuracy: number;
  fast_rate: number;
  recall_at_k: number;
  avg_ms: number;
  p50_ms?: number;
  p95_ms?: number;
  error_rate: number;
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

/** 8 个消融开关 → 中文展示名。 */
export const ABLATION_KEYS: { key: string; label: string }[] = [
  { key: "recall_enabled", label: "召回服务" },
  { key: "agno_semantic_enabled", label: "语义向量召回" },
  { key: "kg_enabled", label: "知识图谱" },
  { key: "agno_tool_agent", label: "工具调用智能体" },
  { key: "decomposed_planning", label: "分解式规划" },
  { key: "empty_self_correct", label: "空结果自纠错" },
  { key: "fewshot_auto_curate", label: "Few-shot 自动沉淀" },
  { key: "enum_hint_enabled", label: "枚举取值提示" },
];

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
