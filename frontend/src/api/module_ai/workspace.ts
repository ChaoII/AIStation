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

/** 触发类型（统一契约，与后端 `TriggerUtil` 一致） */
export type TriggerType = "cron" | "interval" | "date" | "now";

/**
 * 定时任务写入体（统一契约）：`trigger` + `trigger_args` 为四类型的新字段，
 * **显式提供时后端以它为准**；`cron` 仅为兼容字段（仅 cron 类型有值，
 * 仅在 `trigger` 缺省时才被解读）。
 *
 * `trigger_args` 契约：cron 为 5 段串、interval 为对象或 JSON 串、date 为时间串、now 为 null。
 */
export interface WorkspaceCronPayload {
  name: string;
  description?: string;
  trigger?: TriggerType | string;
  trigger_args?: unknown;
  cron?: string;
  target_type?: string;
  target_id?: number | null;
  category_id?: number | null;
  enabled?: boolean;
}

/** 编辑定时任务：只提交本次要改的字段（触发配置同样走 `trigger` + `trigger_args`） */
export type WorkspaceCronUpdatePayload = Partial<WorkspaceCronPayload>;

export function createWorkspaceCron(data: WorkspaceCronPayload) {
  return request({ url: `${WS_PATH}/cron/create`, method: "post", data });
}

export function updateWorkspaceCron(id: number, data: WorkspaceCronUpdatePayload) {
  return request({ url: `${WS_PATH}/cron/update/${id}`, method: "put", data });
}

export function deleteWorkspaceCron(id: number) {
  return request({ url: `${WS_PATH}/cron/delete`, method: "delete", data: id });
}

/** 定时任务列表行（独立菜单页数据源；`needs_review` 由后端统一层判定） */
export interface WorkspaceCronRow {
  id: number;
  name: string;
  description?: string;
  /** 触发类型：cron / interval / date / now */
  trigger: string;
  /** 契约同 `WorkspaceCronPayload.trigger_args`（interval 为对象、now 为 null） */
  trigger_args: unknown;
  /** 后端统一层「人话描述」（如「每天 09:00」）；脏数据为 null */
  trigger_describe?: string | null;
  target_type: string;
  target_id: number | null;
  category_id?: number | null;
  enabled: boolean;
  last_run_time?: string | null;
  next_run_time?: string | null;
  /** 按新校验不通过（或迁移被跳过）：需人工确认，否则「有任务但调度不上」静默停摆 */
  needs_review?: boolean;
}

export function getWorkspaceCronList(params?: {
  category_id?: number | null;
  target_type?: string;
}) {
  return request({ url: `${WS_PATH}/cron/list`, method: "get", params });
}

/** 立即执行一次：接口只入队（后台跑与调度器相同的执行路径），成功返回「已触发执行」 */
export function runWorkspaceCron(id: number) {
  return request({ url: `${WS_PATH}/cron/${id}/run`, method: "post" });
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
 * 触发预览（全平台统一入口）：回显「是否合法 / 可读原因 / 人话描述 / 下次运行时间」。
 *
 * 参数契约与后端 `TriggerUtil` 一致：cron 为 5 段字符串、interval 为
 * `{weeks,days,hours,minutes,seconds}`、date 为 `YYYY-MM-DD HH:mm:ss`、now 为 null。
 * 该接口随输入变化高频调用，故带 `_silent` 关闭全局提示，错误由调用方内联展示。
 *
 * 四个业务入口的预览契约完全一致，仅路由/权限不同，故 `url` 可覆盖：缺省为
 * AI 工作台路由（既有调用方零改动），工作流/训练/节点各自传入本模块预览路由。
 */
export function previewTrigger(
  data: { trigger: string; trigger_args: unknown },
  url: string = `${WS_PATH}/trigger/preview`
) {
  return request<ApiResponse<TriggerPreview>>({
    url,
    method: "post",
    data,
    headers: { _silent: "true" },
  });
}
