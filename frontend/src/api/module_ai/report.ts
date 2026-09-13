import request from "@/utils/request";

const API_PATH = "/ai/report";

export function getAiReportList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiReportDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function deleteAiReport(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}
