import request from "@/utils/request";

export function getAiLogList(params?: any) {
  return request({ url: "/ai/logs/list", method: "get", params });
}

export function getAiLogStats(days = 7) {
  return request({ url: "/ai/logs/stats", method: "get", params: { days } });
}

export function getAiLogExport(days = 30, usage?: string, result?: string) {
  return request({
    url: "/ai/logs/export",
    method: "get",
    params: { days, usage, result },
  });
}

/** 最近运行明细（AI 办公室底部流水条） */
export function getAiLogRecent(limit = 6) {
  return request({ url: "/ai/logs/recent", method: "get", params: { limit } });
}

/** 工具调用时间线（谁调了哪个工具 / 多久 / 成败） */
export function getAiToolCalls(agentId?: number, limit = 20) {
  return request({
    url: "/ai/logs/tool-calls",
    method: "get",
    params: { agent_id: agentId, limit }
  });
}
