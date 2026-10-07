import request from "@/utils/request";

const API_PATH = "/ai/apps";

export function getAiAppList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiAppTemplates() {
  return request({ url: `${API_PATH}/templates`, method: "get" });
}

export function createAiAppFromTemplate(key: string, name: string) {
  return request({ url: `${API_PATH}/create-from-template`, method: "post", data: { key, name } });
}

export function getAiAppDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiApp(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiApp(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiApp(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function batchAppStatus(ids: number[], enabled: boolean) {
  return request({ url: `${API_PATH}/batch/status`, method: "put", data: { ids, enabled } });
}
