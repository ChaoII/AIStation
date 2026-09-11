import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

// 回归护栏：模型仓库「编辑」提交历史上会同时弹「页面 toast(模型已更新) + 拦截器 toast」两个提示。
// 页面 toast 已移除，本用例断言：编辑后页面恰好只有 1 个 .el-message。
// 若页面 toast 被重新加回，则会出现 2 个，用例失败。
test("编辑模型仓库仅弹出一个成功提示", async ({ page, request }) => {
  // 1) 登录拿 token（dev 关闭验证码）
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2) 通过 API 预置一个模型仓库（POST /train/model/repos 会同时创建首个版本行，
  //    该版本行即 /train/model/list 中展示、可编辑的记录）
  const name = `e2e-toast-${Date.now()}`;
  const created = await request.post(`${API}/train/model/repos`, {
    data: { name, framework: "ultralytics" },
    headers: auth,
  });
  expect(created.ok()).toBeTruthy();

  // 3) UI 打开模型仓库页（关闭首次登录引导 tour，避免遮罩层拦截点击）
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/train/repo", { waitUntil: "domcontentloaded" });

  // 用搜索框缩小范围，确保新仓库一定在列表当前页
  const searchInput = page.getByPlaceholder("请输入模型名称");
  await expect(searchInput).toBeVisible({ timeout: 15_000 });
  await searchInput.fill(name);
  await page.locator("form").getByRole("button", { name: "搜索" }).click();

  // 4) 打开目标行的「编辑」弹窗
  const row = page.locator(`tr:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: "编辑" }).click();

  const dialog = page.locator(".el-dialog").filter({ hasText: "编辑模型" });
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  // 修改一个字段后提交
  const updatedDesc = `e2e-updated-${Date.now()}`;
  await dialog.getByPlaceholder("模型描述（可选）").fill(updatedDesc);
  await dialog.getByRole("button", { name: "保存" }).click();

  // 5) 必须出现成功提示：若 PUT 失败只会出现 error 提示，
  //    此断言会失败（避免原用例“失败也恰好 1 个 toast”的假通过）
  await expect(page.locator(".el-message--success")).toHaveCount(1, { timeout: 10_000 });

  // 6) 断言仅一个 el-message（重复 toast 回归时这里会 > 1）
  await expect(page.locator(".el-message")).toHaveCount(1, { timeout: 10_000 });

  // 7) 落库校验：编辑请求失败时不会持久化，行内描述仍是旧值
  const list = await request.get(`${API}/train/model/list`, {
    params: { name },
    headers: auth,
  });
  expect(list.ok()).toBeTruthy();
  const edited = ((await list.json()).data.items as Array<{ name: string; description: string }>).find(
    (it) => it.name === name
  );
  expect(edited?.description).toBe(updatedDesc);
});
