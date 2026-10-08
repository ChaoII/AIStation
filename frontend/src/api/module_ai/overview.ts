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
export function getAiCompliancePosture() {
  return request({ url: "/ai/overview/compliance-posture", method: "get" });
}
export function getAiAnomaly(days = 7) {
  return request({ url: "/ai/overview/anomaly", method: "get", params: { days } });
}
export function getAiDecisionCenter() {
  return request({ url: "/ai/overview/decision-center", method: "get" });
}
export function executeDecision(key: string) {
  return request({ url: "/ai/overview/decision/execute", method: "post", data: { key } });
}
export function runEvalBench(samples: any[], name: string) {
  return request({ url: "/ai/overview/eval-bench/run", method: "post", data: { samples, name } });
}
export function getEvalBenchList(limit = 30) {
  return request({ url: "/ai/overview/eval-bench/list", method: "get", params: { limit } });
}
export function getUnifiedAudit(days = 7) {
  return request({ url: "/ai/overview/unified-audit", method: "get", params: { days } });
}
export function getAiActivityTimeline(days = 7, limit = 60) {
  return request({ url: "/ai/overview/activity-timeline", method: "get", params: { days, limit } });
}
