import request from "@/utils/request";

export function getAlgorithmTaskList(data?: any) {
  return request({ url: "/video/algorithm/task/list", method: "get", params: data });
}

export function createAlgorithmTask(data: any) {
  return request({ url: "/video/algorithm/task/create", method: "post", data });
}

export function updateAlgorithmTask(id: number, data: any) {
  return request({ url: `/video/algorithm/task/update/${id}`, method: "put", data });
}

export function deleteAlgorithmTask(ids: number[]) {
  return request({ url: "/video/algorithm/task/delete", method: "delete", data: { ids } });
}

export function startInferenceTask(id: number) {
  return request({ url: `/video/algorithm/task/${id}/start`, method: "post" });
}

export function stopInferenceTask(id: number) {
  return request({ url: `/video/algorithm/task/${id}/stop`, method: "post" });
}

export function getInferenceStatus(id: number) {
  return request({ url: `/video/algorithm/task/${id}/inference-status`, method: "get" });
}
