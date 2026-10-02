import request from "@/utils/request";

const API_PATH = "/ai/workflows";

export function getAiWorkflowList() {
  return request({ url: `${API_PATH}/list`, method: "get" });
}

export function getAiWorkflowDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiWorkflow(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiWorkflow(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiWorkflow(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}
