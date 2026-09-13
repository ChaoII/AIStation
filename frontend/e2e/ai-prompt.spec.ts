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

test("提示词工作台可打开、添加块并识别变量与预览", async ({ page }) => {
  await page.goto("/#/ai/prompt", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const addButton = page.getByRole("button", { name: "添加块" }).first();
  await expect(addButton).toBeVisible({ timeout: 10_000 });

  const before = await page.locator(".block-editor").count();
  // 引导 tour 遮罩可能拦截指针事件，直接派发 click（与 ai-model.spec.ts 一致）
  await addButton.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".block-editor")).toHaveCount(before + 1);

  await expect(page.getByRole("button", { name: "保存" })).toBeVisible();

  // 新增块后输入含 {{name}} 的内容，验证变量自动识别与预览
  const textarea = page.locator(".block-editor textarea").last();
  await textarea.fill("你好，{{name}}");

  // 右侧「变量」面板自动出现 name 标签
  const variablesCard = page.locator(".col-card").filter({ hasText: "变量" });
  await expect(variablesCard.getByText("name", { exact: true })).toBeVisible();

  // 预览区保留未赋值的占位符原文
  const previewCard = page.locator(".col-card").filter({ hasText: "预览" });
  const preview = previewCard.locator("pre");
  await expect(preview).toContainText("你好，{{name}}");

  // 填写示例值后预览区完成变量替换
  await variablesCard.locator(".var-row input").first().fill("小明");
  await expect(preview).toContainText("你好，小明");
});
