import { test, expect } from "@playwright/test";
import { memberNames, mockDispatch, openOffice, readCam, spyFocus } from "./office-helpers";

/**
 * AI 办公室「体验打磨」回归（快速、确定性）：
 * 引导 / 输入增强 / 空态示例 / 镜头定位 / 快捷键 / 播报流 / 结论复制 / 粘底滚动 / 跟随限流。
 *
 * 派活用**假的 SSE 流**（见 office-helpers.mockDispatch），所以不调模型、不写库；
 * 帧间隔由用例控制，能精确验证「跟随执行者」的 3 秒限流。
 *
 * 跑法（需要前端 dev server + 带办公室接口的后端）：
 *   E2E_BASE_URL=http://127.0.0.1:5182/web E2E_API_URL=http://127.0.0.1:8011/api/v1 \
 *     pnpm e2e office-polish --no-deps
 *
 * 真链路的派活见 office-dispatch-real.spec.ts（需 E2E_OFFICE_DISPATCH=1）。
 */

test.use({ storageState: { cookies: [], origins: [] } });

/* 办公室要加载 3D 模型 + 等场景就位；引导那条还要 reload 一次（两次整页加载），
   机器忙的时候 90 秒会不够（实测偶发超时），给到 150 秒 */
test.describe.configure({ timeout: 150_000 });

test("引导：首次出现三步、关闭后不再自动出现、菜单可重看", async ({
  page,
  request,
  baseURL
}) => {
  await openOffice(page, request, baseURL!, { freshGuide: true });
  const card = page.locator(".guide-card");
  await expect(card).toBeVisible();
  const titles: string[] = [];
  for (let i = 0; i < 3; i++) {
    titles.push((await page.locator(".guide-card .g-t").innerText()).trim());
    await page.locator(".guide-card .g-foot button.primary").click();
    await page.waitForTimeout(150);
  }
  expect(new Set(titles).size).toBe(3);
  await expect(card).toBeHidden();

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-office-page")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".guide-card")).toHaveCount(0);

  await page.locator(".of-more button.of-ico").click();
  await page.locator(".of-menu button", { hasText: "重看引导" }).click();
  await expect(page.locator(".guide-card")).toBeVisible();
  await page.locator(".guide-card .g-foot button", { hasText: "跳过" }).click();
  await expect(page.locator(".guide-card")).toHaveCount(0);
});

test("输入：空内容禁用、Shift+Enter 换行、@成员 切单干", async ({ page, request, baseURL }) => {
  await openOffice(page, request, baseURL!);
  const send = page.locator("button.of-btn.primary", { hasText: "派活" });
  await expect(send).toBeDisabled();

  const box = page.locator(".of-bar-input");
  await box.fill("查一下数据集总数");
  await expect(send).toBeEnabled();

  await box.click();
  await box.press("Shift+Enter");
  await page.waitForTimeout(150);
  expect(await box.inputValue()).toContain("\n");
  await expect(page.locator(".brief-bar")).toHaveCount(0);

  const who = (await memberNames(page))[0];
  await box.fill(`@${who} 查一下数据集总数`);
  await page.waitForTimeout(300);
  await expect(page.locator(".of-picked")).toContainText(who);
  await expect(page.locator(".of-bar-input")).toHaveValue(/查一下数据集总数/);
});

test("空态：切到没有派活的那天，给 3 个示例任务且只填入不发送", async ({
  page,
  request,
  baseURL
}) => {
  await openOffice(page, request, baseURL!);
  await page.locator(".of-tab", { hasText: "任务" }).click();
  await page.locator(".of-dstep button[title='后一天']").click();
  await expect(page.locator(".of-samples .sample")).toHaveCount(3);
  await page.locator(".of-samples .sample").first().click();
  await page.waitForTimeout(200);
  expect((await page.locator(".of-bar-input").inputValue()).length).toBeGreaterThan(6);
  await expect(page.locator(".brief-bar")).toHaveCount(0);
});

test("镜头：预设切换 + 点名单推近（需要 DEV 的 __office 探针）", async ({
  page,
  request,
  baseURL
}) => {
  await openOffice(page, request, baseURL!);
  const hasOffice = await page.evaluate(() => Boolean((window as any).__office));
  test.skip(!hasOffice, "当前构建没有 __office 探针（非 dev）");

  const base = await readCam(page);
  await page.locator(".cam-presets button", { hasText: "白板" }).click();
  await page.waitForTimeout(1600);
  const board = await readCam(page);
  expect(Math.abs(board.x - base.x) + Math.abs(board.z - base.z)).toBeGreaterThan(0.3);

  await page.locator(".cam-presets button", { hasText: "全景" }).click();
  await page.waitForTimeout(1600);
  const back = await readCam(page);
  expect(Math.abs(back.x - 0.42) + Math.abs(back.z - 0.12)).toBeLessThan(0.3);

  await page.locator(".m-row").first().click();
  await page.waitForTimeout(2200);
  const focused = await readCam(page);
  expect(focused.zoom).toBeGreaterThan(1.6);
});

test("快捷键：1/2 切楼层、Esc 取消选中", async ({ page, request, baseURL }) => {
  await openOffice(page, request, baseURL!);
  const hasOffice = await page.evaluate(() => Boolean((window as any).__office));
  test.skip(!hasOffice, "当前构建没有 __office 探针（非 dev）");

  await page.keyboard.press("2");
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as any).__office.floor())).toBe(2);
  await page.keyboard.press("1");
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as any).__office.floor())).toBe(1);

  await page.locator(".m-row").first().click();
  await expect(page.locator(".of-picked")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.locator(".of-picked")).toHaveCount(0);
});

test("派活（假流）：播报流、结论复制、展开全部、跟随 3 秒限流", async ({
  page,
  request,
  baseURL
}) => {
  await openOffice(page, request, baseURL!);
  /* 127.0.0.1 算安全上下文，代码会走 navigator.clipboard；不授权就会失败并弹 warning */
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(baseURL!).origin
  });
  await mockDispatch(page);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".m-row").first()).toBeVisible({ timeout: 30_000 });

  const hasOffice = await page.evaluate(() => Boolean((window as any).__office));
  if (hasOffice) {
    await spyFocus(page);
    await page.locator(".cam-presets button", { hasText: "跟随" }).click();
  }

  await page.locator(".of-bar-input").fill("让两位同事各查一件事，然后汇总");
  await page.locator("button.of-btn.primary", { hasText: "派活" }).click();
  await expect(page.locator(".brief-bar")).toBeVisible({ timeout: 40_000 });

  // 播报流：展开后至少 4 条，含派活/回话/结论
  await page.locator(".cast-bar .of-linkbtn").click();
  const cast = await page.locator(".cast-list .c").allInnerTexts();
  expect(cast.length).toBeGreaterThanOrEqual(4);
  const joined = cast.join("\n");
  expect(joined).toMatch(/派给/);
  expect(joined).toMatch(/回话/);
  expect(joined).toMatch(/结论/);
  await page.locator(".cast-bar .of-linkbtn").click();

  // 结论复制
  await page.locator(".brief-bar button", { hasText: "复制" }).click();
  await expect(page.locator(".el-message--success")).toBeVisible({ timeout: 5_000 });

  // 面板：展开全部 / 收起全部
  const toggle = page.locator(".of-thead .of-linkbtn");
  await expect(toggle).toHaveText("展开全部");
  await toggle.click();
  await expect(toggle).toHaveText("收起全部");
  await toggle.click();
  await expect(toggle).toHaveText("展开全部");

  // 跟随：两次推镜头间隔 ≥ 3 秒（脚本里两次派活间隔 3.5 秒）
  if (hasOffice) {
    const calls = await page.evaluate(
      () => ((window as any).__focusCalls || []) as Array<{ t: number; name: string }>
    );
    expect(calls.length).toBeGreaterThanOrEqual(2);
    const gaps = calls.slice(1).map((c, i) => c.t - calls[i].t);
    for (const g of gaps) expect(g).toBeGreaterThanOrEqual(2800);
  }
});

test("蹦迪：上 2F 后 1F 看不到他们的名牌；清场后全部回座且不再自动开蹦", async ({
  page,
  request,
  baseURL
}) => {
  test.setTimeout(180_000);
  await openOffice(page, request, baseURL!);
  const hasOffice = await page.evaluate(() => Boolean((window as any).__office));
  test.skip(!hasOffice, "当前构建没有 __office 探针（非 dev）");

  const snap = () =>
    page.evaluate(() => {
      const o = (window as any).__office;
      const names = Array.from(document.querySelectorAll(".m-row .n")).map(
        (e) => (e.textContent || "").trim().split("\n")[0]
      );
      const st = names.map((n) => o.debugPerson(n)).filter(Boolean) as Array<{
        floor: number;
        onDance: boolean;
        seat: { key: string; kind: string } | null;
      }>;
      return {
        up: st.filter((d) => d.floor === 2).length,
        upNames: names.filter((n) => {
          const d = o.debugPerson(n);
          return d && d.floor === 2;
        }),
        dancing: st.filter((d) => d.onDance).length,
        kinds: st.map((d) => (d.seat ? d.seat.kind : "")),
        chips: Array.from(document.querySelectorAll(".ag-chip"))
          .filter((e) => (e as HTMLElement).style.display !== "none")
          .map((e) => (e.querySelector(".nm") || { textContent: "" }).textContent || ""),
        leak: o.floorLeak().count,
        leakSample: o.floorLeak().sample
      };
    });

  // 开蹦（走 UI 按钮，和用户操作一致）
  await page.locator(".of-ico[title='叫人来蹦 / 清场']").click();
  /* 等"真有人上去了"而不是干等固定秒数（机器慢的时候 11 秒人还在爬楼梯） */
  await expect
    .poll(() => page.evaluate(() => (window as any).__office.partyCount()), { timeout: 25_000 })
    .toBeGreaterThan(0);
  await expect
    .poll(() => snap().then((s) => s.up), { timeout: 30_000 })
    .toBeGreaterThan(0);
  await page.waitForTimeout(1500); // 等过渡（缩放/换层）收尾再断言
  const mid = await snap();
  test.skip(mid.dancing === 0, "没有待命的人，叫不动（跳过）");
  // 1F 视角下，2F 的人的名牌不能出现（曾经的 bug：名牌悬在半空，像"脚后跟"）
  for (const n of mid.upNames) expect(mid.chips).not.toContain(n);
  expect(mid.leak, JSON.stringify(mid.leakSample)).toBe(0);

  // 清场：全部回座 + 不留在舞池
  await page.locator(".of-ico[title='叫人来蹦 / 清场']").click();
  await expect
    .poll(() => snap().then((s) => s.dancing), { timeout: 30_000 })
    .toBe(0);
  await expect
    .poll(() => snap().then((s) => s.up), { timeout: 40_000 })
    .toBe(0);
  const after = await snap();
  expect(after.kinds.every((k) => k !== "dance")).toBe(true);
});

test("生活感：接水/打印跑腿、两人站着聊天，都会自己回座", async ({
  page,
  request,
  baseURL
}) => {
  test.setTimeout(120_000);
  await openOffice(page, request, baseURL!);
  const hasOffice = await page.evaluate(() => Boolean((window as any).__office));
  test.skip(!hasOffice, "当前构建没有 __office 探针（非 dev）");

  const snap = () =>
    page.evaluate(() => {
      const o = (window as any).__office;
      const names = Array.from(document.querySelectorAll(".m-row .n")).map(
        (e) => (e.textContent || "").trim().split("\n")[0]
      );
      const st = names.map((n) => o.debugPerson(n)).filter(Boolean) as Array<{
        trip: { kind: string } | null;
        chatting: boolean;
        talking: boolean;
      }>;
      return {
        trips: st.filter((d) => d.trip).map((d) => d.trip!.kind),
        chatting: st.filter((d) => d.chatting).length,
        talking: st.filter((d) => d.talking).length
      };
    });

  // 跑腿（接水/打印）：安排一个 → 站一会儿 → 自己回座
  expect(await page.evaluate(() => (window as any).__office.errandNow())).toBe(1);
  await expect.poll(() => snap().then((s) => s.trips.length), { timeout: 15_000 }).toBe(1);
  const kind = (await snap()).trips[0];
  expect(["water", "printer"]).toContain(kind);
  await expect.poll(() => snap().then((s) => s.trips.length), { timeout: 25_000 }).toBe(0);

  // 两人聊天：安排两个人 → 有说话动作 → 自己回座
  expect(await page.evaluate(() => (window as any).__office.chatNow())).toBe(2);
  await expect.poll(() => snap().then((s) => s.chatting), { timeout: 15_000 }).toBe(2);
  await expect.poll(() => snap().then((s) => s.talking), { timeout: 15_000 }).toBeGreaterThan(0);
  await expect.poll(() => snap().then((s) => s.chatting), { timeout: 25_000 }).toBe(0);
});

test("粘底：上滑后不再被拽回，出现「回到最新」并能回到底部", async ({
  page,
  request,
  baseURL
}) => {
  await page.setViewportSize({ width: 1440, height: 620 });
  await openOffice(page, request, baseURL!);
  await page.locator(".of-tab", { hasText: "任务" }).click();
  const items = page.locator(".tl-item");
  test.skip((await items.count()) === 0, "还没有历史 run，跳过（先派一次活）");
  /* 挑步数最多的那一轮：步骤太少面板撑不满，粘底测不出来（会误跳过） */
  const counts = await items.evaluateAll((els) =>
    els.map((el) => {
      const m = (el.querySelector(".tl-m")?.textContent || "").match(/(\d+)\s*步/);
      return m ? Number(m[1]) : 0;
    })
  );
  await items.nth(counts.indexOf(Math.max(...counts))).click();
  await expect(page.locator(".of-trace")).toBeVisible({ timeout: 20_000 });

  const toggle = page.locator(".of-thead .of-linkbtn");
  if (await toggle.count()) {
    await toggle.click();
    await page.waitForTimeout(400);
  }
  const canScroll = await page.evaluate(() => {
    const el = document.querySelector(".of-tbody") as HTMLElement | null;
    return el ? el.scrollHeight - el.clientHeight : 0;
  });
  test.skip(canScroll <= 40, "面板内容不够长，跳过");

  await page.evaluate(() => {
    (document.querySelector(".of-tbody") as HTMLElement).scrollTop = 0;
  });
  const jump = page.locator(".of-jump");
  await expect(jump).toBeVisible({ timeout: 5_000 });
  await jump.click();
  await page.waitForTimeout(400);
  const gap = await page.evaluate(() => {
    const el = document.querySelector(".of-tbody") as HTMLElement;
    return Math.round(el.scrollHeight - el.scrollTop - el.clientHeight);
  });
  expect(gap).toBeLessThanOrEqual(4);
});
