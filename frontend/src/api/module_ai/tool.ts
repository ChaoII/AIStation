import request from "@/utils/request";

const API_PATH = "/ai/tools";

export function getAiToolList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function createAiTool(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiTool(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiTool(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function toggleAiTool(id: number, enabled: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", data: { enabled } });
}

export function testAiTool(id: number) {
  return request({
    url: `${API_PATH}/test/${id}`,
    method: "post",
    headers: { _silent: "true" },
    timeout: 30000,
  });
}
