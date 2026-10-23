import request from "@/utils/request";

const API_PATH = "/ai/agents";

// ---------- 智能体实体 ----------
export function getAiAgentList(params?: { category_id?: number }) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiAgentDashboard() {
  return request({ url: `${API_PATH}/dashboard`, method: "get" });
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

export function getAgentTemplates() {
  return request({ url: `${API_PATH}/templates`, method: "get" });
}
export function createAgentFromTemplate(key: string, name: string) {
  return request({ url: `${API_PATH}/create-from-template`, method: "post", data: { key, name } });
}
