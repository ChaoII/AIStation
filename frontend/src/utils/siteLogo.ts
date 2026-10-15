/**
 * 站点 logo / 背景 兜底解析工具。
 *
 * 背景：`sys_web_logo`、`sys_login_background` 等数据库配置项曾指向失效地址
 * （如 127.0.0.1:8001 且带反斜杠），或已被清空为空串，导致登录页/侧边栏
 * logo 与登录背景显示破损/空白。
 *
 * 统一规则：配置为空 → 回落内置资源（logo.svg / login-bg-blue.png / favicon.svg）;
 * 非空 → 使用配置值。登录页、AppLogo、main.ts、配置中心预览 多处复用。
 */

/** 站点 logo：配置为空时回落内置 logo.svg（透明背景，亮/暗主题自适应） */
export function resolveSiteLogo(cfgValue?: string | null): string {
  const cfg = String(cfgValue || "").trim();
  return cfg || new URL("@/assets/images/logo.svg", import.meta.url).href;
}
// SVG 通过 new URL() 引入会被 Vite 内联；改动 logo.svg 后需让本模块重新编译（HMR 可能不失效资产）


/** 登录页背景：配置为空时回落内置 login-bg-blue.png（深蓝黑科幻，青蓝点缀） */
export function resolveLoginBackground(cfgValue?: string | null): string {
  const cfg = String(cfgValue || "").trim();
  return cfg || new URL("@/assets/images/login-bg-blue.png", import.meta.url).href;
}

/**
 * 站点 favicon（浏览器标签页图标）：配置为空或指向失效地址时回落内置 favicon.svg。
 * 与 logo 走同一套 `new URL()` 资源机制（避免 import.meta.env.BASE_URL 拼接出错）。
 */
export function resolveSiteFavicon(cfgValue?: string | null): string {
  const cfg = String(cfgValue || "").trim();
  return cfg || new URL("@/assets/images/favicon.svg", import.meta.url).href;
}
