import request from "@/utils/request";

const API_PATH = "/ai/ontology";

export function getOntObjects(domain_code?: string) {
  // domain_code 传 undefined = 全部；传 "" = 未分组
  return request({
    url: `${API_PATH}/objects`,
    method: "get",
    params: domain_code === undefined ? {} : { domain_code },
  });
}
export function saveOntObject(data: any) {
  return request({ url: `${API_PATH}/object/save`, method: "post", data });
}
export function getOntObjectFull(code: string) {
  return request({ url: `${API_PATH}/object/${code}/full`, method: "get" });
}
export function getOntDependents(code: string) {
  return request({ url: `${API_PATH}/object/${code}/dependents`, method: "get" });
}

/* ---------------- 工作副本（改动先入草稿，保存才落库） ---------------- */
export function getOntWip() {
  return request({ url: `${API_PATH}/wip`, method: "get" });
}
export function stageOntChange(data: {
  kind: string;
  action: "create" | "update" | "delete" | "restore";
  data: Record<string, any>;
  target_key?: string;
}) {
  return request({ url: `${API_PATH}/wip/stage`, method: "post", data });
}
export function discardOntWip() {
  return request({ url: `${API_PATH}/wip/discard`, method: "post" });
}
export function saveOntWip(confirm_name = "") {
  return request({ url: `${API_PATH}/wip/save`, method: "post", data: { confirm_name } });
}
export function stageOntRestore(version_id: number) {
  return request({ url: `${API_PATH}/wip/restore/${version_id}`, method: "post" });
}

/* ---------------- 导入 / 导出 / 用量 / 清理 ---------------- */
export function exportOntology(domain_code?: string) {
  return request({ url: `${API_PATH}/export`, method: "get", params: { domain_code } });
}
export function importOntology(payload: any, mode: "stage" | "apply" = "stage") {
  return request({ url: `${API_PATH}/import`, method: "post", data: { payload, mode } });
}
export function getOntUsage(object_code = "") {
  return request({ url: `${API_PATH}/usage`, method: "get", params: { object_code } });
}
export function getOntCleanup() {
  return request({ url: `${API_PATH}/cleanup`, method: "get" });
}

/* ---------------- 实例层（对象探索 / 实例图 / 对象视图 / Writeback） ---------------- */
export function searchOntInstances(
  code: string,
  params: {
    keyword?: string;
    limit?: number;
    offset?: number;
    filters?: Record<string, any>;
    /** 场景编码：在场景内读时叠加该场景编辑（留空 = 主本体） */
    scenario?: string;
  } = {}
) {
  return request({
    url: `${API_PATH}/instances/${code}`,
    method: "get",
    params: {
      keyword: params.keyword || "",
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
      filters: params.filters ? JSON.stringify(params.filters) : "",
      scenario: params.scenario || "",
    },
  });
}
export function getOntInstance(code: string, key: string, scenario = "") {
  return request({
    url: `${API_PATH}/instance/${code}/${key}`,
    method: "get",
    params: scenario ? { scenario } : {},
  });
}
export function pivotOntInstance(
  code: string,
  key: string,
  link_id: number,
  limit = 50,
  scenario = ""
) {
  return request({
    url: `${API_PATH}/instance/${code}/${key}/pivot`,
    method: "get",
    params: scenario ? { link_id, limit, scenario } : { link_id, limit },
  });
}
export function getOntInstanceGraph(data: {
  object_code: string;
  key: string;
  link_ids?: number[];
  depth?: number;
  limit?: number;
  /** 场景编码：在场景内展开图谱（邻居也读叠加数据） */
  scenario?: string;
}) {
  return request({ url: `${API_PATH}/instance/graph`, method: "post", data });
}
export function writebackOntInstance(data: {
  object_code: string;
  key: string;
  props: Record<string, any>;
}) {
  return request({ url: `${API_PATH}/instance/writeback`, method: "post", data });
}

/* ---------------- P5：高级类型系统 ---------------- */
// 对象类型组
export function getOntGroups() {
  return request({ url: `${API_PATH}/groups`, method: "get" });
}
export function saveOntGroup(data: Record<string, any>) {
  return request({ url: `${API_PATH}/group/save`, method: "post", data });
}
export function removeOntGroup(id: number) {
  return request({ url: `${API_PATH}/group/remove`, method: "delete", params: { id } });
}
// 值类型
export function getOntValueTypes() {
  return request({ url: `${API_PATH}/value-types`, method: "get" });
}
export function saveOntValueType(data: Record<string, any>) {
  return request({ url: `${API_PATH}/value-type/save`, method: "post", data });
}
export function removeOntValueType(id: number) {
  return request({ url: `${API_PATH}/value-type/remove`, method: "delete", params: { id } });
}
export function validateOntValue(code: string, value: any) {
  return request({ url: `${API_PATH}/value-type/validate`, method: "post", data: { code, value } });
}
// 共享属性
export function getOntSharedProperties() {
  return request({ url: `${API_PATH}/shared-properties`, method: "get" });
}
export function saveOntSharedProperty(data: Record<string, any>) {
  return request({ url: `${API_PATH}/shared-property/save`, method: "post", data });
}
export function removeOntSharedProperty(id: number) {
  return request({ url: `${API_PATH}/shared-property/remove`, method: "delete", params: { id } });
}
// 接口
export function getOntInterfaces() {
  return request({ url: `${API_PATH}/interfaces`, method: "get" });
}
export function saveOntInterface(data: Record<string, any>) {
  return request({ url: `${API_PATH}/interface/save`, method: "post", data });
}
export function removeOntInterface(id: number) {
  return request({ url: `${API_PATH}/interface/remove`, method: "delete", params: { id } });
}
export function setOntInterfaceImpls(code: string, object_codes: string[]) {
  return request({
    url: `${API_PATH}/interface/impls`,
    method: "post",
    data: { code, object_codes },
  });
}
export function checkOntInterface(code = "", object_code = "") {
  return request({
    url: `${API_PATH}/interface/check`,
    method: "get",
    params: { code, object_code },
  });
}
// 派生属性
export function getOntDerivedIssues() {
  return request({ url: `${API_PATH}/derived/issues`, method: "get" });
}
export function computeOntDerived(data: {
  object_code: string;
  key: string;
  property: string;
  limit?: number;
}) {
  return request({ url: `${API_PATH}/derived/compute`, method: "post", data });
}
// 通用引用检查
export function getOntReferences(kind: string, code: string) {
  return request({ url: `${API_PATH}/references`, method: "get", params: { kind, code } });
}
export function getOntProperties(object_code = "") {
  return request({ url: `${API_PATH}/properties`, method: "get", params: { object_code } });
}
export function saveOntProperty(data: any) {
  return request({ url: `${API_PATH}/property/save`, method: "post", data });
}
export function getOntLinks(object_code = "") {
  return request({ url: `${API_PATH}/links`, method: "get", params: { object_code } });
}
export function saveOntLink(data: any) {
  return request({ url: `${API_PATH}/link/save`, method: "post", data });
}
export function getOntActions(object_code = "") {
  return request({ url: `${API_PATH}/actions`, method: "get", params: { object_code } });
}
export function saveOntAction(data: any) {
  return request({ url: `${API_PATH}/action/save`, method: "post", data });
}
export function removeOnt(kind: string, id: number) {
  return request({ url: `${API_PATH}/remove`, method: "delete", params: { kind, id } });
}
export function materializeOntObject(code: string) {
  return request({ url: `${API_PATH}/materialize`, method: "post", data: { code } });
}
export function getOntFunctions(object_code = "") {
  return request({ url: `${API_PATH}/functions`, method: "get", params: { object_code } });
}
export function saveOntFunction(data: any) {
  return request({ url: `${API_PATH}/function/save`, method: "post", data });
}
/** 执行本体函数（表达式/关联聚合/外部服务/模型） */
export function runOntFunction(data: {
  code: string;
  args: Record<string, any>;
  object_key?: string;
}) {
  return request({ url: `${API_PATH}/function/run`, method: "post", data });
}
/** 校验函数定义（不保存） */
export function checkOntFunction(data: Record<string, any>) {
  return request({ url: `${API_PATH}/function/check`, method: "post", data });
}
/** 可用的内置函数清单 */
export function getOntFunctionBuiltins() {
  return request({ url: `${API_PATH}/function/builtins`, method: "get" });
}

/* ---------------- P3：决策数据 + 决策谱系 ---------------- */
export function getOntDecisions(params: Record<string, any> = {}) {
  return request({ url: `${API_PATH}/decisions`, method: "get", params });
}
export function getOntDecision(code: string) {
  return request({ url: `${API_PATH}/decision/${encodeURIComponent(code)}`, method: "get" });
}
export function saveOntDecision(data: Record<string, any>) {
  return request({ url: `${API_PATH}/decision/save`, method: "post", data });
}
export function removeOntDecision(code: string) {
  return request({ url: `${API_PATH}/decision/remove`, method: "post", data: { code } });
}
/** 拍板：批准 / 否决 */
export function decideOntDecision(code: string, approve: boolean, note = "") {
  return request({
    url: `${API_PATH}/decision/decide`,
    method: "post",
    data: { code, approve, note },
  });
}
/** 执行决策（走动作七道闸并自动捕获下游影响） */
export function executeOntDecision(code: string, approve = false) {
  return request({ url: `${API_PATH}/decision/execute`, method: "post", data: { code, approve } });
}
/** 记录决策的事后结果 */
export function recordOntDecisionOutcome(code: string, outcome: Record<string, any>) {
  return request({ url: `${API_PATH}/decision/outcome`, method: "post", data: { code, outcome } });
}
/** 决策谱系（上游依据 + 下游影响，可递归） */
export function getOntDecisionLineage(code: string, depth = 3) {
  return request({
    url: `${API_PATH}/decision-lineage/${encodeURIComponent(code)}`,
    method: "get",
    params: { depth },
  });
}
export function getOntDecisionGraph(params: Record<string, any> = {}) {
  return request({ url: `${API_PATH}/decision-graph`, method: "get", params });
}
export function getOntDecisionStats() {
  return request({ url: `${API_PATH}/decision-stats`, method: "get" });
}
export function initOntDecisionObjectType() {
  return request({ url: `${API_PATH}/decision/init-object-type`, method: "post" });
}

/* ---------------- P4：对象权限 ---------------- */
/** 对象类型的安全概览（Security 标签页） */
export function getOntSecurityOverview(object_code: string) {
  return request({ url: `${API_PATH}/security/overview`, method: "get", params: { object_code } });
}
export function getOntRowPolicies(object_code: string) {
  return request({
    url: `${API_PATH}/security/row-policies`,
    method: "get",
    params: { object_code },
  });
}
export function saveOntRowPolicy(data: Record<string, any>) {
  return request({ url: `${API_PATH}/security/row-policy/save`, method: "post", data });
}
export function removeOntRowPolicy(id: number) {
  return request({ url: `${API_PATH}/security/row-policy/remove`, method: "post", data: { id } });
}
/** 校验策略表达式（不保存） */
export function checkOntPolicy(data: { expression: string; object_code?: string }) {
  return request({ url: `${API_PATH}/security/policy-check`, method: "post", data });
}
export function getOntResourceAcl(resource_kind: string, resource_code: string) {
  return request({
    url: `${API_PATH}/security/resource-acl`,
    method: "get",
    params: { resource_kind, resource_code },
  });
}
export function saveOntResourceAcl(data: {
  resource_kind: string;
  resource_code: string;
  view_roles: string[];
  edit_roles: string[];
  manage_roles: string[];
}) {
  return request({ url: `${API_PATH}/security/resource-acl/save`, method: "post", data });
}
export function clearOntResourceAcl(resource_kind: string, resource_code: string) {
  return request({
    url: `${API_PATH}/security/resource-acl/clear`,
    method: "post",
    data: { resource_kind, resource_code },
  });
}
/** 解释某人能否看到某对象（Check access） */
export function explainOntAccess(params: {
  object_code: string;
  object_key?: string;
  user_id?: number;
}) {
  return request({ url: `${API_PATH}/security/explain`, method: "get", params });
}
export function getOntSecuritySubjects() {
  return request({ url: `${API_PATH}/security/subjects`, method: "get" });
}

/* ---------------- P5：场景（沙箱式 what-if） ---------------- */
export function getOntScenarios(params: Record<string, any> = {}) {
  return request({ url: `${API_PATH}/scenarios`, method: "get", params });
}
export function getOntScenario(code: string) {
  return request({ url: `${API_PATH}/scenario/${encodeURIComponent(code)}`, method: "get" });
}
export function saveOntScenario(data: Record<string, any>) {
  return request({ url: `${API_PATH}/scenario/save`, method: "post", data });
}
/** 合并场景到主本体（单事务，失败全回滚） */
export function applyOntScenario(code: string) {
  return request({ url: `${API_PATH}/scenario/apply`, method: "post", data: { code } });
}
export function discardOntScenario(code: string) {
  return request({ url: `${API_PATH}/scenario/discard`, method: "post", data: { code } });
}
export function duplicateOntScenario(code: string, name = "") {
  return request({
    url: `${API_PATH}/scenario/duplicate`,
    method: "post",
    data: { code, name },
  });
}
export function removeOntScenario(code: string) {
  return request({ url: `${API_PATH}/scenario/remove`, method: "post", data: { code } });
}
export function getOntScenarioDiff(code: string) {
  return request({ url: `${API_PATH}/scenario/${encodeURIComponent(code)}/diff`, method: "get" });
}
export function compareOntScenarios(codes: string[]) {
  return request({ url: `${API_PATH}/scenario/compare`, method: "post", data: { codes } });
}
export function expireOntScenarios() {
  return request({ url: `${API_PATH}/scenario/expire`, method: "post" });
}
export function getOntChangelog(object_code = "", limit = 50) {
  return request({ url: `${API_PATH}/changelog`, method: "get", params: { object_code, limit } });
}
export function publishOntVersion(code: string) {
  return request({ url: `${API_PATH}/version/publish`, method: "post", data: { code } });
}
export function getOntVersions(object_code = "") {
  return request({ url: `${API_PATH}/version/list`, method: "get", params: { object_code } });
}
export function rollbackOntVersion(version_id: number) {
  return request({ url: `${API_PATH}/version/rollback`, method: "post", data: { version_id } });
}
export function getOntVersionDiff(version_id: number) {
  return request({ url: `${API_PATH}/version/diff`, method: "get", params: { version_id } });
}
// 本体能力登记（getOntCapabilities / saveOntCapability）已删除（2026-10-19）：
// Palantir 没有 "Capability" 本体对象类型，且本项目里 Agent 装配能力走的是
// ai_agents.capabilities（函数/动作 code 列表），这张登记表与之零关联。
export function getOntAnalyze() {
  return request({ url: `${API_PATH}/analyze`, method: "get" });
}

// ---- 本体（对象类型的顶层容器）----
export function getOntDomains() {
  return request({ url: `${API_PATH}/domains`, method: "get" });
}
export function saveOntDomain(data: any) {
  return request({ url: `${API_PATH}/domain/save`, method: "post", data });
}
export function removeOntDomain(id: number) {
  return request({ url: `${API_PATH}/domain/remove`, method: "delete", params: { id } });
}
export function assignOntDomain(domain_code: string, object_codes: string[]) {
  return request({
    url: `${API_PATH}/domain/assign`,
    method: "post",
    data: { domain_code, object_codes },
  });
}

// ---- 维护动作（原先只能调接口，现在有界面入口）----
export function enrichOntology() {
  return request({ url: `${API_PATH}/enrich`, method: "post" });
}
export function seedOntologyExamples() {
  return request({ url: `${API_PATH}/seed-examples`, method: "post" });
}
/** 执行本体动作。**不接受 approve 参数**：需审批的动作一律生成待审批单，
 *  由管理员走 {@link approveOntAction} 批准。原先的 approve 入参可由请求体携带，
 *  任何持 execute 权限的人都能自我批准（P0-2），故移除。 */
export function executeOntAction(data: {
  code: string;
  object_key: string;
  params: Record<string, any>;
  /** 场景编码：在场景内执行则只暂存、不写真实表 */
  scenario?: string;
}) {
  return request({ url: `${API_PATH}/action/execute`, method: "post", data });
}
/** 批准一条待审批的本体动作（AuthManage；读回待审批单并原样回放执行） */
export function approveOntAction(approval_id: number) {
  return request({ url: `${API_PATH}/action/approve`, method: "post", data: { approval_id } });
}
/** 试运行本体动作：评估提交条件/规则/副作用，**不写库** */
export function testRunOntAction(data: {
  code: string;
  object_key: string;
  params: Record<string, any>;
}) {
  return request({ url: `${API_PATH}/action/test-run`, method: "post", data });
}
export function getOntVersionPending() {
  return request({ url: `${API_PATH}/version/pending`, method: "get" });
}
export function approveOntVersion(pending_id: number) {
  return request({ url: `${API_PATH}/version/approve`, method: "post", data: { pending_id } });
}

/* ---------------- A) 对象视图 ---------------- */
export function getOntObjectViews(params: Record<string, any> = {}) {
  return request({ url: `${API_PATH}/object-views`, method: "get", params });
}
export function getOntObjectView(code: string) {
  return request({ url: `${API_PATH}/object-views/${encodeURIComponent(code)}`, method: "get" });
}
export function getOntStandardView(objectCode: string, formFactor = "full") {
  return request({
    url: `${API_PATH}/object-views/standard/${encodeURIComponent(objectCode)}`,
    method: "get",
    params: { form_factor: formFactor },
  });
}
export function renderOntObjectView(code: string, objectKey: string, scenario = "") {
  return request({
    url: `${API_PATH}/object-views/render/${encodeURIComponent(code)}/${encodeURIComponent(objectKey)}`,
    method: "get",
    params: { scenario },
  });
}
export function saveOntObjectView(data: Record<string, any>) {
  return request({ url: `${API_PATH}/object-views/save`, method: "post", data });
}
export function setDefaultOntObjectView(code: string) {
  return request({ url: `${API_PATH}/object-views/default`, method: "post", data: { code } });
}
export function removeOntObjectView(code: string) {
  return request({ url: `${API_PATH}/object-views/remove`, method: "post", data: { code } });
}
export function getOntObjectViewVersions(code: string) {
  return request({
    url: `${API_PATH}/object-views/${encodeURIComponent(code)}/versions`,
    method: "get",
  });
}
export function restoreOntObjectView(code: string, version: number) {
  return request({
    url: `${API_PATH}/object-views/restore`,
    method: "post",
    data: { code, version },
  });
}
export function syncDefaultOntObjectViews() {
  return request({ url: `${API_PATH}/object-views/sync-defaults`, method: "post" });
}
export function getOntObjectViewMeta() {
  return request({ url: `${API_PATH}/object-view-meta`, method: "get" });
}

/* ---------------- B) 索引 ---------------- */
export function getOntIndexes(params: Record<string, any> = {}) {
  return request({ url: `${API_PATH}/indexes`, method: "get", params });
}
export function getOntIndexSummary() {
  return request({ url: `${API_PATH}/index/summary`, method: "get" });
}
export function saveOntIndex(data: Record<string, any>) {
  return request({ url: `${API_PATH}/index/save`, method: "post", data });
}
export function buildOntIndex(id: number) {
  return request({ url: `${API_PATH}/index/build`, method: "post", data: { id } });
}
export function buildAllOntIndexes(objectCode = "") {
  return request({
    url: `${API_PATH}/index/build-all`,
    method: "post",
    data: { object_code: objectCode },
  });
}
export function retryOntIndexes() {
  return request({ url: `${API_PATH}/index/retry`, method: "post" });
}
export function removeOntIndex(id: number) {
  return request({ url: `${API_PATH}/index/remove`, method: "post", data: { id } });
}
export function markOntIndexStale(objectCode: string) {
  return request({
    url: `${API_PATH}/index/mark-stale`,
    method: "post",
    data: { object_code: objectCode },
  });
}
export function suggestOntIndexes(objectCode: string) {
  return request({
    url: `${API_PATH}/index/suggest/${encodeURIComponent(objectCode)}`,
    method: "get",
  });
}
export function applyOntIndexSuggestions(objectCode: string, onlyHigh = true) {
  return request({
    url: `${API_PATH}/index/apply-suggestions`,
    method: "post",
    data: { object_code: objectCode, only_high: onlyHigh },
  });
}

/* ---------------- C) 分支 / 提案 ---------------- */
export function getOntBranches(status = "") {
  return request({ url: `${API_PATH}/branches`, method: "get", params: { status } });
}
export function getOntBranch(code: string) {
  return request({ url: `${API_PATH}/branch/${encodeURIComponent(code)}`, method: "get" });
}
export function createOntBranch(title: string, description = "") {
  return request({
    url: `${API_PATH}/branch/create`,
    method: "post",
    data: { title, description },
  });
}
export function saveOntBranchChange(data: Record<string, any>) {
  return request({ url: `${API_PATH}/branch/save`, method: "post", data });
}
export function getOntProposals(tab = "") {
  return request({ url: `${API_PATH}/proposals`, method: "get", params: { tab } });
}
export function getOntProposal(code: string) {
  return request({ url: `${API_PATH}/proposal/${encodeURIComponent(code)}`, method: "get" });
}
export function requestOntProposalReview(code: string, reviewers: string[]) {
  return request({
    url: `${API_PATH}/proposal/request-review`,
    method: "post",
    data: { code, reviewers },
  });
}
export function reviewOntProposalTask(taskId: number, approve: boolean, note = "") {
  return request({
    url: `${API_PATH}/proposal/review-task`,
    method: "post",
    data: { task_id: taskId, approve, note },
  });
}
export function reviewAllOntProposalTasks(code: string, approve: boolean) {
  return request({
    url: `${API_PATH}/proposal/review-all`,
    method: "post",
    data: { code, approve },
  });
}
export function mergeOntProposal(code: string) {
  return request({ url: `${API_PATH}/proposal/merge`, method: "post", data: { code } });
}
export function closeOntProposal(code: string) {
  return request({ url: `${API_PATH}/proposal/close`, method: "post", data: { code } });
}
export function discardOntProposalTask(taskId: number) {
  return request({
    url: `${API_PATH}/proposal/discard-task`,
    method: "post",
    data: { task_id: taskId },
  });
}
export function commentOntProposal(code: string, body: string, taskId = 0) {
  return request({
    url: `${API_PATH}/proposal/comment`,
    method: "post",
    data: { code, body, task_id: taskId },
  });
}
export function getOntProposalChangelog(code: string) {
  return request({
    url: `${API_PATH}/proposal/${encodeURIComponent(code)}/changelog`,
    method: "get",
  });
}

/* ---------------- D) 演示数据 ---------------- */
export function getOntDemoStatus() {
  return request({ url: `${API_PATH}/demo/status`, method: "get" });
}
export function getOntDemoReport() {
  return request({ url: `${API_PATH}/demo/report`, method: "get" });
}
export function loadOntDemo(force = false) {
  return request({ url: `${API_PATH}/demo/load`, method: "post", data: { force } });
}
export function clearOntDemo() {
  return request({ url: `${API_PATH}/demo/clear`, method: "post" });
}

export function shareOntObjectView(code: string, shareMode: string, shareRoles: string[] = []) {
  return request({
    url: `${API_PATH}/object-views/share`,
    method: "post",
    data: { code, share_mode: shareMode, share_roles: shareRoles },
  });
}
export function getOntObjectViewLink(code: string, objectKey = "") {
  return request({
    url: `${API_PATH}/object-views/${encodeURIComponent(code)}/link`,
    method: "get",
    params: { object_key: objectKey },
  });
}
export function getOntFilterOps() {
  return request({ url: `${API_PATH}/object-view-meta/filters`, method: "get" });
}

// ---- 大模型自动建模（两段式：预览 → 勾选 → 精确落库）----
// 预览返回逐条候选（`items`），应用只落用户勾选的那批；**应用阶段不重跑大模型**。
export function autoModelPreview(data: {
  datasource: string;
  scope: "metrics" | "annotations";
  max_objects?: number;
  offset?: number;
}) {
  return request({
    url: `${API_PATH}/auto-model/preview`,
    method: "post",
    data,
    timeout: 180000,
  });
}
export function autoModelApply(data: {
  datasource: string;
  scope: "metrics" | "annotations";
  items: any[];
}) {
  return request({ url: `${API_PATH}/auto-model/apply`, method: "post", data, timeout: 180000 });
}

/* ---------------- 图视图（保存视图 / 图模板 / 时间轴） ---------------- */
export function getGraphViewList(domain_code = "", kind = "", shared = "") {
  return request({
    url: `${API_PATH}/graph-views`,
    method: "get",
    params: { domain_code, kind, shared },
  });
}
export function getGraphViewDetail(code: string) {
  return request({ url: `${API_PATH}/graph-views/${code}`, method: "get" });
}
export function saveGraphView(data: any) {
  return request({ url: `${API_PATH}/graph-views/save`, method: "post", data });
}
export function setDefaultGraphView(code: string, domain_code = "") {
  return request({
    url: `${API_PATH}/graph-views/default`,
    method: "post",
    data: { code, domain_code },
  });
}
export function removeGraphView(code: string) {
  return request({ url: `${API_PATH}/graph-views/remove`, method: "post", data: { code } });
}
export function getGraphViewVersions(code: string) {
  return request({ url: `${API_PATH}/graph-views/${code}/versions`, method: "get" });
}
export function restoreGraphView(code: string, version: number) {
  return request({
    url: `${API_PATH}/graph-views/restore`,
    method: "post",
    data: { code, version },
  });
}
export function shareGraphView(code: string, share_mode: string, share_roles: string[]) {
  return request({
    url: `${API_PATH}/graph-views/share`,
    method: "post",
    data: { code, share_mode, share_roles },
  });
}
export function getGraphViewLink(code: string) {
  return request({ url: `${API_PATH}/graph-views/${code}/link`, method: "get" });
}
export function getTimelineProps(domain_code = "") {
  return request({
    url: `${API_PATH}/graph-views/timeline-props`,
    method: "get",
    params: { domain_code },
  });
}
