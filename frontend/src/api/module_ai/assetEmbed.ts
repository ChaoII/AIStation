import request from "@/utils/request";

// AI 资产嵌入 —— 工作台侧令牌治理（与开放平台应用无关，独立绑定 agent/工作流）。
const API_PATH = "/ai/asset-embed";

/** 为某 agent/工作流签发独立绑定该资产的短期令牌（明文仅返回一次）。 */
export function issueAssetToken(data: {
  kind: string;
  target_id: number;
  ttl?: number;
  permanent?: boolean;
  allow_domains?: string;
  allow_ips?: string;
}) {
  return request({ url: `${API_PATH}/tokens`, method: "post", data });
}

/** 某 agent/工作流已签发令牌列表（只读元信息，绝不含明文）。 */
export function listAssetTokens(kind: string, targetId: number) {
  return request({
    url: `${API_PATH}/tokens`,
    method: "get",
    params: { kind, target_id: targetId },
  });
}

/** 吊销资产嵌入令牌（立即生效，不可恢复）。 */
export function revokeAssetToken(id: number) {
  return request({ url: `${API_PATH}/tokens/${id}/revoke`, method: "put" });
}

/** 更新令牌白名单（域名 / IP；未传字段不改，传空串清零）。 */
export function updateAssetToken(id: number, data: { allow_domains?: string; allow_ips?: string }) {
  return request({ url: `${API_PATH}/tokens/${id}`, method: "put", data });
}

/** 某令牌的使用日志（分页，按时间倒序）。 */
export function listAssetTokenLogs(id: number, params: { page_no: number; page_size: number }) {
  return request({ url: `${API_PATH}/tokens/${id}/logs`, method: "get", params });
}
