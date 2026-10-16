import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["**/e2e/**", "**/node_modules/**"],
  },
  resolve: {
    // 与 vite.config.ts 保持一致：`@/` → `src/`（供纯逻辑测试解析引用）
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
