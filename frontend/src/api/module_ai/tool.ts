import request from "@/utils/request";

const API_PATH = "/ai/tools";

/** Agno 工具配置字段声明（由后端注册表下发，前端据此自动生成表单） */
export interface AiToolConfigField {
  /** 配置键名（如 api_key） */
  key: string;
  /** 展示名（缺省用 key） */
  label?: string;
  /** 是否密钥字段：用密码框并脱敏保存/回显 */
  secret?: boolean;
  /** 是否必填：缺失时工具未就绪 */
  required?: boolean;
}

/** 工具中心列表行 */
export interface AiToolRow {
  id: number;
  name: string;
  kind: string;
  /** 来源：system / agno / http */
  source: string;
  /** 启用状态 */
  enabled: boolean;
  /** 就绪状态与未就绪原因 */
  ready: boolean;
  reason: string;
  /** 展示名（agno 用注册表标题，其余为空） */
  title?: string | null;
  /** 分组（agno） */
  group?: string | null;
  /** 风险级别（agno）：low / high */
  risk?: string | null;
  /** 配置字段声明（agno） */
  config_fields?: AiToolConfigField[];
  /** 运行配置（敏感值已掩码为 ****） */
  config?: Record<string, any> | null;
  description?: string | null;
  method?: string;
  url?: string;
  /** 请求头（敏感值已掩码为 ****） */
  headers?: Record<string, any> | null;
  params_schema?: Record<string, any> | null;
}

export function getAiToolList(params?: any) {
  return request({ url: `${API_PATH}/list`, method: "get", params });
}

export function createAiTool(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateAiTool(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteAiTool(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function toggleAiTool(id: number, enabled: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", data: { enabled } });
}

export function testAiTool(id: number) {
  return request({
    url: `${API_PATH}/test/${id}`,
    method: "post",
    headers: { _silent: "true" },
    timeout: 30000,
  });
}
