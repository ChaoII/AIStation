import request from "@/utils/request";

/** 复用标注数据集列表，供合成时选择目标数据集 */
export function getDatasetOptions(params?: any) {
  return request<ApiResponse<{ total: number; items: any[]; has_next: boolean; page_no: number; page_size: number }>>({
    url: `/annotation/dataset/list`,
    method: "get",
    params: { page_no: 1, page_size: 100, ...params },
  });
}
