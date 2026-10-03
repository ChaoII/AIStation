import request from "@/utils/request";

export function getAiOverviewStats() {
  return request({ url: "/ai/overview/stats", method: "get" });
}
