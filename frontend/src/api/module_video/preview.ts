import request from "@/utils/request";

export function getPlayUrls(cameraId: number) {
  return request({ url: `/video/preview/urls/${cameraId}`, method: "get" });
}
