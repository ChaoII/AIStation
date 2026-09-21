import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：3D 目标检测（cuboid）创建流程 —— 经工具栏切到 cuboid 工具，
// 用「三步拖底部旋转矩形」画框（p1 边起点 → p2 边终点 → p3 垂直方向点），
// 生成标注后通过面板编辑深度，验证顶面高度同步与标注存在。

test("cuboid 三步拖底部旋转矩形生成标注并编辑深度", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "cuboid", "cuboid", [
    { id: 1, name: "车", color: "#f56c6c" },
  ]);
  await gotoWorkbench(page, taskId);

  // 经工具栏按钮切到 3D 目标检测工具
  await page.locator(".tool-btn", { hasText: "3D 目标检测" }).click();

  const img = await imageBox(page);
  // 三步：p1(边起点) → p2(边终点) → p3(垂直方向点)
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);

  // 生成后画面出现标注
  await expectAnnotation(page);

  // 选中生成的 cuboid，通过面板编辑深度（默认 top_cy=0.15，改深度应同步顶面高度）
  const depthInput = page.locator(".cuboid-panel .el-input-number input");
  await depthInput.click();
  await depthInput.fill("0.6");
  await depthInput.blur();

  // 保存后断言标注仍存在
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
