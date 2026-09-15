import { test, expect, type Page } from "@playwright/test";

/**
 * SP6-a 规则作用域 + 跨相机聚合叶子 e2e：登录态（auth.setup 提供）→ 告警页「告警规则」页签
 * → 打开组规则编辑框 → 断言作用域为「相机组」且列表展示组名 → 条件树配置 group_count 叶子并保存
 * → 再次打开断言叶子回填 → 切回「相机」作用域，断言 group_count/group_coverage 从
 * 条件树字段候选中消失（作用域过滤要求）→ 结束时清理规则与相机组。
 *
 * 种子策略：相机组与「组规则」经 API 创建。之所以规则也走 API：group_count 的必填键
 * `window_sec`/`value` 在编译层由 params 的 `group_window_sec`/`group_count` 注入，而当前
 * 场景目录没有任何场景声明这两个参数键，UI 的「新增」对话框无法产出它们（详见 runbook）。
 * 因此用例预置带 `{group_window_sec, group_count}` 参数的规则，再由 UI 完成叶子配置与保存。
 */

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";
const API_BASE = `${BASE_URL.replace(/\/web\/?$/, "")}/api/v1`;

const STAMP = Date.now();
const GROUP_NAME = `SP6A E2E 相机组 ${STAMP}`;
const RULE_NAME = `SP6A E2E 组规则 ${STAMP}`;
/** 组叶子必需参数：编译层由这两个场景参数注入 window_sec / value（见 scene/compile.py） */
const GROUP_PARAMS = { group_window_sec: 10, group_count: 2 };

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

/** 经 API 造一个相机组 + 一条组作用域规则（带组叶子所需参数），返回 id 供清理。 */
async function seedGroupRule(page: Page) {
  const headers = await authHeaders(page);

  const gRes = await page.request.post(`${API_BASE}/video/camera/group/create`, {
    headers,
    data: { name: GROUP_NAME },
  });
  expect(gRes.ok(), `创建相机组失败: ${gRes.status()} ${await gRes.text()}`).toBeTruthy();
  const groupId = (await gRes.json()).data.id as number;

  const rRes = await page.request.post(`${API_BASE}/video/alarm/rule/create`, {
    headers,
    data: {
      name: RULE_NAME,
      group_id: groupId,
      alarm_type: "GATHER",
      severity: "WARNING",
      interval_seconds: 30,
      status: true,
      params: GROUP_PARAMS,
      conditions: null,
    },
  });
  expect(rRes.ok(), `创建组规则失败: ${rRes.status()} ${await rRes.text()}`).toBeTruthy();
  const ruleId = (await rRes.json()).data.id as number;
  expect(ruleId, "规则 id 应已落库").toBeTruthy();
  return { groupId, ruleId };
}

/** 清理种子产生的规则与相机组（失败仅打印告警，不影响用例结论）。 */
async function cleanup(page: Page, ruleId: number, groupId: number) {
  try {
    const headers = await authHeaders(page);
    const rRes = await page.request.delete(`${API_BASE}/video/alarm/rule/delete`, {
      headers,
      data: [ruleId],
    });
    if (!rRes.ok()) console.warn(`清理规则失败: ${rRes.status()} ${await rRes.text()}`);
    const gRes = await page.request.delete(`${API_BASE}/video/camera/group/delete`, {
      headers,
      data: [groupId],
    });
    if (!gRes.ok()) console.warn(`清理相机组失败: ${gRes.status()} ${await gRes.text()}`);
  } catch (e) {
    console.warn(`清理异常: ${e}`);
  }
}

/** 打开条件树「Add filter」的字段下拉，返回可见选项弹层（`.wx-popup`）。 */
async function openFieldPicker(page: Page, dialog: ReturnType<Page["locator"]>) {
  const conditionTree = dialog.locator(".condition-tree");
  await conditionTree.locator(".wx-filter-builder").waitFor({ timeout: 15_000 });
  const addFilter = conditionTree.getByRole("button", { name: "Add filter" });
  if (await addFilter.count()) await addFilter.click();
  const editor = page.locator(".wx-filter-editor").first();
  await editor.waitFor({ timeout: 15_000 });
  await editor.locator(".wx-richselect").first().click();
  const popup = page.locator(".wx-popup:visible").first();
  await popup.waitFor({ timeout: 15_000 });
  return { editor, popup };
}

/**
 * 定位规则行：规则列表按 id 升序、默认 10 条/页，本次种子规则位于末页。
 * 后端 `name` 过滤形参未生效（AlarmRuleQueryParam 只存普通属性），故逐页翻找。
 */
async function locateRuleRow(page: Page, name: string) {
  const pane = page.locator("#pane-rule");
  const row = pane.locator(".el-table__row").filter({ hasText: name }).first();
  await pane.locator(".el-table__row").first().waitFor({ timeout: 15_000 });
  const next = pane.locator(".el-pagination .btn-next");
  for (let i = 0; i < 30; i++) {
    if (await row.count()) break;
    if (await next.isDisabled().catch(() => true)) break;
    await next.click();
    await page.waitForTimeout(500);
  }
  return row;
}

/**
 * 在字段下拉弹层中选中指定字段（用方向键 + Enter）。
 * 弹层末项超出可视区且被对话框层级遮挡，鼠标点击不可达，故用键盘导航；
 * 通过 `.wx-focus` 高亮确认命中目标字段，避免依赖固定项序号。
 */
async function selectFieldByLabel(page: Page, fieldLabel: string) {
  const popup = page.locator(".wx-popup:visible").first();
  await popup.waitFor({ timeout: 15_000 });
  const items = (await popup.locator(".wx-item").allInnerTexts()).map((s) => s.trim());
  for (let i = 0; i < items.length + 2; i++) {
    await page.keyboard.press("ArrowDown");
    const focused = (await popup.locator(".wx-item.wx-focus").first().innerText().catch(() => ""))
      .trim();
    if (focused === fieldLabel) break;
  }
  await page.keyboard.press("Enter");
}

// 放大视口：960px 对话框内的条件树与字段下拉可完整入镜，便于视觉核对截图。
test.use({ viewport: { width: 1600, height: 1000 } });

test("规则作用域：组规则列表展示组名 + 相机作用域隐藏聚合叶子", async ({ page }) => {
  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const { groupId, ruleId } = await seedGroupRule(page);
  try {
    // 种子在首次加载后创建，重载页面以重新拉取相机组列表（列表「作用域」列依赖组名解析）
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    await dismissTour(page);

    // 1. 切到「告警规则」页签（lazy 加载）
    await page.getByRole("tab", { name: "告警规则" }).click();

    // 2. 翻页定位本次种子规则
    const row = await locateRuleRow(page, RULE_NAME);

    // 3. 列表「作用域」列展示相机组名
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row).toContainText(`相机组：${GROUP_NAME}`);

    // 4. 打开编辑：作用域为「相机组」，组下拉回填组名
    await row.getByRole("button", { name: "编辑" }).click();
    const dialog = page.locator(".el-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".rule-editor .el-radio.is-checked")).toContainText("相机组");
    await expect(
      dialog.locator(".el-form-item").filter({ hasText: "关联相机组" }).first()
    ).toContainText(GROUP_NAME);

    // 5. 相机组作用域下，字段候选含 group_count / group_coverage
    const { editor, popup } = await openFieldPicker(page, dialog);
    await expect(popup.locator('.wx-item[data-id=":group_count"]')).toBeVisible();
    await expect(popup.locator('.wx-item[data-id=":group_coverage"]')).toBeVisible();

    // 6. 选 group_count 叶子 + 填值 + Apply，条件树出现该叶子
    await selectFieldByLabel(page, "组内目标总数");
    await expect(editor.locator(".wx-richselect .wx-label").first()).toHaveText("组内目标总数");
    await editor.locator("input").first().fill("2");
    await editor.getByRole("button", { name: "Apply" }).click();
    const ruleRows = dialog.locator(".condition-tree .wx-rule");
    await expect(ruleRows).toHaveCount(1);
    const previewTree = JSON.parse(await dialog.locator(".rule-editor__preview").innerText());
    expect(previewTree.children[0].subject).toBe("group_count");

    // 7. 视觉核对截图：作用域=相机组 + group_count 叶子可见
    // 上面的交互会把对话框滚动到条件树处，先复位滚动，保证「作用域」与叶子同框
    await page.evaluate(() => {
      document
        .querySelectorAll(".el-overlay, .el-overlay-dialog, .el-dialog__body")
        .forEach((el) => (el.scrollTop = 0));
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "../docs/superpowers/runbooks/sp6a-visual/rule-editor-group-scope.png",
    });

    // 8. 保存 → 对话框关闭，列表仍展示组名作用域
    await dialog.getByRole("button", { name: "保存" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    const savedRow = await locateRuleRow(page, RULE_NAME);
    await expect(savedRow).toBeVisible({ timeout: 15_000 });
    await expect(savedRow).toContainText(`相机组：${GROUP_NAME}`);

    // 9. 重新打开：group_count 叶子回填
    await savedRow.getByRole("button", { name: "编辑" }).click();
    await expect(dialog).toBeVisible();
    await expect(ruleRows).toHaveCount(1);
    const refillTree = JSON.parse(await dialog.locator(".rule-editor__preview").innerText());
    expect(refillTree.children[0].subject).toBe("group_count");

    // 10. 切回「相机」作用域：组聚合叶子从条件树与字段候选中消失（作用域过滤要求）
    await dialog.locator(".el-radio").filter({ hasText: "相机" }).first().click();
    await expect(ruleRows).toHaveCount(0);
    const strippedTree = JSON.parse(await dialog.locator(".rule-editor__preview").innerText());
    expect(JSON.stringify(strippedTree)).not.toContain("group_count");

    const cameraPicker = await openFieldPicker(page, dialog);
    await expect(cameraPicker.popup.locator('.wx-item[data-id=":object_present"]')).toBeVisible();
    await expect(cameraPicker.popup.locator('.wx-item[data-id=":group_count"]')).toHaveCount(0);
    await expect(cameraPicker.popup.locator('.wx-item[data-id=":group_coverage"]')).toHaveCount(0);

    // 关闭对话框（相机作用域不落库，避免破坏种子规则的组作用域）
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  } finally {
    await cleanup(page, ruleId, groupId);
  }
});
