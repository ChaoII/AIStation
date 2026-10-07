import request from "@/utils/request";

export function getAiOverviewStats() {
  return request({ url: "/ai/overview/stats", method: "get" });
}
export function runAiEval(samples: any[]) {
  return request({ url: "/ai/overview/eval", method: "post", data: { samples } });
}
export function getAiHealth(days = 7) {
  return request({ url: "/ai/overview/health", method: "get", params: { days } });
}
export function getAiAudit(days = 7) {
  return request({ url: "/ai/overview/audit", method: "get", params: { days } });
}
export function getAiRuntime() {
  return request({ url: "/ai/overview/runtime", method: "get" });
}
export function compassSearch(keyword: string) {
  return request({ url: "/ai/query/compass/search", method: "get", params: { keyword } });
}
export function getAiAipControl(limit = 20) {
  return request({ url: "/ai/overview/aip-control", method: "get", params: { limit } });
}
