import request from "@/utils/request";

const API_PATH = "/ai/market";

/** 市场商品（工具/技能/MCP/插件统一橱窗条目） */
export interface MarketItem {
  id: number;
  /** 资产类型：tool/skill/mcp/plugin */
  asset_type: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  tags: string[];
  version: string;
  owner_id?: number | null;
  is_official: boolean;
  featured: boolean;
  /** 状态：draft/pending/approved/rejected/offline */
  status: string;
  payload?: Record<string, any> | null;
  source_id?: number | null;
  install_count: number;
  favorite_count: number;
  audit_remark: string;
  created_time?: string;
  /** 当前用户是否已安装/已收藏 */
  installed: boolean;
  favorited: boolean;
}

/** 我的资产（个人真实资产 + 关联市场状态） */
export interface MyAsset {
  asset_type: string;
  real_id: number;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  market?: {
    item_id: number;
    status: string;
    featured: boolean;
    install_count: number;
    audit_remark: string;
  } | null;
}

/** 分享记录 */
export interface MarketShare {
  id: number;
  item_id: number;
  item_name: string;
  item_type: string;
  item_icon: string;
  item_description: string;
  from_user_id: number;
  from_user_name: string;
  to_user_id: number;
  to_user_name: string;
  status: string;
  message: string;
  created_time?: string;
}

export function getMarketHome() {
  return request({ url: `${API_PATH}/home`, method: "get" });
}

export function getMarketItems(params?: any) {
  return request({ url: `${API_PATH}/items`, method: "get", params });
}

export function getMarketItemDetail(id: number) {
  return request({ url: `${API_PATH}/items/${id}`, method: "get" });
}

export function installMarketItem(id: number) {
  return request({ url: `${API_PATH}/items/${id}/install`, method: "post" });
}

export function favoriteMarketItem(id: number) {
  return request({ url: `${API_PATH}/items/${id}/favorite`, method: "post" });
}

export function unfavoriteMarketItem(id: number) {
  return request({ url: `${API_PATH}/items/${id}/favorite`, method: "delete" });
}

/** 提交个人资产到市场（进入待审核） */
export function submitMarketItem(data: {
  asset_type: string;
  source_id: number;
  name: string;
  description?: string;
  icon?: string;
  category?: string;
  tags?: string[];
  version?: string;
}) {
  return request({ url: `${API_PATH}/submit`, method: "post", data });
}

export function getMyAssets(params?: { asset_type?: string }) {
  return request({ url: `${API_PATH}/mine`, method: "get", params });
}

export function withdrawMarketItem(id: number) {
  return request({ url: `${API_PATH}/items/${id}/withdraw`, method: "post" });
}

export function getMarketReviewList(params?: { status?: string }) {
  return request({ url: `${API_PATH}/review/list`, method: "get", params });
}

export function reviewMarketItem(data: { item_id: number; action: string; remark?: string }) {
  return request({ url: `${API_PATH}/review`, method: "post", data });
}

export function setMarketFeatured(id: number, featured: boolean) {
  return request({
    url: `${API_PATH}/items/${id}/feature`,
    method: "post",
    params: { featured },
  });
}

export function shareMarketItem(data: { item_id: number; to_user_id: number; message?: string }) {
  return request({ url: `${API_PATH}/shares/share`, method: "post", data });
}

export function getMarketShares(params?: { direction?: string; status?: string }) {
  return request({ url: `${API_PATH}/shares`, method: "get", params });
}

export function acceptMarketShare(id: number) {
  return request({ url: `${API_PATH}/shares/${id}/accept`, method: "post" });
}

export function rejectMarketShare(id: number) {
  return request({ url: `${API_PATH}/shares/${id}/reject`, method: "post" });
}
