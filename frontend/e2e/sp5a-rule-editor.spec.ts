import { test, expect, type Page } from "@playwright/test";

/**
 * SP5-a 规则编辑器 e2e：登录态（auth.setup 提供）→ 告警页「告警规则」页签 → 新建规则
 * → 选场景 DET_ZONE → ROI 画布点 4 点 → 条件树新增 object_present 叶子 → 保存
 * → 列表出现新规则 → 重新打开编辑 → 断言 ROI 点列与条件树回填一致。
 *
 * 说明：后端无 `/rule/detail/{id}`，编辑态由列表接口回填；ROI 经参数编译层注入
 * `conditions[].region`，故「条件预览」即为 ROI + 条件树回填的权威断言点。
 */

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
  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 1. 切到「告警规则」页签（lazy 加载），打开新增对话框
  await page.getByRole("tab", { name: "告警规则" }).click();
  await page.getByRole("button", { name: /新增/ }).first().click({ force: true });
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();

  // 2. 选择业务场景 DET_ZONE（场景码即告警类型）
  await dialog.locator(".rule-editor .el-select").first().click();
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
  await dialog
    .locator(".el-form-item")
    .filter({ hasText: "关联摄像机" })
    .first()
    .locator(".el-select")
    .click();
  const cameraOption = page.locator(".el-select-dropdown__item:visible").first();
  await expect(cameraOption).toBeVisible();
  await cameraOption.click();
  await dialog.getByRole("button", { name: "保存" }).click();

  // 7. 保存成功：对话框关闭，列表出现新规则
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  const row = page.locator(".el-table__row").filter({ hasText: RULE_NAME }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
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
});
