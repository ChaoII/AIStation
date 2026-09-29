import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 画笔自由描画 → 松手转 Polygon → 保存 流程。

test("画笔自由描画生成多边形标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  // 切到「涂抹」工具（画笔的涂抹模式）
  await page.locator(".tool-btn", { hasText: "涂抹" }).click();

  const img = await imageBox(page);
  // 按住拖动画一笔（mouse down → move → up）
  await page.mouse.move(img.x + img.width * 0.35, img.y + img.height * 0.35);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) {
    await page.mouse.move(
      img.x + img.width * (0.35 + i * 0.03),
      img.y + img.height * (0.35 + Math.sin(i / 2) * 0.05)
    );
  }
  await page.mouse.up();

  await expectAnnotation(page);
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
