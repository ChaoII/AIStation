import { request } from "@utils";

const V = "/video";

export const VideoAPI = {
  // ── Camera ──
  listCamera(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/camera/list`, method: "get", params });
  },
  detailCamera(id: number) {
    return request<ApiResponse>({ url: `${V}/camera/detail/${id}`, method: "get" });
  },
  createCamera(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/camera/create`, method: "post", data });
  },
  updateCamera(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/camera/update/${id}`, method: "put", data });
  },
  deleteCamera(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/camera/delete`, method: "delete", data: { ids } });
  },
  startStream(id: number) {
    return request<ApiResponse>({ url: `${V}/camera/stream/start/${id}`, method: "post" });
  },
  stopStream(id: number) {
    return request<ApiResponse>({ url: `${V}/camera/stream/stop/${id}`, method: "post" });
  },
  getStreamUrls(id: number) {
    return request<ApiResponse>({ url: `${V}/camera/stream/urls/${id}`, method: "get" });
  },

  // ── Camera Group ──
  listCameraGroup() {
    return request<ApiResponse>({ url: `${V}/camera/group/list`, method: "get" });
  },
  createCameraGroup(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/camera/group/create`, method: "post", data });
  },
  updateCameraGroup(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/camera/group/update/${id}`, method: "put", data });
  },
  deleteCameraGroup(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/camera/group/delete`, method: "delete", data: { ids } });
  },

  // ── Record ──
  listRecordPlan(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/record/plan/list`, method: "get", params });
  },
  createRecordPlan(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/record/plan/create`, method: "post", data });
  },
  updateRecordPlan(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/record/plan/update/${id}`, method: "put", data });
  },
  deleteRecordPlan(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/record/plan/delete`, method: "delete", data: { ids } });
  },
  startRecord(cameraId: number, streamId: string) {
    return request<ApiResponse>({ url: `${V}/record/start/${cameraId}/${streamId}`, method: "post" });
  },
  stopRecord(streamId: string) {
    return request<ApiResponse>({ url: `${V}/record/stop/${streamId}`, method: "post" });
  },
  listRecordFile(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/record/file/list`, method: "get", params });
  },
  getRecordFilePlayUrl(id: number) {
    return request<ApiResponse>({ url: `${V}/record/file/${id}/play-url`, method: "get" });
  },
  getRecordFileThumbnail(id: number) {
    return request<Blob>({ url: `${V}/record/file/${id}/thumbnail`, method: "get", responseType: "blob" });
  },
  listRecordLog(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/record/log/list`, method: "get", params });
  },
  toggleRecordPlan(id: number) {
    return request<ApiResponse>({ url: `${V}/record/plan/${id}/toggle`, method: "post" });
  },
  executeRecordPlan(id: number) {
    return request<ApiResponse>({ url: `${V}/record/plan/${id}/execute`, method: "post" });
  },
  stopRecordPlan(id: number) {
    return request<ApiResponse>({ url: `${V}/record/plan/${id}/stop`, method: "post" });
  },

  // ── Alarm ──
  listAlarmRule(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/alarm/rule/list`, method: "get", params });
  },
  createAlarmRule(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/alarm/rule/create`, method: "post", data });
  },
  updateAlarmRule(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/alarm/rule/update/${id}`, method: "put", data });
  },
  deleteAlarmRule(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/alarm/rule/delete`, method: "delete", data: { ids } });
  },
  listAlarmRecord(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/alarm/record/list`, method: "get", params });
  },
  getRealtimeAlarms() {
    return request<ApiResponse>({ url: `${V}/alarm/record/realtime`, method: "get" });
  },
  confirmAlarm(id: number, status: string) {
    return request<ApiResponse>({ url: `${V}/alarm/record/confirm/${id}`, method: "put", data: { status } });
  },
  deleteAlarmRecord(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/alarm/record/delete`, method: "delete", data: { ids } });
  },
  testNotification(channel: string, config?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/alarm/notification/test`, method: "post", data: { channel, config: config || {} } });
  },

  // ── Algorithm ──
  listAlgorithm(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/list`, method: "get", params });
  },
  createAlgorithm(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/create`, method: "post", data });
  },
  updateAlgorithm(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/update/${id}`, method: "put", data });
  },
  deleteAlgorithm(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/algorithm/delete`, method: "delete", data: { ids } });
  },
  listAlgorithmTask(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/list`, method: "get", params });
  },
  createAlgorithmTask(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/create`, method: "post", data });
  },
  updateAlgorithmTask(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/update/${id}`, method: "put", data });
  },
  deleteAlgorithmTask(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/delete`, method: "delete", data: { ids } });
  },
  startInferenceTask(id: number) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/${id}/start`, method: "post" });
  },
  stopInferenceTask(id: number) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/${id}/stop`, method: "post" });
  },
  getInferenceStatus(id: number) {
    return request<ApiResponse>({ url: `${V}/algorithm/task/${id}/inference-status`, method: "get" });
  },

  // ── Event ──
  listEvent(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/event/list`, method: "get", params });
  },
  createEvent(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/event/create`, method: "post", data });
  },
  updateEvent(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/event/update/${id}`, method: "put", data });
  },
  deleteEvent(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/event/delete`, method: "delete", data: { ids } });
  },

  // ── Layout ──
  listLayout(params?: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/layout/list`, method: "get", params });
  },
  detailLayout(id: number) {
    return request<ApiResponse>({ url: `${V}/layout/detail/${id}`, method: "get" });
  },
  createLayout(data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/layout/create`, method: "post", data });
  },
  updateLayout(id: number, data: Record<string, unknown>) {
    return request<ApiResponse>({ url: `${V}/layout/update/${id}`, method: "put", data });
  },
  deleteLayout(ids: number[]) {
    return request<ApiResponse>({ url: `${V}/layout/delete`, method: "delete", data: { ids } });
  },

  // ── Preview ──
  getPlayUrls(cameraId: number) {
    return request<ApiResponse>({ url: `${V}/preview/urls/${cameraId}`, method: "get" });
  },
  getSnap(cameraId: number) {
    return request<Blob>({ url: `${V}/preview/snap/${cameraId}`, method: "get", responseType: "blob" });
  },
};

export default VideoAPI;
