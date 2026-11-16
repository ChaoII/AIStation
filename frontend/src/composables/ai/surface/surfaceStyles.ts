/**
 * agent-surface 的接入常量。
 *
 * 为什么单独抽一个文件：样式/默认值散落在页面里会导致「四个入口各写一套」，
 * 后面改主题或语言要改四处。这里只放**常量**，不引组件、不带副作用。
 *
 * 样式安全：agent-surface 的所有 design token 都挂在 `.as-root` 作用域
 * （tokens.css / themes.css 已核实），不会污染 `:root` 与 Element Plus 变量。
 */
export const SURFACE_STYLE_IMPORT = "agent-surface/style.css";

export type SurfaceDefaults = {
  theme: "light" | "dark" | "auto";
  palette: string;
  locale: "zh-CN" | "en-US";
  showReasoning: boolean;
  showToolCalls: boolean;
};

/** AIStation 的默认外观：浅色 + paper + 中文 + 显示思考与工具调用 */
export function surfacePropsDefaults(): SurfaceDefaults {
  return {
    theme: "light",
    palette: "paper",
    locale: "zh-CN",
    showReasoning: true,
    showToolCalls: true,
  };
}
