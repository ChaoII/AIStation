/**
 * AI 工作流节点定义：与后端 `workflow/engine.py` 的节点集一一对应。
 * 前端仅描述展示与表单，不改运行语义。
 *
 * i18n：`label`/`desc` 保留中文（供调色板搜索等）；用户可见展示统一走
 * `labelKey`/`descKey`（对应 ai_workflow.node_<key> 等），由组件用 t() 输出。
 */
export type WorkflowNodeType =
  | "start"
  | "llm"
  | "knowledge"
  | "tool"
  | "code"
  | "condition"
  | "variable"
  | "http"
  | "iteration"
  | "classifier"
  | "extractor"
  | "template"
  | "variable_aggregator"
  | "answer"
  | "sub_workflow"
  | "agent"
  | "loop"
  | "parallel"
  | "doc_extractor"
  | "web_search"
  | "database"
  | "note"
  | "group"
  | "end";

export interface NodeDef {
  type: WorkflowNodeType;
  label: string;
  labelKey: string;
  color: string;
  desc: string;
  descKey: string;
  /** 是否允许作为条件分支边（sourceHandle=true/false）。 */
  branch: boolean;
}

export const NODE_DEFS: NodeDef[] = [
  {
    type: "start",
    label: "开始",
    labelKey: "start",
    color: "#909399",
    desc: "定义工作流输入变量",
    descKey: "start_desc",
    branch: false,
  },
  {
    type: "llm",
    label: "LLM",
    labelKey: "llm",
    color: "#409eff",
    desc: "调用大模型生成内容",
    descKey: "llm_desc",
    branch: false,
  },
  {
    type: "knowledge",
    label: "知识检索",
    labelKey: "knowledge",
    color: "#67c23a",
    desc: "检索知识库内容注入",
    descKey: "knowledge_desc",
    branch: false,
  },
  {
    type: "tool",
    label: "工具调用",
    labelKey: "tool",
    color: "#e6a23c",
    desc: "调用平台工具/HTTP 工具",
    descKey: "tool_desc",
    branch: false,
  },
  {
    type: "code",
    label: "代码转换",
    labelKey: "code",
    color: "#b8a9e0",
    desc: "对变量做 Python 转换",
    descKey: "code_desc",
    branch: false,
  },
  {
    type: "condition",
    label: "条件分支",
    labelKey: "condition",
    color: "#f56c6c",
    desc: "按表达式走真/假分支",
    descKey: "condition_desc",
    branch: true,
  },
  {
    type: "variable",
    label: "变量赋值",
    labelKey: "variable",
    color: "#17b3a3",
    desc: "给变量赋静态值",
    descKey: "variable_desc",
    branch: false,
  },
  {
    type: "http",
    label: "HTTP 请求",
    labelKey: "http",
    color: "#8e44ad",
    desc: "请求外部 HTTP API",
    descKey: "http_desc",
    branch: false,
  },
  {
    type: "iteration",
    label: "迭代/批量",
    labelKey: "iteration",
    color: "#ff9800",
    desc: "遍历列表并调用工具聚合",
    descKey: "iteration_desc",
    branch: false,
  },
  {
    type: "classifier",
    label: "问题分类器",
    labelKey: "classifier",
    color: "#3f8cff",
    desc: "LLM 归类并按类别路由",
    descKey: "classifier_desc",
    branch: false,
  },
  {
    type: "extractor",
    label: "参数提取",
    labelKey: "extractor",
    color: "#00bcd4",
    desc: "LLM 提炼 JSON 结构化数据",
    descKey: "extractor_desc",
    branch: false,
  },
  {
    type: "template",
    label: "模板转换",
    labelKey: "template",
    color: "#9c27b0",
    desc: "按 {{变量}} 模板生成/拼接文本",
    descKey: "template_desc",
    branch: false,
  },
  {
    type: "variable_aggregator",
    label: "变量聚合",
    labelKey: "variable_aggregator",
    color: "#607d8b",
    desc: "把多个变量合并成一个对象",
    descKey: "variable_aggregator_desc",
    branch: false,
  },
  {
    type: "answer",
    label: "回答",
    labelKey: "answer",
    color: "#ff5252",
    desc: "在流程任意处向用户输出文本",
    descKey: "answer_desc",
    branch: false,
  },
  {
    type: "sub_workflow",
    label: "子工作流",
    labelKey: "sub_workflow",
    color: "#00acc1",
    desc: "嵌套调用另一个工作流",
    descKey: "sub_workflow_desc",
    branch: false,
  },
  {
    type: "agent",
    label: "子智能体",
    labelKey: "agent",
    color: "#7cb342",
    desc: "调用另一个 AI 智能体",
    descKey: "agent_desc",
    branch: false,
  },
  {
    type: "loop",
    label: "循环",
    labelKey: "loop",
    color: "#ff7043",
    desc: "对列表逐项运行循环体工作流",
    descKey: "loop_desc",
    branch: false,
  },
  {
    type: "parallel",
    label: "并行",
    labelKey: "parallel",
    color: "#26a69a",
    desc: "并发运行多个分支工作流",
    descKey: "parallel_desc",
    branch: false,
  },
  {
    type: "doc_extractor",
    label: "文档提取",
    labelKey: "doc_extractor",
    color: "#8d6e63",
    desc: "抓取 URL 或内联文本并剥离标签",
    descKey: "doc_extractor_desc",
    branch: false,
  },
  {
    type: "web_search",
    label: "网页搜索",
    labelKey: "web_search",
    color: "#5c6bc0",
    desc: "调用搜索 API 并格式化结果",
    descKey: "web_search_desc",
    branch: false,
  },
  {
    type: "database",
    label: "数据库",
    labelKey: "database",
    color: "#455a64",
    desc: "对数据库执行 SQL 查询",
    descKey: "database_desc",
    branch: false,
  },
  {
    type: "note",
    label: "注释框",
    labelKey: "note",
    color: "#8a6d3b",
    desc: "添加说明文字的分组/注释框（纯视觉）",
    descKey: "note_desc",
    branch: false,
  },
  {
    type: "group",
    label: "分组",
    labelKey: "group",
    color: "#5c7cfa",
    desc: "容器：把节点归入分组，拖动整体移动",
    descKey: "group_desc",
    branch: false,
  },
  {
    type: "end",
    label: "结束",
    labelKey: "end",
    color: "#909399",
    desc: "输出最终回复",
    descKey: "end_desc",
    branch: false,
  },
];

export function nodeDefOf(type: string): NodeDef {
  return NODE_DEFS.find((d) => d.type === type) || NODE_DEFS[0];
}

/** 节点 i18n 键后缀（拼接成 ai_workflow.node_<key>）。 */
export function nodeLabelKey(type: string): string {
  return nodeDefOf(type).labelKey;
}
/** 节点描述 i18n 键后缀（拼接成 ai_workflow.node_<key>）。 */
export function nodeDescKey(type: string): string {
  return nodeDefOf(type).descKey;
}

/** 节点分类（用于调色板分组展示）。 */
const NODE_CATEGORY_MAP: Record<string, string> = {
  start: "io",
  end: "io",
  answer: "io",
  llm: "core",
  tool: "core",
  code: "core",
  http: "core",
  knowledge: "data",
  doc_extractor: "data",
  web_search: "data",
  database: "data",
  condition: "logic",
  classifier: "logic",
  iteration: "logic",
  loop: "logic",
  parallel: "logic",
  variable: "logic",
  template: "logic",
  variable_aggregator: "logic",
  extractor: "logic",
  sub_workflow: "sub",
  agent: "sub",
  note: "note",
  group: "note",
};

export const NODE_CATEGORIES: { key: string; label: string; labelKey: string }[] = [
  { key: "io", label: "输入 / 输出", labelKey: "cat_io" },
  { key: "core", label: "核心处理", labelKey: "cat_core" },
  { key: "data", label: "数据 / 检索", labelKey: "cat_data" },
  { key: "logic", label: "逻辑控制", labelKey: "cat_logic" },
  { key: "sub", label: "子流程", labelKey: "cat_sub" },
  { key: "note", label: "注释", labelKey: "cat_note" },
];

export function categoryOf(type: string): string {
  return NODE_CATEGORY_MAP[type] || "core";
}

export function categoryLabel(key: string): string {
  return NODE_CATEGORIES.find((c) => c.key === key)?.label || "其他";
}

/** 分类 i18n 键后缀（拼接成 ai_workflow.cat_<key>）。 */
export function categoryLabelKey(key: string): string {
  return NODE_CATEGORIES.find((c) => c.key === key)?.labelKey || "cat_core";
}
