/** AI SDK UI Message 的 part 结构（宽松类型，避免与 SDK 泛型耦合）。 */
export interface AiUIPart {
  type: string;
  text?: string;
  delta?: string;
  toolName?: string;
  toolCallId?: string;
  state?: string;
  input?: any;
  output?: any;
  errorText?: string;
  data?: any;
  [k: string]: any;
}

/** 取消息的纯文本（累加 text part）。 */
export function textOf(msg: any): string {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === "text")
    .map((p: AiUIPart) => p.text || "")
    .join("");
}

/** 取思考文本（累加 reasoning part）。 */
export function reasoningOf(msg: any): string {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === "reasoning")
    .map((p: AiUIPart) => p.text || "")
    .join("");
}

/** 取工具类 part（SDK 标准 `tool` part）。 */
export function toolPartsOf(msg: any): AiUIPart[] {
  return (msg?.parts || []).filter((p: AiUIPart) => p.type === "tool");
}

/** 取知识检索引用来源（累积 sources part，兼容旧 messages）。 */
export function sourcesOf(msg: any): any[] {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === "sources")
    .flatMap((p: AiUIPart) => p.sources || []);
}

/** 取来源引用 part（SDK 标准 `source-url` / `source-document`）。 */
export function sourcePartsOf(msg: any): AiUIPart[] {
  return (msg?.parts || []).filter(
    (p: AiUIPart) => p.type === "source-url" || p.type === "source-document"
  );
}

/** 取指定 data-* part 的 data（SDK `DataUIPart` 的 type 为 ``data-${NAME}``，如 `data-finish`）。 */
export function dataPartsOf(msg: any, type?: string): any[] {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === type || (!type && isDataPartType(p.type)))
    .map((p: AiUIPart) => p.data);
}

/** 判断某 part 是否为 SDK 的 data part（type 以 `data-` 开头）。 */
export function isDataPartType(type: string | undefined): boolean {
  return typeof type === "string" && type.startsWith("data-");
}

/** 按 `state` 分组 tool part，返回 `Record<state, part[]>`。 */
export function toolPartsByState(msg: any): Record<string, AiUIPart[]> {
  const groups: Record<string, AiUIPart[]> = {};
  for (const p of (msg?.parts || [])) {
    if (p.type === "tool") {
      const key = p.state || "unknown";
      (groups[key] ||= []).push(p);
    }
  }
  return groups;
}

/** 取单个 part 的文本（text / reasoning 通用）。 */
export function partText(part: AiUIPart): string {
  return part?.text || "";
}
