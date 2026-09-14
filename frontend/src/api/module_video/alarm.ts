import request from "@/utils/request";

/** 场景参数原值（归一化坐标点列等，spec §4.1/§4.3） */
export interface AlarmRuleParams {
  /** 检测区域，归一化点列 [[x,y],...] */
  roi?: number[][];
  /** 绊线，归一化点列 [[x,y],[x,y]] */
  line?: number[][];
  /** 越线方向 */
  direction?: string;
  /** 目标标签 */
  labels?: string[];
  /** 置信度阈值 */
  confidence_threshold?: number;
  /** 数量阈值 */
  count?: number;
  /** 时间窗口（秒） */
  window_sec?: number;
  /** 停留时长（秒） */
  dwell_sec?: number;
  /** 其他场景参数 */
  [key: string]: unknown;
}

/** 告警规则创建/更新载荷 */
export interface AlarmRulePayload {
  name?: string;
  camera_id?: number;
  algorithm_task_id?: number | null;
  alarm_type?: string;
  severity?: string;
  sensitivity?: number;
  interval_seconds?: number;
  notify_channels?: string[];
  schedule_json?: unknown;
  status?: boolean;
  description?: string | null;
  /** 场景码（与 alarm_type 对应） */
  scene_type?: string;
  /** 场景参数原值，保存后参与条件编译 */
  params?: AlarmRuleParams;
  /** 条件树（前端只产 AND/OR，后端兼容一元 not） */
  conditions?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export function getAlarmRuleList(data?: any) {
  return request({ url: "/video/alarm/rule/list", method: "get", params: data });
}

export function createAlarmRule(data: AlarmRulePayload) {
  return request({ url: "/video/alarm/rule/create", method: "post", data });
}

export function updateAlarmRule(id: number, data: AlarmRulePayload) {
  return request({ url: `/video/alarm/rule/update/${id}`, method: "put", data });
}

export function deleteAlarmRule(ids: number[]) {
  return request({ url: "/video/alarm/rule/delete", method: "delete", data: ids });
}

export function getAlarmRecordList(data?: any) {
  return request({ url: "/video/alarm/record/list", method: "get", params: data });
}

export function getRealtimeAlarms() {
  return request({
    url: "/video/alarm/record/realtime",
    method: "get",
    headers: { _silent: "true" },
  });
}

export function confirmAlarm(id: number, status: string) {
  return request({ url: `/video/alarm/record/confirm/${id}`, method: "put", data: { status } });
}

export function deleteAlarmRecord(ids: number[]) {
  return request({ url: "/video/alarm/record/delete", method: "delete", data: ids });
}

export function testNotification(channel: string, config?: any) {
  return request({
    url: "/video/alarm/notification/test",
    method: "post",
    data: { channel, config: config || {} },
  });
}
