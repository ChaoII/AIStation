// 维护面板可达性 + 面板内新能力（此前无 UI 入口）的端到端验证。
//
// 覆盖点：
// 1. 图谱工作区右上角的维护图标能打开「提案 / 场景」面板；
// 2. 提案详情里的「讨论」区能渲染已有留言，并能**发出新留言**（commentOntProposal 此前无入口）；
// 3. 场景面板的「清理过期场景」可用（expireOntScenarios 此前无入口）。
//
// 会真的建分支/提案并留言（这正是被测能力），用 e2e 前缀便于清理。
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";

/** 打开本体页并返回图谱工作区的维护图标按钮 */
async function gotoOntology(page: any) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/ontology", { waitUntil: "domcontentloaded" });
  const maintBtns = page.locator(".ont-gw__maint-btn");
  await expect(maintBtns.first(), "图谱工作区应渲染出维护图标按钮").toBeVisible({
    timeout: 25_000,
  });
  return maintBtns;
}

test("提案面板可达，且能查看/发出留言", async ({ page, request }) => {
  const headers = await login(request);

  // 建一个分支（会自动生成对应提案），用于验证「留言」
  const title = `e2e-维护面板-${Date.now()}`;
  const created = await request.post(`${API}/ai/ontology/branch/create`, {
    headers,
    data: { title, description: "e2e：验证提案面板可达 + 留言" },
  });
  expect(created.ok(), "创建分支/提案应成功").toBeTruthy();

  const maintBtns = await gotoOntology(page);

  await maintBtns.nth(1).click(); // 第 2 个图标 = 提案
  const prDlg = page.locator(".el-dialog", { has: page.locator(".ont-pr") }).first();
  await expect(prDlg, "点「提案」图标应打开维护抽屉").toBeVisible({ timeout: 15_000 });

  // 新建的提案处于「准备中」，默认停在「审查中」页签 ⇒ 先切到「我的提案」
  const mineTab = prDlg.getByRole("tab", { name: "我的提案" });
  await expect(mineTab, "提案面板应有「我的提案」页签").toBeVisible();
  await mineTab.click();
  await expect(mineTab).toHaveAttribute("aria-selected", "true");

  const prRow = prDlg.locator(".el-table__row", { hasText: title }).first();
  await expect(prRow, "新建的提案应出现在「我的提案」里").toBeVisible({ timeout: 20_000 });
  await prRow.getByRole("button", { name: "详情" }).click();

  const drawer = page.locator(".el-drawer", { hasText: title }).first();
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  const discuss = drawer.locator(".ont-pr__comment-form");
  await expect(discuss, "提案详情应有「讨论/留言」区").toBeVisible({ timeout: 15_000 });

  const text = `e2e 留言 ${Date.now()}`;
  await discuss.locator("textarea").fill(text);
  await discuss.getByRole("button", { name: "留言" }).click();
  await expect(drawer.getByText(text), "留言后应出现在讨论列表里").toBeVisible({
    timeout: 20_000,
  });
  await page.screenshot({ path: "e2e/ontology-proposal-comment.png" });
});

test("场景面板可达，且能清理过期场景", async ({ page, request }) => {
  await login(request);
  const maintBtns = await gotoOntology(page);

  await maintBtns.nth(2).click(); // 第 3 个图标 = 场景
  const scnDlg = page.locator(".el-dialog", { has: page.locator(".ont-scn") }).first();
  await expect(scnDlg, "点「场景」图标应打开维护抽屉").toBeVisible({ timeout: 15_000 });

  const expireBtn = scnDlg.getByRole("button", { name: "清理过期场景" });
  await expect(expireBtn, "场景面板应有「清理过期场景」入口").toBeVisible();
  await expireBtn.click();
  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await box.getByRole("button", { name: "清理" }).click();
  await expect(
    page.locator(".el-message--success, .el-message--info").first(),
    "清理后必须给出反馈（已过期 N 个 / 无需清理）"
  ).toBeVisible({ timeout: 20_000 });
});
