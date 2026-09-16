# Phase 0C：浏览器测试护栏与提示体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 Playwright 浏览器 E2E 护栏（登录 + 主链路页面冒烟），并治理"拦截器与页面两次弹 toast"的重复提示问题，统一为拦截器单一来源。

**Architecture:** `frontend/` 引入 `@playwright/test`，配置 hash 路由 baseURL 与 storageState 登录复用；toast 策略为"请求拦截器统一负责 API 成功/失败提示"，页面移除针对 API 结果的重复 ElMessage，仅保留剪贴板/表单校验/确认框取消等非 API 提示。

**Tech Stack:** Playwright (Chromium) + Vue3 + Vite（`base=/web`，hash 路由）+ Element Plus。

## Global Constraints

- Node ≥18、pnpm ≥8。前端命令在 `D:\AIStation\frontend` 下执行。
- 前端类型检查必须通过：`pnpm run type-check`（注意仓库有既有错误，只要求**改动文件不新增**错误）。
- 不新增运行时依赖；`@playwright/test` 仅作为 devDependency。
- 提交信息风格 `feat(scope)`/`refactor(scope): 中文描述`；只 `git add` 本任务文件。
- E2E 前置条件（写进 README 或 `e2e/README.md`）：后端已运行在 `8001`（含 Postgres/Redis/对象存储），前端可运行在 `5180`；`.env.development` 中 `CAPTCHA_ENABLE = false`（登录无需验证码），登录页已预填 `admin/123456`。
- 前端 hash 路由 + `base=/web`，实际地址为 `http://127.0.0.1:5180/web/#/...`。

---

### Task 1: Playwright 护栏 + 登录与主链路冒烟

**背景:** 前端长期无自动化测试，导致"改一处坏一处"（如首图不加载、导出按钮无效）。本任务建立浏览器护栏，后续 Phase 每步都可用。

**Files:**
- Modify: `frontend/package.json`（新增 devDependency 与 `e2e` 脚本）
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/README.md`
- Create: `frontend/e2e/auth.setup.ts`
- Create: `frontend/e2e/smoke.spec.ts`
- Modify: `frontend/.gitignore`（忽略 `e2e/.auth/`、`test-results/`、`playwright-report/`）

**Interfaces:**
- Produces: `pnpm e2e` 运行 Playwright；`e2e/.auth/user.json` 为登录态 storageState。
- Produces: `e2e/smoke.spec.ts` 断言登录成功与主链路页面可渲染。

- [ ] **Step 1: 安装 Playwright 并加脚本**

在 `frontend` 下执行：

```bash
pnpm add -D @playwright/test
pnpm exec playwright install chromium
```

在 `frontend/package.json` 的 `scripts` 增加：

```json
    "e2e": "playwright test",
    "e2e:ui": "playwright test --ui"
```

- [ ] **Step 2: 写 Playwright 配置**

创建 `frontend/playwright.config.ts`：

```ts
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5180/web";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
      dependencies: ["setup"],
    },
  ],
});
```

- [ ] **Step 3: 写登录 setup**

创建 `frontend/e2e/auth.setup.ts`：

```ts
import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  // 登录页已预填 admin/123456（dev 关闭验证码）
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/\/#\/(home|dashboard)/, { timeout: 30_000 });
  await expect(page.locator(".app-main, .el-main").first()).toBeVisible();
  await page.context().storageState({ path: authFile });
});
```

- [ ] **Step 4: 写主链路冒烟**

创建 `frontend/e2e/smoke.spec.ts`：

```ts
import { test, expect } from "@playwright/test";

// routePath -> 用于断言渲染的可见文本或选择器
const PAGES: Array<[string, string]> = [
  ["/#/annotation/dataset", "数据集"],
  ["/#/annotation/task", "标注任务"],
  ["/#/annotation/stats", "工作量"],
  ["/#/train/repo", "模型仓库"],
  ["/#/train/task", "训练任务"],
  ["/#/train/eval", "模型评估"],
  ["/#/train/predict", "模型预测"],
  ["/#/train/deploy", "模型部署"],
];

test("登录后可进入主链路各页面且无致命渲染错误", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  for (const [path, text] of PAGES) {
    await page.goto(path, { waitUntil: "networkidle" });
    await expect(page.locator(`text=${text}`).first()).toBeVisible({ timeout: 15_000 });
    // 页面不应出现全局 500/白屏
    await expect(page.locator("text=系统异常")).toHaveCount(0);
  }

  expect(consoleErrors, `页面抛出未捕获异常:\n${consoleErrors.join("\n")}`).toEqual([]);
});
```

- [ ] **Step 5: 忽略产物目录**

在 `frontend/.gitignore` 追加：

```gitignore
e2e/.auth/
test-results/
playwright-report/
```

- [ ] **Step 6: 写前置说明**

创建 `frontend/e2e/README.md`：

```markdown
# 浏览器 E2E（Playwright）

## 前置
- 后端运行在 http://127.0.0.1:8001（Postgres / Redis / 对象存储就绪）
- 前端 `pnpm dev` 运行在 http://127.0.0.1:5180
- `.env.development` 中 `CAPTCHA_ENABLE=false`，登录页预填 admin/123456

## 运行
```bash
pnpm e2e          # 全部用例
pnpm e2e:ui       # 交互模式
E2E_BASE_URL=http://127.0.0.1:5180/web pnpm e2e
```

失败时 `test-results/` 有截图与 trace；`playwright-report/index.html` 可视化。
```

- [ ] **Step 7: 运行冒烟（需前后端在跑）**

Run: `cd frontend && pnpm run type-check && pnpm e2e`
Expected: `type-check` 无**新增**错误；Playwright setup 登录通过，smoke 用例通过。若某页面文本断言与真实 UI 不符，改为该页面稳定的可见元素（如 `.app-container` + 页面标题），并在报告中记录调整。

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/playwright.config.ts frontend/e2e frontend/.gitignore
git commit -m "test(frontend): 引入 Playwright 浏览器护栏与主链路冒烟"
```

---

### Task 2: 提示单一来源（拦截器）治理

**背景:** `frontend/src/utils/request.ts:69-77` 已对每个非 GET 请求自动弹成功提示、失败时自动弹错误提示；但各业务页面又对同一请求再弹一次，导致"保存成功/创建成功"等重复 toast。

**决策:** **请求拦截器是唯一来源。** 页面移除针对 API 响应结果的 `ElMessage.success/error`；保留：
- 剪贴板操作提示（如 `已复制`）
- 纯前端校验/状态提示（如"关联模型已不存在"）
- `ElMessageBox` 确认框取消分支（不产生请求）
- 需要自定义文案的个别操作：给该次请求加 `headers: { _silent: "true" }` 后再由页面自行提示。

**Files:**
- Modify: 以下页面（逐处确认该 `ElMessage` 针对的是 API 响应结果后再删除）：
  - `frontend/src/views/module_train/task/index.vue`（802,812,818,830,833,841,850）
  - `frontend/src/views/module_train/task/detail.vue`（730,735,747,769,812；保留 844/847）
  - `frontend/src/views/module_train/repo/index.vue`（487,526,534；保留 528 剪贴板）
  - `frontend/src/views/module_train/predict/index.vue`（416,442,445,453,456,466）
  - `frontend/src/views/module_train/predict/detail.vue`（249,254,266,284）
  - `frontend/src/views/module_train/deploy/index.vue`（426,429,437,464；保留 459 剪贴板）
  - `frontend/src/views/module_train/eval/index.vue`（483,506,509,517,526）
  - `frontend/src/views/module_train/eval/detail.vue`（325,330,342,360,389；保留 416/419）
  - `frontend/src/views/module_annotation/dataset/index.vue`（544,573,687,693）
  - `frontend/src/views/module_annotation/annotation/index.vue`（3305,3307；保留 2958/3243/3386/3623 等非 API 提示）
- Create: `frontend/e2e/toast.spec.ts`

**Interfaces:**
- Consumes: `utils/request.ts` 的拦截器成功/失败提示与 `_silent` 选项。
- Produces: 同一用户操作最多出现 1 个 toast。

- [ ] **Step 1: 逐处删除重复提示**

对上述每一处：若该 `ElMessage.success(...)`/`ElMessage.error(...)` 紧跟在 `await XxxAPI...()` 成功/失败分支、且文案描述的是该 API 结果，则删除该行；仅保留 `try/finally` 中的状态复位。删除后若 `catch` 块变空，改为 `catch { /* 提示由请求拦截器统一处理 */ }`（保留注释，避免空块 lint 报错）。

示例（`module_train/eval/index.vue` 的创建评估）：

```ts
// before
try {
  await TrainAPI.createEval(payload);
  ElMessage.success("评估任务已创建");   // 删除（拦截器已提示）
  dialogVisible.value = false;
  loadAllData();
} catch {
  // ...
}

// after
try {
  await TrainAPI.createEval(payload);
  dialogVisible.value = false;
  loadAllData();
} catch {
  /* 提示由请求拦截器统一处理 */
}
```

- [ ] **Step 2: 校验无遗漏**

Run: `cd frontend && rg -n "ElMessage\.(success|error)" src/views/module_train src/views/module_annotation/dataset`
Expected: 仅剩剪贴板/非 API 提示（如 `已复制`）与确认框相关提示；不应对任何 API 结果重复弹窗。

- [ ] **Step 3: 写 toast 单一来源 E2E**

创建 `frontend/e2e/toast.spec.ts`（通过 API 预置一条数据集，再在 UI 删除，断言仅出现 1 个成功 toast）：

```ts
import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

test("删除数据集仅弹出一个成功提示", async ({ page, request }) => {
  // 1) 登录拿 token（dev 关闭验证码）
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 2) API 建一个数据集
  const name = `e2e-toast-${Date.now()}`;
  const created = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(created.ok()).toBeTruthy();

  // 3) UI 打开数据集页，搜索并删除
  await page.goto("/#/annotation/dataset", { waitUntil: "networkidle" });
  // 若页面有搜索框，输入 name 后查询；否则直接在列表按名称定位行
  const row = page.locator(`tr:has-text("${name}")`).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: /删除/ }).click();
  // 确认弹窗
  await page.getByRole("button", { name: "确定" }).click();

  // 4) 断言仅一个 el-message
  await expect(page.locator(".el-message")).toHaveCount(1, { timeout: 10_000 });
});
```

- [ ] **Step 4: 运行 E2E**

Run: `cd frontend && pnpm e2e`
Expected: `toast.spec.ts` 通过（恰好 1 个 `.el-message`）。若删除按钮/确认按钮选择器与真实 DOM 不符，按实际调整选择器并在报告记录；断言（toast 数量为 1）不变。

- [ ] **Step 5: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 改动文件无新增类型错误。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/module_train frontend/src/views/module_annotation/dataset frontend/src/views/module_annotation/annotation/index.vue frontend/e2e/toast.spec.ts
git commit -m "refactor(frontend): 提示统一由请求拦截器负责，移除页面重复 toast"
```

---

## Self-Review

**Spec coverage（对照 design 第 5.1 节 / 第 4 节）:**
- 0.8 浏览器自动化 → Task 1 ✅
- 0.7 重复 toast → Task 2 ✅

**Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码。选择器相关不确定性已在步骤中给出调整指引。

**Type consistency:** `pnpm e2e`、`e2e/.auth/user.json`、`E2E_BASE_URL`/`E2E_API_URL` 在配置、setup、用例中命名一致。

**风险:**
- Task 1 依赖前后端真实运行；若后端未起，setup 会超时——报告中说明而非跳过。
- Task 2 删除页面提示可能让个别操作用户反馈变弱（仅剩后端 `data.msg`）。若某操作确需自定义文案，按决策加 `_silent` 后由页面提示，不要两个都留。
- `pnpm run type-check` 存在仓库既有错误；只要求改动文件不新增。
