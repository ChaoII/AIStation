import { describe, expect, it } from "vitest";

import { SURFACE_STYLE_IMPORT, surfacePropsDefaults } from "../surfaceStyles";

describe("agent-surface 基座", () => {
  it("默认中文 + 纸色 + 显示思考与工具调用", () => {
    expect(surfacePropsDefaults()).toEqual({
      theme: "light",
      palette: "paper",
      locale: "zh-CN",
      showReasoning: true,
      showToolCalls: true,
    });
  });

  it("样式从包导出的入口引入", () => {
    expect(SURFACE_STYLE_IMPORT).toBe("agent-surface/style.css");
  });
});
