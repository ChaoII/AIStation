import { test, expect } from "@playwright/test";
import {
  login,
  createVideoDetectionTask,
  gotoVideoWorkbench,
  videoBox,
  expectAnnotation,
} from "./anno-helper";

// 回归护栏：视频帧级检测（video_detection）端到端流程 —— 上传视频建任务 →
// 进入工作台（<video> 加载 + 帧导航控制条出现）→ 逐帧画框 → 保存 → 跨帧验证持久化。

test("video_detection 逐帧画框并保存", async ({ page, request }) => {
  const auth = await login(request);
  const { taskId } = await createVideoDetectionTask(request, auth, "vid");

  await gotoVideoWorkbench(page, taskId);

  // 切换到框选工具（box / 检测工具）
  await page.keyboard.press("b");

  // 在第 0 帧画一个检测框（鼠标拖拽，坐标落在实际视频画面内）
  const v = await videoBox(page);
  const x1 = v.x + v.width * 0.3;
  const y1 = v.y + v.height * 0.3;
  const x2 = v.x + v.width * 0.7;
  const y2 = v.y + v.height * 0.7;
  await page.mouse.move(x1, y1);
  await page.mouse.down();
  await page.mouse.move(x2, y2, { steps: 8 });
  await page.mouse.up();

  // 画布应出现标注
  await expectAnnotation(page);

  // 保存
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".unsaved-dot")).toHaveCount(0, { timeout: 10_000 });

  // 帧导航：下一步 → 帧文本变 1；再回退到第 0 帧 → 标注应从后端重新加载（持久化验证）
  const frameText = page.locator(".video-player-bar .vp-frame-text");
  const frameCount = (await frameText.textContent())?.trim().split("/")[1]?.trim() || "0";

  await page.locator(".video-player-bar button").nth(2).click();
  await expect(frameText).toContainText(`1 / ${frameCount}`, { timeout: 10_000 });

  await page.locator(".video-player-bar button").nth(0).click();
  await expect(frameText).toContainText(`0 / ${frameCount}`, { timeout: 10_000 });
  await expectAnnotation(page);
});
