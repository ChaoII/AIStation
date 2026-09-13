import request from "@/utils/request";

const API_PATH = "/ai/model";

export function getAiModelList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function createAiModel(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiModel(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiModel(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function setDefaultAiModel(id: number) {
  return request({ url: `${API_PATH}/set-default/${id}`, method: "post" });
}

export function testAiModel(data: any) {
  return request({
    url: `${API_PATH}/test`,
    method: "post",
    data,
    headers: { _silent: "true" },
    timeout: 30000,
  });
}
