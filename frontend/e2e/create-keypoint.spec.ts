import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：关键点（逐点 + 双击进包围框 + 拖拽拉框）创建流程。

test("keypoint 逐点放点后双击拉包围框生成关键点标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "keypoint", "kp");
  await gotoWorkbench(page, taskId);

  // 切到关键点工具（快捷键 5/k）
  await page.keyboard.press("k");

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.4, img.y + img.height * 0.4);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.5);
  // 双击进入包围框绘制模式
  await page.mouse.dblclick(img.x + img.width * 0.5, img.y + img.height * 0.5);
  // 拖拽拉出包围框（按下 → 移动 → 释放，build 返回标注）
  await page.mouse.move(img.x + img.width * 0.25, img.y + img.height * 0.25);
  await page.mouse.down();
  await page.mouse.move(img.x + img.width * 0.75, img.y + img.height * 0.75, { steps: 8 });
  await page.mouse.up();

  await expectAnnotation(page);
});
