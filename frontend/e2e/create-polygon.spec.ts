import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：多边形（逐点 + 点击首点闭合）创建流程。

test("polygon 逐点绘制并点击首点闭合生成多边形", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  // 切到多边形工具（快捷键 4/p）
  await page.keyboard.press("p");

  const img = await imageBox(page);
  const p1 = { x: img.x + img.width * 0.3, y: img.y + img.height * 0.3 };
  const p2 = { x: img.x + img.width * 0.7, y: img.y + img.height * 0.3 };
  const p3 = { x: img.x + img.width * 0.5, y: img.y + img.height * 0.6 };
  await page.mouse.click(p1.x, p1.y);
  await page.mouse.click(p2.x, p2.y);
  await page.mouse.click(p3.x, p3.y);
  // 点击首点附近（闭合半径内）闭合多边形
  await page.mouse.click(p1.x, p1.y);

  await expectAnnotation(page);
});
