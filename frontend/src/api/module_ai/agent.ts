import { Auth } from "@/utils/auth";
import request from "@/utils/request";

const API_PATH = "/ai/agents";
const CAT_PATH = "/ai/agents/categories";

// ---------- 智能体实体 ----------
export function getAiAgentList(params?: { category_id?: number }) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiAgentDashboard() {
  return request({ url: `${API_PATH}/dashboard`, method: "get" });
}

/** AI 办公室：执行步骤时间线（规划 / 工具 / 回话 / 汇总） */
export function getOfficeSteps(params?: { run_id?: string; agent_id?: number; limit?: number }) {
  return request({ url: `${API_PATH}/office/steps`, method: "get", params });
}

/** AI 办公室：任务列表（按天筛选 + 分页；点开看那一次的完整步骤） */
export function getOfficeRuns(params?: {
  page_no?: number;
  page_size?: number;
  date?: string;
  days?: number;
  status?: string;
  agent_name?: string;
}) {
  return request({ url: `${API_PATH}/office/runs`, method: "get", params });
}

/** AI 办公室：清空上下文记忆（最近几轮问答） */
export function clearOfficeMemory() {
  return request({ url: `${API_PATH}/office/memory/clear`, method: "post" });
}

/** AI 办公室：今日简报（派活次数 / 参与人数 / 谁最忙） */
export function getOfficeSummary() {
  return request({ url: `${API_PATH}/office/summary`, method: "get" });
}

/** AI 办公室：在岗智能体 + 运行状态（busy/idle） */
export function getAiAgentOffice() {
  return request({ url: `${API_PATH}/office`, method: "get" });
}

/** AI 办公室：点名给某个智能体派活（不经过组长） */
export function dispatchOfficeAgent(agentId: number, text: string, signal?: AbortSignal) {
  return request({
    url: `${API_PATH}/office/dispatch/${agentId}`,
    method: "post",
    data: { text },
    signal,
    timeout: 300000
  });
}

/**
 * AI 办公室：组长派活（SSE 流式）。
 *
 * 运行过程中就能拿到「谁派给谁、谁回了什么」，办公室据此弹对话气泡；
 * 不能用 axios（拿不到流），这里用 fetch + ReadableStream 解析 SSE。
 */
export async function streamOfficeDispatch(
  text: string,
  onFrame: (frame: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const base = import.meta.env.VITE_APP_BASE_API || "";
  const token = Auth.getAccessToken();
  const resp = await fetch(`${base}${API_PATH}/office/dispatch/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json;charset=utf-8",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`派活失败（${resp.status}）`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf("\n\n");
      while (idx >= 0) {
        const block = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);
        for (const line of block.split("\n")) {
          if (!line.startsWith("data:")) continue;
          try {
            onFrame(JSON.parse(line.slice(5).trim()));
          } catch {
            /* 坏帧忽略，不影响后续 */
          }
        }
        idx = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** AI 办公室：把任务交给组长（后端用 agno Team 协同） */
export function dispatchOfficeTask(text: string) {
  return request({ url: `${API_PATH}/office/dispatch`, method: "post", data: { text } });
}

export function orchestrateAgents(question: string) {
  return request({ url: `${API_PATH}/orchestrate`, method: "post", data: { question } });
}

export function getAiAgentDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiAgent(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiAgent(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiAgent(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function batchAgentStatus(ids: number[], enabled: boolean) {
  return request({ url: `${API_PATH}/batch/status`, method: "put", data: { ids, enabled } });
}

// ---------- 智能体分类 ----------
export function getAgentCategoryList() {
  return request({ url: `${CAT_PATH}/list`, method: "get" });
}

export function createAgentCategory(data: any) {
  return request({ url: `${CAT_PATH}/create`, method: "post", data });
}

export function updateAgentCategory(id: number, data: any) {
  return request({ url: `${CAT_PATH}/update/${id}`, method: "put", data });
}

export function deleteAgentCategory(cat_id: number) {
  return request({ url: `${CAT_PATH}/delete`, method: "delete", data: cat_id });
}
export function getAgentTemplates() {
  return request({ url: `${API_PATH}/templates`, method: "get" });
}
export function createAgentFromTemplate(key: string, name: string) {
  return request({ url: `${API_PATH}/create-from-template`, method: "post", data: { key, name } });
}
