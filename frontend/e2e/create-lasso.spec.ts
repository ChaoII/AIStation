import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 套索：沿目标外轮廓描一圈 → 松手自动闭合填充成多边形标注。

test("套索描圈生成闭合填充多边形标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  await page.locator(".tool-btn", { hasText: "画笔分割" }).click();

  // 切到套索模式：打开右键浮层并选择「套索」
  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.5, { button: "right" });
  await page.locator(".brush-popover .el-radio-button", { hasText: "套索" }).click();
  // 断言套索 radio 已被选中（is-active 为 Element Plus 选中态），确保 mode 已切到套索
  await expect(page.locator(".brush-popover .el-radio-button.is-active", { hasText: "套索" })).toBeVisible();
  await page.mouse.click(img.x + img.width * 0.1, img.y + img.height * 0.9); // 关浮层避免遮挡

  // 描一圈（从顶部中点逆时针绕一圈回到起点附近）
  const cx = img.x + img.width * 0.5;
  const cy = img.y + img.height * 0.5;
  const r = Math.min(img.width, img.height) * 0.25;
  await page.mouse.move(cx, cy - r);
  await page.mouse.down();
  for (let i = 1; i <= 40; i++) {
    const a = (i / 40) * Math.PI * 2 - Math.PI / 2;
    await page.mouse.move(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  }
  await page.mouse.up();

  await expectAnnotation(page);
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
