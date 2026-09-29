import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 套索：沿目标外轮廓描一圈 → 松手自动闭合填充成多边形标注。

test("套索描圈生成闭合填充多边形标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  // 直接点工具栏「套索」按钮进入套索模式
  await page.locator(".tool-btn", { hasText: "套索" }).click();
  const img = await imageBox(page);

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
