// 本体页冒烟：页面能渲染、图谱工作区在、按钮权限门禁没有破坏模板。
//
// 为什么要它：`v-hasPerm` 是**按端点精确**批量加到 16 个组件里的（脚本化），
// 需要一个"页面还能正常打开"的护栏，避免某次批量改动把模板改坏（表现是整页白屏）。
import { test, expect } from "@playwright/test";

test("本体页渲染 + 图谱工作区就位（按钮门禁后不白屏）", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/ontology", { waitUntil: "domcontentloaded" });

  await expect(page.locator(".ai-ontology-page")).toBeVisible({ timeout: 25_000 });
  await expect(page.locator(".ont-gw")).toBeVisible({ timeout: 15_000 });
  // 图谱工具条的读控件（布局/缩放/导出）对只读用户也必须可见 —— 门禁只针对写操作
  await expect(page.locator(".ont-gw__bar")).toContainText("只显示有关联");
  expect(errors, `页面运行时报错：${errors.join(" | ")}`).toHaveLength(0);

  await page.screenshot({ path: "e2e/ontology-page.png" });
});
