import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：折线（开放点串，逐点 + 双击结束）创建流程。

test("polyline 画开放折线生成标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "polyline", "poly", [
    { id: 1, name: "车道", color: "#409eff" },
  ]);
  await gotoWorkbench(page, taskId);

  // 经工具栏按钮切到折线工具（点击文本为「折线」的 tool-btn）
  await page.locator(".tool-btn", { hasText: "折线" }).click();

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.6, img.y + img.height * 0.5);
  await page.mouse.click(img.x + img.width * 0.4, img.y + img.height * 0.7);
  // 双击结束（至少 3 个点）
  await page.mouse.dblclick(img.x + img.width * 0.5, img.y + img.height * 0.4);

  await expectAnnotation(page);
});
