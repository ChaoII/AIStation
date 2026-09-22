import { readFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
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
// 说明：wavesurfer 通过 fetch 加载 presigned play_url 解码波形，对象存储（RustFS/S3）对前端源
// 未开 CORS 会阻止解码。本用例以「同源音频地址 + 拦截返回测试 wav」的方式绕过（前端路由隔离，
// 见 AGENTS.md / Task 9 约定）；annotation 读写接口不做 mock，保存/读取仍走真实后端以验证持久化。

// 测试音频（2s / 16kHz 单声道 wav），由 anno-helper 中的 AUDIO 常量读取，此处用于拦截 play_url 响应。
const AUDIO = readFileSync(fileURLToPath(new URL("./fixtures/test-audio.wav", import.meta.url)));

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

  // 拦截 play-url 端点返回同源音频地址，并拦截该地址提供测试 wav 内容，规避对象存储 CORS。
  const playPath = `/e2e-audio-${Date.now()}.wav`;
  await page.route("**/api/v1/annotation/audio/play-url/*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "ok", data: { play_url: playPath } }),
    })
  );
  await page.route(`**${playPath}`, (route) =>
    route.fulfill({
      contentType: "audio/wav",
      headers: { "Access-Control-Allow-Origin": "*" },
      body: AUDIO,
    })
  );

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
