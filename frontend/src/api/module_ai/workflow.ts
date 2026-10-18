import request from "@/utils/request";

const API_PATH = "/ai/workflows";

export function getAiWorkflowList() {
  return request({ url: `${API_PATH}/list`, method: "get" });
}

export function getAiWorkflowTemplates() {
  return request({ url: `${API_PATH}/templates`, method: "get" });
}

export function createAiWorkflowFromTemplate(key: string, name: string) {
  return request({ url: `${API_PATH}/create-from-template`, method: "post", data: { key, name } });
}

export function getAiWorkflowDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiWorkflow(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiWorkflow(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiWorkflow(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

// ---------- 版本 / 发布 / 回滚 ----------
export function saveAiWorkflowVersion(id: number, data: { remark?: string; graph?: any }) {
  return request({ url: `${API_PATH}/${id}/versions`, method: "post", data });
}

export function listAiWorkflowVersions(id: number) {
  return request({ url: `${API_PATH}/${id}/versions`, method: "get" });
}

export function rollbackAiWorkflowVersion(id: number, versionId: number) {
  return request({ url: `${API_PATH}/${id}/versions/${versionId}/rollback`, method: "post" });
}

export function publishAiWorkflowVersion(id: number, versionId: number) {
  return request({ url: `${API_PATH}/${id}/versions/${versionId}/publish`, method: "post" });
}

// ---------- 运行历史 ----------
export function listAiWorkflowRunLogs(id: number) {
  return request({ url: `${API_PATH}/${id}/run-logs`, method: "get" });
}

export function getAiWorkflowRunLog(runId: number) {
  return request({ url: `${API_PATH}/run-log/${runId}`, method: "get" });
}

/** 请求停止一次运行中的工作流（后端在节点边界/流式帧检查点中断）。 */
export function cancelAiWorkflowRun(runId: number) {
  return request({ url: `${API_PATH}/run-log/${runId}/cancel`, method: "post" });
}

export function getAiWorkflowStats(id: number) {
  return request({ url: `${API_PATH}/${id}/stats`, method: "get" });
}

export function createAiWorkflowShare(id: number) {
  return request({ url: `${API_PATH}/${id}/share`, method: "post" });
}

export function getAiWorkflowSchedule(id: number) {
  return request({ url: `${API_PATH}/${id}/schedule`, method: "get" });
}

export function setAiWorkflowSchedule(id: number, data: { cron?: string; enabled: boolean }) {
  return request({ url: `${API_PATH}/${id}/schedule`, method: "put", data });
}

export function runAiWorkflowSchedule(id: number) {
  return request({ url: `${API_PATH}/${id}/schedule/run`, method: "post" });
}

export function shareAiWorkflowRun(token: string, message: string) {
  return request({ url: `${API_PATH}/share/run`, method: "post", data: { token, message } });
}
