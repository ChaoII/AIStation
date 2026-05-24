import request from "@/utils/request";

export function getEventList(data?: any) {
  return request({ url: "/video/event/list", method: "get", params: data });
}

export function createEvent(data: any) {
  return request({ url: "/video/event/create", method: "post", data });
}

export function updateEvent(id: number, data: any) {
  return request({ url: `/video/event/update/${id}`, method: "put", data });
}

export function deleteEvent(ids: number[]) {
  return request({ url: "/video/event/delete", method: "delete", data: { ids } });
}
