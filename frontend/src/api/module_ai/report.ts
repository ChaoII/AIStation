import request from "@/utils/request";

const BASE = "/ai/report";

export function getAiReportList() {
  return request({ url: `${BASE}/list`, method: "get" });
}
export function getAiReportDetail(id: number) {
  return request({ url: `${BASE}/detail/${id}`, method: "get" });
}
export function deleteAiReport(ids: number[]) {
  return request({ url: `${BASE}/delete`, method: "delete", data: ids });
}
