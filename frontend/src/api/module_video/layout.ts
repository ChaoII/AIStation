import request from "@/utils/request";

export function getLayoutList(data?: any) {
  return request({ url: "/video/layout/list", method: "get", params: data });
}

export function getLayoutDetail(id: number) {
  return request({ url: `/video/layout/detail/${id}`, method: "get" });
}

export function createLayout(data: any) {
  return request({ url: "/video/layout/create", method: "post", data });
}

export function updateLayout(id: number, data: any) {
  return request({ url: `/video/layout/update/${id}`, method: "put", data });
}

export function deleteLayout(ids: number[]) {
  return request({ url: "/video/layout/delete", method: "delete", data: { ids } });
}
