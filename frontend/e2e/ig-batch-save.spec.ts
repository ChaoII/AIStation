import { test, type Page } from "@playwright/test";
async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
  for (let i = 0; i < 8; i++) {
    const tour = page.locator(".el-tour");
    if (!(await tour.count())) return;
    const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
    if (await skip.count()) await skip.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
    await page.waitForTimeout(400);
    if (!(await tour.isVisible().catch(() => false))) return;
  }
}
test("批量维护：界面上真的保存", async ({ page }) => {
  test.setTimeout(180_000);
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message.slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(2500);
  await dismissTour(page);
  await page.waitForTimeout(1500);
  await page.locator(".el-card .el-table__row").first().click();
  await page.waitForTimeout(4000);
  await page.getByRole("button", { name: "批量维护" }).click();
  await page.waitForTimeout(800);
  await page.locator(".el-dialog textarea").fill("FUEL_CMCS_BELT\t皮带秤（界面保存测试）");
  await page.waitForTimeout(1000);
  await page.getByRole("button", { name: /保存 \d+ 条/ }).click();
  await page.waitForTimeout(3000);
  const toast = await page.locator(".el-message").first().innerText().catch(() => "(无提示)");
  await page.screenshot({ path: "e2e/ig-5-保存结果.png" });
  console.log(`\n  保存提示: ${toast}   页面错误: ${errs.length}`);
  for (const e of errs.slice(0, 4)) console.log("    - " + e);
});
