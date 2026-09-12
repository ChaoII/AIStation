import { test, expect } from "@playwright/test";

// 回归护栏：进入标注工作台后，首图必须自动加载渲染（历史 bug：store.images 赋值后
// currentImage 已为真，导致首图永不加载，画布停留在 “No image loaded”）。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d4948445200000010000000100806000000" +
    "1ff3ff610000001d4944415478da63fccfc0f01f8a1930e2d4a8016206" +
    "8c38b5e8d40300b7c02f9c1b3b5c0000000049454e44ae426082",
  "hex"
);

test("工作台首图自动加载", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const name = `wb-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const ds = await dsRes.json();
  const dsId = ds.data.id;

  const upRes = await request.post(`${API}/annotation/dataset/${dsId}/upload`, {
    headers: auth,
    multipart: { files: { name: "a.png", mimeType: "image/png", buffer: PNG } },
  });
  expect(upRes.ok()).toBeTruthy();

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "detection" },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const task = await taskRes.json();
  const taskId = task.data.id;

  // 关闭首次登录引导 tour，避免遮罩层干扰
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });

  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  // 首图应自动加载：不出现 “No image loaded”，且 SVG 画布与图片均可见
  await expect(page.locator("text=No image loaded")).toHaveCount(0);
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("img.ann-img").first()).toBeVisible({ timeout: 15_000 });
});
