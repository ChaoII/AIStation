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

export function orchestrateAgents(question: string) {
  return request({ url: `${API_PATH}/orchestrate`, method: "post", data: { question } });
}

export function getAiAgentDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function getToolApprovals() {
  return request({ url: `${API_PATH}/tool-approvals`, method: "get" });
}

export function setToolApproval(data: { tool_name: string; authorized: boolean }) {
  return request({ url: `${API_PATH}/tool-approvals`, method: "post", data });
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
