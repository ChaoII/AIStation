import request from "@/utils/request";

const API_PATH = "/train";

export const TrainAPI = {
  getModelList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/model/list`, method: "get" });
  },
  getModelDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/model/detail/${id}`, method: "get" });
  },
  createModel(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/model/create`, method: "post", data });
  },

  createTask(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/create`, method: "post", data });
  },
  getTaskList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/task/list`, method: "get" });
  },
  getTaskDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/detail`, method: "get" });
  },
  stopTask(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/stop`, method: "post" });
  },

  createEval(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/create`, method: "post", data });
  },
  getEvalList(modelRepoId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/eval/list`,
      method: "get",
      params: { model_repo_id: modelRepoId },
    });
  },
};
