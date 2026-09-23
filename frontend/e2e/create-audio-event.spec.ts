import { mkdirSync } from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

import {
  login,
  createAudioEventTask,
  gotoAudioWorkbench,
  createAudioSegment,
  selectAudioLabel,
} from "./anno-helper";

// 音频事件（audio_event）工作台端到端：上传音频 → 建 audio_event 任务 → 波形时间轴上
// 拖选区间生成事件 → 编辑类别 → 保存 → 刷新验证持久化 → 删除二次确认。
// 说明：wavesurfer 通过 fetch 加载同源 content URL（`/api/v1/annotation/audio/content/{id}`），
// 由前端 Vite/nginx 对 `/api/v1` 的代理转发到后端（后端从对象存储 RustFS 流式回传字节），属同源，
// 无需 CORS，故本用例不再 mock 音频内容；annotation 读写接口亦走真实后端以验证持久化。

// 事件类别列表（与后端 audio_event `classes` 约定一致）
const CLASSES = [
  { id: 1, name: "广播", color: "#409eff" },
  { id: 2, name: "人声", color: "#67c23a" },
];

test("audio_event：拖选生成事件、编辑类别、保存与刷新持久化", async ({ page, request }) => {
  // 截图落到 gitignore 的 test-results/，避免硬编码本机路径
  const shotDir = path.resolve(process.cwd(), "test-results");
  mkdirSync(shotDir, { recursive: true });
  const shot = (name: string) => path.join(shotDir, name);

  const auth = await login(request);
  const { taskId } = await createAudioEventTask(request, auth, "audio", CLASSES);

  await gotoAudioWorkbench(page, taskId);

  // 1) 波形时间轴拖选区间生成事件 → 弹「新建事件片段」→ 选类别「广播」→ 确定 → 面板出现 1 个片段
  await createAudioSegment(page, 0.2, 0.6);
  const createDialog = page.locator(".el-dialog", { hasText: "新建事件片段" });
  await expect(createDialog).toBeVisible({ timeout: 10_000 });
  await selectAudioLabel(page, "广播");
  await createDialog.getByRole("button", { name: "确定" }).click();
  await expect(createDialog).toBeHidden();
  await expect(page.locator(".audio-event-panel .aep-item")).toHaveCount(1, { timeout: 10_000 });
  await page.screenshot({ path: shot("audio-e2e-1-segment.png") });

  // 2) 编辑类别：面板编辑按钮打开「编辑事件片段」→ 改类别「人声」→ 保存 → 面板类别文案更新
  await page.locator(".audio-event-panel .aep-item .aep-actions .aep-btn").first().click();
  const editDialog = page.locator(".el-dialog", { hasText: "编辑事件片段" });
  await expect(editDialog).toBeVisible({ timeout: 10_000 });
  await selectAudioLabel(page, "人声");
  await editDialog.getByRole("button", { name: "保存" }).click();
  await expect(editDialog).toBeHidden();
  await expect(page.locator(".audio-event-panel .aep-item .aep-type")).toContainText("人声", {
    timeout: 10_000,
  });

  // 3) 保存 → 无未保存标记（unsaved-dot 归零）
  await page.locator(".ann-footer").getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".unsaved-dot")).toHaveCount(0, { timeout: 10_000 });
  await page.screenshot({ path: shot("audio-e2e-2-saved.png") });

  // 4) 刷新持久化：真实后端读取已保存片段，事件仍在且类别为「人声」
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".audio-timeline-canvas__waveform").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".audio-event-panel .aep-item")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator(".audio-event-panel .aep-item .aep-type")).toContainText("人声", {
    timeout: 15_000,
  });

  // 5) 删除二次确认：点删除 → 出确认框（含「不可恢复」提示）→ 取消保留片段
  await page.locator(".audio-event-panel .aep-item .aep-actions .aep-del").first().click();
  const confirm = page.locator(".el-message-box");
  await expect(confirm).toBeVisible({ timeout: 10_000 });
  await expect(confirm).toContainText("不可恢复");
  await confirm.getByRole("button", { name: "取消" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.locator(".audio-event-panel .aep-item")).toHaveCount(1);
});
