import { test, expect, type Page } from "@playwright/test";

/**
 * SP6-b 规则灰度 e2e：登录态（auth.setup 提供）→ 告警页「告警规则」页签 → 新增规则
 * → 配置灰度（生效时段「工作日 08-18」+ 比例 30 + 白名单 1 台相机）→ 保存
 * → 列表「灰度」列出现摘要（30% / 白名单 1 台 / 周一至周五 08:00-18:00）
 * → 重新打开编辑断言回填一致（滑块 30%、白名单选中同一相机、时段 50 个激活格）
 * → 截图供视觉核对。
 *
 * 第二用例覆盖交集守卫：同一台相机同时选入白名单与黑名单 → 行内提示冲突且提交被拦截
 * （不产生任何创建请求、不落库）。
 *
 * 说明：后端无 `/rule/detail/{id}`，编辑态由列表接口回填（与 SP5-a 一致）；
 * 规则名带时间戳，列表用「规则名称」搜索定位（避免翻页）。视频模块路由限流 5 次/10s
 * 且按「(客户端 IP, 路由)」计数，故每个用例使用独立 `X-Forwarded-For` 与其它用例隔离，
 * 并尽量复用接口返回值减少请求（清理按 id 删除，不再二次查询列表）。
 */

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";
const API_BASE = `${BASE_URL.replace(/\/web\/?$/, "")}/api/v1`;

const STAMP = Date.now();
const RULE_NAME = `SP6B E2E 灰度规则 ${STAMP}`;
const CONFLICT_RULE_NAME = `SP6B E2E 冲突规则 ${STAMP}`;

/** 生效时段「工作日 08-18」= 5 天 × 10 小时 = 50 个激活格 */
const WORK_HOURS_CELLS = 50;
/** 灰度比例目标值（滑块默认 100，逐次递减到 30） */
const ROLLOUT_PERCENT = 30;

const SCREENSHOT_DIR = "../docs/superpowers/runbooks/sp6b-visual";

/** 当前用例的伪造客户端 IP（后端限流按 X-Forwarded-For 首段计数；用例间相互隔离） */
let clientIp = "10.66.11.1";

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

/** 读取登录态 access_token（localStorage 中以 JSON 字符串保存）并附带限流隔离头。 */
async function authHeaders(page: Page) {
  const raw = await page.evaluate(() => window.localStorage.getItem("access_token"));
  const token = raw ? (JSON.parse(raw) as string) : "";
  return { Authorization: `Bearer ${token}`, "X-Forwarded-For": clientIp };
}

/** 按 id 删除规则（失败仅打印告警，不影响用例结论）。 */
async function deleteRulesById(page: Page, ids: number[]) {
  if (!ids.length) return;
  try {
    const headers = await authHeaders(page);
    const res = await page.request.delete(`${API_BASE}/video/alarm/rule/delete`, {
      headers,
      data: ids,
    });
    if (!res.ok()) console.warn(`清理规则失败: ${res.status()} ${await res.text()}`);
  } catch (e) {
    console.warn(`清理规则异常: ${e}`);
  }
}

/**
 * 进入告警页并切到「告警规则」页签（lazy 挂载），返回其 tab pane 容器。
 * 同时把当前用例的伪造 IP 注入页面请求头，避免与其它用例共享限流计数。
 */
async function openRuleTab(page: Page, ip: string) {
  clientIp = ip;
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": clientIp });
  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await page.getByRole("tab", { name: "告警规则" }).click();
  const pane = page.locator("#pane-rule");
  await expect(pane.locator(".el-table").first()).toBeVisible({ timeout: 15_000 });
  return pane;
}

/** 打开新增规则对话框。 */
async function openCreateDialog(page: Page, pane: ReturnType<Page["locator"]>) {
  await pane.getByRole("button", { name: /新增/ }).first().click({ force: true });
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

/** 填写规则名称。 */
async function fillRuleName(dialog: ReturnType<Page["locator"]>, name: string) {
  await dialog
    .locator(".el-form-item")
    .filter({ hasText: "规则名称" })
    .first()
    .locator("input")
    .fill(name);
}

/** 在单选框（相机）中选中第一台相机，返回其显示名。 */
async function selectFirstCamera(page: Page, dialog: ReturnType<Page["locator"]>): Promise<string> {
  await dialog.locator('[data-testid="rule-camera-select"]').click();
  return pickFirstOption(page);
}

/** 在多选下拉（白/黑名单）中选中第一项，返回其显示名。 */
async function selectFirstInMulti(page: Page, testid: string): Promise<string> {
  await page.locator(`[data-testid="${testid}"]`).click();
  return pickFirstOption(page);
}

/** 点击当前展开下拉的第一项（多选下不自动收起，需 Escape 关闭）。 */
async function pickFirstOption(page: Page): Promise<string> {
  const option = page.locator(".el-select-dropdown__item:visible").first();
  await expect(option).toBeVisible({ timeout: 15_000 });
  const name = (await option.innerText()).trim();
  await option.click();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  return name;
}

/** 点击「工作日 08-18」预设，写入生效时段（周一至周五 08:00-18:00）。 */
async function pickWorkHours(dialog: ReturnType<Page["locator"]>) {
  await dialog.getByRole("button", { name: "工作日 08-18" }).click();
  await expect(dialog.locator(".schedule-cell.active")).toHaveCount(WORK_HOURS_CELLS);
}

/**
 * 设置灰度比例：滑块默认 100（全量），聚焦滑块按钮包裹层后用方向键逐格递减到目标值
 * （鼠标点击滑轨只能近似定位，键盘路径可精确到整数）。
 * 注意：可聚焦并承载 keydown 的是 `.el-slider__button-wrapper`，内层 `.el-slider__button` 不可聚焦。
 */
async function setRolloutPercent(page: Page, dialog: ReturnType<Page["locator"]>, percent: number) {
  await dialog.locator('[data-testid="rule-rollout-percent"] .el-slider__button-wrapper').focus();
  for (let i = 0; i < 100 - percent; i++) await page.keyboard.press("ArrowLeft");
  await expect(dialog.locator(".rollout-percent__value")).toHaveText(`${percent}%`);
}

/** 经「规则名称」搜索定位列表行（规则列表按 id 升序、分页 10 条，搜索最稳）。 */
async function searchRuleRow(page: Page, pane: ReturnType<Page["locator"]>, name: string) {
  await pane.getByPlaceholder("请输入规则名称").fill(name);
  await pane.getByRole("button", { name: "搜索" }).click();
  const row = pane.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  return row;
}

/** 把「灰度」区块滚动到对话框可视区顶部（对话框超出一屏，外层 overlay 可滚动）。 */
async function scrollRolloutSectionIntoView(page: Page) {
  await page.evaluate(() => {
    const divider = Array.from(document.querySelectorAll(".el-divider")).find((el) =>
      (el.textContent || "").includes("灰度")
    );
    if (!divider) return;
    let node: HTMLElement | null = (divider as HTMLElement).parentElement;
    while (node) {
      const style = window.getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
        const delta = divider.getBoundingClientRect().top - node.getBoundingClientRect().top;
        node.scrollTop += delta - 16;
        return;
      }
      node = node.parentElement;
    }
  });
  await page.waitForTimeout(300);
}

// 放大视口：960px 对话框内的灰度区块（时段网格 + 比例 + 白名单）可完整入镜
test.use({ viewport: { width: 1600, height: 1000 } });

test("规则灰度：比例 30 + 白名单 + 生效时段 保存与回填一致", async ({ page }) => {
  let ruleId: number | undefined;
  const pane = await openRuleTab(page, "10.66.11.1");
  try {
    const dialog = await openCreateDialog(page, pane);

    // 1. 规则名称 + 关联摄像机（相机作用域必填）
    await fillRuleName(dialog, RULE_NAME);
    await selectFirstCamera(page, dialog);

    // 2. 生效时间段：工作日 08-18（50 个激活格），并断言时段网格落在可视区
    await pickWorkHours(dialog);

    // 3. 灰度比例 30
    await setRolloutPercent(page, dialog, ROLLOUT_PERCENT);

    // 4. 相机白名单（1 台）
    const whiteName = await selectFirstInMulti(page, "rule-rollout-whitelist");
    expect(whiteName, "白名单应选中一台相机").toBeTruthy();
    await expect(dialog.locator('[data-testid="rule-rollout-whitelist"]')).toContainText(whiteName);
    await expect(dialog.locator(".rule-editor__field-error")).toHaveCount(0);

    // 5. 视觉核对截图：灰度区块（时段网格 + 比例 30% + 白名单 1 台）同框
    await scrollRolloutSectionIntoView(page);
    const viewport = page.viewportSize()!;
    for (const selector of [
      ".schedule-grid-wrapper",
      ".rollout-percent",
      '[data-testid="rule-rollout-whitelist"]',
    ]) {
      const box = await dialog.locator(selector).first().boundingBox();
      expect(box, `${selector} 应有可见尺寸`).not.toBeNull();
      expect(box!.y, `${selector} 应落在视口内`).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height, `${selector} 应落在视口内`).toBeLessThanOrEqual(viewport.height);
    }
    await page.screenshot({ path: `${SCREENSHOT_DIR}/rule-editor-rollout.png` });

    // 6. 保存 → 断言创建接口 200 并记录 id 供清理
    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/video/alarm/rule/create") && r.request().method() === "POST"
      ),
      dialog.getByRole("button", { name: "保存" }).click(),
    ]);
    expect(createResp.status(), await createResp.text()).toBe(200);
    ruleId = (await createResp.json()).data.id as number;
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    // 7. 列表「灰度」列展示摘要：30% · 白名单 1 台 · 周一至周五 08:00-18:00
    const row = await searchRuleRow(page, pane, RULE_NAME);
    await expect(row).toContainText(`${ROLLOUT_PERCENT}%`);
    await expect(row).toContainText("白名单 1 台");
    await expect(row).toContainText("周一至周五 08:00-18:00");

    // 8. 重新打开编辑：灰度配置回填一致（比例 / 白名单 / 生效时段）
    await row.getByRole("button", { name: "编辑" }).click();
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".rollout-percent__value")).toHaveText(`${ROLLOUT_PERCENT}%`);
    await expect(dialog.locator('[data-testid="rule-rollout-whitelist"]')).toContainText(whiteName);
    await expect(dialog.locator(".schedule-cell.active")).toHaveCount(WORK_HOURS_CELLS);

    // 关闭（不产生更新请求）
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  } finally {
    await deleteRulesById(page, ruleId ? [ruleId] : []);
  }
});

test("灰度交集守卫：同相机同时选入白/黑名单 → 提示冲突并阻止提交", async ({ page }) => {
  /** 兜底清理用：正常情况下该列表为空 */
  let leftoverIds: number[] = [];
  const pane = await openRuleTab(page, "10.66.11.2");
  try {
    const dialog = await openCreateDialog(page, pane);
    await fillRuleName(dialog, CONFLICT_RULE_NAME);
    await selectFirstCamera(page, dialog);

    // 两个名单各选「第一项」→ 同一台相机
    const whiteName = await selectFirstInMulti(page, "rule-rollout-whitelist");
    const blackName = await selectFirstInMulti(page, "rule-rollout-blacklist");
    expect(whiteName, "白/黑名单首项应为同一台相机").toBe(blackName);

    // 1. 行内冲突提示
    const fieldError = dialog.locator(".rule-editor__field-error");
    await expect(fieldError).toBeVisible();
    await expect(fieldError).toContainText("冲突");

    // 2. 提交被拦截：点击保存后对话框不关闭，顶部 alert 展示冲突原因
    await dialog.getByRole("button", { name: "保存" }).click();
    const alert = dialog.locator(".rule-editor__error");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("冲突");
    await expect(dialog).toBeVisible();

    // 3. 关闭并确认未落库
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    const headers = await authHeaders(page);
    const res = await page.request.get(`${API_BASE}/video/alarm/rule/list`, {
      headers,
      params: { name: CONFLICT_RULE_NAME, page_size: 50 },
    });
    const items = (await res.json()).data.items as Array<{ id: number; name: string }>;
    const conflictRows = items.filter((x) => x.name === CONFLICT_RULE_NAME);
    expect(conflictRows).toHaveLength(0);
    leftoverIds = conflictRows.map((x) => x.id);
  } finally {
    await deleteRulesById(page, leftoverIds);
  }
});
