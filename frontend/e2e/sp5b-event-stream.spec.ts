import { test, expect, type Page } from "@playwright/test";

/**
 * SP5-b 边缘事件流 e2e：登录态（auth.setup 提供）→ 打开边缘事件页 → 历史视图展示
 * 由 HTTP 检测回调真实落库的种子事件 → 点击行打开详情抽屉 → 断言检测目标与
 * 「命中叶子」（matched_leaves）高亮标签可见。
 *
 * 种子策略：先经规则接口建一条含条件树的规则（保证命中叶子非空），再走内部回调
 * `/video/algorithm/detection/callback` 落库事件；用例结束清理规则与告警记录。
 * 视频路由限流 5 次/10s 且按路由分桶，本用例调用稀疏，不会触发 429。
 */

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";
const API_BASE = `${BASE_URL.replace(/\/web\/?$/, "")}/api/v1`;
/** 内部推理回调节点共享密钥（dev 默认值，见 backend/env/.env.dev） */
const CALLBACK_TOKEN = "infer_callback_shared_secret";

const STAMP = Date.now();
/** 唯一算法场景码：隔离历史遗留规则，避免 pick_alarm_rule 命中旧规则 */
const ALARM_TYPE = `SP5B_E2E_DET_ZONE_${STAMP}`;
const RULE_NAME = `SP5B E2E 边缘事件规则 ${STAMP}`;
const EVENT_ID = `sp5b-e2e-${STAMP}`;
const DETECTION = {
  label: "person",
  confidence: 0.93,
  bbox: { x: 0.4, y: 0.4, width: 0.2, height: 0.2 },
  track_id: 1,
};

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

/** 造一条含命中叶子的边缘事件；返回规则/告警 ID 供用例结束清理。 */
async function seedEdgeEvent(page: Page) {
  const headers = await authHeaders(page);

  const camRes = await page.request.get(`${API_BASE}/video/camera/list?page_no=1&page_size=1`, {
    headers,
  });
  expect(camRes.ok(), `相机列表请求失败: ${camRes.status()}`).toBeTruthy();
  const cameraId = (await camRes.json()).data.items[0].id as number;

  const ruleRes = await page.request.post(`${API_BASE}/video/alarm/rule/create`, {
    headers,
    data: {
      name: RULE_NAME,
      camera_id: cameraId,
      alarm_type: ALARM_TYPE,
      severity: "WARNING",
      interval_seconds: 0,
      conditions: { op: "and", children: [{ subject: "object_present", label: "person" }] },
      status: true,
    },
  });
  expect(ruleRes.ok(), `创建规则失败: ${ruleRes.status()} ${await ruleRes.text()}`).toBeTruthy();
  const ruleId = (await ruleRes.json()).data.id as number;

  const cbRes = await page.request.post(`${API_BASE}/video/algorithm/detection/callback`, {
    headers: { Authorization: `Bearer ${CALLBACK_TOKEN}` },
    data: {
      event_id: EVENT_ID,
      edge_code: "e2e-edge",
      camera_id: cameraId,
      algorithm_type: ALARM_TYPE,
      ts: new Date().toISOString(),
      objects: [DETECTION],
      detections: [DETECTION],
      latency_ms: 12.3,
    },
  });
  expect(cbRes.ok(), `检测回调失败: ${cbRes.status()} ${await cbRes.text()}`).toBeTruthy();
  const cb = (await cbRes.json()).data;
  expect(cb.alarm_created).toBeTruthy();
  return { ruleId, alarmId: cb.alarm_id as number };
}

/** 清理种子产生的规则与告警记录（失败不影响用例结论，仅打印告警）。 */
async function cleanup(page: Page, ruleId: number, alarmId?: number) {
  try {
    const headers = await authHeaders(page);
    if (alarmId) {
      const recRes = await page.request.delete(`${API_BASE}/video/alarm/record/delete`, {
        headers,
        data: [alarmId],
      });
      if (!recRes.ok()) {
        console.warn(`清理告警失败: ${recRes.status()} ${await recRes.text()}`);
      }
    }
    const ruleRes = await page.request.delete(`${API_BASE}/video/alarm/rule/delete`, {
      headers,
      data: [ruleId],
    });
    if (!ruleRes.ok()) {
      console.warn(`清理规则失败: ${ruleRes.status()} ${await ruleRes.text()}`);
    }
  } catch (e) {
    console.warn(`清理异常: ${e}`);
  }
}

// 放大视口：详情抽屉与检测表格可完整入镜，便于视觉核对截图。
test.use({ viewport: { width: 1600, height: 1000 } });

test("边缘事件流：历史详情展示检测目标与命中叶子高亮", async ({ page }) => {
  await page.goto("/#/video/event-stream", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const { ruleId, alarmId } = await seedEdgeEvent(page);
  try {
    // 切到「历史」视图（PageContent 懒挂载，由 nextTick 触发首屏查询）
    await page
      .locator(".edge-event-switch__bar .el-radio-button")
      .filter({ hasText: "历史" })
      .click();
    await expect(page.locator(".edge-event-switch__count")).toContainText("按筛选条件查询历史事件");

    // 历史列表默认按 id 倒序，刚落库的事件位于首行
    const row = page.locator(".el-table__row").first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row).toContainText("person");
    await expect(row).toContainText("命中");

    // 点击行 → 详情抽屉
    await row.click();
    const drawer = page.locator(".el-drawer:visible").first();
    await expect(drawer).toBeVisible({ timeout: 15_000 });

    // 检测目标：label 与置信度
    await expect(drawer.locator(".event-detail__title", { hasText: "检测目标" })).toBeVisible();
    const detRow = drawer.locator(".el-table__row").filter({ hasText: "person" }).first();
    await expect(detRow).toContainText("0.930");

    // 命中叶子高亮标签：路径 and/0 + 明细 person conf=0.93
    await expect(drawer.locator(".event-detail__title", { hasText: "命中叶子" })).toBeVisible();
    const leafTag = drawer.locator(".event-detail__leaves .el-tag").first();
    await expect(leafTag).toBeVisible();
    await expect(leafTag).toContainText("and/0");
    await expect(leafTag).toContainText("person conf=0.93");

    // 视觉核对截图（抽屉打开态）
    await page.screenshot({
      path: "../docs/superpowers/runbooks/sp5b-visual/event-stream-detail.png",
    });
  } finally {
    await cleanup(page, ruleId, alarmId);
  }
});
