import request from "@/utils/request";
import { Auth } from "@/utils/auth";

const API_PATH = "/ai/query";
//: 长任务超时（3 分钟）：AI 生成/整库同步/报表执行这类接口 10s 必然超时
const LONG_TIMEOUT = 180000;

/** 流式问数：返回 SSE 事件异步迭代器（思考/工具调用/结果/完成等）。 */
export async function* streamQuery(data: {
  question: string;
  session_id?: number | null;
  datasource?: string | null;
  object_code?: string | null;
  object_key?: string | null;
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

// 大模型自动建模（S4）
// 注意：前端走的是**两段式**入口 `@/api/module_ai/ontology` 的 `autoModelPreview/autoModelApply`
// （先预览候选、勾选后精确落库）。后端另有 `POST /ai/query/modeling/{metrics,annotate}` 的
// 「直接落库」路径，仅作程序化/脚本调用，界面不再使用 —— 所以这里不再重复导出。
export function promoteQueryMetric(data: { message_id: number; name: string; key: string }) {
  return request({ url: `${API_PATH}/metrics/promote`, method: "post", data });
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
//: 数据源列表在**一次页面加载里会被多个组件各要一遍**（实测问数评测页 3 次、
//: 数据与集成 2 次）。这里做「进行中复用 + 15 秒缓存」，保存/删除/同步后主动失效。
let _dsCache: { at: number; promise: Promise<any> } | null = null;

export function invalidateDatasourcesCache() {
  _dsCache = null;
}

export function getQueryDatasources(force = false) {
  const now = Date.now();
  if (!force && _dsCache && now - _dsCache.at < 15000) return _dsCache.promise;
  const promise = request({ url: `${API_PATH}/datasources/list`, method: "get" });
  _dsCache = { at: now, promise };
  promise.catch(() => {
    if (_dsCache?.promise === promise) _dsCache = null;
  });
  return promise;
}
export function getDatasourceDetail(id: number) {
  return request({ url: `${API_PATH}/datasources/${id}/detail`, method: "get" });
}
export function saveQueryDatasource(data: any) {
  invalidateDatasourcesCache();
  return request({ url: `${API_PATH}/datasources/save`, method: "post", data });
}
export function deleteQueryDatasources(ids: number[]) {
  invalidateDatasourcesCache();
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
  invalidateDatasourcesCache();
  return request({
    url: `${API_PATH}/datasources/${id}/sync-schema`,
    method: "post",
    timeout: 60000,
  });
}
export function getQueryDatasourceSchema(id: number) {
  return request({ url: `${API_PATH}/datasources/${id}/schema`, method: "get" });
}
export function importDsAsOntology(datasource_id: number, table: string, domain_code = "") {
  return request({
    url: `${API_PATH}/ontology/import-from-ds`,
    method: "post",
    data: { datasource_id, table, domain_code },
    // 单表导入会同步建对象/属性，慢库要十几秒
    timeout: 120000,
  });
}
export function importDsAsOntologyBatch(
  datasource_id: number,
  tables?: string[] | null,
  include_technical = false,
  domain_code = ""
) {
  return request({
    url: `${API_PATH}/ontology/import-from-ds/batch`,
    method: "post",
    data: { datasource_id, tables: tables || null, include_technical, domain_code },
    // 整库导入：331 张表实测约 32 秒（每表建对象+属性）。默认 10s 会「客户端超时、
    // 服务端仍在跑」，用户看到导入失败但数据其实已落库。
    timeout: 300000,
  });
}
/** 筛选规则预览：提交筛选规则并返回命中/预览结果，rules 可为空（区分 None 与显式空规则）。 */
export function previewFilterRules(datasource_id: number, rules?: any) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/preview`,
    method: "post",
    data: { rules },
    timeout: LONG_TIMEOUT,
  });
}
/** 大模型生成候选筛选规则；rules 为当前草稿（可选） */
export function suggestFilterRules(datasource_id: number, rules?: any) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/suggest`,
    method: "post",
    data: { rules },
    timeout: LONG_TIMEOUT,
  });
}
/** 大模型把自然语言转成筛选规则 */
export function parseFilterRules(datasource_id: number, text: string) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/parse`,
    method: "post",
    data: { text },
  });
}
/** 大模型逐表逐字段分类建议 */
export function classifyAdvise(datasource_id: number, rules?: any) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/classify-advise`,
    method: "post",
    data: { rules },
    timeout: LONG_TIMEOUT,
  });
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

// ---------------------------------------------------------------------------
// 自定义报表模板（一次沉淀、长期复用）
// ---------------------------------------------------------------------------
export function getQueryReports(params?: { datasource?: string; verified_only?: boolean }) {
  return request({ url: `${API_PATH}/reports`, method: "get", params });
}
export function saveQueryReport(data: any) {
  return request({ url: `${API_PATH}/reports`, method: "post", data });
}
export function deleteQueryReports(ids: number[]) {
  return request({ url: `${API_PATH}/reports`, method: "delete", data: ids });
}
export function runQueryReport(reportId: number, params?: any) {
  return request({
    url: `${API_PATH}/reports/${reportId}/run`,
    method: "post",
    data: { params: params || {} },
    timeout: LONG_TIMEOUT,
  });
}
export function verifyQueryReport(reportId: number) {
  return request({ url: `${API_PATH}/reports/${reportId}/verify`, method: "post" });
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
/** 问数配置的默认值（恢复默认用） */
export function getQuerySettingsDefaults() {
  return request<ApiResponse<Record<string, string>>>({
    url: `${API_PATH}/settings/defaults`,
    method: "get",
  });
}
export function saveQuerySetting(data: { key: string; value: string; remark: string }) {
  return request({
    url: `${API_PATH}/settings/save`,
    method: "post",
    data,
    // 页面循环逐项保存并自行汇总提示「已保存 N 项设置」，关闭全局「保存成功」避免重复弹窗
    headers: { _silent: "true" },
  });
}

// ---- 生成规则（可配置提示词规则）----
// 规则 = 拼进 NL2SQL 提示词的 SQL 书写规范；核心安全约束（只读 SELECT / 必须 FROM /
// 只用给定表）由后端只读返回，不可关闭、不可改文案。
export function getPromptRules() {
  return request({ url: `${API_PATH}/prompt-rules`, method: "get" });
}
// ---- 治理包（别名/描述/术语）导入导出 ----
export function getGovernanceExport(params: { datasource?: string }) {
  return request({ url: `${API_PATH}/governance/export`, method: "get", params, timeout: 60000 });
}
export function importGovernance(data: { data: any; apply?: boolean; datasource?: string }) {
  return request({ url: `${API_PATH}/governance/import`, method: "post", data, timeout: 60000 });
}

// ---- 指标体检（脏指标/抢答题清单 + 启停）----
export function getMetricsAudit(params: { datasource?: string; top?: number; dataset?: string }) {
  return request({ url: `${API_PATH}/metrics/audit`, method: "get", params, timeout: 60000 });
}
export function setMetricEnabled(data: { key: string; enabled: boolean }) {
  return request({ url: `${API_PATH}/metrics/enabled`, method: "post", data });
}

// ---- 实体映射（业务词 → 表，召回「实体通道」用）----
export function getEntityMap() {
  return request({ url: `${API_PATH}/entity-map`, method: "get" });
}

// ---- 语言规则（可配置词表：计数/物理量/排序/列举…）----
export function getLanguageRules() {
  return request({ url: `${API_PATH}/language/rules`, method: "get" });
}
export function probeLanguageRules(data: { question: string; rules?: any }) {
  return request({ url: `${API_PATH}/language/probe`, method: "post", data });
}

/** 预览当前生效规则（作用域/开关是运行时过滤，列表看不出最终结果） */
export function previewPromptRules(params: {
  datasource?: string;
  dialect?: string;
  disabled?: string;
}) {
  return request({ url: `${API_PATH}/prompt-rules/preview`, method: "get", params });
}
export function createPromptRule(data: {
  title?: string;
  body: string;
  scope?: string;
  scope_value?: string;
  priority?: number;
  enabled?: boolean;
}) {
  return request({ url: `${API_PATH}/prompt-rules`, method: "post", data });
}
export function updatePromptRule(
  id: number,
  data: {
    title?: string;
    body?: string;
    scope?: string;
    scope_value?: string;
    priority?: number;
    enabled?: boolean;
  }
) {
  return request({ url: `${API_PATH}/prompt-rules/${id}`, method: "put", data });
}
export function resetPromptRule(id: number) {
  return request({ url: `${API_PATH}/prompt-rules/${id}/reset`, method: "post" });
}
export function deletePromptRule(id: number) {
  return request({ url: `${API_PATH}/prompt-rules/${id}`, method: "delete" });
}

// 数据资产目录
export function getQueryAssets() {
  return request({ url: `${API_PATH}/assets/list`, method: "get" });
}
export function getQueryAssetColumns(tableName: string) {
  return request({ url: `${API_PATH}/assets/${tableName}/columns`, method: "get" });
}
/** AI 起草表/字段描述（只返回草稿，不落库；确认后由保存接口写入） */
export function draftQueryAssetDesc(tables: string[], missingOnly = false) {
  return request({
    url: `${API_PATH}/assets/draft-desc`,
    method: "post",
    data: { tables, missing_only: missingOnly },
    timeout: 120000,
  });
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
export function getQueryKgUnified(kbId?: number | null, scope = "all", datasource?: string) {
  const params: Record<string, any> = { scope };
  if (kbId != null) params.kb_id = kbId;
  if (datasource) params.datasource = datasource;
  return request({ url: `${API_PATH}/assets/kg/unified`, method: "get", params });
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
  return request({
    url: `${API_PATH}/fde/shadow`,
    method: "post",
    data: { proposition_id },
    timeout: LONG_TIMEOUT,
  });
}
export function getActionList() {
  return request({ url: `${API_PATH}/writeback/list`, method: "get" });
}
export function saveAction(data: any) {
  return request({ url: `${API_PATH}/writeback/save`, method: "post", data });
}
export function executeAction(data: any) {
  return request({
    url: `${API_PATH}/writeback/execute`,
    method: "post",
    data,
    timeout: LONG_TIMEOUT,
  });
}
export function getActionLogs(limit = 100) {
  return request({ url: `${API_PATH}/writeback/logs`, method: "get", params: { limit } });
}
export function getPendingActions(limit = 50) {
  return request({ url: `${API_PATH}/writeback/pending`, method: "get", params: { limit } });
}
export function getApprovalCenter() {
  return request({ url: `${API_PATH}/approval/center`, method: "get" });
}
export function approveAction(data: { approval_id: number }) {
  return request({ url: `${API_PATH}/writeback/approve`, method: "post", data });
}
export function rejectAction(data: { approval_id: number }) {
  return request({ url: `${API_PATH}/writeback/reject`, method: "post", data });
}
export function getAssetVersions(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/versions`, method: "get" });
}
export function publishAsset(table: string, versionId: number) {
  return request({
    url: `${API_PATH}/assets/${table}/publish`,
    method: "post",
    data: { version_id: versionId },
  });
}
export function getAssetReleases(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/releases`, method: "get" });
}
export function getAutopilot() {
  return request({ url: `${API_PATH}/autopilot`, method: "get" });
}
export function autopilotExecute(executable: string, table = "") {
  return request({
    url: `${API_PATH}/autopilot/execute`,
    method: "post",
    data: { executable, table },
  });
}
export function getDerivedMetrics() {
  return request({ url: `${API_PATH}/derived-metrics`, method: "get" });
}
export function computeDerivedMetric(key: string) {
  return request({ url: `${API_PATH}/derived-metrics/compute`, method: "get", params: { key } });
}
export function getSecurityAudit(limit = 30) {
  return request({ url: `${API_PATH}/security/audit`, method: "get", params: { limit } });
}
export function getDerivedObjects() {
  return request({ url: `${API_PATH}/derived-objects`, method: "get" });
}
export function autopilotAutoFix() {
  return request({ url: `${API_PATH}/autopilot/auto-fix`, method: "post" });
}
export function getFavorites() {
  return request({ url: `${API_PATH}/favorites/list`, method: "get" });
}
export function addFavorite(kind: string, ref: string) {
  return request({ url: `${API_PATH}/favorites/add`, method: "post", data: { kind, ref } });
}
export function removeFavorite(id: number) {
  return request({ url: `${API_PATH}/favorites/remove`, method: "post", data: { id } });
}
export function getPlugins() {
  return request({ url: `${API_PATH}/plugins/list`, method: "get" });
}
export function lineagePropagate(table: string, maxDepth = 4) {
  return request({
    url: `${API_PATH}/assets/${table}/propagate`,
    method: "get",
    params: { max_depth: maxDepth },
  });
}
export function exportAsset(table: string, limit = 100) {
  return request({ url: `${API_PATH}/assets/${table}/export`, method: "get", params: { limit } });
}
export function objectBrowse(table: string, page = 1, pageSize = 20) {
  return request({
    url: `${API_PATH}/objects/${table}/browse`,
    method: "get",
    params: { page, page_size: pageSize },
  });
}
export function getShareList() {
  return request({ url: `${API_PATH}/share/list`, method: "get" });
}
export function removeShare(id: number) {
  return request({ url: `${API_PATH}/share/remove`, method: "post", data: { id } });
}
export function getCatalogCategories() {
  return request({ url: `${API_PATH}/catalog/categories`, method: "get" });
}
export function getObjectRelations() {
  return request({ url: `${API_PATH}/objects/relations`, method: "get" });
}
export function getAccessWalkthrough(userId = 0) {
  return request({
    url: `${API_PATH}/access/walkthrough`,
    method: "get",
    params: { user_id: userId },
  });
}
export function getGuardrailsStatus() {
  return request({ url: `${API_PATH}/guardrails`, method: "get" });
}
export function getGovernanceReport() {
  return request({ url: `${API_PATH}/governance/report`, method: "get" });
}
export function getAssetHotspots() {
  return request({ url: `${API_PATH}/assets/hotspots`, method: "get" });
}
export function getObjectLifecycle() {
  return request({ url: `${API_PATH}/objects/lifecycle`, method: "get" });
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
export function getIndustryTemplates() {
  return request({ url: `${API_PATH}/industry/templates`, method: "get" });
}
export function applyIndustryTemplate(template_id: string) {
  return request({ url: `${API_PATH}/industry/apply`, method: "post", data: { template_id } });
}
export function getPipelineList(params?: any) {
  return request({ url: `${API_PATH}/pipeline/list`, method: "get", params });
}
export function getPipelineGraph() {
  return request({ url: `${API_PATH}/pipeline/graph`, method: "get" });
}
export function savePipeline(data: any) {
  return request({ url: `${API_PATH}/pipeline/save`, method: "post", data });
}
export function runPipeline(pipeline_id: number) {
  return request({ url: `${API_PATH}/pipeline/run`, method: "post", data: { pipeline_id } });
}
export function getPipelineData(pipeline_id: number, limit = 50) {
  return request({
    url: `${API_PATH}/pipeline/data`,
    method: "post",
    data: { pipeline_id, limit },
  });
}
export function getWorkshopList() {
  return request({ url: `${API_PATH}/workshop/list`, method: "get" });
}
export function getWorkshopObjects() {
  return request({ url: `${API_PATH}/workshop/objects`, method: "get" });
}
export function saveWorkshopApp(data: any) {
  return request({ url: `${API_PATH}/workshop/save`, method: "post", data });
}
export function workshopPreview(app_id: number, limit = 50) {
  return request({ url: `${API_PATH}/workshop/preview`, method: "post", data: { app_id, limit } });
}
// 后端 `/workshop/delete` 声明的是 `data: dict`；原先这里传裸数字 `id`，
// FastAPI 解不出 dict 直接 422 ⇒ 界面上点「删除应用」永远删不掉。
export function deleteWorkshopApp(id: number) {
  return request({ url: `${API_PATH}/workshop/delete`, method: "delete", data: { id } });
}
export function submitWorkshopApp(app_id: number, data: any) {
  return request({ url: `${API_PATH}/workshop/submit`, method: "post", data: { app_id, data } });
}
export function getAssetLineage(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/lineage`, method: "get" });
}
export function getAccessRules() {
  return request({ url: `${API_PATH}/access/list`, method: "get" });
}
export function getAccessMatrix() {
  return request({ url: `${API_PATH}/access/matrix`, method: "get" });
}
export function accessPreview(userId: number) {
  return request({ url: `${API_PATH}/access/preview`, method: "get", params: { user_id: userId } });
}
export function accessPreviewRole(role: string) {
  return request({ url: `${API_PATH}/access/preview-role`, method: "get", params: { role } });
}
export function saveAccessRule(data: any) {
  return request({ url: `${API_PATH}/access/save`, method: "post", data });
}
export function removeAccessRule(id: number) {
  return request({ url: `${API_PATH}/access/remove`, method: "delete", params: { id } });
}
export function getDqOverview() {
  return request({ url: `${API_PATH}/dq/overview`, method: "get" });
}
export function scanAllDq() {
  return request({ url: `${API_PATH}/dq/scan`, method: "post" });
}
export function scanDq(table: string) {
  return request({ url: `${API_PATH}/dq/run`, method: "post", data: { table } });
}
export function getDqAlert() {
  return request({ url: `${API_PATH}/dq/alert`, method: "get" });
}
export function saveDomain(data: any) {
  return request({ url: `${API_PATH}/domain/save`, method: "post", data });
}
export function removeDomain(id: number) {
  return request({ url: `${API_PATH}/domain/remove`, method: "delete", params: { id } });
}
export function getDomainObjects() {
  return request({ url: `${API_PATH}/domain/objects`, method: "get" });
}
export function getGovernanceOverview() {
  return request({ url: `${API_PATH}/governance/overview`, method: "get" });
}
export function autoLinkQueryKg() {
  return request({ url: `${API_PATH}/assets/kg/auto-link`, method: "post" });
}
export function getQueryConcepts(params?: any) {
  return request({ url: `${API_PATH}/concepts/list`, method: "get", params });
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
// 数据生命周期/删除策略（Palantir Data Lifetime）
export function getDataLifetime() {
  return request({ url: `${API_PATH}/dl/list`, method: "get" });
}
export function saveDataLifetime(data: {
  id?: number;
  table: string;
  retention_days: number;
  enabled?: boolean;
}) {
  return request({ url: `${API_PATH}/dl/save`, method: "post", data });
}
export function removeDataLifetime(ids: number[]) {
  return request({ url: `${API_PATH}/dl/remove`, method: "delete", data: ids });
}
export function saveQueryAsset(
  data: {
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
  },
  opts?: { silent?: boolean }
) {
  return request({
    url: `${API_PATH}/assets/save`,
    method: "post",
    data,
    headers: opts?.silent ? { _silent: "true" } : undefined,
  });
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
  enum?: string[];
}) {
  return request({ url: `${API_PATH}/assets/column/save`, method: "post", data });
}

/**
 * 批量维护表级元数据（中文名/业务域/描述）。
 * 上游库常缺注释，一张张填不现实；这里一次提交多行，同一事务保存。
 * 只传 alias 时不会清空已填的 description（服务端"给了才覆盖"）。
 */
export function batchSaveQueryAssetMeta(
  items: Array<{
    table_name: string;
    alias?: string;
    domain?: string;
    description?: string;
    business_scenarios?: string;
  }>
) {
  return request({ url: `${API_PATH}/assets/batch-meta`, method: "post", data: { items } });
}

// 基准测试
export function runQueryBenchmark() {
  return request({ url: `${API_PATH}/benchmark/run`, method: "post" });
}
export function getQueryBenchmarkStatus(run_id: string) {
  return request({ url: `${API_PATH}/benchmark/status`, method: "get", params: { run_id } });
}

// ---------------------------------------------------------------------------
// 问数评测（NL2SQL Eval）：测试集 / 生成 / 运行 / 报表 / 消融
// ---------------------------------------------------------------------------
export function getEvalCases(params?: {
  datasource?: string;
  difficulty?: string;
  form?: string;
  scenario?: string;
  dataset?: string;
  enabled?: boolean;
}) {
  return request({ url: `${API_PATH}/eval/cases`, method: "get", params });
}

export function upsertEvalCase(data: any) {
  return request({ url: `${API_PATH}/eval/cases`, method: "post", data });
}

export function deleteEvalCases(ids: number[]) {
  return request({ url: `${API_PATH}/eval/cases`, method: "delete", data: ids });
}

/** 批量导入题库：items（JSON 数组）或 csv（文本，含表头）。 */
export function importEvalCases(data: { items?: any[]; csv?: string; datasource?: string }) {
  return request({
    url: `${API_PATH}/eval/cases/import`,
    method: "post",
    data,
    timeout: 180000,
  });
}

/** 校验金标 SQL：ids 为空时按 datasource/dataset 全量校验。 */
export function verifyEvalCases(data: { ids?: number[]; datasource?: string; dataset?: string }) {
  return request({
    url: `${API_PATH}/eval/cases/verify`,
    method: "post",
    data: data || {},
    timeout: 300000,
  });
}

/** 停止进行中的评测（含消融/方差子运行）。 */
export function stopEvalRun(run_id: string) {
  return request({ url: `${API_PATH}/eval/stop`, method: "post", data: { run_id } });
}

/** 逐题进度（运行中实时表）。 */
export function getEvalItems(run_id: string) {
  return request({
    url: `${API_PATH}/eval/items`,
    method: "get",
    params: { run_id },
    headers: { _silent: "true" },
  });
}

/** 导出题库 CSV（responseType=blob）。 */
export function exportEvalCases(params?: { datasource?: string; dataset?: string }) {
  return request({
    url: `${API_PATH}/eval/cases/export`,
    method: "get",
    params,
    responseType: "blob",
  });
}

/** 导出逐题结果 CSV（responseType=blob）。 */
export function exportEvalReport(run_id: string) {
  return request({
    url: `${API_PATH}/eval/report/export`,
    method: "get",
    params: { run_id },
    responseType: "blob",
  });
}

/** 生成一轮测试题：LLM 出题 + 金标执行校验，耗时较长（30~60s）。 */
export function generateEvalRound(data: {
  datasource: string;
  difficulty: string;
  form: string;
  n: number;
}) {
  return request({
    url: `${API_PATH}/eval/generate`,
    method: "post",
    data,
    timeout: 180000,
  });
}

/** 启动一轮评测（后台执行，立即返回 run_id）。 */
export function startEvalRun(data?: { filter?: any; mode?: string; config?: any }) {
  return request({ url: `${API_PATH}/eval/run`, method: "post", data: data ?? {} });
}

export function getEvalStatus(run_id: string) {
  return request({
    url: `${API_PATH}/eval/status`,
    method: "get",
    params: { run_id },
    headers: { _silent: "true" },
  });
}

export function getEvalReport(run_id: string) {
  return request({ url: `${API_PATH}/eval/report`, method: "get", params: { run_id } });
}

/** 两次运行对比（跨模型/跨版本回归）。 */
export function compareEvalRuns(base: string, target: string) {
  return request({
    url: `${API_PATH}/eval/compare`,
    method: "get",
    params: { base, target },
    timeout: 300000,
  });
}

/** 对比结果导出为 HTML 报告（自包含、可打印）。 */
export function exportEvalCompare(base: string, target: string) {
  return request({
    url: `${API_PATH}/eval/compare/report`,
    method: "get",
    params: { base, target },
    responseType: "blob",
    timeout: 300000,
  });
}

export function getEvalRuns(limit = 30, params?: { mode?: string; dataset?: string }) {
  return request({
    url: `${API_PATH}/eval/runs`,
    method: "get",
    params: { limit, ...(params || {}) },
  });
}

/** 启动消融评测（串行跑 baseline + 各组，立即返回 run_id）。 */
export function startEvalAblation(data?: { keys?: string[]; filter?: any }) {
  return request({ url: `${API_PATH}/eval/ablation`, method: "post", data: data ?? {} });
}

export function getEvalAblation(run_id: string) {
  return request({
    url: `${API_PATH}/eval/ablation`,
    method: "get",
    params: { run_id },
    headers: { _silent: "true" },
  });
}

/** 启动**方差**评测：同一批题重复跑 N 次（串行），用于判断"差异是否真实"。 */
export function startEvalVariance(data?: { repeats?: number; filter?: any }) {
  return request({ url: `${API_PATH}/eval/variance`, method: "post", data: data ?? {} });
}

/** 方差报告：跨次均值/标准差/噪声带 + 逐题翻转 + McNemar。 */
export function getEvalVariance(run_id: string) {
  return request({
    url: `${API_PATH}/eval/variance`,
    method: "get",
    params: { run_id },
    headers: { _silent: "true" },
  });
}

/** 治理概览：覆盖率 / 孤儿表 / 敏感列暴露 */
export function getGovernanceSummary(datasource = "ds:4") {
  return request({
    url: `${API_PATH}/governance/summary`,
    method: "get",
    params: { datasource },
  });
}

/** 策略列表 */
export function getPolicyList(params?: any) {
  return request({ url: `${API_PATH}/policy/list`, method: "get", params });
}

/** 新建/更新策略 */
export function savePolicy(data: any) {
  return request({ url: `${API_PATH}/policy/save`, method: "post", data });
}

/** 删除策略（二次确认由调用方做） */
export function deletePolicies(ids: number[]) {
  return request({ url: `${API_PATH}/policy/delete`, method: "post", data: { ids } });
}

/** 解释某用户对表/列的访问判定（治理页「为什么」） */
export function explainAccess(params: { user_id: number; table: string; column?: string }) {
  return request({ url: `${API_PATH}/access/explain`, method: "get", params });
}

/** 访问审计（最近 N 条，新的在前） */
export function getAccessLogs(limit = 100) {
  return request({ url: `${API_PATH}/access/logs`, method: "get", params: { limit } });
}

/** 召回探针：某问题会选中哪些表（语义层调优用） */
export function recallProbe(question: string) {
  return request({ url: `${API_PATH}/recall/probe`, method: "get", params: { question } });
}

/** 重建语义召回单元（改了资产/术语/指标后手动刷新） */
export function rebuildRecall() {
  return request({ url: `${API_PATH}/recall/rebuild`, method: "post" });
}

/** 静默降级快照（哪些能力坏了但流程还在跑） */
export function getDegradedStatus() {
  return request({ url: `${API_PATH}/system/degraded`, method: "get" });
}

/** 重算表级血缘（外键 / 视图 / 命名约定 / 使用记录四源） */
export function rebuildLineage(datasource = "ds:4") {
  return request({ url: `${API_PATH}/lineage/rebuild`, method: "post", params: { datasource } });
}

/** 访问审计按入口汇总（看板：哪个入口在用、拒了多少） */
export function getAccessStats(hours = 24) {
  return request({ url: `${API_PATH}/access/stats`, method: "get", params: { hours } });
}

/** 数据质量规则模板（非空/唯一/范围） */
export function getDqRules() {
  return request({ url: `${API_PATH}/dq-rules`, method: "get" });
}

/** 执行一条质量规则（table/column 会被后端做标识符 + 白名单校验） */
export function runDqRule(params: { table: string; column: string; rule_type: string }) {
  return request({ url: `${API_PATH}/dq-rules/run`, method: "get", params });
}

/** 数据域对账：域里引用的表是否都已登记（系统库 + 各业务源已同步 schema） */
export function domainReconcile() {
  return request({ url: `${API_PATH}/domain/reconcile`, method: "get" });
}

/** 从 information_schema 全量同步表/字段到资产目录（新表白名单内的默认纳入） */
export function syncQueryAssets() {
  return request({ url: `${API_PATH}/assets/sync`, method: "post" });
}

/** 版本 diff：对比两个版本快照，返回字段级差异 */
export function getAssetVersionDiff(idA: number, idB: number) {
  return request({
    url: `${API_PATH}/assets/version/diff`,
    method: "get",
    params: { id_a: idA, id_b: idB },
  });
}

/** 权限检查（用户 × 表）：能否访问、角色、敏感列可见性 */
export function checkPermission(user_id: number, table: string) {
  return request({
    url: `${API_PATH}/access/permission-check`,
    method: "get",
    params: { user_id, table },
  });
}

/** 跨域多跳图检索：从某张表出发，返回可达节点（表/指标/对象，排除字段噪声） */
export function kgTraverse(start: string, hops = 2) {
  return request({ url: `${API_PATH}/assets/kg/traverse`, method: "post", data: { start, hops } });
}
