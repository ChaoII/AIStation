import request from "@/utils/request";

const API_PATH = "/ai/providers";

export function getAiProviderList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function createAiProvider(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiProvider(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiProvider(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function getAiProviderRemoteModels(id: number) {
  return request({ url: `${API_PATH}/remote-models/${id}`, method: "get" });
}

export function testAiProvider(id: number) {
  return request({
    url: `${API_PATH}/test/${id}`,
    method: "get",
    headers: { _silent: "true" },
    timeout: 20000,
  });
}
