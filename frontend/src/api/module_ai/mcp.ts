import request from "@/utils/request";

const API_PATH = "/ai/mcp";

/** MCP 服务器配置 */
export interface McpServer {
  id: number;
  name: string;
  /** 传输方式：stdio/sse/streamable-http */
  transport: string;
  command: string;
  args: string[];
  env: Record<string, any>;
  url: string;
  headers: Record<string, any>;
  /** 鉴权：none/bearer/custom */
  auth_type: string;
  enabled: boolean;
  description: string;
  created_time?: string;
}

export function getMcpList() {
  return request({ url: `${API_PATH}/list`, method: "get" });
}

export function getMcpDetail(id: number) {
  return request({ url: `${API_PATH}/detail/${id}`, method: "get" });
}

export function createMcp(data: any) {
  return request({ url: `${API_PATH}/create`, method: "post", data });
}

export function updateMcp(id: number, data: any) {
  return request({ url: `${API_PATH}/update/${id}`, method: "put", data });
}

export function deleteMcp(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}

export function toggleMcp(id: number, enabled: boolean) {
  return request({ url: `${API_PATH}/toggle/${id}`, method: "put", data: { enabled } });
}

/** 测试 MCP 连接（可达性探测） */
export function testMcp(id: number) {
  return request({
    url: `${API_PATH}/test/${id}`,
    method: "post",
    headers: { _silent: "true" },
    timeout: 20000,
  });
}
