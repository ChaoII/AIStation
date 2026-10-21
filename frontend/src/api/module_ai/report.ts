import request from "@/utils/request";

/** AI 报告列表（轻量，不含 content） */
export function getAiReportList() {
  return request({ url: "/ai/report/list", method: "get" });
}

/** AI 报告详情（含 Markdown 正文 content） */
export function getAiReportDetail(id: number) {
  return request({ url: `/ai/report/detail/${id}`, method: "get" });
}

/** 批量删除 AI 报告（软删，按 ids） */
export function deleteAiReports(ids: number[]) {
  return request({ url: "/ai/report/delete", method: "delete", data: { ids } });
}
