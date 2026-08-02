import { request } from "@utils";

const API_PATH = "/annotation";

export interface AnnotationDataset extends BaseType {
  name?: string;
  description?: string;
  bucket_name?: string;
  image_count?: number;
  annotated_count?: number;
  tasks?: Record<string, unknown>[];
}

export interface AnnotationImage {
  id: number;
  dataset_id: number;
  filename: string;
  object_key: string;
  width: number;
  height: number;
  status: string;
  locked_by: number | null;
  annotation_count: number;
  updated_by?: { id: number; name: string };
  updated_time?: string;
}

export const AnnotationAPI = {
  // Dataset
  listDataset(params?: Record<string, unknown>) {
    return request<ApiResponse<PageResult<AnnotationDataset>>>({
      url: `${API_PATH}/dataset/list`,
      method: "get",
      params,
    });
  },
  createDataset(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${API_PATH}/dataset/create`, method: "post", data });
  },
  updateDataset(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${API_PATH}/dataset/update/${id}`, method: "put", data });
  },
  deleteDataset(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/dataset/delete`, method: "delete", data: ids });
  },
  uploadImages(id: number, formData: FormData) {
    return request<ApiResponse>({
      url: `${API_PATH}/dataset/${id}/upload`,
      method: "post",
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  getImages(id: number, taskId?: number, pageNo?: number, pageSize?: number) {
    return request<ApiResponse<{ items: any[]; total: number; page: number }>>({
      url: `${API_PATH}/dataset/${id}/images`,
      method: "get",
      params: { task_id: taskId, page_no: pageNo, page_size: pageSize },
      timeout: 60000,
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
  listTask(params?: Record<string, unknown>) {
    return request<ApiResponse<PageResult<any>>>({
      url: `${API_PATH}/task/list`,
      method: "get",
      params,
    });
  },
  createTask(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${API_PATH}/task/create`, method: "post", data });
  },
  updateTask(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${API_PATH}/task/update/${id}`, method: "put", data });
  },
  deleteTask(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/task/delete`, method: "delete", data: ids });
  },
  getTaskProgress(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/task/${id}/progress`, method: "get" });
  },
  getTaskDetail(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/task/${id}/detail`, method: "get" });
  },

  // Annotation
  getAnnotations(taskId: number, imageId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/anno/image/${imageId}/annotations`,
      method: "get",
      params: { task_id: taskId },
    });
  },
  saveAnnotations(imageId: number, data: Record<string, unknown>) {
    return request<ApiResponse>({
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
    return request<ApiResponse>({
      url: `${API_PATH}/anno/image/${imageId}/lock`,
      method: "post",
      params: { task_id: taskId },
    });
  },
  unlockImage(imageId: number, taskId: number) {
    return request<ApiResponse>({
      url: `${API_PATH}/anno/image/${imageId}/unlock`,
      method: "post",
      params: { task_id: taskId },
    });
  },

  // Import
  importXAnyLabeling(datasetId: number, file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return request<ApiResponse>({
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
    return request<ApiResponse>({ url: `${API_PATH}/stats/overview`, method: "get" });
  },
  getDatasetStats(datasetId: number) {
    return request<ApiResponse>({ url: `${API_PATH}/stats/dataset/${datasetId}`, method: "get" });
  },
  getExportHistory(datasetId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/dataset/export/history/${datasetId}`,
      method: "get",
    });
  },
};

export default AnnotationAPI;
