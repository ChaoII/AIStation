import request from "@/utils/request";

const API_PATH = "/annotation";

/**
 * 文本文档元数据（与后端 `DocumentService.document_out` 出参一致）。
 */
export interface TextDocumentMeta {
  id: number;
  dataset_id: number;
  filename: string;
  object_key: string;
  content_hash: string;
  encoding: string;
  character_count: number;
  line_count: number;
  status: "unannotated" | "in_progress" | "annotated";
  locked_by: number | null;
  locked_at: string | null;
  annotation_count: number;
  created_time?: string;
  updated_time?: string;
}

/**
 * 文本实体区间（字符级 [start, end)，与后端字符偏移对齐）。
 */
export interface EntitySpan {
  id: string;
  type: "EntitySpan";
  start: number;
  end: number;
  label_id: number;
  text: string;
}

/**
 * 实体关系（from/to 为实体 id，relation_type 对应任务关系类型）。
 */
export interface Relation {
  id: string;
  type: "Relation";
  from: string;
  to: string;
  relation_type: number;
}

/** 文本标注 = 实体 或 关系。 */
export type TextAnnotation = EntitySpan | Relation;

/** 文本标注保存载荷。 */
export interface TextAnnotationsPayload {
  task_id: number;
  document_id: number;
  annotations: TextAnnotation[];
}

/**
 * 上传文本文档（multipart，datasetId 走 query）。
 * 文档可能较大，不设超时，由调用方处理加载态。
 */
export function uploadDocument(file: File, datasetId: number) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ApiResponse<TextDocumentMeta>>({
    url: `${API_PATH}/document/upload`,
    method: "post",
    params: { dataset_id: datasetId },
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 0,
  });
}

/** 查询数据集下的文本文档列表。 */
export function getDocumentList(datasetId: number) {
  return request<ApiResponse<{ items: TextDocumentMeta[] }>>({
    url: `${API_PATH}/document/list`,
    method: "get",
    params: { dataset_id: datasetId },
  });
}

/** 查询单个文本文档详情。 */
export function getDocumentDetail(id: number) {
  return request<ApiResponse<TextDocumentMeta>>({
    url: `${API_PATH}/document/detail/${id}`,
    method: "get",
  });
}

/** 获取文本文档全文（纯文本，response.data 为字符串）。 */
export function getDocumentContent(id: number) {
  return request<string>({
    url: `${API_PATH}/document/content/${id}`,
    method: "get",
    responseType: "text",
  });
}

/** 锁定文本文档（按文档整体加锁）。 */
export function lockDocument(id: number) {
  return request<ApiResponse<{ locked: boolean; locked_by: number | null }>>({
    url: `${API_PATH}/document/lock/${id}`,
    method: "post",
  });
}

/** 解锁文本文档。 */
export function unlockDocument(id: number) {
  return request<ApiResponse>({
    url: `${API_PATH}/document/unlock/${id}`,
    method: "post",
  });
}

/** 保存文本文档的标注。 */
export function saveTextAnnotations(payload: TextAnnotationsPayload) {
  return request<ApiResponse<{ version: number; annotation_count: number }>>({
    url: `${API_PATH}/anno/document/save`,
    method: "post",
    data: payload,
  });
}

/** 读取文本文档的标注。 */
export function loadTextAnnotations(taskId: number, documentId: number) {
  return request<ApiResponse<{ annotation_data: TextAnnotation[]; version: number }>>({
    url: `${API_PATH}/anno/document/load`,
    method: "get",
    params: { task_id: taskId, d_id: documentId },
  });
}
