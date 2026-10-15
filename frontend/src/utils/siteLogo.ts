/**
 * 站点 logo / 背景 兜底解析工具。
 *
 * 背景：`sys_web_logo`、`sys_login_background` 等数据库配置项曾指向失效地址
 * （如 127.0.0.1:8001 且带反斜杠），或已被清空为空串，导致登录页/侧边栏
 * logo 与登录背景显示破损/空白。
 *
 * 统一规则：配置为空 → 回落内置资源（logo.png / login-bg.svg）;
 * 非空 → 使用配置值。登录页、AppLogo、main.ts 三处复用。
 */

/** 站点 logo：配置为空时回落内置 logo.png */
export function resolveSiteLogo(cfgValue?: string | null): string {
  const cfg = String(cfgValue || "").trim();
  return cfg || new URL("@/assets/images/logo.png", import.meta.url).href;
}

/** 登录页背景：配置为空时回落内置 login-bg.svg */
export function resolveLoginBackground(cfgValue?: string | null): string {
  const cfg = String(cfgValue || "").trim();
  return cfg || new URL("@/assets/images/login-bg.svg", import.meta.url).href;
}
