import request from "@/utils/request";

const API_PATH = "/ai/apps";

export function getAiAppList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
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
