import request from "@/utils/request";

export function getCameraList(data?: any) {
  return request({ url: "/video/camera/list", method: "get", params: data });
}

export function getCameraDetail(id: number) {
  return request({ url: `/video/camera/detail/${id}`, method: "get" });
}

export function createCamera(data: any) {
  return request({ url: "/video/camera/create", method: "post", data });
}

export function updateCamera(id: number, data: any) {
  return request({ url: `/video/camera/update/${id}`, method: "put", data });
}

export function deleteCamera(ids: number[]) {
  return request({ url: "/video/camera/delete", method: "delete", data: { ids } });
}

export function startStream(id: number) {
  return request({ url: `/video/camera/stream/start/${id}`, method: "post" });
}

export function stopStream(id: number) {
  return request({ url: `/video/camera/stream/stop/${id}`, method: "post" });
}

export function getStreamUrls(id: number) {
  return request({ url: `/video/camera/stream/urls/${id}`, method: "get" });
}

export function getCameraGroupList() {
  return request({ url: "/video/camera/group/list", method: "get" });
}

export function createCameraGroup(data: any) {
  return request({ url: "/video/camera/group/create", method: "post", data });
}

export function updateCameraGroup(id: number, data: any) {
  return request({ url: `/video/camera/group/update/${id}`, method: "put", data });
}

export function deleteCameraGroup(ids: number[]) {
  return request({ url: "/video/camera/group/delete", method: "delete", data: { ids } });
}
