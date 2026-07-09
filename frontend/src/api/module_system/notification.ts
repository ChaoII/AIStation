import request from "@/utils/request";

const API_PATH = "/system/notification";

export const NotificationAPI = {
  list(pageNo = 1, pageSize = 20) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/list`, method: "get", params: { page_no: pageNo, page_size: pageSize } });
  },

  unreadCount() {
    return request<ApiResponse<{ count: number }>>({ url: `${API_PATH}/unread-count`, method: "get" });
  },

  markRead(id: number) {
    return request<ApiResponse>({ url: `${API_PATH}/${id}/read`, method: "patch" });
  },

  markAllRead() {
    return request<ApiResponse<{ count: number }>>({ url: `${API_PATH}/read-all`, method: "post" });
  },
};