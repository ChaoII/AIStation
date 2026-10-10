/** 数据与集成：管道/指标/术语/概念 四个页签的「新建」弹窗可用性走查。 */
import { test, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
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

async function openTabDialog(page: Page, tab: string, button: string, title: string) {
  await page.getByRole("tab", { name: tab }).click();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: button }).first().click();
  const dlg = page.locator(".el-dialog").filter({ hasText: title });
  await dlg.waitFor({ state: "visible", timeout: 8_000 });
  const fields = await dlg.locator("input, textarea").count();
  await dlg.getByRole("button", { name: "取消" }).first().click();
  await dlg.waitFor({ state: "hidden", timeout: 8_000 });
  return fields;
}

test("数据与集成：四个页签新建弹窗可用", async ({ page }) => {
  test.setTimeout(180_000);
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message.slice(0, 200)));
  page.on("console", (m) => {
    if (m.type() === "error") errs.push(m.text().slice(0, 200));
  });

  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(2_500);
  await dismissTour(page);
  await page.waitForTimeout(1_000);

  const report: string[] = [];
  report.push(`管道: 字段数=${await openTabDialog(page, "管道", "新建管道", "新建管道")}`);
  report.push(`指标: 字段数=${await openTabDialog(page, "指标", "新建指标", "新建指标")}`);
  report.push(`术语: 字段数=${await openTabDialog(page, "术语", "新建术语", "新建术语")}`);
  report.push(`概念: 字段数=${await openTabDialog(page, "概念", "新建概念", "新建概念")}`);

  // eslint-disable-next-line no-console
  console.log(`\n  ${report.join("  ")}  页面报错=${errs.length}\n` + errs.map((e) => "    - " + e).join("\n"));
  if (errs.length) throw new Error(`页面报错 ${errs.length} 条`);
});
