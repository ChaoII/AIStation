import { expect, type Page, type APIRequestContext } from "@playwright/test";

/**
 * AI 办公室 e2e 的公共工具。
 *
 * 两个刻意的选择（两个 spec 都靠它）：
 * 1) **自己登录**（接口拿 token 写 localStorage），不依赖 auth.setup —— 关闭验证码的 dev 环境里
 *    登录页点「登录」不一定跳转，用它会让整组用例连带失败。跑的时候加 `--no-deps`。
 * 2) **用 route 转发 /api/v1** 到 E2E_API_URL（默认 8002）：页面在 5182、接口在 8002 是跨域，
 *    浏览器会拦 CORS；转发之后由 Playwright 代发，不受 CORS 限制。
 */

export const GUIDE_KEY = "office.guide.v1";

/** 接口登录 → 把 token 塞进 localStorage（之后所有请求都带得上） */
export async function login(page: Page, request: APIRequestContext, baseURL: string) {
  const origin = new URL(baseURL).origin;
  const res = await request.post(`${origin}/api/v1/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" }
  });
  expect(res.ok(), `登录失败：${res.status()} ${await res.text()}`).toBeTruthy();
  const token = (await res.json()).data.access_token as string;
  await page.addInitScript((t) => {
    localStorage.setItem("access_token", JSON.stringify(t));
    localStorage.setItem("refresh_token", JSON.stringify(t));
    localStorage.setItem("remember_me", "true");
  }, token);
}

/** 进办公室页；默认先把引导标记为已看过，避免遮住后续点击 */
export async function openOffice(
  page: Page,
  request: APIRequestContext,
  baseURL: string,
  opts: { freshGuide?: boolean } = {}
) {
  await login(page, request, baseURL);
  const target = (process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1").replace(/\/$/, "");
  await page.route("**/api/v1/**", async (route) => {
    const u = new URL(route.request().url());
    const rest = u.pathname.replace(/^\/api\/v1/, "");
    await route.continue({ url: `${target}${rest}${u.search}` });
  });
  await page.addInitScript(
    ([key, fresh]) => {
      try {
        if (fresh) localStorage.removeItem(key);
        else localStorage.setItem(key, "1");
      } catch {
        /* 忽略 */
      }
    },
    [GUIDE_KEY, !!opts.freshGuide] as const
  );
  await page.goto("/#/ai/office", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-office-page")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".m-row").first()).toBeVisible({ timeout: 30_000 });
}

/**
 * 用假流替换派活接口。默认时序：
 * 派给甲 → 3.5s 派给乙 → 1s 乙调工具 → 1s 乙回话 → 3.5s 甲回话 → 0.5s 完成。
 * 期望跟随：甲(0s) → 乙(3.5s) → 甲(9s)，间隔都 ≥ 3s。
 */
export async function mockDispatch(page: Page) {
  await page.addInitScript(() => {
    const origFetch = window.fetch.bind(window);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).fetch = async (input: any, init?: any) => {
      const url = typeof input === "string" ? input : (input?.url ?? "");
      if (!url.includes("/office/dispatch/stream")) return origFetch(input, init);
      const names = Array.from(document.querySelectorAll(".m-row .n")).map(
        (el) => (el.textContent || "").trim().split("\n")[0]
      );
      const A = names[0] || "甲";
      const B = names[1] || "乙";
      const leader = names.find((n) => n.includes("助理")) || names[0] || "组长";
      const script: Array<[number, Record<string, unknown>]> = [
        [0, { type: "start", leader, members: [leader, A, B], memory: false }],
        [0, { type: "delegate", from: leader, to: A, task: "查数据集总数" }],
        [3500, { type: "delegate", from: leader, to: B, task: "查标注任务总数" }],
        [
          1000,
          {
            type: "tool",
            from: B,
            tool: "list_annotation_tasks",
            args: {},
            result: '{"total":237}'
          }
        ],
        [1000, { type: "reply", from: B, text: "标注任务总数为 237 个。" }],
        [3500, { type: "reply", from: A, text: "数据集总数为 273 个。" }],
        [
          500,
          {
            type: "done",
            ok: true,
            leader,
            content: "数据集 273 个；标注 237 个。",
            run_id: "e2e-mock"
          }
        ]
      ];
      const enc = new TextEncoder();
      const body = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const [wait, frame] of script) {
            if (wait) await new Promise((r) => setTimeout(r, wait));
            controller.enqueue(enc.encode(`data: ${JSON.stringify(frame)}\n\n`));
          }
          controller.close();
        }
      });
      return new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" }
      });
    };
  });
}

/** 记录 __office.focusAgent 的调用（时间 + 人名） */
export async function spyFocus(page: Page) {
  await page.evaluate(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    w.__focusCalls = [];
    const o = w.__office;
    if (!o) return;
    const orig = o.focusAgent.bind(o);
    o.focusAgent = (n: string, z?: number) => {
      w.__focusCalls.push({ t: Date.now(), name: n });
      return orig(n, z);
    };
  });
}

/** 读镜头状态（只在 dev 构建可用：__office 探针） */
export function readCam(page: Page) {
  return page.evaluate(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const o = (window as any).__office;
    const t = o.controls.target;
    return { x: +t.x.toFixed(2), z: +t.z.toFixed(2), zoom: +o.camera.zoom.toFixed(2) };
  });
}

/** 办公室里成员的名字（去掉「组长」徽标） */
export function memberNames(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll(".m-row")).map((el) => {
      const n = el.querySelector(".n");
      if (!n) return "";
      const clone = n.cloneNode(true) as HTMLElement;
      clone.querySelector(".lead")?.remove();
      return (clone.textContent || "").trim();
    })
  );
}
