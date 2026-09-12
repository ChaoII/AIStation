import request from "@/utils/request";

const API_PATH = "/train";

export const TrainAPI = {
  getModelList(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/model/list`,
      method: "get",
      params,
    });
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
  updateTask(taskId: number, data: any) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/task/${taskId}/update`,
      method: "put",
      data,
    });
  },
  getTaskList(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/task/list`,
      method: "get",
      params,
    });
  },
  getTaskDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/detail`, method: "get" });
  },
  getTaskLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/task/${id}/logs`,
      method: "get",
    });
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
  getEvalList(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/eval/list`,
      method: "get",
      params,
    });
  },
  deleteEval(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/delete`, method: "delete", data: ids });
  },

  exportDataset(data: {
    dataset_id: number;
    annotation_task_id?: number;
    format: string;
    ocr_rec?: boolean;
    train_ratio?: number;
  }) {
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
  getEvalLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/eval/${id}/logs`,
      method: "get",
    });
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
  getPredictList(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/predict/list`,
      method: "get",
      params,
    });
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
    files.forEach((f) => formData.append("files", f));
    return request<ApiResponse<string[]>>({
      url: `${API_PATH}/predict/upload`,
      method: "post",
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  getTempDir() {
    return request<ApiResponse<{ tempdir: string }>>({
      url: `${API_PATH}/system/tempdir`,
      method: "get",
    });
  },

  // Model export
  exportModel(modelId: number, data: any) {
    return request<
      ApiResponse<{ download_url: string; format: string; file_size: number; file_name: string }>
    >({
      url: `${API_PATH}/model/${modelId}/export`,
      method: "post",
      data,
      timeout: 1800000,
    });
  },
  updateModel(modelId: number, data: any) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/update/${modelId}`,
      method: "put",
      data,
    });
  },

  // Deploy
  createDeploy(data: any, silent = false) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/deploy/create`,
      method: "post",
      data,
      headers: silent ? { _silent: "true" } : undefined,
    });
  },
  startDeploy(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/deploy/${id}/start`, method: "post" });
  },
  stopDeploy(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/deploy/${id}/stop`, method: "post" });
  },
  renewDeployKey(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/deploy/${id}/renew-key`, method: "put" });
  },
  getDeployList(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/deploy/list`,
      method: "get",
      params,
    });
  },
  getDeployDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/deploy/${id}/detail`, method: "get" });
  },
  getDeployLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/deploy/${id}/logs`,
      method: "get",
    });
  },
  deleteDeploy(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/deploy/delete`, method: "delete", data: ids });
  },
  getTrainScheduleList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/schedule/list`, method: "get" });
  },
  createTrainSchedule(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/schedule/create`, method: "post", data });
  },
  updateTrainSchedule(id: number, data: any) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/schedule/update/${id}`,
      method: "put",
      data,
    });
  },
  deleteTrainSchedule(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/schedule/delete`, method: "delete", data: ids });
  },
};
