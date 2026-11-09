/**
 * 系统管理 CRUD 冒烟：参数 / 字典 / 岗位 / 角色。
 *
 * 之前这一块**完全没有 e2e 覆盖**，而它是框架自带页面的基准（其它模块都照它抄），
 * 表单字段/按钮文案一改，别处的复制品也会跟着错。这里覆盖：
 *   搜索 → 新增（弹窗表单）→ 列表能看到 → 编辑落库 → 删除（二次确认）
 * 每个用例都用 API 兜底清理，避免 dev 库堆垃圾。
 */
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

function uniq(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

async function authOf(request: APIRequestContext) {
  const r = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(r.ok()).toBeTruthy();
  const token = (await r.json()).data.access_token;
  return { Authorization: `Bearer ${token}` };
}

async function searchName(page: Page, placeholder: string, name: string) {
  const input = page.getByPlaceholder(placeholder).first();
  await expect(input).toBeVisible({ timeout: 20_000 });
  await input.fill(name);
  await page.locator("form").getByRole("button", { name: /^(查询|搜索)$/ }).first().click();
  await page.waitForTimeout(600);
}

async function openAddDialog(page: Page) {
  await page.getByRole("button", { name: /^(新增|添加)$/ }).first().click();
  const dialog = page.locator(".el-dialog").filter({ hasNotText: "导入" }).last();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  return dialog;
}

async function submitDialog(dialog: ReturnType<Page["locator"]>) {
  await dialog.getByRole("button", { name: /^(确定|保存)$/ }).last().click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });
}

/** 按名称从列表接口拿 id，然后 DELETE（兜底清理，失败只告警） */
async function apiDeleteByName(
  request: APIRequestContext,
  headers: Record<string, string>,
  listPath: string,
  deletePath: string,
  name: string
) {
  try {
    const r = await request.get(`${API}${listPath}`, { headers, params: { name, page_no: 1, page_size: 50 } });
    if (!r.ok()) return;
    const items = (await r.json())?.data?.items || [];
    const hit = items.filter((it: any) => it.name === name).map((it: any) => it.id);
    if (hit.length) {
      await request.delete(`${API}${deletePath}`, { headers, data: hit });
    }
  } catch {
    /* 清理失败不影响主断言 */
  }
}

test("参数管理：新增 → 搜索命中 → 编辑落库 → 删除", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-param");
  const key = name.replace(/-/g, "_");
  try {
    await page.goto("/#/system/param", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });

    const dialog = await openAddDialog(page);
    await dialog.getByPlaceholder("请输入配置名称").fill(name);
    await dialog.getByPlaceholder("请输入配置键").fill(key);
    await dialog.getByPlaceholder("请输入配置值").fill("v1");
    await submitDialog(dialog);

    await searchName(page, "请输入配置名称", name);
    const row = page.locator(".el-table__row", { hasText: name }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });

    // 编辑：改值 → 保存 → 接口能读到新值
    await row.getByRole("button", { name: "编辑" }).click();
    const edit = page.locator(".el-dialog").last();
    await expect(edit).toBeVisible({ timeout: 10_000 });
    await edit.getByPlaceholder("请输入配置值").fill("v2");
    await submitDialog(edit);

    await expect
      .poll(async () => {
        const r = await request.get(`${API}/system/param/list`, {
          headers,
          params: { config_name: name, page_no: 1, page_size: 10 },
        });
        const items = (await r.json())?.data?.items || [];
        return items.find((it: any) => it.config_name === name)?.config_value;
      }, { timeout: 15_000 })
      .toBe("v2");

    // 删除：行内删除 → 二次确认（按钮文案是「删除」）
    const delRow = page.locator(".el-table__row", { hasText: name }).first();
    await delRow.getByRole("button", { name: "删除" }).click();
    const box = page.locator(".el-message-box").first();
    await expect(box).toBeVisible({ timeout: 10_000 });
    await box.locator(".el-message-box__btns").getByRole("button", { name: /^(删除|确定|确认)$/ }).last().click();
    await expect(page.locator(".el-table__row", { hasText: name })).toHaveCount(0, { timeout: 15_000 });
  } finally {
    await apiDeleteByName(request, headers, "/system/param/list", "/system/param/delete", name);
  }
});

test("字典管理：新增字典类型并能被搜索到", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-dict");
  const type = name.replace(/-/g, "_");
  try {
    await page.goto("/#/system/dict", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });

    const dialog = await openAddDialog(page);
    await dialog.getByPlaceholder("请输入字典名称").fill(name);
    await dialog.getByPlaceholder("请输入字典类型").fill(type);
    await submitDialog(dialog);

    await searchName(page, "请输入字典名称", name);
    await expect(page.locator(".el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 15_000 });
  } finally {
    await apiDeleteByName(request, headers, "/system/dict/type/list", "/system/dict/type/delete", name);
  }
});

test("岗位管理：新增岗位并能被搜索到", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-post");
  try {
    await page.goto("/#/system/position", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });

    const dialog = await openAddDialog(page);
    await dialog.getByPlaceholder("请输入岗位名称").fill(name);
    await submitDialog(dialog);

    await searchName(page, "请输入岗位名称", name);
    await expect(page.locator(".el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 15_000 });
  } finally {
    await apiDeleteByName(request, headers, "/system/position/list", "/system/position/delete", name);
  }
});

test("角色管理：新增角色并能被搜索到", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-role");
  const code = name.replace(/-/g, "_").slice(0, 16);
  try {
    await page.goto("/#/system/role", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });

    const dialog = await openAddDialog(page);
    await dialog.getByPlaceholder("请输入角色名称").fill(name);
    await dialog.getByPlaceholder("字母开头，2-16位字母/数字/下划线").fill(code);
    await submitDialog(dialog);

    await searchName(page, "请输入角色名称", name);
    await expect(page.locator(".el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 15_000 });
  } finally {
    await apiDeleteByName(request, headers, "/system/role/list", "/system/role/delete", name);
  }
});

test("部门管理：新增部门并能被搜索到", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-dept");
  const code = name.replace(/-/g, "_").slice(0, 16);
  try {
    await page.goto("/#/system/dept", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });

    const dialog = await openAddDialog(page);
    await dialog.getByPlaceholder("请输入部门名称").fill(name);
    await dialog.getByPlaceholder("字母开头，2-16位字母/数字/下划线").fill(code);
    await submitDialog(dialog);

    await searchName(page, "请输入部门名称", name);
    await expect(page.locator(".el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 15_000 });
  } finally {
    await apiDeleteByName(request, headers, "/system/dept/list", "/system/dept/delete", name);
  }
});

test("菜单管理：树能加载、新增表单可打开（不落库）", async ({ page }) => {
  await page.goto("/#/system/menu", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });
  // 菜单是树表：行数应远大于 10（框架自带 300+ 菜单）
  await expect(page.locator(".el-table__row").first()).toBeVisible({ timeout: 20_000 });
  expect(await page.locator(".el-table__row").count()).toBeGreaterThan(10);

  // 新增打开的是抽屉/弹窗，只验证能开、字段在，然后关闭（避免污染菜单结构）
  await page.getByRole("button", { name: /^(新增|添加)$/ }).first().click();
  const form = page.locator(".el-drawer:visible").last();
  await expect(form).toBeVisible({ timeout: 15_000 });
  await expect(form.getByPlaceholder("请输入菜单名称")).toBeVisible();
  await page.keyboard.press("Escape");
});
