import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// 旧独立聊天页 /#/ai/chat 已随菜单收敛下线（见 init_app 注释与 c874fc62），
// 对话入口改为「工作台 → 卡片对话」：/#/ai/workspace/chat/:kind/:id。
// 本 spec 已迁移到新入口，覆盖原三个意图：输入区铺满与文案、会话新建/切换、未知 app 不崩。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

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

async function loginHeaders(request: APIRequestContext) {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  const token = (await login.json()).data.access_token;
  return { Authorization: `Bearer ${token}` };
}

/** 对话路由目标：取现有智能体；没有则临时创建并在 afterAll 清理 */
let chatAgentId = 0;
let createdAgentId = 0;

test.beforeAll(async ({ request }) => {
  try {
    const headers = await loginHeaders(request);
    const lst = await request.get(`${API}/ai/agents/list`, { headers });
    const items: Array<{ id: number }> = (await lst.json()).data || [];
    if (items.length) {
      chatAgentId = items[0].id;
    } else {
      const c = await request.post(`${API}/ai/agents/create`, {
        headers,
        data: {
          agent_name: `e2e-chat-${Date.now()}`,
          agent_role: "e2e",
          enabled: true,
          tool_ids: [],
          knowledge_ids: [],
          markdown: true,
          order: 0,
        },
      });
      createdAgentId = (await c.json()).data.id;
      chatAgentId = createdAgentId;
    }
  } catch {
    // beforeAll 失败会在用例内以 chatAgentId=0 暴露（路由 0 → 页面仍渲染输入区）
  }
});

test.afterAll(async ({ request }) => {
  if (!createdAgentId) return;
  try {
    const headers = await loginHeaders(request);
    await request
      .delete(`${API}/ai/agents/delete`, { headers, data: [createdAgentId] })
      .catch(() => {});
  } catch {
    // 清理失败不影响用例结论
  }
});

/** 打开工作台对话页并关掉引导（该页是根级独立全屏路由，无 .app-main 侧栏布局） */
async function openChat(page: Page, kind: "agent" | "app", id: number) {
  await page.goto(`/#/ai/workspace/chat/${kind}/${id}`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-container.ai-workspace-chat").first()).toBeVisible({
    timeout: 15_000,
  });
  await dismissTour(page);
}

test("工作台对话输入区铺满且可输入（无旧助手文案）", async ({ page }) => {
  await openChat(page, "agent", chatAgentId);

  // 输入区（CodeMirror 编辑器容器）可见
  const input = page.locator(".chat-input .cm-host").first();
  await expect(input).toBeVisible({ timeout: 10_000 });

  // 输入区铺满聊天区：容器宽度 > 600px
  const box = await page.locator(".chat-input").boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(600);

  // 可正常键入（CodeMirror 内容落到 .cm-content），随后清空
  await input.click();
  await page.keyboard.type("e2e 输入检查");
  await expect(page.locator(".cm-content").first()).toContainText("e2e 输入检查");
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  await expect(page.locator(".cm-content").first()).not.toContainText("e2e 输入检查");

  // 旧「FA助手」占位文案不得回归
  expect(await page.getByText("FA助手").count()).toBe(0);
});

test("新建/切换会话后输入区仍可输入且无未捕获异常", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  await openChat(page, "agent", chatAgentId);

  // 新建会话后输入区仍可用
  await page
    .getByRole("button", { name: "新建会话" })
    .first()
    .evaluate((el) => (el as HTMLElement).click());
  const input = page.locator(".chat-input .cm-host").first();
  await expect(input).toBeVisible({ timeout: 10_000 });
  await input.click();
  await page.keyboard.type("e2e 会话切换检查");
  await expect(page.locator(".cm-content").first()).toContainText("e2e 会话切换检查");

  // 切换已有会话后输入区仍可用（select-session 路径）
  const firstSession = page.locator(".chat-sess").first();
  if (await firstSession.count()) {
    await firstSession.evaluate((el) => (el as HTMLElement).click());
    await expect(input).toBeVisible();
  }

  expect(pageErrors, `页面抛出未捕获异常\n${pageErrors.join("\n")}`).toEqual([]);
});

test("带未知 app_id 打开工作台对话不崩溃", async ({ page }) => {
  await openChat(page, "app", 999999);

  // 未知应用时页面照常渲染输入区（运行错误由对话流 RunError 呈现，不崩页面）
  await expect(page.locator(".chat-input .cm-host").first()).toBeVisible({ timeout: 10_000 });
  // 不显示应用标签（旧页遗留元素，新页不存在即通过）
  await expect(page.locator(".app-tag")).toHaveCount(0);
});
