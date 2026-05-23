import request from '@/utils/request'

export function getAlarmRuleList(data?: any) {
  return request({ url: '/video/alarm/rule/list', method: 'get', params: data })
}

export function createAlarmRule(data: any) {
  return request({ url: '/video/alarm/rule/create', method: 'post', data })
}

export function updateAlarmRule(id: number, data: any) {
  return request({ url: `/video/alarm/rule/update/${id}`, method: 'put', data })
}

export function deleteAlarmRule(ids: number[]) {
  return request({ url: '/video/alarm/rule/delete', method: 'delete', data: { ids } })
}

export function getAlarmRecordList(data?: any) {
  return request({ url: '/video/alarm/record/list', method: 'get', params: data })
}

export function getRealtimeAlarms() {
  return request({ url: '/video/alarm/record/realtime', method: 'get' })
}

export function confirmAlarm(id: number, status: string) {
  return request({ url: `/video/alarm/record/confirm/${id}`, method: 'put', data: { status } })
}

export function deleteAlarmRecord(ids: number[]) {
  return request({ url: '/video/alarm/record/delete', method: 'delete', data: { ids } })
}
