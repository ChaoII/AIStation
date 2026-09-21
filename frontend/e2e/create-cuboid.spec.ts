import { test, expect, type Page } from "@playwright/test";
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

  // 编辑深度前，先读取顶面首个顶点 y（top_cy 默认 0.15 时的高度位置）
  const topYBefore = await topFirstY(page);
  expect(topYBefore).not.toBeNull();

  // 选中生成的 cuboid，通过面板编辑深度（默认 top_cy=0.15，改深度应同步顶面高度）
  const depthInput = page.locator(".cuboid-panel .el-input-number input");
  await depthInput.click();
  await depthInput.fill("0.6");
  await depthInput.blur();

  // 断言编辑真正生效：applyDepth 会把 top_cy 同步为 depth(0.6)，顶面被整体顶起，
  // 表现为顶面首个顶点 y 变小（顶面向上移动）。仅测“输入框可交互”无法证明同步，故改测可视效果。
  await expect.poll(async () => topFirstY(page)).toBeLessThan(topYBefore as number);

  // 保存后断言标注仍存在
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});

/**
 * 读取 cuboid 标注顶面多边形（该 plugin 画布 [data-ann-id] 下的第一个 <polygon>，即 topPoints）
 * 的首个顶点 y 值。top_cy 越大，顶面越靠上（y 越小），故可用该值证明深度编辑真正同步到画面。
 */
async function topFirstY(page: Page): Promise<number | null> {
  const pts = await page
    .locator(".ann-svg [data-ann-id] polygon")
    .first()
    .getAttribute("points");
  if (!pts) return null;
  const [x, y] = pts.trim().split(/\s+/)[0].split(",").map(Number);
  return Number.isFinite(y) ? y : null;
}
