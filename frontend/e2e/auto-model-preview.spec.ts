// 本体「大模型自动建模」两段式界面（Task：本体权限分级 + 自动建模 UI）。
//
// 覆盖点：
// 1. 集成页「AI 辅助建模」Tab 的按钮打开的是**预览对话框**（不再"点了就直接落库"）；
// 2. 对话框里能看到大模型产出的**逐条候选**（表格），或明确告知没有候选；
// 3. 「应用选中 N 条」按钮的可用性跟随勾选（默认全选 ⇒ 可点）。
//
// ⚠️ 本用例**只预览、不应用**（不点「应用选中」），所以不会往本体/指标库里写任何东西，
//    无需清理数据。落库路径由后端用例 `tests/test_ontology_auto_model.py` 覆盖。
import { test, expect } from "@playwright/test";

test("AI 辅助建模：打开预览对话框并看到候选（不落库）", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded" });

  // 左侧数据源列表就绪后选第一个（预览按钮要求已选数据源）
  const dsList = page.locator(".ig-ds-list").first();
  await expect(dsList).toBeVisible({ timeout: 25_000 });
  const firstDs = page.locator(".ig-ds-item").first();
  await firstDs.waitFor({ state: "visible", timeout: 15_000 });
  // 点**名称**（条目的中心可能落在右侧操作按钮上，会误触编辑）
  await firstDs.locator(".ig-ds-item__name").click();

  // 切到「AI 辅助建模」
  await page.locator(".el-tabs__item", { hasText: "AI 辅助建模" }).first().click();

  // 先确认真的选中了（表单里出现数据源 tag）——否则「生成」按钮是禁用的，点了也没反应
  await expect(
    page.locator(".el-form-item", { hasText: "数据源" }).locator(".el-tag").first()
  ).toBeVisible({ timeout: 10_000 });

  // 点「生成绑定型指标」→ 应打开**预览**对话框（而不是直接跑）
  await page.getByRole("button", { name: "生成绑定型指标" }).click();
  const dlg = page.locator(".el-dialog", { hasText: "自动生成绑定型指标" }).first();
  await expect(dlg).toBeVisible({ timeout: 10_000 });

  // 等分析结束：要么表格出候选，要么给出「没有候选」的明确说明（两者都证明两段式界面工作）
  const rows = dlg.locator(".el-table__row");
  const empty = dlg.locator(".el-alert--warning");
  await expect(rows.first().or(empty.first())).toBeVisible({ timeout: 120_000 });

  if (await rows.count()) {
    // 默认全选 ⇒ 应用按钮可点，且文案带条数
    const applyBtn = dlg.getByRole("button", { name: /应用选中/ });
    await expect(applyBtn).toBeEnabled();
    await expect(applyBtn).toContainText("应用选中");
    await expect(dlg.locator(".am-head")).toContainText("已选");
  }

  await page.screenshot({ path: "e2e/auto-model-preview.png" });
  await dlg.getByRole("button", { name: "取消" }).click();
  await expect(dlg).toBeHidden({ timeout: 10_000 });
});
