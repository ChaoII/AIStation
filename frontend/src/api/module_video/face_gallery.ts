import request from "@/utils/request";

/** 底库条目（列表/详情输出，不含特征向量） */
export interface FaceGalleryItem {
  id: number;
  name: string;
  person_no?: string | null;
  /** 底库类型：face=人脸（FACE_REC/STRANGER）/ reid=跨镜重识别（REID_TRACK） */
  kind: string;
  model_key: string;
  dimension: number;
  face_image_url?: string | null;
  description?: string | null;
  updated_time?: string | null;
}

/** 录入/更新入参（id 省略=新增，embedding 必填；带 id 时 embedding 可省略） */
export interface FaceGalleryEnrollPayload {
  id?: number;
  name: string;
  person_no?: string | null;
  /** 底库类型；新增缺省 face，更新省略则保持原类型 */
  kind?: string | null;
  model_key?: string;
  description?: string | null;
  face_image_url?: string | null;
  embedding?: number[] | null;
  dimension?: number | null;
}

/** 分页查询底库（params 可含 kind 过滤） */
export function getFaceGalleryList(data?: any) {
  return request({ url: "/video/face-gallery/list", method: "get", params: data });
}

/** 录入/更新底库条目（id 提供时为更新） */
export function enrollFaceGallery(data: FaceGalleryEnrollPayload) {
  return request({ url: "/video/face-gallery/enroll", method: "post", data });
}

/** 删除底库条目（软删除，body 为 id 列表） */
export function deleteFaceGallery(ids: number[]) {
  return request({ url: "/video/face-gallery/delete", method: "delete", data: ids });
}

/** 底库比对（给定特征向量返回同类底库相似度 top-k） */
export function matchFaceGallery(data: {
  embedding: number[];
  kind?: string;
  top_k?: number;
  threshold?: number;
}) {
  return request({ url: "/video/face-gallery/match", method: "post", data });
}
