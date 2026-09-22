# Task 1 报告：引入 Vitest 并配置纯函数单测框架

## 状态
DONE

## 实现内容
- `frontend/package.json`：新增 `test:unit: vitest run` 脚本，devDependencies 新增 `vitest@^5.0.1`。
- `frontend/vitest.config.ts`：新增 Vitest 配置（`environment: node`，`include: ["src/**/*.test.ts"]`，`exclude: ["**/e2e/**", "**/node_modules/**"]`）。
- `frontend/src/annotation/core/__tests__/smoke.test.ts`：新增 smoke 单测确认框架可用。

## 测试结果
`pnpm run test:unit` 输出 `Test Files 1 passed / Tests 1 passed`，符合 brief 预期 "1 passed"。

## 变更文件
- `frontend/package.json`（修改）
- `frontend/pnpm-lock.yaml`（修改，由 pnpm add 生成）
- `frontend/vitest.config.ts`（新建）
- `frontend/src/annotation/core/__tests__/smoke.test.ts`（新建）

## 自审发现
1. **版本偏差**：brief 预期 `vitest@^3.x`，但 `pnpm add -D vitest` 实际解析到 `vitest@^5.0.1`（vitest 当前最新主版本）。node v24.14.0 满足 vitest 5 的 `node ^22.12 || ^24 || >=26` 要求，测试运行正常，故按实际安装版本继续。若需严格对齐 3.x 可改。
2. **安装走直连，非 7890 代理**：brief 指定的 `127.0.0.1:7890` 代理未监听（连接被拒），但 registry.npmjs.org 直连可用。尝试过该代理后，改用无代理直连安装成功。另一候选端口 10809/8080 有监听，但未采用，直连即可。
3. **lockfile 附带无关改动**：`webworkify-webpack` 的 lockfile 描述从 `codeload.github.com` tarball 改写为 `git+https` 形式，属 pnpm 安装时对既有依赖的重新解析（mpegts.js 依赖），非本任务新增，已随 lockfile 一并提交。属轻微噪音，不影响功能。

## 顾虑
无阻断性顾虑。版本 5.x 与 brief 预期 3.x 不一致，属可接受的已更新版本；如需各单测依赖版本锁定可与上下游对齐。

## 复查修复（对照评审意见）

### 修复 1：vitest 版本对齐 brief（5.x → 3.x）
- 原按 `pnpm add -D vitest` 解析到 `vitest@5.0.1`（vitest 5 引擎要求 node>=22.12，与项目 `engines.node: ">=18.0.0"` 冲突）。
- 已改为 `vitest@^3`：`vitest@3.2.7` 已写入 `frontend/package.json` 的 devDependencies。
- 代理说明：brief 指定的 `127.0.0.1:7890` 代理**未监听**（TCP 连接失败），故改用无代理直连 registry 安装成功，未静默保留 v5。

### 修复 2：剔除 lockfile 无关改动（webworkify-webpack）
- 原 `pnpm add` 把 `webworkify-webpack` 从 `codeload.github.com/...tar.gz` 改写为 `git+https://git@github.com:...`，属 mpegts.js 附带依赖的非预期重写。
- 处理：`git checkout 78cb2c1 -- frontend/pnpm-lock.yaml` 还原 lockfile 到任务前基线，再重新 `pnpm add -D vitest@^3` 仅生成 vitest 条目。
- 复核：`git diff 78cb2c1 -- frontend/pnpm-lock.yaml` 仅出现**新增**（287 行插入），无内容删除；`webworkify`/`mpegts` 相关行与基线一致（保持 codeload 形式），无无关改动残留。

### 测试命令与输出
命令（在 `D:\AIStation\frontend`）：
```powershell
pnpm run test:unit
```
输出：
```
> aistation@2.2.0 test:unit D:\AIStation\frontend
> vitest run

 RUN  v3.2.7 D:/AIStation/frontend
 ✓ src/annotation/core/__tests__/smoke.test.ts (1 test) 1ms

 Test Files  1 passed (1)
      Tests  1 passed (1)
   Duration 430ms
```

### lockfile 差异状态
- `frontend/pnpm-lock.yaml`：仅含 vitest@3 相关新增条目，无 webworkify 无关改动。
- `frontend/package.json`：`"vitest": "^3.2.7"`。
