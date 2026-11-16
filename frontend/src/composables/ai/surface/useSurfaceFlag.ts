/**
 * 对话界面的灰度开关（浏览器级，改完刷新即生效）：
 * - 默认 `legacy`（旧组件），避免上线即换
 * - 打开方式：`localStorage.setItem('ai_chat_surface','surface')` 或 URL 带 `?surface=1`
 * - 回退：删掉该键或设为 `legacy`
 *
 * 为什么先做浏览器级：验证阶段要能一个人先看效果、随时切回；
 * 全量后再决定是否升级成系统参数（服务端统一下发）。
 */
const KEY = "ai_chat_surface";

export function surfaceEnabled(): boolean {
  try {
    const q = new URLSearchParams(window.location.search);
    if (q.get("surface") === "1") return true;
    if (q.get("surface") === "0") return false;
    return window.localStorage.getItem(KEY) === "surface";
  } catch {
    return false;
  }
}

export function setSurfaceEnabled(on: boolean): void {
  try {
    if (on) window.localStorage.setItem(KEY, "surface");
    else window.localStorage.removeItem(KEY);
  } catch {
    /* 隐私模式下忽略 */
  }
}
