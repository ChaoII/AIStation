import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：OCR 矩形（两次点击对角 + 输入文本确认）创建流程。

test("ocr 两次点击对角并确认文本生成 OCR 标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "ocr", "ocr");
  await gotoWorkbench(page, taskId);

  // 切到 OCR 工具（快捷键 6/o），默认矩形模式
  await page.keyboard.press("o");

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.7);

  // 矩形区域创建后弹出 OCR 文本输入框
  const ocrInput = page.getByPlaceholder("OCR 文本");
  await expect(ocrInput).toBeVisible({ timeout: 10_000 });
  await ocrInput.fill("hello");
  await page.getByRole("button", { name: "确定" }).click();

  await expectAnnotation(page);
});
