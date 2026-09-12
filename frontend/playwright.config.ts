import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // 全量跑时后端登录/编辑偏慢，10s 断言窗口偶发不足；适度放宽（不改变任何断言内容）
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // 串行执行：后端按客户端 IP 限流，多个浏览器上下文并发会互相触发 429
  workers: 1,
  // 全量串行跑时偶发超时（单跑通过），开启 1 次重试作为标准 flake 兜底
  retries: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
      dependencies: ["setup"],
    },
  ],
});
