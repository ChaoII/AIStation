import request from "@/utils/request";

const API_PATH = "/train";

// ------------------------------------------------------------------
// TorchKiln 训练服务类型（后端 torchkiln_client.py / torchkiln_executor.py 对应）
// ------------------------------------------------------------------

/** 参数控件类型：决定动态表单用哪种 Element Plus 控件 */
export type TorchKilnWidget = "switch" | "slider" | "number" | "path" | "text" | "list";

/** 单个超参的 schema 描述 */
export interface TorchKilnParam {
  key: string;
  /** 中文标签（服务端下发，已按常见键表 + 配置内 `_ui` 段标注） */
  label: string;
  /** 所属分组（Global / Optimizer / Architecture / …），用于表单分区 */
  group: string;
  type: "int" | "float" | "bool" | "str" | "list" | "null" | "unknown";
  default: any;
  min?: number;
  max?: number;
  widget: TorchKilnWidget;
  nullable?: boolean;
  options?: (string | number)[];
}

/** 单个模型的 schema */
export interface TorchKilnSchema {
  schema_version: number;
  model_name: string;
  config_path: string;
  task?: string;
  model_family?: string;
  algorithm?: string;
  scale?: string;
  /** 主指标名（mAP50-95 / acc / hmean / RMSE…），随任务变化 */
  main_indicator: string;
  /** 主指标方向：max=越大越好，min=越小越好 */
  main_indicator_mode: "max" | "min";
  groups: string[];
  params: Record<string, TorchKilnParam>;
  /** 平台托管键（输出目录/续训权重等），不该出现在用户表单里 */
  managed_keys: string[];
  defaults: Record<string, any>;
  data: Record<string, any>;
}

/** 模型清单项 */
export interface TorchKilnModel {
  model_name: string;
  config_path: string;
  task?: string;
  model_family?: string;
  algorithm?: string;
  scale?: string;
  main_indicator?: string;
  main_indicator_mode?: string;
  epoch_num?: number;
  has_pretrained?: boolean;
}

/** 服务可用性 + 版本声明 */
export interface TorchKilnStatus {
  available: boolean;
  url?: string;
  reason?: string;
  framework?: string;
  framework_version?: string;
  api_version?: string;
  spec_version?: string;
  config_root?: string;
  config?: Record<string, any>;
  metrics?: Record<string, any>;
  job?: Record<string, any>;
}

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
  getModelRepos(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/model/repos`,
      method: "get",
      params,
    });
  },
  getModelVersions(repoId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/model/${repoId}/versions`,
      method: "get",
    });
  },
  deleteModelRepos(ids: number[]) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/repos`,
      method: "delete",
      data: ids,
    });
  },
  createModelRepo(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/model/repos`, method: "post", data });
  },
  updateModelRepo(id: number, data: any) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/repos/${id}`,
      method: "put",
      data,
    });
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
  getTaskList(params?: Record<string, any>, opts?: { silent?: boolean }) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/task/list`,
      method: "get",
      params,
      headers: opts?.silent ? { _silent: "true" } : undefined,
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

  // ------------------------------------------------------------------
  // TorchKiln 训练服务（自研平台 D:\TorchKiln）
  // 模型清单与超参 schema 都由服务端动态下发，**前端不硬编码任何模型/参数**——
  // 加模型 = 训练服务里丢一个 YAML，本页面无需改动。
  // ------------------------------------------------------------------
  /** 训练服务可用性 + 版本声明（页面据此提示，避免点了开始才报错） */
  getTorchKilnStatus() {
    return request<ApiResponse<TorchKilnStatus>>({
      url: `${API_PATH}/framework/torchkiln/status`,
      method: "get",
    });
  },
  /** 模型清单：{ model_name, task, model_family, algorithm, main_indicator, epoch_num } */
  getTorchKilnModels(params?: { task?: string; model_family?: string; name?: string }) {
    return request<ApiResponse<{ items: TorchKilnModel[]; total: number }>>({
      url: `${API_PATH}/framework/torchkiln/models`,
      method: "get",
      params,
    });
  },
  /**
   * 超参 schema：驱动参数表单**动态渲染**。
   * widget 决定用哪种控件：switch / slider / number / path / text / list。
   */
  getTorchKilnModelSchema(modelName: string, o?: string) {
    return request<ApiResponse<TorchKilnSchema>>({
      url: `${API_PATH}/framework/torchkiln/models/${modelName}/schema`,
      method: "get",
      params: o ? { o } : undefined,
    });
  },
  /**
   * 训练指标：按 seq 补发，**可断点续传**。
   *
   * ⚠️ 替代「每秒整表重拉」：整表重拉会闪烁、丢滚动位置与选中态。
   * 带 offset（= 已收到的最大 seq）即可只拿增量。
   */
  getTaskMetrics(id: number, offset = -1) {
    return request<ApiResponse<{ items: any[]; total: number; status?: string }>>({
      url: `${API_PATH}/task/${id}/metrics`,
      method: "get",
      params: { offset },
    });
  },
  /** 指标 SSE 地址（配合 EventSource 使用；后端已带 no-transform 头防代理缓冲） */
  taskMetricsStreamUrl(id: number, offset = -1) {
    return `/api/v1${API_PATH}/task/${id}/metrics/stream?offset=${offset}`;
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
  getEvalList(params?: Record<string, any>, opts?: { silent?: boolean }) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/eval/list`,
      method: "get",
      params,
      headers: opts?.silent ? { _silent: "true" } : undefined,
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
  getPredictList(params?: Record<string, any>, opts?: { silent?: boolean }) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/predict/list`,
      method: "get",
      params,
      headers: opts?.silent ? { _silent: "true" } : undefined,
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
  getDeployList(params?: Record<string, any>, opts?: { silent?: boolean }) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/deploy/list`,
      method: "get",
      params,
      headers: opts?.silent ? { _silent: "true" } : undefined,
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
