import { test, expect, type Page } from "@playwright/test";

/**
 * SP5-a 规则编辑器 e2e：登录态（auth.setup 提供）→ 告警页「告警规则」页签 → 新建规则
 * → 选场景 DET_ZONE → ROI 画布点 4 点 → 条件树新增 object_present 叶子 → 保存
 * → 列表出现新规则 → 重新打开编辑 → 断言 ROI 点列与条件树回填一致。
 *
 * 说明：后端无 `/rule/detail/{id}`，编辑态由列表接口回填；ROI 经参数编译层注入
 * `conditions[].region`，故「条件预览」即为 ROI + 条件树回填的权威断言点。
 *
 * 自建自清：本用例经 API 按名称删除自己创建的规则（列表断言改用「规则名称」搜索定位，
 * 不受历史数据分页影响）；视频模块路由限流 5 次/10s，用例内调用稀疏不触发 429。
 */

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";
const API_BASE = `${BASE_URL.replace(/\/web\/?$/, "")}/api/v1`;

/** 关闭可能遮挡点击的新手引导 Tour（el-tour），避免拦截交互。 */
async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) {
    await close.click({ force: true }).catch(() => {});
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page
    .locator(".el-tour")
    .waitFor({ state: "hidden", timeout: 3000 })
    .catch(() => {});
}

/** 读取登录态 access_token（localStorage 中以 JSON 字符串保存）。 */
async function authHeaders(page: Page) {
  const raw = await page.evaluate(() => window.localStorage.getItem("access_token"));
  const token = raw ? (JSON.parse(raw) as string) : "";
  return { Authorization: `Bearer ${token}` };
}

/** 按名称删除本用例创建的规则（失败仅打印告警，不影响用例结论）。 */
async function deleteRuleByName(page: Page, name: string) {
  try {
    const headers = await authHeaders(page);
    const res = await page.request.get(`${API_BASE}/video/alarm/rule/list`, {
      headers,
      params: { name, page_size: 50 },
    });
    if (!res.ok()) {
      console.warn(`清理前查询规则失败: ${res.status()} ${await res.text()}`);
      return;
    }
    const items = (await res.json()).data.items as Array<{ id: number; name: string }>;
    const ids = items.filter((x) => x.name === name).map((x) => x.id);
    if (!ids.length) return;
    const del = await page.request.delete(`${API_BASE}/video/alarm/rule/delete`, {
      headers,
      data: ids,
    });
    if (!del.ok()) console.warn(`清理规则失败: ${del.status()} ${await del.text()}`);
  } catch (e) {
    console.warn(`清理规则异常: ${e}`);
  }
}

/** 按「规则名称」搜索定位列表行（列表分页不保证新规则落在首页，搜索最稳）。 */
async function searchRuleRow(page: Page, name: string) {
  const pane = page.locator("#pane-rule");
  await pane.getByPlaceholder("请输入规则名称").fill(name);
  await pane.getByRole("button", { name: "搜索" }).click();
  const row = pane.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  return row;
}

/** 唯一规则名，避免与历史数据冲突（后端无按名去重）。 */
const RULE_NAME = `SP5A E2E 区域入侵 ${Date.now()}`;

/** 归一化 ROI 点列（与 RoiCanvas 画布相对位置一致）。 */
const ROI_POINTS: Array<[number, number]> = [
  [0.2, 0.2],
  [0.8, 0.2],
  [0.8, 0.8],
  [0.2, 0.8],
];

// 放大视口：对话框（960px）与 ROI 画布、条件树可完整入镜，便于视觉核对截图。
test.use({ viewport: { width: 1600, height: 1000 } });

test("规则编辑器：ROI 画布 + 条件树 创建并回填", async ({ page }) => {
  try {
    await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    await dismissTour(page);

    // 1. 切到「告警规则」页签（lazy 加载），打开新增对话框
    await page.getByRole("tab", { name: "告警规则" }).click();
    await page.getByRole("button", { name: /新增/ }).first().click({ force: true });
    const dialog = page.locator(".el-dialog");
    await expect(dialog).toBeVisible();

    // 2. 选择业务场景 DET_ZONE（场景码即告警类型）
    await dialog.locator('[data-testid="rule-scene-select"]').click();
    const sceneOption = page.getByRole("option", { name: /DET_ZONE/ }).first();
    await expect(sceneOption).toBeVisible({ timeout: 15_000 });
    await sceneOption.click();

    // 3. 场景默认规则回填：条件树应有 1 个叶子（object_present）
    const ruleRows = dialog.locator(".condition-tree .wx-rule");
    await expect(ruleRows).toHaveCount(1);

    // 4. ROI 画布点 4 个点（归一化坐标由组件换算，点击位置按画布相对比例）
    const canvas = dialog.locator(".roi-canvas__stage canvas").first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box, "ROI 画布应有可见尺寸").not.toBeNull();
    for (const [rx, ry] of ROI_POINTS) {
      await canvas.click({ position: { x: box!.width * rx, y: box!.height * ry } });
    }

    // 5. 条件树新增一个 object_present 叶子（第三方 FilterBuilder：默认字段即首个能力叶子）
    await dialog.locator(".condition-tree").getByRole("button", { name: "Add filter" }).click();
    const editor = page.locator(".wx-filter-editor").first();
    await expect(editor).toBeVisible();
    await editor.locator(".wx-text input").fill("person");
    await editor.getByRole("button", { name: "Apply" }).click();
    await expect(ruleRows).toHaveCount(2);

    // 保存前预览：2 个 object_present 叶子
    const previewTree = JSON.parse(await dialog.locator(".rule-editor__preview").innerText());
    expect(previewTree.children).toHaveLength(2);
    for (const leaf of previewTree.children) {
      expect(leaf.subject).toBe("object_present");
    }

    // 6. 填写规则名称 + 关联摄像机（后端 camera_id 必填），保存
    await dialog
      .locator(".el-form-item")
      .filter({ hasText: "规则名称" })
      .first()
      .locator("input")
      .fill(RULE_NAME);
    await dialog.locator('[data-testid="rule-camera-select"]').click();
    const cameraOption = page.locator(".el-select-dropdown__item:visible").first();
    await expect(cameraOption).toBeVisible();
    await cameraOption.click();
    await dialog.getByRole("button", { name: "保存" }).click();

    // 7. 保存成功：对话框关闭，按名称搜索定位新规则（避免历史数据分页干扰）
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    const row = await searchRuleRow(page, RULE_NAME);
    await expect(row).toContainText("DET_ZONE");

    // 8. 重新打开编辑：断言 ROI 点列与条件树回填一致
    await row.getByRole("button", { name: "编辑" }).click();
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".condition-tree .wx-rule")).toHaveCount(2);

    const editTree = JSON.parse(await dialog.locator(".rule-editor__preview").innerText());
    expect(editTree.children).toHaveLength(2);
    for (const leaf of editTree.children) {
      expect(leaf.subject).toBe("object_present");
      expect(leaf.label).toBe("person");
      // ROI 4 点经 params.roi 编译注入 region，回填后点数一致
      expect(leaf.region).toHaveLength(ROI_POINTS.length);
      // 场景参数（置信度默认值）同样回填
      expect(leaf.min_confidence).toBe(0.4);
    }
    await expect(dialog.locator(".roi-canvas__stage canvas").first()).toBeVisible();

    // 9. 视觉核对截图：编辑态对话框（含 ROI 多边形与条件树）+ 页面框架，便于与既有模块风格对比
    await page.screenshot({ path: "../docs/superpowers/runbooks/sp5a-visual/rule-editor.png" });
  } finally {
    await deleteRuleByName(page, RULE_NAME);
  }
});
