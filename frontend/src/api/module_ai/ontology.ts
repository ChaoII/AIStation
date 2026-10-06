import request from "@/utils/request";

const API_PATH = "/ai/ontology";

export function getOntObjects() {
  return request({ url: `${API_PATH}/objects`, method: "get" });
}
export function saveOntObject(data: any) {
  return request({ url: `${API_PATH}/object/save`, method: "post", data });
}
export function getOntObjectFull(code: string) {
  return request({ url: `${API_PATH}/object/${code}/full`, method: "get" });
}
export function getOntProperties(object_code = "") {
  return request({ url: `${API_PATH}/properties`, method: "get", params: { object_code } });
}
export function saveOntProperty(data: any) {
  return request({ url: `${API_PATH}/property/save`, method: "post", data });
}
export function getOntLinks(object_code = "") {
  return request({ url: `${API_PATH}/links`, method: "get", params: { object_code } });
}
export function saveOntLink(data: any) {
  return request({ url: `${API_PATH}/link/save`, method: "post", data });
}
export function getOntActions(object_code = "") {
  return request({ url: `${API_PATH}/actions`, method: "get", params: { object_code } });
}
export function saveOntAction(data: any) {
  return request({ url: `${API_PATH}/action/save`, method: "post", data });
}
export function removeOnt(kind: string, id: number) {
  return request({ url: `${API_PATH}/remove`, method: "delete", params: { kind, id } });
}
export function materializeOntObject(code: string) {
  return request({ url: `${API_PATH}/materialize`, method: "post", data: { code } });
}
