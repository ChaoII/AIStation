import request from "@/utils/request";

export function getAlgorithmList(data?: any) {
  return request({ url: "/video/algorithm/list", method: "get", params: data });
}

export function createAlgorithm(data: any) {
  return request({ url: "/video/algorithm/create", method: "post", data });
}

export function updateAlgorithm(id: number, data: any) {
  return request({ url: `/video/algorithm/update/${id}`, method: "put", data });
}

export function deleteAlgorithm(ids: number[]) {
  return request({ url: "/video/algorithm/delete", method: "delete", data: ids });
}

export function getAlgorithmTaskList(data?: any) {
  return request({ url: "/video/algorithm/task/list", method: "get", params: data });
}

export function createAlgorithmTask(data: any) {
  return request({ url: "/video/algorithm/task/create", method: "post", data });
}

export function updateAlgorithmTask(id: number, data: any) {
  return request({ url: `/video/algorithm/task/update/${id}`, method: "put", data });
}

export function deleteAlgorithmTask(ids: number[]) {
  return request({ url: "/video/algorithm/task/delete", method: "delete", data: ids });
}

/** 热更新/回滚下发结果：成功任务ID列表 + 失败任务及原因 */
export interface AlgorithmDispatchResult {
  succeeded: number[];
  failed: { task_id: number; error: string }[];
}

/** 模型热更新：把当前模型下发到所有引用该算法的任务（_silent 由页面自行汇总提示） */
export function hotUpdateAlgorithm(id: number) {
  return request({
    url: `/video/algorithm/${id}/hot-update`,
    method: "post",
    headers: { _silent: "true" },
  });
}

/** 模型回滚：恢复上一版本并下发到所有引用任务 */
export function rollbackAlgorithm(id: number) {
  return request({
    url: `/video/algorithm/${id}/rollback`,
    method: "post",
    headers: { _silent: "true" },
  });
}

/** 重试模型下发：仅对指定失败任务重新下发当前模型（补偿部分失败） */
export function retryDispatchAlgorithm(id: number, taskIds: number[]) {
  return request({
    url: `/video/algorithm/${id}/dispatch-retry`,
    method: "post",
    data: { task_ids: taskIds },
    headers: { _silent: "true" },
  });
}
