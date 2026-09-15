import request from "@/utils/request";
import { Auth } from "@/utils/auth";

/** 边缘事件列表查询参数（对齐后端 `GET /video/edge/event/list`） */
export interface EdgeEventQuery {
  page_no?: number;
  page_size?: number;
  /** 相机ID */
  camera_id?: number;
  /** 布控任务ID */
  task_id?: number;
  /** 场景码 */
  algorithm_type?: string;
  /** 是否命中规则 */
  matched?: boolean;
  /** 事件起始时间（含） */
  start_time?: string;
  /** 事件结束时间（含） */
  end_time?: string;
  /** 目标 label / 文本模糊 */
  keyword?: string;
  [key: string]: any;
}

/** 检测框（v2 objects / 兼容 detections 元素） */
export interface EdgeEventObject {
  label?: string;
  confidence?: number;
  bbox?: { x?: number; y?: number; width?: number; height?: number };
  track_id?: number | string;
  attributes?: Record<string, unknown>;
  text?: string;
  [key: string]: any;
}

/** 命中叶子描述（`explain_conditions` 产物） */
export interface EdgeEventMatchedLeaf {
  /** 条件树路径，如 `and/0` */
  path?: string;
  /** 叶子主体，如 `object_present` */
  subject?: string;
  /** 可读明细，如 `person conf=0.42` */
  detail?: string;
  /** 否定叶子（not 分支）标记 */
  negated?: boolean;
}

/** 边缘事件列表项（轻量摘要） */
export interface EdgeEventItem {
  id: number;
  event_id?: string;
  edge_code?: string;
  camera_id?: number;
  task_id?: number;
  algorithm_type?: string;
  ts?: string;
  latency_ms?: number;
  /** 快照原始存储引用（对象存储 key / 本地路径 / URL） */
  snapshot_ref?: string;
  /** 归一化后的可取图地址（后端解析，可能为 null） */
  snapshot_url?: string | null;
  matched?: boolean;
  matched_rule_id?: number | null;
  object_count?: number;
  labels?: string[];
  created_time?: string;
}

/** 边缘事件详情（含全量对象/检测/命中叶子） */
export interface EdgeEventDetail extends EdgeEventItem {
  objects?: EdgeEventObject[];
  detections?: EdgeEventObject[];
  matched_leaves?: EdgeEventMatchedLeaf[];
}

/** 分页查询边缘事件（历史视图） */
export function getEdgeEventList(params?: EdgeEventQuery) {
  return request({ url: "/video/edge/event/list", method: "get", params });
}

/** 查询边缘事件详情（含 objects / detections / matched_leaves） */
export function getEdgeEventDetail(id: number) {
  return request({ url: `/video/edge/event/detail/${id}`, method: "get" });
}

/** 后端基址（与既有 WS 工具一致：优先 VITE_API_BASE_URL，其次当前页 origin） */
const WS_BASE = import.meta.env.VITE_API_BASE_URL || "";

/**
 * 构造边缘事件实时推送 WebSocket 地址。
 *
 * 浏览器 WS 无法携带自定义请求头，故 token 走 query 参数（与告警/协作 WS 一致）。
 * @param token 访问令牌；缺省时读取当前登录态 token
 */
export function buildEdgeEventWsUrl(token?: string): string {
  const jwt = token ?? Auth.getAccessToken() ?? "";
  const base = WS_BASE || (typeof window !== "undefined" ? window.location.origin : "");
  return `${base.replace(/^http/, "ws")}/api/v1/video/edge/event/ws?token=${encodeURIComponent(jwt)}`;
}
