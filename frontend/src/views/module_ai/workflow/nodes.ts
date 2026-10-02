/**
 * AI 工作流节点定义：与后端 `workflow/engine.py` 的节点集一一对应。
 * 前端仅描述展示与表单，不改运行语义。
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
  | "end";

export interface NodeDef {
  type: WorkflowNodeType;
  label: string;
  color: string;
  desc: string;
  /** 是否允许作为条件分支边（sourceHandle=true/false）。 */
  branch: boolean;
}

export const NODE_DEFS: NodeDef[] = [
  { type: "start", label: "开始", color: "#909399", desc: "定义工作流输入变量", branch: false },
  { type: "llm", label: "LLM", color: "#409eff", desc: "调用大模型生成内容", branch: false },
  {
    type: "knowledge",
    label: "知识检索",
    color: "#67c23a",
    desc: "检索知识库内容注入",
    branch: false,
  },
  {
    type: "tool",
    label: "工具调用",
    color: "#e6a23c",
    desc: "调用平台工具/HTTP 工具",
    branch: false,
  },
  {
    type: "code",
    label: "代码转换",
    color: "#b8a9e0",
    desc: "对变量做 Python 转换",
    branch: false,
  },
  {
    type: "condition",
    label: "条件分支",
    color: "#f56c6c",
    desc: "按表达式走真/假分支",
    branch: true,
  },
  {
    type: "variable",
    label: "变量赋值",
    color: "#17b3a3",
    desc: "给变量赋静态值",
    branch: false,
  },
  {
    type: "http",
    label: "HTTP 请求",
    color: "#8e44ad",
    desc: "请求外部 HTTP API",
    branch: false,
  },
  {
    type: "iteration",
    label: "迭代/批量",
    color: "#ff9800",
    desc: "遍历列表并调用工具聚合",
    branch: false,
  },
  {
    type: "classifier",
    label: "问题分类器",
    color: "#3f8cff",
    desc: "LLM 归类并按类别路由",
    branch: false,
  },
  {
    type: "extractor",
    label: "参数提取",
    color: "#00bcd4",
    desc: "LLM 提炼 JSON 结构化数据",
    branch: false,
  },
  {
    type: "template",
    label: "模板转换",
    color: "#9c27b0",
    desc: "按 {{变量}} 模板生成/拼接文本",
    branch: false,
  },
  {
    type: "variable_aggregator",
    label: "变量聚合",
    color: "#607d8b",
    desc: "把多个变量合并成一个对象",
    branch: false,
  },
  {
    type: "answer",
    label: "回答",
    color: "#ff5252",
    desc: "在流程任意处向用户输出文本",
    branch: false,
  },
  {
    type: "sub_workflow",
    label: "子工作流",
    color: "#00acc1",
    desc: "嵌套调用另一个工作流",
    branch: false,
  },
  {
    type: "agent",
    label: "子智能体",
    color: "#7cb342",
    desc: "调用另一个 AI 智能体",
    branch: false,
  },
  {
    type: "loop",
    label: "循环",
    color: "#ff7043",
    desc: "对列表逐项运行循环体工作流",
    branch: false,
  },
  {
    type: "parallel",
    label: "并行",
    color: "#26a69a",
    desc: "并发运行多个分支工作流",
    branch: false,
  },
  {
    type: "doc_extractor",
    label: "文档提取",
    color: "#8d6e63",
    desc: "抓取 URL 或内联文本并剥离标签",
    branch: false,
  },
  {
    type: "web_search",
    label: "网页搜索",
    color: "#5c6bc0",
    desc: "调用搜索 API 并格式化结果",
    branch: false,
  },
  {
    type: "database",
    label: "数据库",
    color: "#455a64",
    desc: "对数据库执行 SQL 查询",
    branch: false,
  },
  { type: "end", label: "结束", color: "#909399", desc: "输出最终回复", branch: false },
];

export function nodeDefOf(type: string): NodeDef {
  return NODE_DEFS.find((d) => d.type === type) || NODE_DEFS[0];
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
};

export const NODE_CATEGORIES: { key: string; label: string }[] = [
  { key: "io", label: "输入 / 输出" },
  { key: "core", label: "核心处理" },
  { key: "data", label: "数据 / 检索" },
  { key: "logic", label: "逻辑控制" },
  { key: "sub", label: "子流程" },
];

export function categoryOf(type: string): string {
  return NODE_CATEGORY_MAP[type] || "core";
}

export function categoryLabel(key: string): string {
  return NODE_CATEGORIES.find((c) => c.key === key)?.label || "其他";
}
