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
