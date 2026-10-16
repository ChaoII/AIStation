import request from "@/utils/request";

const WS_PATH = "/ai/workspace";

export interface WorkspaceCategory {
  id: number;
  name: string;
  parent_id?: number | null;
  icon?: string;
  color?: string;
  sort?: number;
  children?: WorkspaceCategory[];
}

export interface WorkspaceItem {
  type: "agent" | "workflow" | "app" | "cron";
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  color?: string;
  category_id?: number | null;
  label: string;
}

// ---------- 分类树 ----------
export function getWorkspaceCategoryTree() {
  return request({ url: `${WS_PATH}/categories/tree`, method: "get" });
}

export function createWorkspaceCategory(data: {
  name: string;
  parent_id?: number | null;
  icon?: string;
  color?: string;
  sort?: number;
}) {
  return request({ url: `${WS_PATH}/categories/create`, method: "post", data });
}

export function updateWorkspaceCategory(id: number, data: Record<string, unknown>) {
  return request({ url: `${WS_PATH}/categories/update/${id}`, method: "put", data });
}

export function deleteWorkspaceCategory(id: number) {
  return request({ url: `${WS_PATH}/categories/delete`, method: "delete", data: id });
}

// ---------- 聚合条目 ----------
export function getWorkspaceItems(params?: { category_id?: number | null; asset_type?: string }) {
  return request({ url: `${WS_PATH}/items`, method: "get", params });
}
