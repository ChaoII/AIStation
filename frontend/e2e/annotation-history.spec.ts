import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const PNG = readFileSync(fileURLToPath(new URL("./fixtures/test-image.jpg", import.meta.url)));

test("工作台可打开标注历史抽屉", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const name = `hist-${Date.now()}`;
  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  const dsId = (await dsRes.json()).data.id;

  const upRes = await request.post(`${API}/annotation/dataset/${dsId}/upload`, {
    headers: auth,
    multipart: { files: { name: "test-image.jpg", mimeType: "image/jpeg", buffer: PNG } },
  });
  expect(upRes.ok()).toBeTruthy();

  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "detection" },
    headers: auth,
  });
  const taskId = (await taskRes.json()).data.id;

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });

  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 15_000 });

  const btn = page.getByRole("button", { name: "历史" }).first();
  await btn.waitFor({ state: "visible", timeout: 10_000 });
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
  await expect(page.locator(".el-drawer:visible").getByText("标注历史")).toBeVisible();
});
