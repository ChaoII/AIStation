import { expect, type Page, type APIRequestContext } from "@playwright/test";

// 创建流程 e2e 公共步骤：登录 → 建数据集 → 上传 16x16 PNG → 建任务 → 进入标注工作台。
// 供各 create-*.spec.ts 复用，避免重复的“造数据 + 进工作台”样板。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
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
  prefix: string
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
    data: { dataset_id: dsId, name: `t-${name}`, task_type: taskType },
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
