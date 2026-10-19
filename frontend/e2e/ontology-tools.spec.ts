// 本体级工具入口验证：建模分析 / 派生属性问题扫描 / 补齐默认视图 / 能力登记 / 值类型试校验
// —— 这些后端能力此前前端封装了却**没有任何界面入口**，用户根本用不到。
//
// 每个工具一个独立用例（避免多弹窗叠加互相遮挡），逐个打开并断言内容真的渲染出来。
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";

/** 打开本体页 → 点「维护」下拉 → 选中某个命令 */
async function pickMaintCommand(page: any, label: string) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/ontology", { waitUntil: "domcontentloaded" });
  const dropdown = page.getByRole("button", { name: "维护" }).first();
  await expect(dropdown).toBeVisible({ timeout: 25_000 });
  await dropdown.click();
  const item = page.locator(".el-dropdown-menu__item", { hasText: label }).first();
  await expect(item, `维护菜单应有「${label}」`).toBeVisible({ timeout: 10_000 });
  await item.click();
}

test("维护 → 建模分析：结构诊断能渲染", async ({ page, request }) => {
  await login(request);
  await pickMaintCommand(page, "建模分析");

  const dlg = page.locator(".el-dialog", { hasText: "本体建模分析" }).first();
  await expect(dlg).toBeVisible({ timeout: 15_000 });
  // 统计块 + 建议 + 中心度表都要真的渲染出来（不是空壳）
  await expect(dlg.getByText("对象类型").first()).toBeVisible({ timeout: 20_000 });
  await expect(dlg.getByText("关系密度").first()).toBeVisible();
  await expect(dlg.getByText("建模建议").first()).toBeVisible();
  await expect(dlg.locator(".ont-analyze__recs li").first()).toBeVisible();
  await expect(dlg.locator(".el-table").first()).toBeVisible();
  await page.screenshot({ path: "e2e/ontology-analyze.png" });
});

test("维护 → 派生属性问题扫描：能渲染列表或空态", async ({ page, request }) => {
  await login(request);
  await pickMaintCommand(page, "派生属性问题扫描");

  const dlg = page.locator(".el-dialog", { hasText: "派生属性问题扫描" }).first();
  await expect(dlg).toBeVisible({ timeout: 15_000 });
  await expect(dlg.locator(".el-table").first()).toBeVisible({ timeout: 20_000 });
  await expect(dlg.getByText("没有发现配置问题").or(dlg.locator(".el-table__row").first())).toBeVisible({
    timeout: 20_000,
  });
});

test("维护 → 补齐默认对象视图：确认后给出反馈", async ({ page, request }) => {
  await login(request);
  await pickMaintCommand(page, "补齐默认对象视图");

  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await box.getByRole("button", { name: "补齐" }).click();
  // 全量批处理（421 对象 × 2 形态）：修复前光重复查询就要 ~89 秒 ⇒ 这里给足 150 秒
  await expect(page.locator(".el-message--success").first()).toBeVisible({ timeout: 150_000 });
});

test("值类型「试校验」：能按约束校验取值", async ({ page, request }) => {
  const headers = await login(request);

  // 造一个带约束的值类型（长度 3~8 且必须以 E2E 开头），这样校验必然有明确结论
  const code = `e2e_vt_${Date.now()}`;
  const saved = await request.post(`${API}/ai/ontology/value-type/save`, {
    headers,
    data: {
      code,
      name: `e2e 值类型 ${code}`,
      base_type: "string",
      constraints: { min_length: 3, max_length: 8, pattern: "^E2E" },
    },
  });
  expect(saved.ok(), "创建值类型应成功").toBeTruthy();

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/ontology", { waitUntil: "domcontentloaded" });

  // 维护图标第 7 个 = 值类型
  const maintBtns = page.locator(".ont-gw__maint-btn");
  await expect(maintBtns.first()).toBeVisible({ timeout: 25_000 });
  await maintBtns.nth(6).click();
  const dlg = page.locator(".el-dialog", { has: page.locator(".ont-adv") }).first();
  await expect(dlg).toBeVisible({ timeout: 15_000 });

  const row = dlg.locator(".el-table__row", { hasText: code }).first();
  await expect(row, "刚建的值类型应出现在列表里").toBeVisible({ timeout: 20_000 });
  await row.getByRole("button", { name: "试校验" }).click();

  const vDlg = page.locator(".el-dialog", { hasText: "按值类型约束校验取值" }).first();
  await expect(vDlg).toBeVisible({ timeout: 10_000 });

  // 不合规：不满足 min_length / pattern
  await vDlg.getByLabel("取值").fill("bad");
  await vDlg.getByRole("button", { name: "校验" }).click();
  await expect(vDlg.getByText("校验不通过")).toBeVisible({ timeout: 20_000 });
  await expect(vDlg.locator(".ont-validate__errs li").first(), "应列出具体不满足的约束").toBeVisible();

  // 合规
  await vDlg.getByLabel("取值").fill("E2E-ok");
  await vDlg.getByRole("button", { name: "校验" }).click();
  await expect(vDlg.getByText("校验通过")).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: "e2e/ontology-value-validate.png" });
});
