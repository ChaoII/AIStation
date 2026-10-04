import request from "@/utils/request";

const API_PATH = "/ai/query";

export function queryAsk(data: {
  question: string;
  session_id?: number | null;
  datasource?: string | null;
}) {
  return request({ url: `${API_PATH}/ask`, method: "post", data });
}

// 指标运营
export function getQueryMetrics(params?: any) {
  return request({ url: `${API_PATH}/metrics/list`, method: "get", params });
}
export function saveQueryMetric(data: any) {
  return request({ url: `${API_PATH}/metrics/save`, method: "post", data });
}
export function deleteQueryMetrics(ids: number[]) {
  return request({ url: `${API_PATH}/metrics/delete`, method: "delete", data: ids });
}

// 术语运营
export function getQueryTerms(params?: any) {
  return request({ url: `${API_PATH}/terms/list`, method: "get", params });
}
export function saveQueryTerm(data: any) {
  return request({ url: `${API_PATH}/terms/save`, method: "post", data });
}
export function deleteQueryTerms(ids: number[]) {
  return request({ url: `${API_PATH}/terms/delete`, method: "delete", data: ids });
}

// 数据源
export function getQueryDatasources() {
  return request({ url: `${API_PATH}/datasources/list`, method: "get" });
}
export function saveQueryDatasource(data: any) {
  return request({ url: `${API_PATH}/datasources/save`, method: "post", data });
}
export function deleteQueryDatasources(ids: number[]) {
  return request({ url: `${API_PATH}/datasources/delete`, method: "delete", data: ids });
}
export function testQueryDatasource(id: number) {
  return request({
    url: `${API_PATH}/datasources/${id}/test`,
    method: "post",
    headers: { _silent: "true" },
    timeout: 20000,
  });
}
export function syncQueryDatasourceSchema(id: number) {
  return request({
    url: `${API_PATH}/datasources/${id}/sync-schema`,
    method: "post",
    timeout: 60000,
  });
}
export function getQueryDatasourceSchema(id: number) {
  return request({ url: `${API_PATH}/datasources/${id}/schema`, method: "get" });
}
export function getQueryRoles() {
  return request({ url: `${API_PATH}/datasources/roles`, method: "get" });
}

// 会话
export function getQuerySessions() {
  return request({ url: `${API_PATH}/sessions/list`, method: "get" });
}
export function getQueryMessages(sessionId: number) {
  return request({ url: `${API_PATH}/sessions/${sessionId}/messages`, method: "get" });
}
export function deleteQuerySession(sessionId: number) {
  return request({ url: `${API_PATH}/sessions/${sessionId}`, method: "delete" });
}

// 反馈
export function queryFeedback(data: {
  message_id: number;
  feedback: string;
  correct_sql?: string | null;
}) {
  return request({ url: `${API_PATH}/feedback`, method: "post", data });
}

// 示例工程 / 统计 / 限额
export function getQueryFewshots(params?: any) {
  return request({ url: `${API_PATH}/fewshots/list`, method: "get", params });
}
export function saveQueryFewshot(data: any) {
  return request({ url: `${API_PATH}/fewshots/save`, method: "post", data });
}
export function deleteQueryFewshots(ids: number[]) {
  return request({ url: `${API_PATH}/fewshots/delete`, method: "delete", data: ids });
}
export function getQueryStats() {
  return request({ url: `${API_PATH}/stats`, method: "get" });
}
export function getQuerySettings() {
  return request({ url: `${API_PATH}/settings`, method: "get" });
}
export function saveQuerySetting(data: { key: string; value: string; remark: string }) {
  return request({ url: `${API_PATH}/settings/save`, method: "post", data });
}
