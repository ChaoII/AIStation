import { test } from "@playwright/test";

test("import dialog style", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 950 });
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await page.locator(".el-table__row").first().waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForTimeout(1200);
  await page.locator(".el-table__row").first().getByRole("button", { name: /更多/ }).click();
  await page.getByRole("menuitem", { name: "导入标注" }).first().click();
  await page.locator(".el-dialog").filter({ hasText: "导入标注到" }).waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.locator(".el-dialog").filter({ hasText: "导入标注到" }).screenshot({ path: "e2e/.shots/70-dialog.png" });
});
