import { test, expect, type Page } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：3D 目标检测（cuboid）创建流程 —— 经工具栏切到 cuboid 工具，
// 用「4 步」画框（p1 边起点 → p2 边终点 → p3 垂直方向点定底面 → 向上拖出高度），
// 生成标注后通过面板编辑深度，验证顶面高度同步与标注存在。

test("cuboid 4 步拖底部旋转矩形加高度生成标注并编辑深度", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "cuboid", "cuboid", [
    { id: 1, name: "车", color: "#f56c6c" },
  ]);
  await gotoWorkbench(page, taskId);

  // 经工具栏按钮切到 3D 目标检测工具
  await page.locator(".tool-btn", { hasText: "3D 目标检测" }).click();
  await page.waitForTimeout(200);

  const img = await imageBox(page);
  // 三步定底面：p1(边起点) → p2(边终点) → p3(垂直方向点)
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.waitForTimeout(250);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.waitForTimeout(250);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);
  await page.waitForTimeout(250);
  // 第 4 步：向上移动拖出高度并点击生成
  await page.mouse.move(img.x + img.width * 0.5, img.y + img.height * 0.25, { steps: 8 });
  await page.waitForTimeout(150);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.25);

  // 生成后画面出现标注
  await expectAnnotation(page);

  // 切到「选择」工具后点击底面中心以选中标注（绘制工具下点击会继续绘制），
  // 读取顶面首个顶点 y（当前高度位置）
  await page.locator(".tool-btn", { hasText: "选择" }).click();
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.45);
  const topYBefore = await topFirstY(page);
  expect(topYBefore).not.toBeNull();

  // 拖动蓝色「高度手柄」向上，顶面应被整体顶起（top_cy 增大 → 顶面首点 y 变小）
  const h = await page.locator("[data-handle='cuboid-h']").first().boundingBox();
  expect(h).not.toBeNull();
  await page.mouse.move(h!.x + h!.width / 2, h!.y + h!.height / 2);
  await page.mouse.down();
  await page.mouse.move(h!.x + h!.width / 2, h!.y + h!.height / 2 - 120, { steps: 12 });
  await page.mouse.up();

  // 断言编辑真正生效：顶面首个顶点 y 变小（顶面向上移动）
  await expect.poll(async () => topFirstY(page)).toBeLessThan(topYBefore as number);

  // 保存后断言标注仍存在
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});

/**
 * 读取 cuboid 标注顶面多边形（该 plugin 画布 [data-ann-id] 下 data-role="top" 的 <polygon>，即 topPoints）
 * 的首个顶点 y 值。top_cy 越大，顶面越靠上（y 越小），故可用该值证明深度编辑真正同步到画面。
 */
async function topFirstY(page: Page): Promise<number | null> {
  const pts = await page
    .locator(".ann-svg [data-ann-id] polygon[data-role='top']")
    .first()
    .getAttribute("points");
  if (!pts) return null;
  const [x, y] = pts.trim().split(/\s+/)[0].split(",").map(Number);
  return Number.isFinite(y) ? y : null;
}
