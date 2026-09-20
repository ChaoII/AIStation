import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：旋转框（三步点击）创建流程。此前 onStep 存在缺陷导致旋转框永远无法创建，
// 本用例用 3 次点击补上创建流程覆盖，防止该缺陷回归。

test("rotated_box 三步点击生成旋转框", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "rotated_detection", "rot");
  await gotoWorkbench(page, taskId);

  // 切到旋转框工具（快捷键 3/r）
  await page.keyboard.press("r");

  const img = await imageBox(page);
  const p1 = { x: img.x + img.width * 0.3, y: img.y + img.height * 0.3 };
  const p2 = { x: img.x + img.width * 0.7, y: img.y + img.height * 0.3 };
  const p3 = { x: img.x + img.width * 0.5, y: img.y + img.height * 0.7 };
  await page.mouse.click(p1.x, p1.y);
  await page.mouse.click(p2.x, p2.y);
  await page.mouse.click(p3.x, p3.y);

  await expectAnnotation(page);
});
