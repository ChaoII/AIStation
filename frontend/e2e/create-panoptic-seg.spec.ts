import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：全景分割（thing 多边形 + stuff 填充背景）创建流程。

test("panoptic_segmentation 画多边形 + 填充背景生成标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "panoptic_segmentation", "panoptic", [
    { id: 1, name: "车", color: "#409eff", is_instance: true },
    { id: 2, name: "路面", color: "#909399", is_instance: false },
  ]);
  await gotoWorkbench(page, taskId);

  // 经工具栏按钮切到全景分割工具
  await page.locator(".tool-btn", { hasText: "全景分割" }).click();

  const img = await imageBox(page);
  const p1 = { x: img.x + img.width * 0.3, y: img.y + img.height * 0.3 };
  const p2 = { x: img.x + img.width * 0.7, y: img.y + img.height * 0.3 };
  const p3 = { x: img.x + img.width * 0.5, y: img.y + img.height * 0.6 };
  await page.mouse.click(p1.x, p1.y);
  await page.mouse.click(p2.x, p2.y);
  await page.mouse.click(p3.x, p3.y);
  // 点击首点闭合
  await page.mouse.click(p1.x, p1.y);

  await expectAnnotation(page);

  // 选择背景类别并填充
  await page.locator(".seg-panel .el-select").click();
  await page.getByRole("option", { name: "路面" }).click();
  const fillBtn = page.locator(".seg-panel button", { hasText: "填充背景" });
  await fillBtn.click();
  await page.locator(".el-message-box").getByRole("button", { name: "填充" }).click();
  await expect(page.locator(".el-message-box")).toHaveCount(0);

  // 保存后断言存在两条标注（thing 多边形 + stuff 背景）
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
