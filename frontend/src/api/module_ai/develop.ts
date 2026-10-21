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
