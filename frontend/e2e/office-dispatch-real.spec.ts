import { test, expect } from "@playwright/test";
import { memberNames, openOffice, readCam, spyFocus } from "./office-helpers";

/**
 * AI 办公室「真链路派活」回归（**默认跳过**，会真的调模型、真的写 run）。
 *
 * 为什么单独放：一条派活要 20~60 秒、会消耗模型额度、还会在开发库里留一条 run。
 * 日常回归跑 office-polish.spec.ts（假流，秒级）；要验真链路时：
 *
 *   E2E_OFFICE_DISPATCH=1 E2E_BASE_URL=http://127.0.0.1:5182/web \
 *     E2E_API_URL=http://127.0.0.1:8011/api/v1 pnpm e2e office-dispatch-real --no-deps
 *
 * 验证点：真实 SSE 帧驱动的「跟随执行者」——推镜头的人名都在办公室名单里、
 * 相邻两次间隔 ≥ 3 秒、结束后镜头停在某人身上（离开默认位）。
 *
 * 注意：跑完开发库会多一条 run（执行过程可回放），不需要就手工删。
 */

const ENABLED = process.env.E2E_OFFICE_DISPATCH === "1";

test.describe("办公室真链路派活", () => {
  test.skip(!ENABLED, "未开启 E2E_OFFICE_DISPATCH=1（会真调模型）");
  test.use({ storageState: { cookies: [], origins: [] } });
  test.setTimeout(180_000);

  test("派活 → 跟随执行者按事件推镜头且 3 秒限流", async ({ page, request, baseURL }) => {
    await openOffice(page, request, baseURL!);
    const names = await memberNames(page);
    expect(names.length).toBeGreaterThan(1);

    await spyFocus(page);
    await page.locator(".cam-presets button", { hasText: "跟随" }).click();
    await expect(page.locator(".cam-presets button.on")).toHaveText("跟随");

    const prompt =
      "请分别让问数助手查数据集总数、数据洞察助手查标注任务总数，各一句话，然后汇总成两行。";
    await page.locator(".of-bar-input").fill(prompt);
    await page.locator("button.of-btn.primary", { hasText: "派活" }).click();
    await expect(page.locator(".brief-bar")).toBeVisible({ timeout: 150_000 });

    const calls = await page.evaluate(
      () => ((window as any).__focusCalls || []) as Array<{ t: number; name: string }>
    );
    expect(calls.length).toBeGreaterThanOrEqual(1);
    for (const c of calls) expect(names).toContain(c.name);
    const gaps = calls.slice(1).map((c, i) => c.t - calls[i].t);
    for (const g of gaps) expect(g).toBeGreaterThanOrEqual(2800);

    const cam = await readCam(page);
    expect(Math.abs(cam.x - 0.42) + Math.abs(cam.z - 0.12)).toBeGreaterThan(0.3);
  });
});
