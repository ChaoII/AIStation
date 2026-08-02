import { request } from "@utils";

const API_PATH = "/train";

export interface TrainModelTable extends BaseType {
  name?: string;
  framework?: string;
  version?: string;
  description?: string;
  storage_path?: string;
  format?: string;
  export_format?: string;
  metrics?: Record<string, unknown> | null;
  annotation_dataset_id?: number;
}

export interface TrainModelRepoTable extends BaseType {
  name?: string;
  framework?: string;
  description?: string;
  latest_version_id?: number;
  version_count?: number;
  annotation_dataset_id?: number;
}

export interface TrainModelVersionTable extends BaseType {
  repo_id?: number;
  name?: string;
  framework?: string;
  version?: string;
  description?: string;
  storage_path?: string;
  format?: string;
  export_format?: string;
  metrics?: Record<string, unknown> | null;
  annotation_dataset_id?: number;
}

export interface TrainModelForm extends BaseFormType {
  name?: string;
  framework?: string;
  description?: string;
  annotation_dataset_id?: number;
  export_format?: string;
  status?: string;
}

export interface TablePageQuery extends PageQuery {
  name?: string;
  framework?: string;
  status?: string;
}

export interface TrainTaskTable extends BaseType {
  name?: string;
  framework?: string;
  dataset_id?: number;
  annotation_task_id?: number;
  model_repo_id?: number;
  docker_image?: string;
  hyperparams?: Record<string, unknown>;
  status?: string;
  progress?: number;
  error_log?: string;
  started_at?: string;
  finished_at?: string;
}

export interface TrainTaskForm extends BaseFormType {
  name?: string;
  framework?: string;
  dataset_id?: number;
  annotation_task_id?: number;
  base_model_id?: number;
  hyperparams?: Record<string, unknown>;
}

export interface TrainEvalTable extends BaseType {
  model_repo_id?: number;
  model_id?: number;
  eval_dataset_id?: number;
  framework?: string;
  hyperparams?: Record<string, unknown>;
  metrics?: Record<string, unknown> | null;
  status?: string;
  progress?: number;
  error_log?: string;
  started_at?: string;
  finished_at?: string;
}

export interface TrainEvalForm extends BaseFormType {
  model_repo_id?: number;
  model_id?: number;
  eval_dataset_id?: number;
  hyperparams?: Record<string, unknown>;
}

export interface TrainPredictTable extends BaseType {
  model_repo_id?: number;
  model_id?: number;
  framework?: string;
  source_type?: string;
  source_dataset_id?: number;
  result_images?: string[];
  result_zip_path?: string;
  hyperparams?: Record<string, unknown>;
  status?: string;
  progress?: number;
  error_log?: string;
  started_at?: string;
  finished_at?: string;
}

export interface TrainPredictForm extends BaseFormType {
  model_repo_id?: number;
  model_id?: number;
  source_type?: string;
  source_dataset_id?: number;
  source_images?: string[];
  hyperparams?: Record<string, unknown>;
}

export interface TrainDeployTable extends BaseType {
  name?: string;
  model_id?: number;
  model_name?: string;
  model_version?: string;
  framework?: string;
  device?: string;
  host_port?: number;
  container_id?: string;
  status?: string;
  api_url?: string;
  api_key?: string;
  hyperparams?: Record<string, unknown>;
  error_log?: string;
  started_at?: string;
  finished_at?: string;
}

export const TrainAPI = {
  // ── Model ──
  listModel(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainModelTable>>>({
      url: `${API_PATH}/model/list`,
      method: "get",
      params: query,
    });
  },
  listModelRepos(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainModelRepoTable>>>({
      url: `${API_PATH}/model/repos`,
      method: "get",
      params: query,
    });
  },
  createModelRepo(body: { name: string; framework: string; description?: string; annotation_dataset_id?: number }) {
    return request<ApiResponse>({ url: `${API_PATH}/model/repos`, method: "post", data: body });
  },
  deleteModelRepos(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/model/repos`, method: "delete", data: body });
  },
  listModelVersions(repoId: number) {
    return request<ApiResponse<TrainModelVersionTable[]>>({
      url: `${API_PATH}/model/${repoId}/versions`,
      method: "get",
    });
  },
  detailModelRepoOfVersion(versionId: number) {
    return request<ApiResponse<{ repo_id: number; repo_name: string }>>({
      url: `${API_PATH}/model/version/${versionId}/repo`,
      method: "get",
    });
  },
  downloadModel(modelId: number) {
    return request<ApiResponse<{ download_url: string; format: string }>>({
      url: `${API_PATH}/model/${modelId}/download`,
      method: "get",
    });
  },
  detailModel(query: number) {
    return request<ApiResponse<TrainModelTable>>({
      url: `${API_PATH}/model/detail/${query}`,
      method: "get",
    });
  },
  createModel(body: TrainModelForm) {
    return request<ApiResponse>({ url: `${API_PATH}/model/create`, method: "post", data: body });
  },
  updateModel(id: number, body: TrainModelForm) {
    return request<ApiResponse>({ url: `${API_PATH}/model/update/${id}`, method: "put", data: body });
  },
  deleteModel(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/model/delete`, method: "delete", data: body });
  },
  exportModel(modelId: number, body: Record<string, unknown>) {
    return request<ApiResponse<{ download_url: string; format: string }>>({
      url: `${API_PATH}/model/${modelId}/export`,
      method: "post",
      data: body,
      timeout: 1800000,
    });
  },

  // ── Task ──
  listTask(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainTaskTable>>>({
      url: `${API_PATH}/task/list`,
      method: "get",
      params: query,
    });
  },
  detailTask(query: number) {
    return request<ApiResponse<TrainTaskTable>>({
      url: `${API_PATH}/task/${query}/detail`,
      method: "get",
    });
  },
  createTask(body: TrainTaskForm) {
    return request<ApiResponse>({ url: `${API_PATH}/task/create`, method: "post", data: body });
  },
  deleteTask(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/task/delete`, method: "delete", data: body });
  },
  startTask(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/task/${id}/start`, method: "post" });
  },
  stopTask(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/task/${id}/stop`, method: "post" });
  },
  getTaskLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/task/${id}/logs`,
      method: "get",
    });
  },

  // ── Eval ──
  listEval(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainEvalTable>>>({
      url: `${API_PATH}/eval/list`,
      method: "get",
      params: query,
    });
  },
  detailEval(query: number) {
    return request<ApiResponse<TrainEvalTable>>({
      url: `${API_PATH}/eval/${query}/detail`,
      method: "get",
    });
  },
  createEval(body: TrainEvalForm) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/create`, method: "post", data: body });
  },
  deleteEval(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/delete`, method: "delete", data: body });
  },
  startEval(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/${id}/start`, method: "post" });
  },
  stopEval(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/eval/${id}/stop`, method: "post" });
  },
  getEvalLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/eval/${id}/logs`,
      method: "get",
    });
  },

  // ── Predict ──
  listPredict(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainPredictTable>>>({
      url: `${API_PATH}/predict/list`,
      method: "get",
      params: query,
    });
  },
  detailPredict(query: number) {
    return request<ApiResponse<TrainPredictTable>>({
      url: `${API_PATH}/predict/${query}/detail`,
      method: "get",
    });
  },
  createPredict(body: TrainPredictForm) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/create`, method: "post", data: body });
  },
  deletePredict(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/delete`, method: "delete", data: body });
  },
  startPredict(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/${id}/start`, method: "post" });
  },
  stopPredict(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/${id}/stop`, method: "post" });
  },
  uploadPredictImages(formData: FormData) {
    return request<ApiResponse<string[]>>({
      url: `${API_PATH}/predict/upload`,
      method: "post",
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  // ── Deploy ──
  listDeploy(query?: TablePageQuery) {
    return request<ApiResponse<PageResult<TrainDeployTable>>>({
      url: `${API_PATH}/deploy/list`,
      method: "get",
      params: query,
    });
  },
  detailDeploy(query: number) {
    return request<ApiResponse<TrainDeployTable>>({
      url: `${API_PATH}/deploy/${query}/detail`,
      method: "get",
    });
  },
  createDeploy(body: Record<string, unknown>) {
    return request<ApiResponse<TrainDeployTable>>({
      url: `${API_PATH}/deploy/create`,
      method: "post",
      data: body,
    });
  },
  deleteDeploy(body: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/deploy/delete`, method: "delete", data: body });
  },
  startDeploy(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/deploy/${id}/start`, method: "post" });
  },
  stopDeploy(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/deploy/${id}/stop`, method: "post" });
  },
  renewDeployKey(id: number) {
    return request<ApiResponse<{ api_key: string }>>({
      url: `${API_PATH}/deploy/${id}/renew-key`,
      method: "put",
    });
  },

  // ── System ──
  getTempDir() {
    return request<ApiResponse<{ tempdir: string }>>({
      url: `${API_PATH}/system/tempdir`,
      method: "get",
    });
  },

  // ── Dataset export (used by annotation dataset page) ──
  exportDataset(data: Record<string, unknown>) {
    return request<ApiResponse<{ download_url: string; format: string }>>({
      url: `${API_PATH}/dataset/export`,
      method: "post",
      data,
      timeout: 300000,
    });
  },
};

export default TrainAPI;
