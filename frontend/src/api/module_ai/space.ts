import request from "@/utils/request";

const SPACE_PATH = "/ai/space";

// ---------- 类型 ----------
export interface SpaceFolder {
  id: number;
  name: string;
  parent_id?: number | null;
  children?: SpaceFolder[];
  created_time?: string;
  updated_time?: string;
  file_count?: number;
  size?: number;
}

export interface SpaceFileItem {
  id: number;
  uuid: string;
  name: string;
  ext: string;
  file_type: string;
  mime_type: string;
  size: number;
  source: "upload" | "agent";
  folder_id: number | null;
  created_time: string;
  updated_time: string;
}

export interface SpaceFileListResult {
  page_no: number;
  page_size: number;
  total: number;
  has_next: boolean;
  items: SpaceFileItem[];
}

export interface SpaceQuota {
  used_bytes: number;
  quota_bytes: number;
  max_file_bytes: number;
  default_quota_bytes: number;
  has_pending_request: boolean;
}

export interface SpaceQuotaRequest {
  id: number;
  user_id: number;
  target_mb: number;
  reason: string;
  status: "pending" | "approved" | "rejected";
  reviewed_by?: number | null;
  review_note?: string;
  review_time?: string;
  created_time?: string;
  username?: string;
}

// ---------- 文件夹 ----------
export function getSpaceFolderTree() {
  return request<ApiResponse<SpaceFolder[]>>({
    url: `${SPACE_PATH}/folders/tree`,
    method: "get",
  });
}

export function createSpaceFolder(data: { name: string; parent_id?: number | null }) {
  return request<ApiResponse<SpaceFolder>>({
    url: `${SPACE_PATH}/folders/create`,
    method: "post",
    data,
  });
}

export function updateSpaceFolder(id: number, data: { name: string }) {
  return request<ApiResponse<SpaceFolder>>({
    url: `${SPACE_PATH}/folders/update/${id}`,
    method: "put",
    data,
  });
}

export function deleteSpaceFolder(id: number) {
  return request<ApiResponse<{ deleted_files: number }>>({
    url: `${SPACE_PATH}/folders/delete`,
    method: "delete",
    data: id,
  });
}

// ---------- 文件 ----------
export function getSpaceFileList(params: {
  folder_id?: number | null;
  keyword?: string;
  file_type?: string;
  page_no?: number;
  page_size?: number;
}) {
  const clean: Record<string, unknown> = { ...params };
  // axios 会把 null 序列化为空串（如 folder_id=），后端 int 校验 422 → 直接剔除空值
  for (const k of Object.keys(clean)) {
    if (clean[k] == null || clean[k] === "") delete clean[k];
  }
  return request<ApiResponse<SpaceFileListResult>>({
    url: `${SPACE_PATH}/files/list`,
    method: "get",
    params: clean,
  });
}

export function uploadSpaceFile(
  file: File,
  folderId: number | null,
  onProgress?: (percent: number) => void
) {
  const form = new FormData();
  form.append("file", file);
  if (folderId != null) form.append("folder_id", String(folderId));
  return request<ApiResponse<SpaceFileItem>>({
    url: `${SPACE_PATH}/files/upload`,
    method: "post",
    data: form,
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e: any) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
    },
  });
}

export function downloadSpaceFile(fileId: number) {
  return request({
    url: `${SPACE_PATH}/files/${fileId}/download`,
    method: "get",
    responseType: "blob",
  });
}

export function previewSpaceFile(fileId: number) {
  return request<ApiResponse<{ kind: string; content?: string; truncated?: boolean }>>({
    url: `${SPACE_PATH}/files/${fileId}/preview`,
    method: "get",
  });
}

/** office 文档(pptx/docx/xlsx) 转 PDF 预览，返回二进制/pdf。 */
export function previewOfficePdf(fileId: number) {
  return request({
    url: `${SPACE_PATH}/files/${fileId}/preview-pdf`,
    method: "get",
    responseType: "blob",
  });
}

export function renameSpaceFile(data: { file_id: number; name: string }) {
  return request<ApiResponse<SpaceFileItem>>({
    url: `${SPACE_PATH}/files/rename`,
    method: "put",
    data,
  });
}

export function moveSpaceFile(data: { file_id: number; folder_id?: number | null }) {
  return request<ApiResponse<SpaceFileItem>>({
    url: `${SPACE_PATH}/files/move`,
    method: "post",
    data,
  });
}

export function deleteSpaceFiles(fileIds: number[]) {
  return request<ApiResponse<{ deleted: number }>>({
    url: `${SPACE_PATH}/files/delete`,
    method: "delete",
    data: fileIds,
  });
}

// ---------- 配额 ----------
export function getSpaceQuota() {
  return request<ApiResponse<SpaceQuota>>({
    url: `${SPACE_PATH}/quota`,
    method: "get",
  });
}

// ---------- 扩容申请与审核 ----------
export function submitSpaceQuotaRequest(data: { target_mb: number; reason?: string }) {
  return request<
    ApiResponse<{ request_id: number; target_mb: number; status: string; msg: string }>
  >({
    url: `${SPACE_PATH}/quota/request`,
    method: "post",
    data,
  });
}

export function getMySpaceQuotaRequests() {
  return request<ApiResponse<SpaceQuotaRequest[]>>({
    url: `${SPACE_PATH}/quota/requests/mine`,
    method: "get",
  });
}

export function getSpaceQuotaRequests(params?: { status?: string }) {
  return request<ApiResponse<SpaceQuotaRequest[]>>({
    url: `${SPACE_PATH}/quota/requests`,
    method: "get",
    params,
  });
}

export function reviewSpaceQuotaRequest(
  id: number,
  data: { approve: boolean; quota_mb?: number | null; note?: string }
) {
  return request<ApiResponse<{ request_id: number; status: string; msg: string }>>({
    url: `${SPACE_PATH}/quota/requests/${id}/review`,
    method: "post",
    data,
  });
}
