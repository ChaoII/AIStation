/**
 * WebSocket 服务管理
 *
 * @description
 * 统一管理应用中的所有 WebSocket 连接
 * - 字典同步 WebSocket
 * - 在线用户计数 WebSocket
 * - 其他业务 WebSocket
 *
 * @author AIStation
 */

import { Auth } from "@/utils/auth";

const WS_BASE = import.meta.env.VITE_API_BASE_URL || "";

/**
 * WebSocket 服务实例约定接口
 */
type WebSocketService = {
  disconnect?: () => void;
  closeWebSocket?: () => void;
  cleanup?: () => void;
  [key: string]: any;
};

/**
 * 全局 WebSocket 实例管理
 */
const websocketInstances = new Map<string, WebSocketService>();

/**
 * 防止重复初始化的状态标记
 */
let isInitialized = false;

/**
 * 注册 WebSocket 实例
 */
export function registerWebSocketInstance(key: string, instance: WebSocketService) {
  websocketInstances.set(key, instance);
}

/**
 * 获取 WebSocket 实例
 */
export function getWebSocketInstance(key: string) {
  return websocketInstances.get(key);
}

/**
 * 初始化 WebSocket 服务
 */
export function setupWebSocket() {
  if (isInitialized) {
    console.warn("[WebSocket] 已初始化，跳过重复初始化");
    return;
  }

  if (!Auth.getAccessToken()) {
    console.warn("[WebSocket] 未登录，跳过 WebSocket 初始化");
    return;
  }

  try {
    // 建立告警通知 WebSocket 连接
    const token = Auth.getAccessToken();
    const wsUrl = `${WS_BASE.replace(/^http/, "ws")}/api/v1/video/alarm/ws?token=${token}`;
    const alarmWs = new WebSocket(wsUrl);

    alarmWs.onopen = () => {
      console.log("[WebSocket] 告警通知连接已建立");
      // 发送心跳
      alarmWs.send(JSON.stringify({ type: "ping" }));
    };

    alarmWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "pong") return;
        // 收到告警通知，触发自定义事件供页面消费
        window.dispatchEvent(new CustomEvent("alarm-notification", { detail: data }));
        console.log("[WebSocket] 收到告警通知:", data.alarm_type);
      } catch {
        /* ignore */
      }
    };

    alarmWs.onclose = () => {
      console.log("[WebSocket] 告警通知连接已关闭");
    };

    alarmWs.onerror = (err) => {
      console.warn("[WebSocket] 告警通知连接出错:", err);
    };

    registerWebSocketInstance("alarm", {
      closeWebSocket: () => alarmWs.close(),
    });

    // 定时心跳保持连接
    const heartbeat = setInterval(() => {
      try {
        alarmWs.send(JSON.stringify({ type: "ping" }));
      } catch {
        clearInterval(heartbeat);
      }
    }, 30000);

    registerWebSocketInstance("alarm-heartbeat", {
      cleanup: () => clearInterval(heartbeat),
    });

    isInitialized = true;
    console.log("[WebSocket] 初始化成功");
  } catch (error) {
    console.error("[WebSocket] 初始化失败:", error);
  }
}

/**
 * 清理所有 WebSocket 连接
 */
export function cleanupWebSocket() {
  console.log("[WebSocket] 开始清理连接...");

  websocketInstances.forEach((instance, key) => {
    try {
      if (instance.disconnect) {
        instance.disconnect();
      } else if (instance.closeWebSocket) {
        instance.closeWebSocket();
      } else if (instance.cleanup) {
        instance.cleanup();
      }
      console.log(`[WebSocket] ${key} 已断开`);
    } catch (error) {
      console.error(`[WebSocket] ${key} 清理失败:`, error);
    }
  });

  websocketInstances.clear();
  isInitialized = false;
  console.log("[WebSocket] 清理完成");
}

/**
 * 重新初始化 WebSocket
 */
export function reinitializeWebSocket() {
  cleanupWebSocket();
  setupWebSocket();
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    cleanupWebSocket();
  });
}
