import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：语义分割（逐点 + 双击闭合 + 填充背景）创建流程。

test("semantic_segmentation 画多边形 + 填充背景生成标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "semantic_segmentation", "semseg");
  await gotoWorkbench(page, taskId);

  // 切到多边形工具（快捷键 p）
  await page.keyboard.press("p");

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);
  // 双击闭合
  await page.mouse.dblclick(img.x + img.width * 0.6, img.y + img.height * 0.7);

  await expectAnnotation(page);
});
