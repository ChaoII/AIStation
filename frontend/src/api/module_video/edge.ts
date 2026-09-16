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

/**
 * 边缘布控任务最新帧快照地址（受鉴权代理）。
 *
 * 返回浏览器可直接访问的完整路径（含 `/api/v1` 前缀）。注意：该地址需带
 * Authorization 头请求，请使用 SnapshotImage 之类的 blob 加载方式，不要直接塞给 <img>。
 */
export function edgeTaskSnapshotUrl(deviceId: number, taskId: number): string {
  return `/api/v1/video/edge/${deviceId}/tasks/${taskId}/snapshot`;
}
