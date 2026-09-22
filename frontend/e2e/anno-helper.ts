import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, type Page, type APIRequestContext } from "@playwright/test";

// 创建流程 e2e 公共步骤：登录 → 建数据集 → 上传 16x16 PNG → 建任务 → 进入标注工作台。
// 供各 create-*.spec.ts 复用，避免重复的“造数据 + 进工作台”样板。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

// 视频帧级测试用的小 MP4 fixture（320x240 / 25fps / 2s ≈ 50 帧）。
const VIDEO = readFileSync(fileURLToPath(new URL("./fixtures/test.mp4", import.meta.url)));
const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d4948445200000010000000100806000000" +
    "1ff3ff610000001d4944415478da63fccfc0f01f8a1930e2d4a8016206" +
    "8c38b5e8d40300b7c02f9c1b3b5c0000000049454e44ae426082",
  "hex"
);

export async function login(request: APIRequestContext) {
  const loginRes = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const token = (await loginRes.json()).data.access_token;
  return { Authorization: `Bearer ${token}` } as Record<string, string>;
}

export async function createAnnotationTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskType: string,
  prefix: string,
  classes: any[] = []
): Promise<number> {
  const name = `${prefix}-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  const upRes = await request.post(`${API}/annotation/dataset/${dsId}/upload`, {
    headers: auth,
    multipart: { files: { name: "a.png", mimeType: "image/png", buffer: PNG } },
  });
  expect(upRes.ok()).toBeTruthy();

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: taskType, classes },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const taskId = (await taskRes.json()).data.id;
  return Number(taskId);
}

export async function gotoWorkbench(page: Page, taskId: number) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("img.ann-img").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("text=No image loaded")).toHaveCount(0);
}

/** 返回图片在页面上的可视区域包围框（用于把点击落在实际图像内，避免归一化越界） */
export async function imageBox(page: Page) {
  const img = await page.locator("img.ann-img").first().boundingBox();
  expect(img).not.toBeNull();
  return img!;
}

/** 断言画布出现至少一个标注（带 data-ann-id） */
export async function expectAnnotation(page: Page) {
  await expect(page.locator(".ann-svg [data-ann-id]").first()).toBeVisible({ timeout: 10_000 });
}

// ==== 视频帧级标注专用步骤 ====

/** 向指定数据集上传测试视频（multipart，字段名 file）。返回后端 video 元数据。 */
export async function uploadTestVideo(
  request: APIRequestContext,
  auth: Record<string, string>,
  datasetId: number
) {
  const upRes = await request.post(`${API}/annotation/video/upload?dataset_id=${datasetId}`, {
    headers: auth,
    multipart: { file: { name: "test.mp4", mimeType: "video/mp4", buffer: VIDEO } },
  });
  expect(upRes.ok()).toBeTruthy();
  return (await upRes.json()).data;
}

/** 创建含一个测试视频的 video_detection 标注任务，返回 { taskId, videoId, datasetId }。 */
export async function createVideoDetectionTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  prefix: string
): Promise<{ taskId: number; videoId: number; datasetId: number }> {
  const name = `${prefix}-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  const video = await uploadTestVideo(request, auth, dsId);

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "video_detection" },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const taskId = (await taskRes.json()).data.id;
  return { taskId: Number(taskId), videoId: video.id, datasetId: dsId };
}

/** 进入视频工作台：等待 <video> 加载且出现帧导航控制条。 */
export async function gotoVideoWorkbench(page: Page, taskId: number) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("video.ann-video").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".video-player-bar").first()).toBeVisible({ timeout: 20_000 });
  // 等待视频元数据就绪，确保 cw/ch 已有值
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 20_000 });
}

/** 返回视频元素在页面上的可视区域包围框（用于把画框点击落在实际画面内）。 */
export async function videoBox(page: Page) {
  const v = await page.locator("video.ann-video").first().boundingBox();
  expect(v).not.toBeNull();
  return v!;
}
