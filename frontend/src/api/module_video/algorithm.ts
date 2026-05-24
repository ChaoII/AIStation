import request from "@/utils/request";

export function getAlgorithmList(data?: any) {
  return request({ url: "/video/algorithm/list", method: "get", params: data });
}

export function createAlgorithm(data: any) {
  return request({ url: "/video/algorithm/create", method: "post", data });
}

export function updateAlgorithm(id: number, data: any) {
  return request({ url: `/video/algorithm/update/${id}`, method: "put", data });
}

export function deleteAlgorithm(ids: number[]) {
  return request({ url: "/video/algorithm/delete", method: "delete", data: { ids } });
}

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
