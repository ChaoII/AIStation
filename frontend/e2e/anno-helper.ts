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
// 文本 NER 测试用中文 fixture（多句，每行一句，供实体/关系标注与「同一句」校验）。
const TEXT = readFileSync(fileURLToPath(new URL("./fixtures/sample.txt", import.meta.url)), "utf-8");
// 音频事件 e2e 用测试音频（2s / 16kHz 单声道 wav，由 ffmpeg 生成），供上传与波形加载校验。
const AUDIO = readFileSync(fileURLToPath(new URL("./fixtures/test-audio.wav", import.meta.url)));
// 时间序列事件 e2e 用测试 CSV（timestamp + value 双列数值序列），供上传与折线图渲染校验。
const SERIES = readFileSync(fileURLToPath(new URL("./fixtures/test-series.csv", import.meta.url)));

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

// ==== 文本 NER 标注专用步骤 ====

/** 向指定数据集上传测试文本文档（multipart，字段名 file）。返回后端文档元数据。 */
export async function uploadTestDocument(
  request: APIRequestContext,
  auth: Record<string, string>,
  datasetId: number
) {
  const upRes = await request.post(`${API}/annotation/document/upload?dataset_id=${datasetId}`, {
    headers: auth,
    multipart: { file: { name: "sample.txt", mimeType: "text/plain", buffer: TEXT } },
  });
  expect(upRes.ok()).toBeTruthy();
  return (await upRes.json()).data;
}

/**
 * 创建含一个测试文本文档的 text_ner 标注任务。
 * `classes` 为 `{ entities, relations }` 字典形状（实体/关系类型配置），与后端 text_ner 约定一致。
 *
 * 注意：后端 `task/create` 与 `task/update` 的 `classes` 字段目前仍为 `list[dict]`，
 * 尚无法通过标准任务接口注入 text_ner 所需的 `{entities, relations}` 字典（见
 * `backend/tests/test_text_ner_annotation.py`「直接插入，避免依赖前端任务创建表单的
 * classes 结构注入」注释）。因此该 helper 面向后端补齐该能力后的真实端到端场景；
 * 当前工作台 e2e 走前端路由隔离（mock），不依赖它。
 */
export async function createTextNerTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  prefix: string,
  classes: { entities: any[]; relations: any[] }
): Promise<number> {
  const name = `${prefix}-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  await uploadTestDocument(request, auth, dsId);

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "text_ner", classes },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  return Number((await taskRes.json()).data.id);
}

/** 进入文本 NER 工作台：等待 CodeMirror 只读编辑器挂载（全文就绪）。 */
export async function gotoTextNerWorkbench(page: Page, taskId: number) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".text-ner-canvas .cm-editor").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".text-ner-canvas .cm-content .cm-line").first()).toBeVisible();
  await expect(page.locator(".text-ner-bar")).toBeVisible();
}

/**
 * 在指定文本行上按文字外接矩形百分比拖选一段文字。
 * 中文文本实际宽度远窄于 `.cm-line` 整行盒，故用 Range 量测该行文字矩形再按宽度定位，
 * 避免按行盒百分比拖到文字右侧空白导致选区坍缩成光标。
 */
export async function dragSelectText(page: Page, lineIdx: number, fromFrac: number, toFrac: number) {
  const editor = page.locator(".text-ner-canvas .cm-editor .cm-content");
  const line = editor.locator(".cm-line").nth(lineIdx);
  await line.scrollIntoViewIfNeeded();
  const textRect = await line.evaluate((el) => {
    const r = document.createRange();
    r.selectNodeContents(el);
    const rect = r.getBoundingClientRect();
    return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
  });
  const y = textRect.y + textRect.h / 2;
  await page.mouse.move(textRect.x + textRect.w * fromFrac, y);
  await page.mouse.down();
  await page.mouse.move(textRect.x + textRect.w * toFrac, y, { steps: 20 });
  await page.mouse.up();
}

/** 从当前打开的 Element Plus 下拉中按可见文本选中一项，避免把点击落到隐藏的重复悬浮层。 */
export async function pickSelectOption(
  page: Page,
  selectLocator: any,
  optionText: string
) {
  const opt = page
    .locator(".el-select-dropdown__item", { hasText: optionText })
    .filter({ visible: true })
    .first();
  // 若下拉尚未展开，先点击展开；已展开则直接点击选项（避免二次点击把下拉又收起）。
  if (!(await opt.isVisible())) {
    await selectLocator.click();
  }
  await expect(opt).toBeVisible({ timeout: 6_000 });
  await opt.click();
}

/** 拖选一段文字后在「选择实体类型」弹窗中指定实体类型并确认。 */
export async function selectTextEntity(
  page: Page,
  lineIdx: number,
  fromFrac: number,
  toFrac: number,
  typeName: string
) {
  const before = await page.locator("[data-entity-id]").count();
  await dragSelectText(page, lineIdx, fromFrac, toFrac);
  const dialog = page.locator(".el-dialog", { hasText: "选择实体类型" });
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await pickSelectOption(page, dialog.locator(".el-select"), typeName);
  await dialog.locator("button", { hasText: "确定" }).click();
  await expect(page.locator("[data-entity-id]")).toHaveCount(before + 1, { timeout: 10_000 });
  // 等待弹窗遮罩完全移除，避免吞掉下一次拖选的 mousedown
  await expect(dialog).toBeHidden();
}

/** 读取右侧实体面板中当前所有实体的文本（按出现顺序）。 */
export async function readEntityTexts(page: Page): Promise<string[]> {
  return page
    .locator(".text-ner-bar .titem .titem-text")
    .evaluateAll((els) => els.map((e) => (e.textContent ?? "").trim()));
}

/** 在「新建关系」弹窗中选择起点/终点实体与关系类型并创建。 */
export async function createTextRelation(
  page: Page,
  fromText: string,
  toText: string,
  relationType: string
) {
  await page.locator(".text-ner-bar").getByRole("button", { name: /新建/ }).click();
  const relDialog = page.locator(".el-dialog", { hasText: "新建关系" });
  await expect(relDialog).toBeVisible({ timeout: 10_000 });
  const items = relDialog.locator(".el-form-item");
  await pickSelectOption(page, items.nth(0).locator(".el-select"), fromText);
  await pickSelectOption(page, items.nth(1).locator(".el-select"), toText);
  await pickSelectOption(page, items.nth(2).locator(".el-select"), relationType);
  await relDialog.locator("button", { hasText: "创建关系" }).click();
  await expect(relDialog).toBeHidden();
}

// ==== 音频事件（audio_event）标注专用步骤 ====

/** 向指定数据集上传测试音频（multipart，字段名 file）。返回后端 audio 元数据。 */
export async function uploadTestAudio(
  request: APIRequestContext,
  auth: Record<string, string>,
  datasetId: number
) {
  const upRes = await request.post(`${API}/annotation/audio/upload?dataset_id=${datasetId}`, {
    headers: auth,
    multipart: { file: { name: "test-audio.wav", mimeType: "audio/wav", buffer: AUDIO } },
  });
  expect(upRes.ok()).toBeTruthy();
  return (await upRes.json()).data;
}

/**
 * 创建含一个测试音频的 audio_event 标注任务。
 * `classes` 为事件类别列表（每项 `{id, name, color}`），与后端 audio_event 约定一致。
 * 返回 { taskId, audioId, datasetId }。
 */
export async function createAudioEventTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  prefix: string,
  classes: any[] = []
): Promise<{ taskId: number; audioId: number; datasetId: number }> {
  const name = `${prefix}-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  const audio = await uploadTestAudio(request, auth, dsId);

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "audio_event", classes },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const taskId = (await taskRes.json()).data.id;
  return { taskId: Number(taskId), audioId: audio.id, datasetId: dsId };
}

/** 进入音频事件工作台：等待波形容器与事件面板挂载，并确认波形已解码（时间控件显示非 0 总时长）。 */
export async function gotoAudioWorkbench(page: Page, taskId: number) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".audio-timeline-canvas__waveform").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".audio-event-panel").first()).toBeVisible({ timeout: 20_000 });
  // 波形就绪后时间控件会显示 `0:00 / 0:02`（总时长已解码），据此确认可拖选区间。
  await expect(page.locator(".audio-timeline-canvas__time")).toContainText("/ 0:02", { timeout: 20_000 });
}

/** 在波形时间轴上按宽度百分比拖选一段区间，触发「新建事件片段」弹窗。 */
export async function createAudioSegment(page: Page, fromFrac: number, toFrac: number) {
  const wf = await page.locator(".audio-timeline-canvas__waveform").first().boundingBox();
  expect(wf).not.toBeNull();
  const y = wf!.y + wf!.height / 2;
  await page.mouse.move(wf!.x + wf!.width * fromFrac, y, { steps: 5 });
  await page.mouse.down();
  await page.mouse.move(wf!.x + wf!.width * toFrac, y, { steps: 20 });
  await page.mouse.up();
}

/** 在当前可见的音频事件弹窗中按类别名选择事件类别。 */
export async function selectAudioLabel(page: Page, labelName: string) {
  const dialog = page.locator(".el-dialog", { hasText: /事件片段/ }).filter({ visible: true }).first();
  await pickSelectOption(page, dialog.locator(".el-select"), labelName);
}

// ==== 时间序列事件（time_series_event）标注专用步骤 ====

/** 向指定数据集上传测试 CSV（multipart，字段名 file）。返回后端 time series 元数据。 */
export async function uploadTimeSeriesCsv(
  request: APIRequestContext,
  auth: Record<string, string>,
  datasetId: number
) {
  const upRes = await request.post(`${API}/annotation/timeseries/upload?dataset_id=${datasetId}`, {
    headers: auth,
    multipart: { file: { name: "test-series.csv", mimeType: "text/csv", buffer: SERIES } },
  });
  expect(upRes.ok()).toBeTruthy();
  return (await upRes.json()).data;
}

/**
 * 创建含一个测试 CSV 的 time_series_event 标注任务。
 * `classes` 为事件类别列表（每项 `{id, name, color}`），与后端 time_series_event 约定一致。
 * 返回 { taskId, seriesId, datasetId }。
 */
export async function createTimeSeriesEventTask(
  request: APIRequestContext,
  auth: Record<string, string>,
  prefix: string,
  classes: any[] = []
): Promise<{ taskId: number; seriesId: number; datasetId: number }> {
  const name = `${prefix}-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  const series = await uploadTimeSeriesCsv(request, auth, dsId);

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "time_series_event", classes },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const taskId = (await taskRes.json()).data.id;
  return { taskId: Number(taskId), seriesId: series.id, datasetId: dsId };
}

/** 进入时间序列事件工作台：等待 echarts 折线图容器与事件面板挂载，并确认已渲染数据点。 */
export async function gotoTimeSeriesWorkbench(page: Page, taskId: number) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".time-series-canvas__chart").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".time-series-panel").first()).toBeVisible({ timeout: 20_000 });
  // 面板元数据显示行数（CSV 21 行数据行），确认序列已加载可拖选。
  await expect(page.locator(".tsp-meta-item", { hasText: "行数" })).toContainText("21", {
    timeout: 20_000,
  });
}

/**
 * 在折线图网格区按水平百分比拖选一段区间，触发「新建事件区间」弹窗。
 * 拖选落在网格竖向中部并横跨一段宽度，避开底部 dataZoom 滑条与上下轴边距，
 * 确保 convertFromPixel 能映射到序列时间值（start<end）。
 */
export async function createTimeSeriesSegment(page: Page, fromFrac: number, toFrac: number) {
  const chart = await page.locator(".time-series-canvas__chart").first().boundingBox();
  expect(chart).not.toBeNull();
  const y = chart!.y + chart!.height * 0.5;
  await page.mouse.move(chart!.x + chart!.width * fromFrac, y, { steps: 5 });
  await page.mouse.down();
  await page.mouse.move(chart!.x + chart!.width * toFrac, y, { steps: 20 });
  await page.mouse.up();
}

/** 在当前可见的时间序列事件弹窗中按类别名选择事件类别。 */
export async function selectTimeSeriesLabel(page: Page, labelName: string) {
  const dialog = page.locator(".el-dialog", { hasText: /事件区间/ }).filter({ visible: true }).first();
  await pickSelectOption(page, dialog.locator(".el-select"), labelName);
}
