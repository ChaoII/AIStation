import { test, expect, type Page } from "@playwright/test";

/**
 * SP6-a 规则作用域 + 跨相机聚合叶子 e2e：登录态（auth.setup 提供）→ 告警页「告警规则」页签
 * → 打开组规则编辑框 → 断言作用域为「相机组」且列表展示组名 → 条件树配置 group_count 叶子并保存
 * → 再次打开断言叶子回填 → 切回「相机」作用域，断言 group_count/group_coverage 从
 * 条件树字段候选中消失（作用域过滤要求）→ 结束时清理规则与相机组。
 *
 * 种子策略：列表回填用例的「组规则」经 API 创建（仅需预置一条组作用域规则，用于断言
 * 列表作用域列与编辑回填）；而**纯 UI 新增组规则**路径由第二个用例覆盖：场景目录已声明
 * `group_window_sec`/`group_count`/`group_labels`，UI 可产出组叶子必填参数并保存成功。
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

/** 已创建资源句柄：创建即登记，保证 finally 能清理半途失败的残留。 */
interface Created {
  groupId?: number;
  ruleId?: number;
}

/** 经 API 造一个相机组 + 一条组作用域规则（带组叶子所需参数），id 同步登记到 created。 */
async function seedGroupRule(page: Page, created: Created) {
  const headers = await authHeaders(page);

  const gRes = await page.request.post(`${API_BASE}/video/camera/group/create`, {
    headers,
    data: { name: GROUP_NAME },
  });
  expect(gRes.ok(), `创建相机组失败: ${gRes.status()} ${await gRes.text()}`).toBeTruthy();
  const groupId = (await gRes.json()).data.id as number;
  created.groupId = groupId;

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
  created.ruleId = ruleId;
  return { groupId, ruleId };
}

/** 清理种子产生的规则与相机组（失败仅打印告警，不影响用例结论）。 */
async function cleanup(page: Page, ruleId?: number, groupId?: number) {
  try {
    const headers = await authHeaders(page);
    if (ruleId) {
      const rRes = await page.request.delete(`${API_BASE}/video/alarm/rule/delete`, {
        headers,
        data: [ruleId],
      });
      if (!rRes.ok()) console.warn(`清理规则失败: ${rRes.status()} ${await rRes.text()}`);
    }
    if (groupId) {
      const gRes = await page.request.delete(`${API_BASE}/video/camera/group/delete`, {
        headers,
        data: [groupId],
      });
      if (!gRes.ok()) console.warn(`清理相机组失败: ${gRes.status()} ${await gRes.text()}`);
    }
  } catch (e) {
    console.warn(`清理异常: ${e}`);
  }
}

/** 经 API 造一个相机组，返回 id 供清理（纯 UI 用例只预置组、不预置规则）。 */
async function seedGroup(page: Page, name: string): Promise<number> {
  const headers = await authHeaders(page);
  const res = await page.request.post(`${API_BASE}/video/camera/group/create`, {
    headers,
    data: { name },
  });
  expect(res.ok(), `创建相机组失败: ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()).data.id as number;
}

/** 按名称删除规则（纯 UI 用例的规则 id 需先查列表获得）。 */
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

/** 删除相机组（失败仅打印告警）。 */
async function deleteGroup(page: Page, groupId: number) {
  try {
    const headers = await authHeaders(page);
    const res = await page.request.delete(`${API_BASE}/video/camera/group/delete`, {
      headers,
      data: [groupId],
    });
    if (!res.ok()) console.warn(`清理相机组失败: ${res.status()} ${await res.text()}`);
  } catch (e) {
    console.warn(`清理相机组异常: ${e}`);
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
 * 定位规则行：改用「规则名称」搜索（列表分页下新规则不保证落在首页；
 * 后端 `name` 过滤为 like 语义，搜索最稳，也避免历史数据翻页导致的假失败）。
 */
async function locateRuleRow(page: Page, name: string) {
  const pane = page.locator("#pane-rule");
  await pane.getByPlaceholder("请输入规则名称").fill(name);
  await pane.getByRole("button", { name: "搜索" }).click();
  const row = pane.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  return row;
}

/**
 * 在字段下拉弹层中选中指定字段（方向键 + Enter）。
 * 保留键盘导航作为「弹层可用性」的独立探针：弹层层级/限高修复后鼠标同样可点，
 * 但键盘路径不受弹层定位影响，故此处继续用键盘以避免与第二个用例的鼠标验证重复。
 */
async function selectFieldByLabel(page: Page, fieldLabel: string) {
  const popup = page.locator(".wx-popup:visible").first();
  await popup.waitFor({ timeout: 15_000 });
  const items = (await popup.locator(".wx-item").allInnerTexts()).map((s) => s.trim());
  for (let i = 0; i < items.length + 2; i++) {
    await page.keyboard.press("ArrowDown");
    const focused = (
      await popup
        .locator(".wx-item.wx-focus")
        .first()
        .innerText()
        .catch(() => "")
    ).trim();
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

  const created: Created = {};
  try {
    await seedGroupRule(page, created);
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
    await expect(
      dialog.locator('[data-testid="rule-scope-select"] .el-radio.is-checked')
    ).toContainText("相机组");
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
    await dialog
      .locator('[data-testid="rule-scope-select"] .el-radio')
      .filter({ hasText: "相机" })
      .first()
      .click();
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
    await cleanup(page, created.ruleId, created.groupId);
  }
});

const PURE_UI_RULE_NAME = `SP6A E2E 纯UI组规则 ${STAMP}`;
const PURE_UI_GROUP_NAME = `SP6A E2E 纯UI相机组 ${STAMP}`;

/**
 * 缺陷修复回归（纯 UI 路径）：
 * 1) 场景目录声明 group_window_sec/group_count/group_labels → 组作用域下参数表单出现对应字段；
 * 2) 条件树字段下拉层级/限高修复 → 可**鼠标点击**选中断言项（group_count）；
 * 3) 「新增」对话框全程纯 UI（不预置 params）保存 → POST /video/alarm/rule/create 返回 200，
 *    组叶子必填键 window_sec/value 由目录参数默认值经编译层注入。
 */
test("纯 UI 新增组规则：组参数声明 + group_count 叶子鼠标选择 + 保存 200", async ({ page }) => {
  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  let groupId: number | undefined;
  try {
    groupId = await seedGroup(page, PURE_UI_GROUP_NAME);
    // 种子组在首次加载后创建，重载以刷新组下拉
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    await dismissTour(page);
    await page.getByRole("tab", { name: "告警规则" }).click();
    await page.getByRole("button", { name: /新增/ }).first().click({ force: true });

    const dialog = page.locator(".el-dialog");
    await expect(dialog).toBeVisible();

    // 1. 作用域切到「相机组」，选择本用例相机组
    await dialog
      .locator('[data-testid="rule-scope-select"] .el-radio')
      .filter({ hasText: "相机组" })
      .first()
      .click();
    await dialog.locator('[data-testid="rule-group-select"]').click();
    await page.getByRole("option", { name: PURE_UI_GROUP_NAME }).first().click();

    // 2. 选择场景 GATHER（目录已声明组聚合参数）
    await dialog.locator('[data-testid="rule-scene-select"]').click();
    await page
      .getByRole("option", { name: /GATHER/ })
      .first()
      .click();

    // 3. 组作用域参数表单出现（此前目录未声明，表单无字段 → 保存 400）
    await expect(dialog.getByText("组内目标数阈值").first()).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText("组聚合滑窗(秒)").first()).toBeVisible();

    // 4. 条件树新增 group_count 叶子：用鼠标点击字段下拉项（验证弹层层级/限高修复）
    const conditionTree = dialog.locator(".condition-tree");
    await conditionTree.locator(".wx-filter-builder").waitFor({ timeout: 15_000 });
    await conditionTree.getByRole("button", { name: "Add filter" }).click();
    const editor = page.locator(".wx-filter-editor").first();
    await editor.waitFor({ timeout: 15_000 });
    await editor.locator(".wx-richselect").first().click();
    const popup = page.locator(".wx-popup:visible").first();
    await popup.waitFor({ timeout: 15_000 });
    await page.screenshot({
      path: "C:/Users/aichao/AppData/Local/Temp/opencode/sp6a-defect2-popup.png",
    });
    // 鼠标点击（若被对话框层级遮挡，Playwright 可点击性检查会失败）
    await popup.locator('.wx-item[data-id=":group_count"]').click();
    await expect(editor.locator(".wx-richselect .wx-label").first()).toHaveText("组内目标总数");
    await editor.locator("input").first().fill("2");
    await editor.getByRole("button", { name: "Apply" }).click();

    // 5. 填写规则名称并保存，直接断言创建接口 HTTP 200
    await dialog
      .locator(".el-form-item")
      .filter({ hasText: "规则名称" })
      .first()
      .locator("input")
      .fill(PURE_UI_RULE_NAME);
    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/video/alarm/rule/create") && r.request().method() === "POST"
      ),
      dialog.getByRole("button", { name: "保存" }).click(),
    ]);
    expect(createResp.status(), await createResp.text()).toBe(200);
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    // 6. 落库校验：group_count 叶子的必填键由目录参数默认值注入
    const headers = await authHeaders(page);
    const listResp = await page.request.get(`${API_BASE}/video/alarm/rule/list`, {
      headers,
      params: { name: PURE_UI_RULE_NAME, page_size: 50 },
    });
    const items = (await listResp.json()).data.items as Array<{
      name: string;
      conditions: { children: Array<Record<string, unknown>> };
    }>;
    const found = items.find((x) => x.name === PURE_UI_RULE_NAME);
    expect(found, "纯 UI 组规则应已落库").toBeTruthy();
    const leaf = found!.conditions.children.find((c) => c.subject === "group_count");
    expect(leaf, "条件树应含 group_count 叶子").toBeTruthy();
    expect(leaf!.window_sec).toBe(10);
    expect(leaf!.value).toBe(2);
  } finally {
    await deleteRuleByName(page, PURE_UI_RULE_NAME);
    if (groupId) await deleteGroup(page, groupId);
  }
});
