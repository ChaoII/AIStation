import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

test("删除数据集仅弹出一个成功提示", async ({ page, request }) => {
  // 1) 登录拿 token（dev 关闭验证码）
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2) 通过 API 预置一个数据集（不经过 UI，避免产生 toast）
  const name = `e2e-toast-${Date.now()}`;
  const created = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(created.ok()).toBeTruthy();

  // 3) UI 打开数据集页，搜索并删除
  // 页面有轮询/长连接，networkidle 可能永不满足，用 domcontentloaded
  // 首次登录会弹出引导 tour，覆盖层会拦截点击——进入前先关闭引导
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });

  // 搜索框缩小范围，避免新数据不在当前页
  const searchInput = page.getByPlaceholder("请输入数据集名称");
  await expect(searchInput).toBeVisible({ timeout: 15_000 });
  await searchInput.fill(name);
  await page.locator("form").getByRole("button", { name: "搜索" }).click();

  const row = page.locator(`tr:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: /删除/ }).click();

  // 确认弹窗（PageContent 默认确认按钮文案为“确定”）
  await page.getByRole("button", { name: "确定" }).click();

  // 4) 断言仅一个 el-message（重复 toast 回归时这里会 > 1）
  await expect(page.locator(".el-message")).toHaveCount(1, { timeout: 10_000 });
});
