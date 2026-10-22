import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page
    .locator(".el-tour")
    .waitFor({ state: "visible", timeout: 2500 })
    .catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("提示词列表搜索在上，弹窗内画布可添加块并识别变量与预览", async ({ page }) => {
  await page.goto("/#/ai/prompt", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 搜索表单在列表上方（DOM 纵向顺序）
  const search = page.locator(".ai-prompt-page .search-container");
  await expect(search).toBeVisible({ timeout: 10_000 });
  const table = page.locator(".ai-prompt-page .el-table").first();
  await expect(table).toBeVisible({ timeout: 10_000 });
  const searchBox = await search.boundingBox();
  const tableBox = await table.boundingBox();
  expect(searchBox).not.toBeNull();
  expect(tableBox).not.toBeNull();
  expect(searchBox!.y).toBeLessThan(tableBox!.y);

  // 点击新增打开全屏画布弹窗
  const addButton = page.getByRole("button", { name: "新增" }).first();
  await expect(addButton).toBeVisible({ timeout: 10_000 });
  await addButton.evaluate((el) => (el as HTMLElement).click());

  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".el-dialog.is-fullscreen")).toBeVisible();

  // 画布内的「添加块」按钮
  const addBlock = dialog.getByRole("button", { name: "添加块" }).first();
  await expect(addBlock).toBeVisible({ timeout: 10_000 });

  const before = await dialog.locator(".prompt-editor .nav-item").count();
  // 引导 tour 遮罩可能拦截指针事件，直接派发 click（与 ai-model.spec.ts 一致）
  await addBlock.evaluate((el) => (el as HTMLElement).click());
  // 编辑器已改版：块列表为左侧导航 .nav-item（原 .block-editor 已移除）
  await expect(dialog.locator(".prompt-editor .nav-item")).toHaveCount(before + 1);

  await expect(dialog.getByRole("button", { name: "保存" })).toBeVisible();

  // 新增块后输入含 {{name}} 的内容，验证变量自动识别与预览
  const textarea = dialog.locator(".prompt-editor__textarea textarea");
  await textarea.fill("你好，{{name}}");

  // 右侧「变量」页签（默认激活）自动出现 name 标签
  const aside = dialog.locator(".prompt-editor__aside");
  await expect(aside.locator(".var-row .el-tag", { hasText: "name" }).first()).toBeVisible();

  // 切「预览」页签：未赋值时保留占位符原文
  await aside.getByRole("tab", { name: "预览" }).click();
  const preview = aside.locator(".preview");
  await expect(preview).toContainText("你好，{{name}}");

  // 切回「变量」填写示例值，再看预览完成变量替换
  await aside.getByRole("tab", { name: "变量" }).click();
  await aside.locator(".var-row input").first().fill("小明");
  await aside.getByRole("tab", { name: "预览" }).click();
  await expect(preview).toContainText("你好，小明");
});
