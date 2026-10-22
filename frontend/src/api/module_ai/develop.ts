import request from "@/utils/request";

// AI 集成开放平台 —— 管理面 API 前缀。
// 说明：开放数据面（/develop-api）供外部平台持 appid:appkey 调用，本文件也导出对应封装。
const API_PATH = "/ai/develop";

/** 分页查询 AI 集成应用（params: keyword / page_no / page_size） */
export function getDevelopAppList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

/** 创建应用；返回一次明文 appkey（仅此一次） */
export function createApp(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

/** 更新应用 */
export function updateApp(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

/** 批量删除应用（ids 为应用 ID 数组） */
export function deleteApp(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

/** 启停应用 */
export function toggleApp(id: number, enabled: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", data: { enabled } });
}

/** 重置应用 AppKey；返回一次明文新 appkey（仅此一次） */
export function resetAppkey(id: number) {
  return request({ url: `${API_PATH}/reset-key/${id}`, method: "post" });
}

/** 分页查询调用日志（params: app_id / category / method / status / page_no / page_size） */
export function getCallLogs(params?: any) {
  return request({ url: `${API_PATH}/call-logs`, method: "get", params });
}

/** 分页查询 MCP 会话（params: app_id / page_no / page_size） */
export function getMcpSessions(params?: any) {
  return request({ url: `${API_PATH}/mcp-sessions`, method: "get", params });
}

/** 全部开放能力元数据（管理面，接入文档展示「有哪些能力可授权」）。 */
export function getCapabilities() {
  return request({ url: `${API_PATH}/capabilities`, method: "get" });
}

/** 分页查询调用审批（params: status / app_id / page_no / page_size）。 */
export function getApprovals(params?: any) {
  return request({ url: `${API_PATH}/approvals`, method: "get", params });
}

/** 审批调用：批准会立即以原应用身份执行；拒绝只记录意见。 */
export function reviewApproval(id: number, data: { approve: boolean; note?: string }) {
  return request({ url: `${API_PATH}/approvals/${id}/review`, method: "post", data });
}

/** 调用概览（今日/趋势/Top 能力/应用与审批计数）。 */
export function getDevelopStats(days = 7) {
  return request({ url: `${API_PATH}/stats`, method: "get", params: { days } });
}

/** 某应用当日按品类调用次数 + 配额上限（用量可视化）。 */
export function getAppUsage(appId: number) {
  return request({ url: `${API_PATH}/apps/${appId}/usage`, method: "get" });
}

/** 导出调用日志 CSV（返回 blob）。 */
export function exportCallLogs(params?: any) {
  return request({
    url: `${API_PATH}/call-logs/export`,
    method: "get",
    params,
    responseType: "blob",
  });
}

/** 管理端能力试调（跳过审批，仍走权限与审计）。 */
export function tryCapability(appId: number, data: { capability: string; payload: any }) {
  return request({ url: `${API_PATH}/apps/${appId}/try`, method: "post", data });
}

/**
 * 开放数据面鉴权校验：携带 `Authorization: Bearer <appid>:<appkey>` 调用。
 * 未传入 appid/appkey 时不覆盖自动附加的会话令牌（此时会命中管理面鉴权）。
 */
export function verifyAuth(appid?: string, appkey?: string) {
  return request({
    url: "/ai/develop-api/auth/verify",
    method: "get",
    headers: appid && appkey ? { Authorization: `Bearer ${appid}:${appkey}` } : undefined,
  });
}

/** 某应用的嵌入令牌列表（只读元信息，绝不含明文）。 */
export function getEmbedTokens(appId: number) {
  return request({ url: `${API_PATH}/tokens`, method: "get", params: { app_id: appId } });
}

/** 管理端签发体验令牌（有效期 2 小时；明文仅返回一次）。 */
export function mintEmbedToken(data: { app_id: number; kind: string; target_id: number }) {
  return request({ url: `${API_PATH}/tokens`, method: "post", data });
}

/** 吊销嵌入令牌（立即生效，不可恢复）。 */
export function revokeEmbedToken(id: number) {
  return request({ url: `${API_PATH}/tokens/${id}/revoke`, method: "put" });
}
