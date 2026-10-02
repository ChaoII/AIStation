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
  { type: "end", label: "结束", color: "#909399", desc: "输出最终回复", branch: false },
];

export function nodeDefOf(type: string): NodeDef {
  return NODE_DEFS.find((d) => d.type === type) || NODE_DEFS[0];
}
