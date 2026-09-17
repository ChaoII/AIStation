import request from "@/utils/request";

/** 人脸底库条目（列表/详情输出，不含特征向量） */
export interface FaceGalleryItem {
  id: number;
  name: string;
  person_no?: string | null;
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
  model_key?: string;
  description?: string | null;
  face_image_url?: string | null;
  embedding?: number[] | null;
  dimension?: number | null;
}

/** 分页查询人脸底库 */
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

/** 底库比对（给定特征向量返回相似度 top-k） */
export function matchFaceGallery(data: {
  embedding: number[];
  top_k?: number;
  threshold?: number;
}) {
  return request({ url: "/video/face-gallery/match", method: "post", data });
}
