import { test } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const OUT = "e2e/.shots";

test.setTimeout(120_000);

test("delete + purge feedback", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}`, "X-Forwarded-For": "127.0.0.1" };

  const name = `del-fb-${Date.now()}`;
  const ds = await request.post(`${API}/annotation/dataset/create`, {
    data: { name }, headers: auth,
  });
  const dsId = (await ds.json()).data.id;

  page.on("console", (m) => {
    if (["error", "warning", "log"].includes(m.type())) console.log(`[console.${m.type()}] ${m.text()}`);
  });
  page.on("response", async (r) => {
    if (r.url().includes("/dataset/delete") || r.url().includes("/dataset/purge")) {
      console.log("[resp]", r.request().method(), r.url(), r.status());
    }
  });

  await page.setViewportSize({ width: 1600, height: 950 });
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await page.locator(".el-table__row").first().waitFor({ state: "visible", timeout: 30_000 });
  await page.waitForTimeout(1200);

  const row = page.locator(".el-table__row", { hasText: name }).first();
  await row.waitFor({ state: "visible", timeout: 15_000 });

  // 删除（软删）
  await row.getByRole("button", { name: /更多/ }).click();
  await page.getByRole("menuitem", { name: "删除" }).first().click();
  await page.waitForTimeout(600);
  const box = page.locator(".el-message-box");
  console.log("soft-delete confirm visible:", await box.isVisible().catch(() => false));
  console.log("soft-delete confirm text:", (await box.innerText().catch(() => "")).replace(/\n/g, "|"));
  await page.screenshot({ path: `${OUT}/60-soft-delete-confirm.png` });
  if (await box.isVisible().catch(() => false)) {
    await box.locator("button.el-button--primary").click();
    await page.waitForTimeout(1800);
  }
  console.log("toast after soft delete:", (await page.locator(".el-message").allInnerTexts().catch(() => [])).join(" / "));
  await page.screenshot({ path: `${OUT}/61-after-soft-delete.png` });

  // 彻底删除：新建一个数据集测
  const name2 = `del-fb2-${Date.now()}`;
  const ds2 = await request.post(`${API}/annotation/dataset/create`, {
    data: { name: name2 }, headers: auth,
  });
  console.log("dataset2 id:", (await ds2.json()).data.id);
  await page.getByRole("button", { name: "搜索" }).first().click().catch(() => {});
  await page.waitForTimeout(1200);
  const row2 = page.locator(".el-table__row", { hasText: name2 }).first();
  const found2 = await row2.isVisible().catch(() => false);
  console.log("row2 found:", found2);
  if (!found2) {
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.locator(".el-table__row").first().waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(800);
  }
  await row2.getByRole("button", { name: /更多/ }).click();
  await page.getByRole("menuitem", { name: "彻底删除" }).first().click();
  await page.waitForTimeout(600);
  console.log("purge confirm visible:", await box.isVisible().catch(() => false));
  console.log("purge confirm text:", (await box.innerText().catch(() => "")).replace(/\n/g, "|"));
  await page.screenshot({ path: `${OUT}/62-purge-confirm.png` });
  if (await box.isVisible().catch(() => false)) {
    await box.locator("button.el-button--primary").click();
    await page.waitForTimeout(1500);
  }
  console.log("toast after purge start:", (await page.locator(".el-message").allInnerTexts().catch(() => [])).join(" / "));
  await page.screenshot({ path: `${OUT}/63-after-purge-start.png` });
  console.log("banner:", await page.locator(".task-banner").innerText().catch(() => "<none>"));
});
