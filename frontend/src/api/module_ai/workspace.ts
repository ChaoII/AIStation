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
  created_time?: string | null;
  meta?: Record<string, any>;
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

// ---------- 定时任务 ----------
export function createWorkspaceCron(data: {
  name: string;
  description?: string;
  cron: string;
  target_type: string;
  target_id?: number | null;
  category_id?: number | null;
  enabled?: boolean;
}) {
  return request({ url: `${WS_PATH}/cron/create`, method: "post", data });
}

export function updateWorkspaceCron(id: number, data: Record<string, unknown>) {
  return request({ url: `${WS_PATH}/cron/update/${id}`, method: "put", data });
}

export function deleteWorkspaceCron(id: number) {
  return request({ url: `${WS_PATH}/cron/delete`, method: "delete", data: id });
}

// ---------- 触发预览 ----------

/** 触发预览结果：描述与下次运行时间由后端统一层（TriggerUtil）产出，前端不自算 */
export interface TriggerPreview {
  /** 配置是否合法 */
  valid: boolean;
  /** 非法时的可读原因（合法时为空串） */
  reason: string;
  /** 人话描述；非法时为「尽力而为」，可能为空串 */
  describe: string;
  /** 下次运行时间（Asia/Shanghai 墙钟，`YYYY-MM-DD HH:mm:ss`）；无下次运行时为 null */
  next_run: string | null;
}

/**
 * 触发预览（AI 侧统一入口）：回显「是否合法 / 可读原因 / 人话描述 / 下次运行时间」。
 *
 * 参数契约与后端 `TriggerUtil` 一致：cron 为 5 段字符串、interval 为
 * `{weeks,days,hours,minutes,seconds}`、date 为 `YYYY-MM-DD HH:mm:ss`、now 为 null。
 * 该接口随输入变化高频调用，故带 `_silent` 关闭全局提示，错误由调用方内联展示。
 */
export function previewTrigger(data: { trigger: string; trigger_args: unknown }) {
  return request<ApiResponse<TriggerPreview>>({
    url: `${WS_PATH}/trigger/preview`,
    method: "post",
    data,
    headers: { _silent: "true" },
  });
}
