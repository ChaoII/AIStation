import { mkdirSync } from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

import {
  login,
  createVideoEventTask,
  gotoVideoEventWorkbench,
  createVideoEventSegment,
  selectVideoEventLabel,
} from "./anno-helper";

// 视频事件（video_event）工作台端到端：上传视频 → 建 video_event 任务 → 视频时间轴（0..duration）
// 拖选区间生成事件 → 编辑类别 → 保存 → 刷新验证持久化 → 删除二次确认。
// 说明：video_event 走 `getVideoDetail` 拿到时长后渲染纯时间轴（不播放视频），同源拉取视频元数据，
// 无音频那样跨源解码的 CORS 问题；annotation 读写接口走真实后端以验证持久化。

// 事件类别列表（与后端 video_event `classes` 约定一致）
const CLASSES = [
  { id: 1, name: "正常运行", color: "#409eff" },
  { id: 2, name: "异常", color: "#67c23a" },
];

test("video_event：时间轴拖选生成事件、编辑类别、保存与刷新持久化", async ({ page, request }) => {
  // 截图落到 gitignore 的 test-results/，避免硬编码本机路径
  const shotDir = path.resolve(process.cwd(), "test-results");
  mkdirSync(shotDir, { recursive: true });
  const shot = (name: string) => path.join(shotDir, name);

  const auth = await login(request);
  const { taskId } = await createVideoEventTask(request, auth, "ve", CLASSES);

  await gotoVideoEventWorkbench(page, taskId);

  // 1) 时间轴拖选区间生成事件 → 弹「新建事件片段」→ 选类别「正常运行」→ 确定 → 面板出现 1 个片段
  await createVideoEventSegment(page, 0.2, 0.7);
  const createDialog = page.locator(".el-dialog", { hasText: "新建事件片段" });
  await expect(createDialog).toBeVisible({ timeout: 10_000 });
  await selectVideoEventLabel(page, "正常运行");
  await createDialog.getByRole("button", { name: "确定" }).click();
  await expect(createDialog).toBeHidden();
  await expect(page.locator(".video-event-panel .vep-item")).toHaveCount(1, { timeout: 10_000 });
  await page.screenshot({ path: shot("ve-e2e-1-segment.png") });

  // 2) 编辑类别：面板编辑按钮打开「编辑事件片段」→ 改类别「异常」→ 保存 → 面板类别文案更新
  await page.locator(".video-event-panel .vep-item .vep-actions .vep-btn").first().click();
  const editDialog = page.locator(".el-dialog", { hasText: "编辑事件片段" });
  await expect(editDialog).toBeVisible({ timeout: 10_000 });
  await selectVideoEventLabel(page, "异常");
  await editDialog.getByRole("button", { name: "保存" }).click();
  await expect(editDialog).toBeHidden();
  await expect(page.locator(".video-event-panel .vep-item .vep-type")).toContainText("异常", {
    timeout: 10_000,
  });

  // 3) 保存 → 无未保存标记（unsaved-dot 归零）
  await page.locator(".ann-footer").getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".unsaved-dot")).toHaveCount(0, { timeout: 10_000 });
  await page.screenshot({ path: shot("ve-e2e-2-saved.png") });

  // 4) 刷新持久化：真实后端读取已保存片段，事件仍在且类别为「异常」
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".video-timeline-canvas .vtc-track").first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".video-event-panel .vep-item")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator(".video-event-panel .vep-item .vep-type")).toContainText("异常", {
    timeout: 15_000,
  });

  // 5) 删除二次确认：点删除 → 出确认框（含「不可恢复」提示）→ 取消保留片段
  await page.locator(".video-event-panel .vep-item .vep-actions .vep-del").first().click();
  const confirm = page.locator(".el-message-box");
  await expect(confirm).toBeVisible({ timeout: 10_000 });
  await expect(confirm).toContainText("不可恢复");
  await confirm.getByRole("button", { name: "取消" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.locator(".video-event-panel .vep-item")).toHaveCount(1);
});
