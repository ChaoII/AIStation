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
test("批量维护表信息", async ({ page }) => {
  test.setTimeout(180_000);
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message.slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });

  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(2500);
  await dismissTour(page);
  await page.waitForTimeout(1500);
  // 选数据源
  await page.locator(".el-card .el-table__row").first().click();
  await page.waitForTimeout(4000);
  // 打开批量维护
  await page.getByRole("button", { name: "批量维护" }).click();
  await page.waitForTimeout(1000);
  await page.locator(".el-dialog textarea").fill("FUEL_CMCS_ASSAY\t化验表\nFUEL_CMCS_BELT,皮带秤,燃煤\nNOT_EXIST_TABLE,不存在的表");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "e2e/ig-4-批量维护.png" });
  const parsed = await page.locator(".el-dialog .el-tag").first().innerText();
  console.log(`\n  解析结果: ${parsed}`);
  const previewRows = await page.locator(".el-dialog .el-table__row").count();
  console.log(`  预览行数: ${previewRows}  页面错误: ${errs.length}`);
  for (const e of errs.slice(0, 4)) console.log("    - " + e);
});
