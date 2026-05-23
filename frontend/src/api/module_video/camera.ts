import request from '@/utils/request'

export function getCameraList(data?: any) {
  return request({ url: '/video/camera/list', method: 'get', params: data })
}

export function getCameraDetail(id: number) {
  return request({ url: `/video/camera/detail/${id}`, method: 'get' })
}

export function createCamera(data: any) {
  return request({ url: '/video/camera/create', method: 'post', data })
}

export function updateCamera(id: number, data: any) {
  return request({ url: `/video/camera/update/${id}`, method: 'put', data })
}

export function deleteCamera(ids: number[]) {
  return request({ url: '/video/camera/delete', method: 'delete', data: { ids } })
}

export function startStream(id: number) {
  return request({ url: `/video/camera/stream/start/${id}`, method: 'post' })
}

export function stopStream(id: number) {
  return request({ url: `/video/camera/stream/stop/${id}`, method: 'post' })
}
