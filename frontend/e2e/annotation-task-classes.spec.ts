import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

// 回归护栏：后端 classes 可能是字典形态（{"classes":[...]} 或 id 键字典），
// 编辑时若直接丢弃会清空类别定义。用例拦截 detail 返回字典形态，
// 断言弹窗能渲染出类别，且保存请求体里 classes 已归一化为数组。
test("编辑任务：字典形态 classes 归一化后保存不丢类别", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const dsRes = await request.post(`${API}/annotation/dataset/create`, {
    data: { name: `cls-ds-${Date.now()}` },
    headers: auth,
  });
  expect(dsRes.ok()).toBeTruthy();
  const datasetId = (await dsRes.json()).data.id;

  const name = `cls-task-${Date.now()}`;
  const taskRes = await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: datasetId, name, task_type: "detection", classes: [] },
    headers: auth,
  });
  expect(taskRes.ok()).toBeTruthy();
  const real = (await taskRes.json()).data;

  // detail 返回字典形态 classes（对象定义 + 纯字符串两种键值）
  await page.route("**/api/v1/annotation/task/*/detail", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        code: 0,
        msg: "success",
        data: {
          ...real,
          classes: { "0": { name: "dog", color: "#67c23a" }, "1": "bird" },
        },
      }),
    });
  });

  // 捕获保存请求体，验证 classes 归一化为数组
  let savedClasses: any[] | undefined;
  await page.route("**/api/v1/annotation/task/update/*", async (route) => {
    savedClasses = route.request().postDataJSON()?.classes;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "更新成功", data: {} }),
    });
  });

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/annotation/task", { waitUntil: "domcontentloaded" });

  const searchInput = page.getByPlaceholder("请输入任务名称");
  await expect(searchInput).toBeVisible({ timeout: 15_000 });
  await searchInput.fill(name);
  await page.locator("form").getByRole("button", { name: "搜索" }).click();

  const row = page.locator(`tr:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: "编辑" }).click();

  const dialog = page.locator(".el-dialog").filter({ hasText: "编辑任务" });
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await expect(dialog.locator(".el-tag", { hasText: "dog" })).toBeVisible();
  await expect(dialog.locator(".el-tag", { hasText: "bird" })).toBeVisible();

  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".el-message--success")).toHaveCount(1, { timeout: 10_000 });
  expect(Array.isArray(savedClasses)).toBeTruthy();
  expect(savedClasses?.map((c) => c.name).sort()).toEqual(["bird", "dog"]);
});

// 回归护栏：新增任务弹窗添加类别并关闭后，再次打开必须是空类别列表。
// 历史 bug：resetForm 里 Object.assign 让 formData.classes 与初始对象共享同一数组引用，
// handleAddClass 的 push 会把共享数组写脏，导致之后每次「新增」都带出残留类别。
test("新增任务：关闭后重开弹窗类别列表为空", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/annotation/task", { waitUntil: "domcontentloaded" });

  const addBtn = page.getByRole("button", { name: "新增" });
  await expect(addBtn).toBeVisible({ timeout: 15_000 });

  const dialog = page.locator(".el-dialog").filter({ hasText: "新增任务" });
  const classInput = dialog.getByPlaceholder("输入类别名称，如 person");
  const addClassBtn = dialog.getByRole("button", { name: "添加" });

  // 打开弹窗 → 添加一个类别 → 取消关闭
  async function addClassThenClose(name: string) {
    await addBtn.click();
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await classInput.fill(name);
    await addClassBtn.click();
    await expect(dialog.locator(".el-tag", { hasText: name })).toBeVisible();
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  }

  // 第一次关闭会把 formData.classes 与初始对象绑成同一引用，
  // 第二次 push 才会把共享数组写脏（复现 bug 所需）。
  await addClassThenClose("__e2e_class_a__");
  await addClassThenClose("__e2e_class_b__");

  // 第三次打开：必须没有任何残留类别
  await addBtn.click();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await expect(dialog.locator(".el-tag")).toHaveCount(0);
  await expect(dialog.getByText("暂无类别，添加后可在标注工作台使用")).toBeVisible();
});
