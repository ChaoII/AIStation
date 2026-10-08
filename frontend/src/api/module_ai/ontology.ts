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
export function getOntFunctions(object_code = "") {
  return request({ url: `${API_PATH}/functions`, method: "get", params: { object_code } });
}
export function saveOntFunction(data: any) {
  return request({ url: `${API_PATH}/function/save`, method: "post", data });
}
export function getOntChangelog(object_code = "") {
  return request({ url: `${API_PATH}/changelog`, method: "get", params: { object_code } });
}
export function publishOntVersion(code: string) {
  return request({ url: `${API_PATH}/version/publish`, method: "post", data: { code } });
}
export function getOntVersions(object_code = "") {
  return request({ url: `${API_PATH}/version/list`, method: "get", params: { object_code } });
}
export function rollbackOntVersion(version_id: number) {
  return request({ url: `${API_PATH}/version/rollback`, method: "post", data: { version_id } });
}
export function getOntVersionDiff(version_id: number) {
  return request({ url: `${API_PATH}/version/diff`, method: "get", params: { version_id } });
}
export function getOntCapabilities() {
  return request({ url: `${API_PATH}/capabilities`, method: "get" });
}
export function saveOntCapability(data: any) {
  return request({ url: `${API_PATH}/capability/save`, method: "post", data });
}
export function getOntAnalyze() {
  return request({ url: `${API_PATH}/analyze`, method: "get" });
}
