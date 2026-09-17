import { test, expect, type Page } from "@playwright/test";

/** 关闭可能遮挡点击的新手引导 Tour（el-tour），避免拦截交互。 */
async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) {
    await close.click({ force: true }).catch(() => {});
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page
    .locator(".el-tour")
    .waitFor({ state: "hidden", timeout: 3000 })
    .catch(() => {});
}

test("人脸底库页可加载并完成录入→列表→删除", async ({ page }) => {
  await page.goto("/#/video/face-gallery", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".tags-item.active .tag-text").first()).toHaveText("人脸底库");
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  await dismissTour(page);

  const name = `E2E 底库 ${Date.now()}`;

  // 录入：粘贴 JSON 特征向量
  await page
    .getByRole("button", { name: /新增|添加|Add/i })
    .first()
    .click({ force: true });
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("姓名/标签").fill(name);
  await dialog.getByLabel("工号/编号").fill("E2E-001");
  await dialog.getByLabel("特征向量").fill("[0.1, 0.2, 0.3, 0.4]");
  // 解析维度提示
  await expect(dialog.locator(".gallery-dialog__dim")).toContainText("4");
  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(dialog).toBeHidden();

  // 列表可见
  const row = page.locator(".el-table__row", { hasText: name }).first();
  await expect(row).toBeVisible();

  // 删除（勾选行 → 工具栏删除 → 确认）
  await row.locator(".el-checkbox").click();
  await page.getByRole("button", { name: /^删除$/ }).first().click({ force: true });
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.locator(".el-table__row", { hasText: name })).toHaveCount(0);
});
