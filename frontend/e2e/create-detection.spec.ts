import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 回归护栏：检测（detection）绘制流程下沉到插件 tool 后，仍能
// “切换框选工具 → 拖拽 → 生成标注并可拖动”。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const PNG = readFileSync(fileURLToPath(new URL("./fixtures/test-image.jpg", import.meta.url)));

test("detection 框选拖拽生成标注", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const name = `det-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const dsId = (await dsRes.json()).data.id;

  const upRes = await request.post(`${API}/annotation/dataset/${dsId}/upload`, {
    headers: auth,
    multipart: { files: { name: "test-image.jpg", mimeType: "image/jpeg", buffer: PNG } },
  });
  expect(upRes.ok()).toBeTruthy();

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: {
      dataset_id: dsId,
      name: `t-${name}`,
      task_type: "detection",
      classes: [{ id: 1, name: "默认", color: "#409eff" }],
    },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const taskId = (await taskRes.json()).data.id;

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });

  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("img.ann-img").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("text=No image loaded")).toHaveCount(0);

  // 切换到框选（box / 检测工具）
  await page.keyboard.press("b");

  // 图像仅数十像素（16x16 缩略图放大渲染），须在实际图像区域内拖拽，
  // 否则归一化坐标溢出 [0,1] 会被 create() 拒绝。
  const img = await page.locator("img.ann-img").first().boundingBox();
  expect(img).not.toBeNull();
  const x1 = img!.x + img!.width * 0.3;
  const y1 = img!.y + img!.height * 0.3;
  const x2 = img!.x + img!.width * 0.7;
  const y2 = img!.y + img!.height * 0.7;
  await page.mouse.move(x1, y1);
  await page.mouse.down();
  await page.mouse.move(x2, y2, { steps: 8 });
  await page.mouse.up();

  // 标注应被创建（画布出现带 data-ann-id 的标注组）
  await expect(page.locator(".ann-svg [data-ann-id]").first()).toBeVisible({ timeout: 10_000 });
});
