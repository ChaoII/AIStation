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
  deleteModel(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/model/delete`, method: "delete", data: ids });
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
  getTaskLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({ url: `${API_PATH}/task/${id}/logs`, method: "get" });
  },
  stopTask(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/stop`, method: "post" });
  },
  startTask(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/start`, method: "post" });
  },
  deleteTask(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/task/delete`, method: "delete", data: ids });
  },

  createEval(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/create`, method: "post", data });
  },
  getEvalList(modelRepoId: number) {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/eval/list`, method: "get", params: { model_repo_id: modelRepoId } });
  },
  deleteEval(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/delete`, method: "delete", data: ids });
  },

  exportDataset(data: { dataset_id: number; annotation_task_id?: number; format: string; ocr_rec?: boolean }) {
    return request<ApiResponse<{ download_url: string; format: string; dataset_id: number }>>({
      url: `${API_PATH}/dataset/export`,
      method: "post",
      data,
      timeout: 300000,
    });
  },

  getEvalDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/detail`, method: "get" });
  },
  startEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/start`, method: "post" });
  },
  stopEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/stop`, method: "post" });
  },

  createPredict(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/create`, method: "post", data });
  },
  getPredictList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/predict/list`, method: "get" });
  },
  getPredictDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/detail`, method: "get" });
  },
  startPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/start`, method: "post" });
  },
  stopPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/stop`, method: "post" });
  },
  deletePredict(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/delete`, method: "delete", data: ids });
  },
  uploadPredictImages(files: File[]) {
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    return request<ApiResponse<string[]>>({ url: `${API_PATH}/predict/upload`, method: "post", data: formData, headers: { "Content-Type": "multipart/form-data" } });
  },
};
