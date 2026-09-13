import request from "@/utils/request";

const API_PATH = "/ai/sessions";

export function getAiSessionList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiSessionDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiSession(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function deleteAiSessions(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}
