import request from "@/utils/request";

export function getAiLogList(params?: any) {
  return request({ url: "/ai/logs/list", method: "get", params });
}
