import request from "@/utils/request";

const API_PATH = "/ai/plugins";

/** AI 能力插件 */
export interface AiPlugin {
  id: number;
  key: string;
  label: string;
  /** builtin/custom */
  kind: string;
  config: Record<string, any>;
  config_schema: Record<string, any>;
  /** 执行器是否已实现（未实现仅可展示/配置，不可运行） */
  executor_ready: boolean;
  enabled: boolean;
  description: string;
  created_time?: string;
}

export function getPluginList() {
  return request({ url: `${API_PATH}/list`, method: "get" });
}

export function createPlugin(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updatePlugin(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deletePlugin(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function togglePlugin(id: number, enabled: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", data: { enabled } });
}
