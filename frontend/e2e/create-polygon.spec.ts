import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：多边形（逐点 + 双击闭合）创建流程。

test("polygon 逐点绘制并双击闭合生成多边形", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  // 切到多边形工具（快捷键 4/p）
  await page.keyboard.press("p");

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);
  // 双击闭合（dblclick 自身会追加该点并闭合多边形）
  await page.mouse.dblclick(img.x + img.width * 0.6, img.y + img.height * 0.7);

  await expectAnnotation(page);
});
