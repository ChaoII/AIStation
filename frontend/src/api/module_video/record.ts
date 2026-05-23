import request from '@/utils/request'

export function getRecordPlanList(data?: any) {
  return request({ url: '/video/record/plan/list', method: 'get', params: data })
}

export function createRecordPlan(data: any) {
  return request({ url: '/video/record/plan/create', method: 'post', data })
}

export function updateRecordPlan(id: number, data: any) {
  return request({ url: `/video/record/plan/update/${id}`, method: 'put', data })
}

export function deleteRecordPlan(ids: number[]) {
  return request({ url: '/video/record/plan/delete', method: 'delete', data: { ids } })
}

export function startRecord(cameraId: number, streamId: string) {
  return request({ url: `/video/record/start/${cameraId}/${streamId}`, method: 'post' })
}

export function stopRecord(streamId: string) {
  return request({ url: `/video/record/stop/${streamId}`, method: 'post' })
}
