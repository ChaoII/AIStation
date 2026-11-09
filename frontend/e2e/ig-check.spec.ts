/** 数据与集成新页面的走查：选数据源 → 选表 → 看到元数据与字段（并截图） */
import { test, type Page } from "@playwright/test";

/** 关掉引导遮罩。它有多步，且可能延迟出现，所以循环点到消失为止。 */
async function dismissTour(page: Page) {
  // 遮罩是**延迟出现**的：先等它，再关。否则"现在没有"就返回了，后面照样被挡。
  await page
    .locator(".el-tour")
    .waitFor({ state: "visible", timeout: 8_000 })
    .catch(() => {});
  for (let i = 0; i < 8; i++) {
    const tour = page.locator(".el-tour");
    if (!(await tour.count())) return;
    const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
    if (await skip.count()) {
      await skip.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
    }
    await page.waitForTimeout(400);
    if (!(await tour.isVisible().catch(() => false))) return;
  }
}

test("数据与集成：选数据源 → 选表 → 元数据维护", async ({ page }) => {
  test.setTimeout(240_000);
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message.slice(0, 200)));
  page.on("console", (m) => {
    if (m.type() === "error") errs.push(m.text().slice(0, 200));
  });

  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(2_500);
  await dismissTour(page);
  await page.waitForTimeout(1_500);
  await page.screenshot({ path: "e2e/ig-1-初始.png" });

  // ① 选数据源（左侧第一张表的第一行）
  // 左侧数据源已从表格改成卡片列表（.ig-ds-item）；点第二个（业务库）才有表
  const dsItem = page.locator(".ig-ds-item").nth(1);
  await dsItem.waitFor({ state: "visible", timeout: 20_000 });
  await dsItem.click();
  await page.waitForTimeout(4_000);
  await page.screenshot({ path: "e2e/ig-2-选数据源.png" });

  const tableCount = await page.locator(".app-main .el-table__row:visible").count();

  // ② 选表
  let colCount = 0;
  if (tableCount > 0) {
    await page.locator(".app-main .el-table__row:visible").first().click();
    await page.waitForTimeout(4_000);
    await page.screenshot({ path: "e2e/ig-3-选表.png" });
    colCount = await page.locator(".app-main .el-table__row:visible").count();
  }

  // eslint-disable-next-line no-console
  console.log(
    `\n  【走查结果】表=${tableCount}  字段行=${colCount}  页面错误=${errs.length}\n` +
      errs
        .slice(0, 6)
        .map((e) => "    - " + e)
        .join("\n")
  );
});
