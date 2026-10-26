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

## AI 办公室（`office-*.spec.ts`）

办公室的用例**自己登录**（接口拿 token 写 localStorage）、**自己转发 `/api/v1`**，
所以不依赖 `auth.setup`，也不会被「登录页点了不跳转」拖垮。跑的时候加 `--no-deps`：

```bash
# 快速回归（假 SSE 流，不调模型、不写库，约 2.5 分钟）
E2E_BASE_URL=http://127.0.0.1:5182/web \
E2E_API_URL=http://127.0.0.1:8011/api/v1 \
  pnpm e2e office-polish --no-deps

# 真链路派活（会真调模型、会消耗额度、会在库里留一条 run，约 40 秒）
E2E_OFFICE_DISPATCH=1 E2E_BASE_URL=... E2E_API_URL=... \
  pnpm e2e office-dispatch-real --no-deps
```

- `E2E_API_URL` 必须是**带办公室接口**的后端（`/ai/agents/office/*`）。老实例没有这些路由，
  页面会渲染成「0 在岗 / 还没有智能体」，用例会在等名单那步失败。
- 用例用到 `window.__office` 探针（镜头/楼层），**只在 dev 构建存在**；对着打包产物跑会自动 skip 相关断言。
- 注意连接数：页面每 20 秒轮询一次，同时开着两三个后端实例时 PG 可能报
  `too many clients already`（跑之前把不用的实例停掉）。

