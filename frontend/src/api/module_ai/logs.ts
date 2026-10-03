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
