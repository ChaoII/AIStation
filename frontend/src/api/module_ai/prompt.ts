import request from "@/utils/request";

const API_PATH = "/ai/prompts";

export function getAiPromptList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiPromptDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiPrompt(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiPrompt(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiPrompt(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}
