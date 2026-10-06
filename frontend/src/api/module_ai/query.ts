import request from "@/utils/request";
import { Auth } from "@/utils/auth";

const API_PATH = "/ai/query";

export function queryAsk(data: {
  question: string;
  session_id?: number | null;
  datasource?: string | null;
}) {
  return request({ url: `${API_PATH}/ask`, method: "post", data });
}

/** 流式问数：返回 SSE 事件异步迭代器（思考/工具调用/结果/完成等）。 */
export async function* streamQuery(data: {
  question: string;
  session_id?: number | null;
  datasource?: string | null;
}): AsyncGenerator<{ type: string; data: any }, void, unknown> {
  const base = import.meta.env.VITE_APP_BASE_API || "";
  const token = Auth.getAccessToken();
  const resp = await fetch(`${base}${API_PATH}/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json;charset=utf-8",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`流式请求失败：${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 事件以空行分隔
      let idx = buffer.indexOf("\n\n");
      while (idx >= 0) {
        const block = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);
        if (block) {
          const ev = parseSseBlock(block);
          if (ev) yield ev;
        }
        idx = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(block: string): { type: string; data: any } | null {
  let event = "message";
  let dataLine = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
  }
  if (dataLine === "" && event !== "done") return null;
  let data: any = dataLine;
  try {
    data = JSON.parse(dataLine);
  } catch {
    /* 保留原始字符串 */
  }
  return { type: event, data };
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

// 数据资产目录
export function syncQueryAssets() {
  return request({ url: `${API_PATH}/assets/sync`, method: "post", timeout: 60000 });
}
export function getQueryAssets() {
  return request({ url: `${API_PATH}/assets/list`, method: "get" });
}
export function getQueryAssetColumns(tableName: string) {
  return request({ url: `${API_PATH}/assets/${tableName}/columns`, method: "get" });
}
export function generateQueryAssetDesc(force = false) {
  return request({
    url: `${API_PATH}/assets/generate-desc`,
    method: "post",
    timeout: 300000,
    params: { force: force ? 1 : 0 },
  });
}
export function rebuildQueryKg() {
  return request({ url: `${API_PATH}/assets/kg/rebuild`, method: "post", timeout: 60000 });
}
export function getQueryKgStats() {
  return request({ url: `${API_PATH}/assets/kg/stats`, method: "get" });
}
export function getQueryKgUnified(kbId?: number | null, scope = "all") {
  const params: Record<string, any> = { scope };
  if (kbId != null) params.kb_id = kbId;
  return request({ url: `${API_PATH}/assets/kg/unified`, method: "get", params });
}
export function getQueryKgKbs() {
  return request({ url: `${API_PATH}/assets/kg/kbs`, method: "get" });
}
export function saveQueryKgLayout(items: { name: string; x: number; y: number }[]) {
  return request({ url: `${API_PATH}/assets/kg/layout`, method: "post", data: { items } });
}
export function getQueryObjects() {
  return request({ url: `${API_PATH}/assets/objects`, method: "get" });
}
export function getFdeList() {
  return request({ url: `${API_PATH}/fde/list`, method: "get" });
}
export function saveFdeProposition(data: any) {
  return request({ url: `${API_PATH}/fde/save`, method: "post", data });
}
export function deleteFdePropositions(ids: number[]) {
  return request({ url: `${API_PATH}/fde/delete`, method: "delete", data: ids });
}
export function fdeShadowCheck(proposition_id: number) {
  return request({ url: `${API_PATH}/fde/shadow`, method: "post", data: { proposition_id } });
}
export function getActionList() {
  return request({ url: `${API_PATH}/action/list`, method: "get" });
}
export function saveAction(data: any) {
  return request({ url: `${API_PATH}/action/save`, method: "post", data });
}
export function executeAction(data: any) {
  return request({ url: `${API_PATH}/action/execute`, method: "post", data });
}
export function getActionLogs(limit = 100) {
  return request({ url: `${API_PATH}/action/logs`, method: "get", params: { limit } });
}
export function getAssetVersions(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/versions`, method: "get" });
}
export function rollbackAssetVersion(version_id: number) {
  return request({
    url: `${API_PATH}/assets/version/rollback`,
    method: "post",
    data: { version_id },
  });
}
export function getAssetImpact(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/impact`, method: "get" });
}
export function extractQueryObjects() {
  return request({ url: `${API_PATH}/assets/extract-objects`, method: "post", timeout: 120000 });
}
export function autoLinkQueryKg() {
  return request({ url: `${API_PATH}/assets/kg/auto-link`, method: "post" });
}
export function getQueryConcepts() {
  return request({ url: `${API_PATH}/concepts/list`, method: "get" });
}
export function saveQueryConcept(data: any) {
  return request({ url: `${API_PATH}/concepts/save`, method: "post", data });
}
export function deleteQueryConcepts(ids: number[]) {
  return request({ url: `${API_PATH}/concepts/delete`, method: "delete", data: ids });
}
export function inferQueryAssetRelations() {
  return request({ url: `${API_PATH}/assets/infer-relations`, method: "post", timeout: 120000 });
}
export function suggestQueryAssets() {
  return request({ url: `${API_PATH}/assets/suggest`, method: "post", timeout: 120000 });
}
export function saveQueryAsset(data: {
  table_name: string;
  alias?: string;
  domain?: string;
  description: string;
  business_scenarios?: string;
  included: boolean;
  remark?: string;
  object_enabled?: boolean;
  object_key_col?: string;
  object_name_col?: string;
  object_icon?: string;
}) {
  return request({ url: `${API_PATH}/assets/save`, method: "post", data });
}
export function saveQueryAssetColumn(data: {
  table_name: string;
  column_name: string;
  description: string;
  business_scenarios?: string;
  related_table?: string;
  related_field?: string;
  included: boolean;
  sensitive: boolean;
}) {
  return request({ url: `${API_PATH}/assets/column/save`, method: "post", data });
}

// 基准测试
export function runQueryBenchmark() {
  return request({ url: `${API_PATH}/benchmark/run`, method: "post" });
}
export function getQueryBenchmarkStatus(run_id: string) {
  return request({ url: `${API_PATH}/benchmark/status`, method: "get", params: { run_id } });
}
