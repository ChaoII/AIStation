import request from "@/utils/request";

const API_PATH = "/annotation";

export const AnnotationAPI = {
  // Dataset
  getDatasetList(params?: any) {
    return request<ApiResponse<PageResult<any>>>({
      url: `${API_PATH}/dataset/list`,
      method: "get",
      params,
    });
  },
  createDataset(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/dataset/create`, method: "post", data });
  },
  updateDataset(id: number, data: any) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/update/${id}`,
      method: "put",
      data,
    });
  },
  deleteDataset(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/dataset/delete`, method: "delete", data: ids });
  },
  uploadImages(id: number, files: FormData) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/${id}/upload`,
      method: "post",
      data: files,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  getImages(id: number, taskId?: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/dataset/${id}/images`,
      method: "get",
      params: { task_id: taskId },
    });
  },
  getPresignedUrl(imageId: number, taskId?: number) {
    return request<ApiResponse<{ url: string }>>({
      url: `${API_PATH}/anno/image/${imageId}/presigned-url`,
      method: "get",
      params: { task_id: taskId },
    });
  },

  // Task
  getTaskList(params?: any) {
    return request<ApiResponse<PageResult<any>>>({
      url: `${API_PATH}/task/list`,
      method: "get",
      params,
    });
  },
  createTask(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/create`, method: "post", data });
  },
  updateTask(id: number, data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/update/${id}`, method: "put", data });
  },
  deleteTask(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/task/delete`, method: "delete", data: ids });
  },
  getTaskProgress(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/progress`, method: "get" });
  },
  getTaskDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/detail`, method: "get" });
  },

  // Annotation
  getAnnotations(taskId: number, imageId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/anno/image/${imageId}/annotations`,
      method: "get",
      params: { task_id: taskId },
    });
  },
  saveAnnotations(imageId: number, data: any) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/anno/image/${imageId}/annotations`,
      method: "put",
      data,
    });
  },
  getAnnotationHistory(taskId: number, imageId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/anno/image/${imageId}/history`,
      method: "get",
      params: { task_id: taskId },
    });
  },
  lockImage(imageId: number, taskId: number) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/anno/image/${imageId}/lock`,
      method: "post",
      params: { task_id: taskId },
    });
  },
  unlockImage(imageId: number, taskId: number) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/anno/image/${imageId}/unlock`,
      method: "post",
      params: { task_id: taskId },
      headers: { _silent: "true" },
    });
  },

  importXAnyLabeling(datasetId: number, file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/import/x-anylabeling`,
      method: "post",
      params: { dataset_id: datasetId },
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    });
  },

  // Stats
  getOverview() {
    return request<ApiResponse<any>>({ url: `${API_PATH}/stats/overview`, method: "get" });
  },
  getDatasetStats(datasetId: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/stats/dataset/${datasetId}`, method: "get" });
  },

  // Export history
  getExportHistory(datasetId: number) {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/dataset/export/history/${datasetId}`, method: "get" });
  },
};
