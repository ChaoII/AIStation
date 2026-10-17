import request from "@/utils/request";
import { Auth } from "@/utils/auth";

const API_PATH = "/ai/query";

export function queryAsk(data: {
  question: string;
  session_id?: number | null;
  datasource?: string | null;
  /** 当前对象上下文（从本体/实例页跳转时带上），作为确定性上下文注入 */
  object_code?: string | null;
  object_key?: string | null;
}) {
  return request({
    url: `${API_PATH}/ask`,
    method: "post",
    data,
    // 问数是"慢"功能：对象查询 / NL2SQL 单次可达 10~40s，默认 10s 超时会把请求掐断，
    // 表现为"页面没反应、输入框不清空"（实测踩到）。与其它长任务接口保持一致给足超时。
    timeout: 120000,
  });
}

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
export function getModelingObjects(datasource: string) {
  return request({
    url: `${API_PATH}/modeling/objects`,
    method: "get",
    params: { datasource },
    timeout: 30000,
  });
}
export function runModelingMetrics(data: {
  datasource: string;
  max_objects?: number;
  dry?: boolean;
}) {
  return request({ url: `${API_PATH}/modeling/metrics`, method: "post", data, timeout: 180000 });
}
export function runModelingAnnotate(data: { datasource: string; max_objects?: number }) {
  return request({ url: `${API_PATH}/modeling/annotate`, method: "post", data, timeout: 180000 });
}
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
export function getQueryDatasources() {
  return request({ url: `${API_PATH}/datasources/list`, method: "get" });
}
export function getConnectorTypes() {
  return request({ url: `${API_PATH}/connector-types`, method: "get" });
}
export function getDatasourceDetail(id: number) {
  return request({ url: `${API_PATH}/datasources/${id}/detail`, method: "get" });
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
export function importDsAsOntology(datasource_id: number, table: string, domain_code = "") {
  return request({
    url: `${API_PATH}/ontology/import-from-ds`,
    method: "post",
    data: { datasource_id, table, domain_code },
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
  });
}
export function getQueryRoles() {
  return request({ url: `${API_PATH}/datasources/roles`, method: "get" });
}
/** 筛选规则预览：提交筛选规则并返回命中/预览结果，rules 可为空（区分 None 与显式空规则）。 */
export function previewFilterRules(datasource_id: number, rules?: any) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/preview`,
    method: "post",
    data: { rules },
  });
}
/** 大模型生成候选筛选规则；rules 为当前草稿（可选） */
export function suggestFilterRules(datasource_id: number, rules?: any) {
  return request({
    url: `${API_PATH}/datasources/${datasource_id}/rules/suggest`,
    method: "post",
    data: { rules },
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
  return request({ url: `${API_PATH}/writeback/list`, method: "get" });
}
export function saveAction(data: any) {
  return request({ url: `${API_PATH}/writeback/save`, method: "post", data });
}
export function executeAction(data: any) {
  return request({ url: `${API_PATH}/writeback/execute`, method: "post", data });
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
export function approveVersionPublish(pending_id: number) {
  return request({ url: `/ai/ontology/version/approve`, method: "post", data: { pending_id } });
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
export function getVersionDiff(idA: number, idB: number) {
  return request({
    url: `${API_PATH}/assets/version/diff`,
    method: "get",
    params: { id_a: idA, id_b: idB },
  });
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
export function getDqRules() {
  return request({ url: `${API_PATH}/dq-rules`, method: "get" });
}
export function runDqRule(table: string, column: string, ruleType: string) {
  return request({
    url: `${API_PATH}/dq-rules/run`,
    method: "get",
    params: { table, column, rule_type: ruleType },
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
export function createShare(table: string) {
  return request({ url: `${API_PATH}/share/create`, method: "post", data: { table } });
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
export function getPipelineList() {
  return request({ url: `${API_PATH}/pipeline/list`, method: "get" });
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
export function deleteWorkshopApp(id: number) {
  return request({ url: `${API_PATH}/workshop/delete`, method: "delete", data: id });
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
export function runDq(table: string) {
  return request({ url: `${API_PATH}/dq/run`, method: "post", data: { table } });
}
export function scanAllDq() {
  return request({ url: `${API_PATH}/dq/scan`, method: "post" });
}
export function scanAssetSensitive(table: string) {
  return request({ url: `${API_PATH}/assets/${table}/scan-sensitive`, method: "post" });
}
export function getDqAlert() {
  return request({ url: `${API_PATH}/dq/alert`, method: "get" });
}
export function getDomains() {
  return request({ url: `${API_PATH}/domain/list`, method: "get" });
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
export function domainReconcile() {
  return request({ url: `${API_PATH}/domain/reconcile`, method: "get" });
}
export function getGovernanceOverview() {
  return request({ url: `${API_PATH}/governance/overview`, method: "get" });
}
export function getOntologyGovernance() {
  return request({ url: `${API_PATH}/ontology/governance`, method: "get" });
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
}) {
  return request({ url: `${API_PATH}/eval/cases`, method: "get", params });
}

export function upsertEvalCase(data: any) {
  return request({ url: `${API_PATH}/eval/cases`, method: "post", data });
}

export function deleteEvalCases(ids: number[]) {
  return request({ url: `${API_PATH}/eval/cases`, method: "delete", data: ids });
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

export function getEvalRuns(limit = 30) {
  return request({ url: `${API_PATH}/eval/runs`, method: "get", params: { limit } });
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
