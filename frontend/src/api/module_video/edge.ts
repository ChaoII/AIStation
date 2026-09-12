import request from "@/utils/request";

export function getEdgeDeviceList(data?: any) {
  return request({ url: "/video/edge/list", method: "get", params: data });
}

export function getEdgeDeviceDetail(id: number) {
  return request({ url: `/video/edge/detail/${id}`, method: "get" });
}

export function createEdgeDevice(data: any) {
  return request({ url: "/video/edge/create", method: "post", data });
}

export function updateEdgeDevice(id: number, data: any) {
  return request({ url: `/video/edge/update/${id}`, method: "put", data });
}

export function deleteEdgeDevice(ids: number[]) {
  return request({ url: "/video/edge/delete", method: "delete", data: ids });
}
