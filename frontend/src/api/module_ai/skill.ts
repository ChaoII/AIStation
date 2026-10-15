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

export function batchSkillStatus(ids: number[], enabled: boolean) {
  return request({ url: `${API_PATH}/batch/status`, method: "put", data: { ids, enabled } });
}

/** 安装技能到智能体（同步 agent.skill_ids 并累加安装次数）。 */
export function installAiSkillToAgent(agentId: number, skillId: number) {
  return request({
    url: `/ai/agents/${agentId}/install-skill`,
    method: "post",
    data: { skill_id: skillId },
  });
}

/** 卸载智能体上的技能。 */
export function uninstallAiSkillFromAgent(agentId: number, skillId: number) {
  return request({
    url: `/ai/agents/${agentId}/uninstall-skill`,
    method: "post",
    data: { skill_id: skillId },
  });
}

/** 导入技能：粘贴 SKILL.md 全文（SkillHub / Claude Skills 规范）。 */
export function importAiSkill(data: {
  content: string;
  name?: string;
  category?: string;
  source?: string;
}) {
  return request({ url: `${API_PATH}/import`, method: "post", data });
}

/** 导入技能：上传 Zip 包（内含 SKILL.md）。 */
export function importAiSkillZip(file: File, category?: string, source?: string) {
  const form = new FormData();
  form.append("file", file);
  if (category) form.append("category", category);
  form.append("source", source || "SkillHub");
  return request({
    url: `${API_PATH}/import-zip`,
    method: "post",
    data: form,
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });
}
