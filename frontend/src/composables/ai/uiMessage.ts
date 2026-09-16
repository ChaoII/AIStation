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

/** 取工具类 part（dynamic-tool）。 */
export function toolPartsOf(msg: any): AiUIPart[] {
  return (msg?.parts || []).filter((p: AiUIPart) => p.type === "dynamic-tool");
}

/** 取指定 data-* part 的 data（如 "data-finish"）。 */
export function dataPartsOf(msg: any, type: string): any[] {
  return (msg?.parts || []).filter((p: AiUIPart) => p.type === type).map((p: AiUIPart) => p.data);
}

/** 取单个 part 的文本（text / reasoning 通用）。 */
export function partText(part: AiUIPart): string {
  return part?.text || "";
}
