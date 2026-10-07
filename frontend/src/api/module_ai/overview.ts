import request from "@/utils/request";

export function getAiOverviewStats() {
  return request({ url: "/ai/overview/stats", method: "get" });
}
export function runAiEval(samples: any[]) {
  return request({ url: "/ai/overview/eval", method: "post", data: { samples } });
}
