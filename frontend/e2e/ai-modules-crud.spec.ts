/**
 * 问数之外的三块主流程写操作：智能体 / 知识库 / 定时任务。
 *
 * 覆盖：新建（真实表单）→ 列表里能查到 → API 清理。
 * 只验证「能建出来、列表对得上」，不触发模型调用（避免依赖模型网关）。
 */
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

function uniq(p: string) {
  return `${p}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

async function authOf(request: APIRequestContext) {
  const r = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(r.ok()).toBeTruthy();
  return { Authorization: `Bearer ${(await r.json()).data.access_token}` };
}

async function apiCleanup(
  request: APIRequestContext,
  headers: Record<string, string>,
  listPath: string,
  deletePath: string,
  field: string,
  value: string
) {
  try {
    const r = await request.get(`${API}${listPath}`, { headers, params: { page_no: 1, page_size: 100 } });
    if (!r.ok()) return;
    const body = await r.json();
    // 三个接口形状不一：agents/knowledge 的 data 直接是数组，cron 是 {total, items}
    const d = body?.data;
    const items = Array.isArray(d) ? d : d?.items || [];
    const ids = items.filter((it: any) => it[field] === value).map((it: any) => it.id);
    if (ids.length) await request.delete(`${API}${deletePath}`, { headers, data: ids });
  } catch {
    /* 清理失败不影响主断言 */
  }
}

async function closeTour(page: Page) {
  await page.evaluate(() => document.querySelectorAll(".el-tour").forEach((el) => el.remove())).catch(() => {});
}

test("智能体：新建 → 工作台卡片出现 → 清理", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-agent");
  try {
    await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    await closeTour(page);

    await page.getByRole("button", { name: "新建" }).first().click();
    await page.locator(".el-popper:visible .el-dropdown-menu__item", { hasText: "传统智能体" }).first().click();

    const dialog = page.locator(".el-dialog").filter({ hasText: "新建智能体" }).first();
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await dialog.getByPlaceholder("智能体名称").fill(name);
    await dialog.getByPlaceholder("这个智能体是做什么的").fill("e2e 冒烟");
    await dialog.getByRole("button", { name: /^(确定|保存)$/ }).last().click();
    await expect(dialog).toBeHidden({ timeout: 25_000 });

    // 列表按名称搜索（工作台搜索框）
    const search = page.getByPlaceholder(/搜索/).first();
    if (await search.count()) {
      await search.fill(name);
      await page.waitForTimeout(1200);
    }
    await expect(page.locator(".ws-card", { hasText: name }).first()).toBeVisible({ timeout: 20_000 });
  } finally {
    await apiCleanup(request, headers, "/ai/agents/list", "/ai/agents/delete", "agent_name", name);
  }
});

test("知识库：新建 → 列表出现 → 清理", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-kb");
  try {
    await page.goto("/#/ai/knowledge", { waitUntil: "domcontentloaded" });
    // 知识库是「左分类树 + 右列表」布局，没有 PageSearch 的 .search-container
    await expect(page.locator(".el-table").first()).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: /新建知识库|新建/ }).first().click();
    const dialog = page.locator(".el-dialog").filter({ hasText: "新建知识库" }).first();
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await dialog.getByPlaceholder("知识库名称").fill(name);
    await dialog.getByPlaceholder("描述").fill("e2e 冒烟");
    await dialog.getByRole("button", { name: /^(确定|保存)$/ }).last().click();
    await expect(dialog).toBeHidden({ timeout: 20_000 });

    await expect(page.locator(".el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 20_000 });
  } finally {
    await apiCleanup(request, headers, "/ai/knowledge/bases/list", "/ai/knowledge/bases/delete", "name", name);
  }
});

test("定时任务：新建（立即触发 + 智能体目标）→ 列表出现 → 清理", async ({ page, request }) => {
  const headers = await authOf(request);
  const name = uniq("e2e-cron");

  // 取一个已有智能体作为执行目标
  const agents = await request.get(`${API}/ai/agents/list`, { headers, params: { page_no: 1, page_size: 20 } });
  const agentBody = (await agents.json())?.data;
  const agent = (Array.isArray(agentBody) ? agentBody : agentBody?.items || [])[0];
  expect(agent?.id, "需要至少一个智能体作为定时任务目标").toBeTruthy();

  try {
    await page.goto("/#/ai/cron", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    await page.getByRole("button", { name: /新建|添加/ }).first().click();

    const dialog = page.locator(".el-dialog").filter({ hasText: "新建定时任务" }).first();
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await dialog.getByPlaceholder(/任务名称|请输入/).first().fill(name);
    // 触发方式：立即
    await dialog.locator(".el-radio-button, .el-radio").filter({ hasText: "立即" }).first().click();
    // 目标ID 是 el-input-number（无 placeholder）→ 按表单项定位
    const targetItem = dialog.locator(".el-form-item").filter({ hasText: "目标ID" }).first();
    await targetItem.locator("input").fill(String(agent.id));
    await dialog.getByRole("button", { name: /^(确定|保存)$/ }).last().click();
    await expect(dialog).toBeHidden({ timeout: 25_000 });

    await expect(page.locator(".cron-card, .el-table__row", { hasText: name }).first()).toBeVisible({ timeout: 20_000 });
  } finally {
    await apiCleanup(request, headers, "/ai/workspace/cron/list", "/ai/workspace/cron/delete", "name", name);
  }
});
