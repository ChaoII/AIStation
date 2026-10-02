import request from "@/utils/request";

const API_PATH = "/ai/skills";

export function getAiSkillList(params?: { category?: string; skill_type?: string }) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function getAiSkillCategories() {
  return request({ url: `${API_PATH}/categories`, method: "get" });
}

export function getAiSkillDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createAiSkill(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiSkill(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiSkill(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function toggleAiSkillFeatured(id: number, featured: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", params: { featured } });
}
