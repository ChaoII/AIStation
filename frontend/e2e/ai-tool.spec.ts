import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// 旧「工具中心」独立页 /#/ai/tool 已下线（菜单 hidden + 组件删除，能力并入能力市场，
// 见 aff76ac3「能力市场我的资产集成四类资产」），本 spec 迁移到
// 能力市场 → 我的资产 → 工具：覆盖原意图（卡片网格、创建入口、启用开关往返）。
// 注意：「我的资产」只含用户自建/安装的资产（内置工具不计入，dev 库常为 0 项），
// 故用例先经 API 创建一张测试工具卡，结束后清理。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

let createdToolName = "";

async function loginHeaders(request: APIRequestContext) {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  const token = (await login.json()).data.access_token;
  return { Authorization: `Bearer ${token}` };
}

test.beforeAll(async ({ request }) => {
  try {
    const headers = await loginHeaders(request);
    createdToolName = `e2e-mine-tool-${Date.now()}`;
    await request.post(`${API}/ai/tools/create`, {
      headers,
      data: {
        name: createdToolName,
        kind: "http",
        method: "GET",
        url: "http://127.0.0.1:1/e2e-probe",
        params_schema: { type: "object", properties: {} },
        enabled: true,
      },
    });
  } catch {
    // 创建失败会在用例「卡片至少一张」处暴露
  }
});

test.afterAll(async ({ request }) => {
  if (!createdToolName) return;
  try {
    const headers = await loginHeaders(request);
    const lst = await request.get(`${API}/ai/tools/list`, { headers });
    const items: Array<{ id: number; name: string }> = (await lst.json()).data || [];
    const hit = items.find((t) => t.name === createdToolName);
    if (hit) {
      await request.delete(`${API}/ai/tools/delete`, { headers, data: [hit.id] }).catch(() => {});
    }
  } catch {
    // 清理失败不影响用例结论
  }
});

// 关闭引导遮罩。Guide 组件设置了 :show-close="false"，不存在关闭按钮，仅底部「跳过」可退出。
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;

  const skip = tour.getByRole("button", { name: "跳过" }).first();
  const close = tour.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  await page
    .evaluate(() => {
      document.querySelectorAll(".el-tour").forEach((el) => el.remove());
    })
    .catch(() => {});
}

test("工具资产管理（能力市场·我的资产）：类型筛选、卡片网格与启用开关", async ({ page }) => {
  await page.goto("/#/ai/market", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 切到「我的资产」页签
  await page.getByRole("tab", { name: "我的资产" }).click();
  const mine = page.locator(".market-mine");
  await expect(mine).toBeVisible({ timeout: 10_000 });

  // 筛选「工具」类型（工具/技能/MCP/插件 四类）
  await mine.locator(".type-tab", { hasText: "工具" }).first().click();

  // 卡片网格：至少一张工具卡片
  const cards = mine.locator(".market-card");
  await expect(cards.first()).toBeVisible({ timeout: 10_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(1);

  // 创建入口（新建工具）
  await expect(
    mine.getByRole("button", { name: /新建/ }).first()
  ).toBeVisible();

  // 启用开关可切换，且切回后还原（与旧工具中心同一语义）。
  // 注意：aria-checked 在内部 input 上、wrapper 无此属性（实测恒 null），
  // 选中态以 wrapper 的 is-checked class 为准。
  const sw = cards.first().locator(".el-switch").first();
  await expect(sw).toBeVisible({ timeout: 10_000 });
  const checked = async () => ((await sw.getAttribute("class")) || "").includes("is-checked");
  const before = await checked();
  await sw.evaluate((el) => (el as HTMLElement).click());
  await expect.poll(checked, { timeout: 10_000 }).not.toBe(before);
  await sw.evaluate((el) => (el as HTMLElement).click());
  await expect.poll(checked, { timeout: 10_000 }).toBe(before);
});
