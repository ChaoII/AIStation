/**
 * 框架级只读页面冒烟：监控管理 / 接口文档 / 代码生成 / 应用市场。
 *
 * 这几页之前同样零 e2e 覆盖，且都很容易「整页渲染失败但没人发现」
 * （iframe 被 X-Frame 拦、Redis 连不上导致整块空白、空表把表头也吞掉）。
 * 这里只做**读**验证：列表/卡片/iframe 真的渲染出来，且带关键文案。
 */
import { test, expect } from "@playwright/test";

test("在线用户：列表渲染且能按 IP 过滤", async ({ page }) => {
  await page.goto("/#/monitor/online", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });
  // 当前登录的 admin 一定在线
  await expect(page.locator(".el-table__row").first()).toBeVisible({ timeout: 20_000 });
  expect(await page.locator(".el-table__row").count()).toBeGreaterThan(0);

  await page.getByPlaceholder("请输入IP地址").fill("127.0.0.1");
  await page.locator("form").getByRole("button", { name: /^(查询|搜索)$/ }).first().click();
  await expect(page.locator(".el-table__row").first()).toBeVisible({ timeout: 15_000 });
  const text = await page.locator(".el-table__row").first().innerText();
  expect(text).toContain("127.0.0.1");
});

test("服务器监控：CPU/内存等指标卡渲染", async ({ page }) => {
  await page.goto("/#/monitor/server", { waitUntil: "domcontentloaded" });
  const main = page.locator(".app-main");
  await expect(main).toBeVisible({ timeout: 20_000 });
  await expect(main.getByText("CPU使用情况").first()).toBeVisible({ timeout: 20_000 });
  await expect(main.getByText("内存使用情况").first()).toBeVisible();
  // 指标卡（el-statistic/progress）至少要有一批，不能整块空白
  expect(await main.locator(".el-card").count()).toBeGreaterThan(3);
});

test("缓存监控：Redis 信息与 key 列表渲染", async ({ page }) => {
  await page.goto("/#/monitor/cache", { waitUntil: "domcontentloaded" });
  const main = page.locator(".app-main");
  await expect(main.getByText("Redis监控信息").first()).toBeVisible({ timeout: 20_000 });
  // 缓存 key 在「缓存管理」页签里（默认停在「监控信息」），先切页签再断言
  await page.getByRole("tab", { name: "缓存管理" }).click();
  await expect(main.getByText("access_token", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(main.getByText("system_config", { exact: true })).toBeVisible();
});

test("接口文档：Swagger iframe 指向 /docs 且可加载", async ({ page }) => {
  await page.goto("/#/common/docs", { waitUntil: "domcontentloaded" });
  const frame = page.locator("iframe");
  await expect(frame).toBeVisible({ timeout: 20_000 });
  const src = await frame.getAttribute("src");
  expect(src).toContain("/docs");
  // 内容加载成功时 Swagger UI 会渲染出 .swagger-ui / #swagger-ui
  const inner = page.frameLocator("iframe");
  await expect(inner.locator("#swagger-ui, .swagger-ui").first()).toBeVisible({ timeout: 25_000 });
});

test("代码生成：搜索区与表头渲染（空数据也不塌）", async ({ page }) => {
  await page.goto("/#/generator/gencode", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByPlaceholder("请输入表名称")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建" })).toBeVisible();
  // 表头必须存在（哪怕没有数据行）
  await expect(page.locator(".el-table__header-wrapper th").first()).toBeVisible({ timeout: 15_000 });
});

test("应用市场：创建入口与空态/列表渲染", async ({ page }) => {
  await page.goto("/#/application/portal", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".search-container")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "创建应用" })).toBeVisible();
  // 空态或卡片列表，二者必有其一
  const empty = page.getByText("暂无应用");
  const row = page.locator(".el-table__row").first();
  await expect(empty.or(row)).toBeVisible({ timeout: 20_000 });
});
