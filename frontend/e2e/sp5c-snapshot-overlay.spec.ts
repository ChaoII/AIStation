import { test, expect, type Page } from "@playwright/test";
import { unlink } from "node:fs/promises";
import { deflateSync } from "node:zlib";

/**
 * SP5-c 快照叠加查看器 e2e：登录态（auth.setup 提供）→ 造一条**带真实内联快照**的
 * 边缘事件（经内部回调 `/video/algorithm/detection/callback`，同步创建告警记录）→
 * 打开告警详情抽屉与事件流详情抽屉 → 断言 `[data-testid="snapshot-overlay"]` 存在、
 * `data-box-count` 等于 `objects` 数量、`data-image-loaded="true"`（底图真实加载）。
 *
 * 种子策略（复用 sp5b 的登录/导航手法）：
 * - 先建一条含条件树（object_present person）的规则，保证命中非空；
 * - 回调 body 携带 `snapshot: { ref, data }`（内联 base64 PNG）→ 后端落盘到
 *   `DETECTIONS_DIR/<ref>` 并写 `snapshot_path`；
 * - 同时显式传 `snapshot_ref = /api/v1/video/detections/<ref>`（即告警 `snapshot_url`
 *   的同款受保护相对路径），使事件流抽屉也能命中受保护快照路由。若只传对象存储 key
 *   （如 `edge/2026-09-15/x.jpg`），查看器会请求 `/api/v1/<key>` 而 404 —— 该集成
 *   缺口已在 `docs/superpowers/runbooks/sp5c-visual.md` 记录。
 *
 * 用例结束清理规则、告警记录与落盘快照；视频路由限流 5 次/10s 且按路由分桶，
 * 本用例调用稀疏，不会触发 429。
 */

const BASE_URL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";
const API_BASE = `${BASE_URL.replace(/\/web\/?$/, "")}/api/v1`;
/** 内部推理回调节点共享密钥（dev 默认值，见 backend/env/.env.dev） */
const CALLBACK_TOKEN = "infer_callback_shared_secret";

const STAMP = Date.now();
/** 唯一算法场景码：隔离历史遗留规则，避免 pick_alarm_rule 命中旧规则 */
const ALARM_TYPE = `SP5C_E2E_DET_ZONE_${STAMP}`;
const RULE_NAME = `SP5C E2E 快照叠加规则 ${STAMP}`;
const EVENT_ID = `sp5c-e2e-${STAMP}`;
/** 落盘文件名（相对 DETECTIONS_DIR） */
const SNAPSHOT_NAME = `sp5c-e2e-${STAMP}.png`;
/** 受保护快照相对路径（与告警记录 `snapshot_url` 同构） */
const SNAPSHOT_REF = `/api/v1/video/detections/${SNAPSHOT_NAME}`;

/** CRC32 查表（PNG chunk 校验用，Node 内置 zlib 不提供） */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const byte of buf) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/**
 * 构造 192x108 三色块 PNG（含橙色边框与网格线）并返回 base64。
 * 零依赖运行时生成，避免手抄 base64 出错；真实落盘后由后端
 * `/video/detections/...` 返回，用于验证底图加载与 letterbox 留边。
 */
function buildSnapshotPngBase64(): string {
  const W = 192;
  const H = 108;
  const raw = Buffer.alloc((W * 3 + 1) * H);
  let p = 0;
  for (let y = 0; y < H; y += 1) {
    raw[p++] = 0; // 行过滤器：none
    for (let x = 0; x < W; x += 1) {
      let rgb: [number, number, number];
      if (x < 3 || y < 3 || x >= W - 3 || y >= H - 3) rgb = [255, 80, 0];
      else if (x % 48 === 0 || y % 36 === 0) rgb = [235, 235, 235];
      else if (x < W / 3) rgb = [44, 82, 150];
      else if (x < (2 * W) / 3) rgb = [58, 122, 88];
      else rgb = [120, 66, 130];
      raw[p++] = rgb[0];
      raw[p++] = rgb[1];
      raw[p++] = rgb[2];
    }
  }
  const chunk = (tag: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(tag, "ascii"), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(body));
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0);
  ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; // 位深
  ihdr[9] = 2; // 颜色类型：truecolor
  const png = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
  return png.toString("base64");
}

const SNAPSHOT_B64 = buildSnapshotPngBase64();

/** 叠加对象（v2 `objects`）：2 个目标，含属性与 track_id，用于断言框数与渲染内容 */
const OBJECTS = [
  {
    label: "person",
    label_id: 0,
    confidence: 0.93,
    bbox: { x: 0.06, y: 0.12, width: 0.22, height: 0.62 },
    track_id: 7,
    attributes: { helmet: 0.12, vest: 0.88 },
  },
  {
    label: "car",
    label_id: 1,
    confidence: 0.81,
    bbox: { x: 0.55, y: 0.45, width: 0.36, height: 0.4 },
    track_id: 12,
    attributes: { color: "white" },
  },
];

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

/** 造一条带真实快照的边缘事件；返回规则/告警 ID 供用例结束清理。 */
async function seedEventWithSnapshot(page: Page) {
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
      snapshot_ref: SNAPSHOT_REF,
      snapshot: { ref: SNAPSHOT_NAME, data: SNAPSHOT_B64 },
      objects: OBJECTS,
      latency_ms: 12.3,
    },
  });
  expect(cbRes.ok(), `检测回调失败: ${cbRes.status()} ${await cbRes.text()}`).toBeTruthy();
  const cb = (await cbRes.json()).data;
  expect(cb.alarm_created).toBeTruthy();
  return { ruleId, alarmId: cb.alarm_id as number };
}

/** 清理种子产生的规则、告警记录与落盘快照（失败不影响用例结论，仅打印告警）。 */
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
  // 落盘快照位于 backend/data/detections/（相对 frontend 工作目录）
  await unlink(`../backend/data/detections/${SNAPSHOT_NAME}`).catch(() => {});
}

/** 断言叠加层渲染结果；`withImage` 为真时要求底图真实加载。 */
async function expectOverlay(scope: ReturnType<Page["locator"]>, withImage: boolean) {
  const overlay = scope.locator('[data-testid="snapshot-overlay"]');
  await expect(overlay).toBeVisible({ timeout: 15_000 });
  await expect(overlay).toHaveAttribute("data-box-count", String(OBJECTS.length));
  await expect(overlay).toHaveAttribute("data-image-loaded", withImage ? "true" : "false", {
    timeout: 15_000,
  });
  // Konva 舞台实际挂载（canvas 存在）
  await expect(overlay.locator("canvas").first()).toBeVisible();
  return overlay;
}

// 放大视口：详情抽屉与叠加舞台可完整入镜，便于视觉核对截图。
test.use({ viewport: { width: 1600, height: 1000 } });

test("快照叠加查看器：告警详情与事件流详情渲染检测框", async ({ page }) => {
  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const { ruleId, alarmId } = await seedEventWithSnapshot(page);
  try {
    // 种子在页面加载后落库，刷新列表让新告警（按 alarm_time 倒序）出现在首行
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    await dismissTour(page);

    const alarmRow = page.locator(".el-table__row").first();
    await expect(alarmRow).toBeVisible({ timeout: 15_000 });
    await expect(alarmRow).toContainText(ALARM_TYPE);
    await alarmRow.getByRole("button", { name: "详情" }).click();

    const alarmDrawer = page.locator(".el-drawer:visible").first();
    await expect(alarmDrawer).toBeVisible({ timeout: 15_000 });
    const alarmOverlay = await expectOverlay(alarmDrawer, true);
    await expect(alarmOverlay.getByText("快照叠加")).toBeVisible();

    await page.screenshot({
      path: "../docs/superpowers/runbooks/sp5c-visual/alarm-snapshot-overlay.png",
    });

    // 关闭告警抽屉，避免跨页面残留
    await alarmDrawer.locator(".el-drawer__close-btn").click();
    await expect(alarmDrawer).toBeHidden({ timeout: 10_000 });

    // ---- 事件流详情抽屉 ----
    await page.goto("/#/video/event-stream", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    await dismissTour(page);

    await page
      .locator(".edge-event-switch__bar .el-radio-button")
      .filter({ hasText: "历史" })
      .click();
    await expect(page.locator(".edge-event-switch__count")).toContainText("按筛选条件查询历史事件");

    const eventRow = page.locator(".el-table__row").first();
    await expect(eventRow).toBeVisible({ timeout: 15_000 });
    await expect(eventRow).toContainText("person");
    await eventRow.click();

    const eventDrawer = page.locator(".el-drawer:visible").first();
    await expect(eventDrawer).toBeVisible({ timeout: 15_000 });
    await expect(eventDrawer.locator(".event-detail__title", { hasText: "检测目标" })).toBeVisible();
    await expectOverlay(eventDrawer, true);

    await page.screenshot({
      path: "../docs/superpowers/runbooks/sp5c-visual/event-stream-snapshot-overlay.png",
    });
  } finally {
    await cleanup(page, ruleId, alarmId);
  }
});
