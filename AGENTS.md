# AIStation — Agent Guide

## 交流语言（强制）

- **所有对用户的回复一律使用中文**，包括但不限于：提问、进度汇报、结果总结、问题排查说明、设计与方案描述、验收标准。不要只在小结/提问用中文而正文夹带英文。
- 技术名词可保留英文原词，但**解释性文字必须用中文**（如「静默加载（silent）」这一行，应写作「静默加载，即请求失败时不弹全局错误提示」）。
- 文档/规格/计划（`docs/` 下的 spec、plan）正文也用中文；代码注释用中文；提交信息用 `fix(train): 中文描述` 格式。
- 给用户的列表、表格、标题、小标题一律中文；避免用英文做大标题或段落。

## Quick Start

## Setup

```bash
# Backend — create Python 3.13 virtual env, install deps with Tsinghua mirror
cd backend
uv venv --python 3.13   # creates .venv/ with Python 3.13
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Start backend (first run auto-inits DB schema + seed data)
uv run main.py run --env=dev

# Lint
uv run ruff check && uv run ruff check --fix

# 测试（注意效率，见下方「测试效率」）
uv run pytest -q                      # 全量；提交前跑
uv run pytest tests/test_xxx.py -q    # 单文件：日常只跑这个

# Alembic (only needed after model changes)
uv run main.py revision --env=dev
uv run main.py upgrade --env=dev

# Frontend
cd frontend && pnpm install
pnpm run dev                   # Vite at http://localhost:5180
pnpm run type-check            # vue-tsc --noEmit --skipLibCheck
pnpm run lint                  # eslint + prettier + stylelint
```

## 测试效率（重要，直接决定开发速度）

实测（2026-10）：一次测试进程的**固定成本 ≈ 25 秒**，其中 `create_app()`（440+ 路由发现 +
插件扫描）就占 **≈ 22 秒**；`import main` 仅 1.6 秒。叠加 `.env.dev` 的
`LOGGER_LEVEL=DEBUG`（**每次运行 3 万行 SQL 日志**）后，跑一次单文件要 45 秒以上。

已做的修复与正确用法：

- **conftest 已强制测试期 `LOGGER_LEVEL=WARNING` + 关闭 `DATABASE_ECHO`/`ECHO_POOL`**
  （日志 3 万行 → 几行）。这是全量测试变快的主因。
- **纯逻辑测试（不碰 DB/HTTP）用快速模式**，约 **2 秒**：
  ```bash
  PYTEST_NO_APP=1 uv run pytest tests/test_xxx.py -k "..." -q
  ```
  （`PYTEST_NO_APP=1` 跳过应用构造；需要应用的用例会被自动 skip。）
- **日常只跑单文件**，别动不动全量；全量留给提交前。
- 用 `backend/.venv/Scripts/python.exe -m pytest ...` 代替 `uv run pytest` 可再省 ~2 秒。
- **全量用并行**：`uv run pytest -q -n 4` —— 实测 **367s → 225s**（1962 用例）。
  ⚠️ **别用 `-n 8`**（实测反而 256s：每个 worker 都要构造应用，CPU 争抢）。
  `pytest-xdist` 已加入 dev 依赖（`uv.lock` 仅新增 `pytest-xdist` + `execnet`，未升级其它包）。

### 首次跑测试 / 新建 worktree 必看（2026-10 实测）

worktree 里**没有 `backend/.venv`、没有 `backend/env/.env.dev`**（都被 gitignore），直接 `pytest` 会
`ModuleNotFoundError: sqlalchemy`；拷了 env 但不禁验证码，又会挂在 `auth_headers` 夹具：

```
ERROR tests/test_office_dispatch.py ... AssertionError: {"msg":"验证码不能为空"}
```

三步走（缺一不可）：

```powershell
cd backend
# 1) 建 venv + 装依赖（走清华源，实测可用）
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
# 2) 从主检出拷 env（主库在 D:\AIStation，PG 在 127.0.0.1:5432）
Copy-Item D:\AIStation\backend\env\.env.dev .\env\.env.dev
# 3) 关掉验证码再跑（.env.dev 里 CAPTCHA_ENABLE 已是 false，环境变量兜底）
$env:CAPTCHA_ENABLE="false"; .\.venv\Scripts\python.exe -m pytest tests/test_xxx.py -q
```

**起后端做联调时不要用 `.env.dev` 里的 8002**（那是别人在跑的服务）：`$env:SERVER_PORT="8011"` +
`--no-reload` 起第二个实例，用完按端口杀干净（`Get-NetTCPConnection -LocalPort 8011`）。

### 在 worktree 里跑前端（2026-10 实测）

worktree 同样没有 `frontend/node_modules` 和 `frontend/.env.development`。`pnpm install` 会因为
`mpegts.js` 依赖一个 GitHub git 地址而失败（离线/代理不通时）。可行做法：

```powershell
# 1) 拷 env（主检出 D:\AIStation）
Copy-Item D:\AIStation\frontend\.env.development .\frontend\.env.development
# 2) node_modules 用 junction 指向主检出（robocopy 会破坏 pnpm 的符号链接，vite 起不来）
cmd /c mklink /J .\frontend\node_modules D:\AIStation\frontend\node_modules
# 3) 新依赖（如 three）手工放进目标目录，否则解析不到
#    （package.json 里已声明，用户本地 pnpm install 后即可去掉这步）
# 4) 起在别的端口，绝不占 5181
cd frontend; node_modules\.bin\vite.cmd --port 5182 --strictPort
```

⚠️ junction 指向的是**主检出的 node_modules**，在 worktree 里 `pnpm install` 会写进主仓库；
测试完记得 `cmd /c rmdir .\frontend\node_modules`（只删链接，不动目标）。



## 国内镜像源（**强制**，apt / pip / 任何拉取）

### 用户原话（要求原样记录，不得改写）

> 现在跟你说你不管是有装拍神库还是apt get的这源全部都用国内的镜像听到没把它写在agents.md里面。

> 还有apt也要换阿里镜像

（"拍神库" = 第三方库，指 pip 装包；这两句是本节的**唯一来源**。）

### 硬规矩

- **apt → 清华**：`https://mirrors.tuna.tsinghua.edu.cn/ubuntu`
  （备选中科大 `https://mirrors.ustc.edu.cn/ubuntu`；
  **阿里云实测仅 0.02 MB/s，82s 拉 1.7MB，别用**）
- **pip / uv → 清华**：`https://pypi.tuna.tsinghua.edu.cn/simple`
- 本项目 `uv sync` 已带 `--index-url`（见 Quick Start），**不要去掉**
- Dockerfile / CI 里装包同样走国内源，见 `D:\TorchKiln\service\Dockerfile`
- 唯一例外：pytorch 官方 CUDA 轮子（`download.pytorch.org`）国内常未同步，
  用时须在提交信息里注明「国内无等价源」
- 装包一律 `pip install --no-deps` + 手工补传递依赖，避免 resolver
  顺手升级 torch/numpy/opencv 毁掉已跑通的通路

### PyTorch CUDA 轮子也有国内镜像（用户原话）

> 对于pytorch的cuda版本也有国内镜像你比如说南科科大的。

- 实测可用：**清华** `https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu132/`（6.2 MB/s）、中科大（5.2 MB/s）
- ❌ **南科大有反爬挑战**，HEAD 返回 200 但正文是验证页，pip 拉不到，别用
- ⚠️ 南京大学目录可访问但无 torch 2.1x 条目
- PyPI 同步源（清华/阿里云 simple）里**没有** CUDA 轮子，这是独立索引，需单独指定
- 探测可用性必须 GET 一次看正文，`-Method Head` 的 200 不可信

#### 2026-10-20 实测修正（simple 模式 GPU 安装）

- ⚠️ **清华/中科大的 `pytorch-wheels/cu132/` 现已 404**（2026-10-20 GET 探测）；当前可用的是
  **阿里云** `https://mirrors.aliyun.com/pytorch-wheels/cu132/`（实测列出 480 个轮子，
  `torch-2.14.1+cu132-cp313-cp313-win_amd64`、`torchvision-0.29.1+cu132-cp313-cp313-win_amd64` 齐全），
  官方 `https://download.pytorch.org/whl/cu132` 作兜底。
- 安装命令（版本必须与 `backend/uv.lock` 对齐；`--no-deps` 防止 resolver 动其它包）：
  ```powershell
  cd backend
  uv pip install --no-deps --find-links https://mirrors.aliyun.com/pytorch-wheels/cu132/ `
    "torch==2.14.1+cu132" "torchvision==0.29.1+cu132"
  ```
- ⚠️ **装完 CUDA 轮子后不要再执行 `uv sync`**：它会按锁文件把 PyPI 的 CPU 版 torch 装回来、
  覆盖 CUDA 轮子（实测踩过）。需要补包用 `uv pip install`；若不得不 `uv sync`，**同步后必须
  重跑上面两条安装命令**再验证。
- 验证：`.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"`。
- `backend/scripts/smoke_simple_mode.py` 默认用 GPU（无 CUDA 自动回退 CPU），`--cpu` 可强制 CPU。

## Architecture

**Monorepo**: `backend/` (FastAPI + SQLAlchemy 2.0 + Pydantic v2), `frontend/` (Vue 3 + Vite + Element Plus + TypeScript).

### Backend — package-by-feature (vertical slices)

Each business module under `app/api/v1/module_*/` contains:

```
controller.py  →  service.py  →  crud.py  →  model.py  schema.py  param.py
```

Static routes are wired explicitly in `app/scripts/init_app.py:register_routers()`.  
Dynamic routes auto-discovered from `app/plugin/module_*/**/controller.py` via `app/core/discover.py`.

**Important**: New submodules under `app/api/v1/module_*` **must** be manually imported in that module's `__init__.py` and registered in `register_routers()`. Plugin modules (`app/plugin/`), however, are auto-discovered.

### Backend model base classes (`app/core/base_model.py`)

- **`MappedBase`** — bare DeclarativeBase with `__permission_strategy__`. No common columns.
- **`ModelMixin(MappedBase)`** — adds id, uuid, status, created_time, updated_time, is_deleted, deleted_time.
- **`UserMixin(MappedBase)`** — adds created_id, updated_id, deleted_id + FK relationships.
- **`TenantMixin(MappedBase)`** — adds tenant_id FK.

Models that inherit only `MappedBase` (e.g., `CameraGroupModel`) have **no soft-delete, no user audit fields**. CRUDBase's `delete()` will physically delete them.

### Backend CRUDBase (`app/core/base_crud.py`)

Generic class `CRUDBase[ModelType, CreateSchemaType, UpdateSchemaType]` provides:  
`get`, `list`, `tree_list`, `page`, `create`, `update`, `delete`, `clear`, `set`, `restore`.

- Query conditions: `[("like", value)]`, `[("eq", value)]`, `[("between", (min, max))]`, etc.
- `page()` returns `{page_no, page_size, total, has_next, items}`.
- `delete()` soft-deletes if model has `is_deleted` field, otherwise physical delete.
- Auto-filters by data-scope permissions via `__permission_strategy__`.

### Frontend page CRUD pattern

Every CRUD page follows:

```
PageSearch (search form, config-driven) +
PageContent (table, config-driven) +
EnhancedDialog (create/update form)
```

Key imports:
- `useCrudList()` from `@/components/CURD/useCrudList` — provides `searchRef`, `contentRef`, `handleQueryClick`, `handleResetClick`, `refreshList`.
- `v-hasPerm` directive — removes DOM element if user lacks permission string.
- `contentConfig.indexAction` — async function returning `{ total, list }`.
- `contentConfig.deleteAction` — async function receiving comma-separated IDs.

Backend `page_size` is **not constrained server-side**; the CRUDBase.page accepts any valid integer.

### API conventions

- Prefix: `ROOT_PATH = "/api/v1"`
- Response: `SuccessResponse(data=..., msg="...")` / `ErrorResponse(msg="...")`.
- Pagination request: `page_no`, `page_size` query params.
- Pagination response: `{ page_no, page_size, total, has_next, items }`.
- Auth: every endpoint uses `Depends(AuthPermission(["module:feature:action"]))`.
- Datetime serialization: `DateTimeStr` / `DateStr` / `TimeStr` in `app/core/validator.py` — use `model_dump(mode='json')` for Redis writes.

### Environment & services

- DB: PostgreSQL, configured in `backend/env/.env.dev`. Also supports MySQL / SQLite.
- Redis: required. Configured in same `.env.dev` file.
- Ports: backend `8001`, frontend `5180`.
- Login: admin / 123456 (from seed data). Captcha is required.
- Docker Compose: `docker-compose.yaml` includes postgres:17, redis:7, zlmediakit.

### Menu + permission registration

New menu entries must be:
1. Inserted into `sys_menu` table (seed data only runs on empty DB).
2. Assigned to admin role via `sys_role_menus`.
For existing DBs, use the menu management UI or manual `INSERT`.

### Notable gotchas

- `auth/dependencies.py` has a circular import that does not block normal runtime.
- Frontend `src/views/` (not `src/view/` as some docs say).
- Frontend router is hash-based (`createWebHashHistory`); dynamic routes come from backend menu data.
- Pre-existing lint errors exist in `LivePlayer.vue`, `live/index.vue`, `playback/index.vue` (unrelated to new work).
- When creating a model that inherits `MappedBase` directly (no `ModelMixin`), CRUDBase skips `created_id`/`updated_id` but also skips soft-delete.
- Tree structures use `parent_id` FK + `children` relationship + `traversal_to_tree(flat_dicts)` from `app/utils/common_util.py`.
- Frontend API functions are named `getXxxList`, `getXxxDetail`, `createXxx`, `updateXxx`, `deleteXxx` — co-located by module in `src/api/`.

### Gotcha: `v-model` with separate reactive object + dynamic keys

When using `v-for="(val, key) in objA"` with `v-model="objB[key]"` where `objB` is a **separate** reactive object populated from `objA`, the initial value may not be tracked correctly by Vue 3's reactivity system — especially with `el-switch` (boolean values appear as `undefined` despite being set).  

**Fix**: bind `v-model` directly to the same object being iterated: `v-model="objA[key]"`. No intermediate mapping object.

### Gotcha: Using `watch` vs `@change` for async data loading

A `watch` on a reactive property that triggers an async data load can race with other code that also modifies the same property. **Use `@change` on the form control instead** + a dedicated async handler function. This guarantees synchronous control flow and avoids double-fetch/race conditions.

### Gotcha: Multi-root component inside `<Transition mode="out-in">` causes white screen

When a component with **two or more root elements** in its `<template>` is rendered inside `<transition mode="out-in">` (e.g., via `<router-view>`), Vue cannot animate the leave transition. The `<Transition>` component hangs waiting for the leave animation to complete, so the **enter phase never starts** and the next page never mounts — resulting in a blank white screen.

Vue logs: `"Component inside <Transition> renders non-element root node that cannot be animated"`.

**Fix**: Ensure the component has exactly **one root element** by wrapping all content (including dialogs, modals, etc.) inside a single container `<div>`. For example, move `<el-dialog>` from a sibling position to inside the main container div:

```html
<!-- ❌ BAD: two roots -->
<template>
  <div class="page">...</div>
  <el-dialog v-model="visible">...</el-dialog>
</template>

<!-- ✅ GOOD: single root, dialog inside wrapper -->
<template>
  <div class="page">
    ...
    <el-dialog v-model="visible">...</el-dialog>
  </div>
</template>
```

## 前端交互与样式规范（强制）

### 1. 局部刷新优先，禁止整控件刷新
- **进度/状态变化只更新对应的一条数据**（行/项），**不要周期性地整体 `refreshList()` / 重拉整表** —— 会闪烁、丢滚动与选中态，体验极差。
- 正确做法（按优先级）：
  1. 把状态放到**行数据对象**上（如 `row.import = {...}`），并对承载它的 `ref` 数组整体重新赋值触发渲染；
  2. 或用**独立的局部组件/横幅**（一个 `ref` 列表）承载实时进度，不动主列表；
  3. 仅在任务**状态跃迁（开始/结束）**时刷新**一次**列表。
- 反面教材：模型训练详情页最初也是"整体刷新"，后改为局部刷新；本项目的列表/详情页**一律遵循局部刷新**。
- 若发现控件（尤其 `el-table` 插槽）不跟随组件外部响应式状态刷新，**不要用"每秒整表刷新"绕过**：应把状态落到行数据，或用独立局部组件承载。

### 2. 样式必须与 Element Plus / 项目一致
- **禁止到处自定义 `font-size`**。统一用 Element Plus 变量与默认字号：正文 `var(--el-font-size-base)`（14px）、次要说明 12px、标签/按钮用组件默认；**不要 13/15/16px 零散混用**。
- **优先使用 Element Plus 原生组件**（`el-steps`/`el-progress`/`el-descriptions`/`el-alert`/`el-tag`/`el-dialog`/`el-form`/`el-checkbox` 等）；**不要自造主题化外壳**。
- 颜色/间距/圆角引用 `--el-*` 变量，禁止写死主题色（`#409eff` 等）。
- 列宽、`label-width`、按钮 `size` 与**同模块既有页面**保持一致。

### 3. 弹窗（el-dialog）规范
- 宽度用常用档位（500 / 520 / 600px 等），不要"稀奇古怪"的尺寸与位置；需要时 `append-to-body`。
- 弹窗必须放在**页面根元素内**（单根，见上面的 `<Transition>` 陷阱）。
- 内容用 `el-form` + `label-width` 或标准块级布局；**禁止内联 `style="font-size:..."`**。

### 3.1 删除类操作必须二次确认（强制）
- **凡是"删除/移除/清空/覆盖"类操作，必须二次确认**（`ElMessageBox.confirm`），无一例外。包括但不限于：删除实体、批量删除、彻底删除、删除图片/标注、清空数据集、覆盖式导入、取消/中止进行中的任务。
- 确认文案必须写明**影响范围与不可逆性**，并带上数量（如「将删除 12 张图片及其标注，且不可恢复」）。
- 确认/取消按钮文案必须**语义明确**（如「删除 / 取消」「覆盖导入 / 取消」），严禁让用户把"继续/确定"误读为"取消"，或反之。
- 前端按钮必须带对应权限（`v-hasPerm`），后端接口必须有对应权限校验；两者都不可省。
- 若操作可能耗时较长，确认后给出加载态或进度（后台任务 + 进度），不要"点完没反应"。

### 4. 写代码前先对齐框架
- 动手前先找**同类页面/组件**作参照（列表页看 `module_system/param`，训练详情看 `module_train/task/detail`），照其结构、字号、间距、交互实现；**不要自创风格**。
- 完成后用无头浏览器截图，**直接用模型自身的多模态能力读图**与既有页面对照，确认风格一致再交付（**不要**依赖 `vision-recognition` 技能）。

### 5. 页面布局统一（强制，2026-10）

参照「系统管理」（用户/角色/参数等框架自带 CRUD 页），所有页面必须满足：

- **白色面板铺满**：页面根 `app-container` 显式 `display:flex; flex-direction:column; height:100%;
  overflow:hidden`，卡片/面板 `flex:1 1 auto; min-height:0`，内容区自己滚。
  禁止「表格几行就结束、下面露一大截灰底」（曾出现：知识库 446px / 空间扩容审核 327px /
  AI 集成 490px 处截止，用户明确否掉）。
- **左右布局左栏固定 240px**（`flex:0 0 240px`），左右各自独立 `el-card`，`gap:12px`。
  不要用 `el-col` 百分比栅格定左栏（实测 354px 等各页不一），也不要 260/272 混用。
  已统一：工作台、定时任务（单卡）、个人工作空间、智能问数、本体、数据与集成。
- 保留 `el-row` 时必须清掉 gutter 负边距：`margin:0!important` + col `padding:0!important` + `gap:12px`，
  否则左卡实际宽度是 240-12=228px，与 flex 布局页差 12px（视觉上"割裂"）。
- 布局覆盖一律**非 scoped + 唯一类名**（防 data-v 在 keep-alive/HMR 下失效）；
  `el-tabs` 页必须给 `.el-tabs` / `.el-tabs__content` 补 flex 高度链（否则 tab 内容区不撑满）。
- 无卡片的列表页（provider/develop）要么给表格包 `flex:1` 容器 + `height="100%"`，要么套统一
  `el-card` 让白色面板铺满；不要一半有卡一半裸表格。
### 6. 页面外壳 / 表格 / 表单必须与框架页面同构（强制）

> 2026-10-22 教训：AI 集成页写了 `padding: 0` 且没有面板容器，标题/表格直接贴住侧边栏，我仅看内容就说"检查通过"，
> 被用户当场否掉（"没有白色背景也没边框，都和菜单挨在一起了"）。**"看了一眼觉得还行"不算检查，必须量数值。**

**唯一风格来源 = 框架自带页面**（不要自创）：
- CRUD 列表：`frontend/src/views/module_system/param/index.vue`
- 页签 + 面板：`frontend/src/views/module_ai/market/index.vue`（`market-shell`）
- 多卡片工作台：`frontend/src/views/module_ai/ontology/index.vue`

**页面外壳（照抄 market-shell）**
```scss
/* 非 scoped！scoped 在 keep-alive / HMR 下可能不命中（见本文件下方调试记忆） */
.app-container.xxx-page {
  display: flex; flex-direction: column; height: 100%;
  overflow: hidden; padding: 12px; box-sizing: border-box;
}
.xxx-page .xxx-shell {            /* el-card shadow="never" */
  flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}
/* body / 页签 / 内容区依次 flex:1 + min-height:0，内容区 overflow-y:auto */
```
- **禁止** `padding: 0`、禁止内容直接挂在 `app-container` 下无面板（只有纯表单类简单页可例外，且需与同模块对齐）。

**表格（竖线框必须有）**
- 一律 `border` + `stripe`：`<el-table ... border stripe>`。**裸 `el-table`（无边框）视为缺陷**。
- 列以 `min-width` 为主、短列用 `width`；长文本 `show-overflow-tooltip`。
- 空态统一 `<template #empty><el-empty :image-size="80" description="暂无数据" /></template>`。
- 分页统一 `layout="total, sizes, prev, pager, next"` + `background`，右对齐；表格容器沿用 `data-table__content`（`height="100%"` 时）。
- 列表页优先直接用 `PageSearch` + `PageContent`（自带上述规范）；自定义页签页也要满足同样外观。

**表单 / 弹窗**
- 搜索区 `el-form :inline="true"`；弹窗 `el-form :label-width`（与同模块一致，常见 90~110）。
- 字号只用 `var(--el-font-size-base)` / 12px 次要说明；颜色/圆角只用 `--el-*`；按钮 `size` 与同模块一致。

**探测验收（不做 = 没做完）**

必须用无头浏览器读计算样式，与参照页**逐项数值相等**（不是看着像）：
```js
const m = await page.evaluate(() => {
  const shell = document.querySelector(".develop-shell");
  const cs = getComputedStyle(shell);
  const r = shell.getBoundingClientRect();
  return {
    padding: getComputedStyle(document.querySelector(".app-container")).padding,
    border: cs.borderTopWidth, radius: cs.borderTopLeftRadius, bg: cs.backgroundColor,
    rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
  };
});
```
- 参照页实测基线（1440×900，侧边栏 210；2026-10-22 重测 system/param）：`padding 16px`（历史记录 12px 已过时，AI 管理 23 页已全部对齐 16px）、`border 1px solid var(--el-border-color-light)`（解析值 srgb 0.882/0.915/0.971；勿用 `--el-border-color`/`lighter` 档，色差肉眼可辨）、`radius 4px`、`bg rgb(255,255,255)`、root `1230×816`、单壳页壳 `1198×784`（gap 16 撑满）。
- 表格额外探测：`document.querySelectorAll(".el-table--border").length` 覆盖页内所有表格；`getComputedStyle(th).borderRightWidth === "1px"`。
- 截图覆盖：**每个页签 ×（有数据态 + 空态）**，弹窗各态，以及同尺寸的参照页一张；用模型自身读图对照。

**自查清单（每次交付前逐条打勾）**
1. 每个页签都在面板内、四边留白一致、无贴边；
2. 页内所有表格都有竖线框（`border`）且空态/分页一致；
3. 计算样式与参照页数值相等 + 截图逐张看过（含弹窗、空态、窄屏）。

## 标注标签渲染经验（标注重中之重）

### 坐标系统
- SVG `viewBox="0 0 cw ch"`，CSS大小 `dw = cw * zoom`，1 viewBox单位 = zoom CSS像素
- 所有 `getBBox()` 返回值在 viewBox 坐标系

### 文字 `<text>` 属性关键
| 属性 | 作用 |
|------|------|
| `y` | 默认是 **基线**（baseline），中文基线在字符底部 |
| `dominant-baseline="text-after-edge"` | **强制** y=文字最底部，不依赖字体基线 |
| `text-anchor="start"` | 文字从左到右，x 是文字左边缘 |
| `font-size="6"` | 6 viewBox单位，不用 `style="font-size:6px"`（CSS像素会和 getBBox 测量不一致） |
| `font-family="Microsoft YaHei,sans-serif"` | 必须设置，否则默认字体影响 getBBox |

### 标签布局公式（AxisAlignedBox）
```
框左上角 = (ann.x1*cw, ann.y1*ch)
文字底部 = 框上 - 2 (2px间隙)
文字y = ann.y1*ch - 2, dominant-baseline="text-after-edge"
文字x = ann.x1*cw + 2 (框左边+2px)
文字大小 = font-size="6"

背景框:
  左边 = ann.x1*cw (和框左边对齐)
  底部 = ann.y1*ch (和框上边对齐)
  宽 = getBBox文字宽 + 2 (2px边距)
  高 = getBBox文字高 + 4 (含2px下间隙+2px上边距)
  背景y = 框上 - 文字高 - 4
  背景底部 = 背景y + 背景高 = 框上 ✅
```

### 标签布局公式（RotatedBox）
```
旋转后左上角 = rbHandlePos(ann, 'tl', cw, ch)
文字底部 = 旋转后左上角.y - 2
文字x = 旋转后左上角.x + 2
文字大小 = font-size="6", dominant-baseline="text-after-edge"

背景框:
  左边 = 旋转后左上角.x
  底部 = 旋转后左上角.y
  宽高 / 边距 / 填充 与 AxisAlignedBox 完全一致
```

### 测量流程
```js
// 1. 先渲染文字（`font-size="6"` SVG属性，不要CSS像素）
// 2. 等100ms让SVG完成布局
// 3. getBBox() 获取实际渲染宽高
// 4. 用测量值设置背景框宽高
// 5. 测量值存到 labelTextRects Map，后续通过 ann.id 取用
```

### 关键陷阱
- ❌ 不要混用 `font-size="6"`（SVG属性）和 `style="font-size:6px"`（CSS）→ getBBox 测不准
- ❌ 不要让文字基线直接用 `y=框上` → 文字可能比框线低（字体基线问题）
- ✅ 用 `dominant-baseline="text-after-edge"` 解决
- ✅ 背景宽高都用 getBBox 实测值 + 固定边距，不猜
```

## 调试记忆：Vue scoped CSS + el-card flex shrink 导致内容不可见

### 问题现象
页面渲染后，部分 `<el-card>` 内部内容完全不可见，但 Vue 模板正常渲染、数据正确加载。

### 根因链
1. **全局 `.app-container`** 有 `display: flex; flex-direction: column; height: 100%; overflow: auto`
2. **`el-card`** 自带 `overflow: hidden` → 在 flex 容器中触发 CSS 规范：`overflow != visible` 时 `min-height` 被设为 `0`（而非默认的 `auto`）
3. 当 flex 容器有**确定高度**（`height: 100%` 继承自父级）且子项总高度超出时，flex 算法收缩所有 `flex-shrink: 1` 的子项
4. `el-card` 因 `min-height: 0` 可被收缩到**近零高度**，其内部内容被 `overflow: hidden` 裁剪，表现为"不见了"

### 调试方法（当怀疑 scoped CSS 未生效时）
1. 在模板顶部添加可见的调试元素（如 `<div class="debug-bar">{{ state }}</div>`）
2. 在 scoped 和非 scoped 中分别设置不同样式（如 `background: #ffeeba`）
3. 若 scoped 样式未生效但非 scoped 生效 → 判定 scoped CSS 的 `data-v-xxx` hash 不匹配

### 修复方案
**不要依赖 scoped CSS 覆盖全局 `.app-container` 的 flex 布局**。改用**非 scoped `<style>` 块** + 唯一类选择器：

```vue
<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>
```

并在根元素上同时使用两个 class：`<div class="app-container train-detail-page">`

### 已知限制
- `data-v-xxx` hash 可能在 keep-alive 缓存 + Vite HMR 场景下不同步，原因尚不完全明确
- 非 scoped 样式是已知可靠的回避方案
- flex 容器中只要同时满足：确定高度 + `overflow != visible` + `flex-shrink: 1`，就存在收缩风险

### 相关文件
- `frontend/src/views/module_train/task/detail.vue` — 问题页面，非 scoped 修复入口
- `frontend/src/styles/index.scss` — 全局 `.app-container` 定义
- `frontend/src/layouts/components/AppMain/index.vue` — 父容器 `.app-main`

---

## 调试记忆：Dashboard 图表布局被全局样式覆盖（CSS Grid 失效）

### 问题现象
Dashboard `index.vue` 图表区使用自定义 CSS Grid (`display: grid; grid-template-columns: 1fr 1fr`)，但始终渲染为单列，无法两列并排。el-card 不随 grid 父容器分流。

### 排查过程（踩坑记录）
1. 确认模板通过简单的 `<div class="dash-charts">` 包裹 el-card
2. 确认 `.dash-charts { display: grid; grid-template-columns: 1fr 1fr; }` 已写入全局 `dashboard.css`
3. 确认 `main.ts` 已正确 `import "@/styles/dashboard.css"`
4. 确认无 scoped style 覆盖
5. 在 `dashboard.css` 加 `!important` 仍无效
6. 在 `dashboard.css` 的 `.dash-charts` 加红色背景 → 确认 CSS 文件已加载
7. 仍单列 → CSS 中 `display: grid` 和 `grid-template-columns` 被更深层规则覆盖
8. 在 `.dash-charts` 上加内联 `style="display: grid !important; grid-template-columns: 1fr 1fr !important;"` → 终于生效，确认并排
9. 但 `!important` 会让手机端无法自适应单列 → 不可持续
10. 最终改用 **Element Plus 原生 `el-row` / `el-col`** 立即解决：`<el-col :xs="24" :sm="24" :md="12" :lg="12">`

### 根因分析
- **未完全确认的根因**：项目存在复杂的 CSS 层叠（Element Plus 全局样式、UnoCSS、scss 变量、其他全局 CSS），自写的 `display: grid` 被某条全局规则覆盖
- `@media (width <= 1100px)` 曾把 `.dash-charts` 改成 `1fr`，是一次直接触发因素
- **核心教训**：在这个项目中，**自定义 CSS Grid/Flex 布局在主布局级不稳定**，容易被全局样式或响应式断点意外覆盖

### 修复方案（ definitive fix ）
```html
<el-row :gutter="12">
  <el-col :xs="24" :sm="24" :md="12" :lg="12">...</el-col>
  <el-col :xs="24" :sm="24" :md="12" :lg="12">...</el-col>
</el-row>
```

### 预防措施（以后不要再踩）
1. **优先使用 Element Plus 栅格 (`el-row` / `el-col`)**：这是项目已深度集成的响应式布局方案，不会被全局 CSS 覆盖
2. **谨慎使用自定义 CSS Grid**：仅在 Element Plus 栅格无法满足的极端场景使用，且必须加 `!important` 兜底
3. **媒体查询断点统一用 `max-width`**：避免使用 `@media (width <= Xpx)` 这种非常规语法，减少意外覆盖风险
4. **调试 CSS 时先加视觉标记**：如 `background: red !important`，确认"规则是否被加载"比确认"规则内容"更重要
5. **如果 3 次以上 CSS patch 都失效 → 立即换架构**：不要继续在 CSS 层加 `!important` 叠加，应切换到框架原生组件

### 相关文件
- `frontend/src/views/dashboard/index.vue` — 问题页面，已改为 el-row/el-col
- `frontend/src/styles/dashboard.css` — 原自定义 CSS Grid 定义地

### 同类风险文件（其他可能存在相似布局覆盖问题的位置）
这些文件使用了自定义 CSS Grid/Flex，若出现布局异常，优先考虑改用 el-row/el-col：

| 文件 | 风险点 | 当前状态 |
|------|--------|----------|
| `frontend/src/styles/train-detail.css` | ~~`.info-cards`、`.chart-row`、`.metric-grid` 使用 CSS Grid~~ | **已修复** — grid 规则已删除，布局移交 el-row/el-col |
| `frontend/src/views/dashboard/workplace.vue` | 多个 `display: flex/grid` + `@media (width <= ...)` | 使用 scoped 样式，风险较低但已有非标准媒体查询语法 |
| `frontend/src/styles/dashboard.css` | ~~`.dash-metrics`、`.dash-footer`、`.dash-charts` 使用 CSS Grid~~ | **已修复** — 全部迁移到 el-row/el-col，只保留视觉装饰类 |

### 媒体查询语法警告
项目内多处使用非标准语法 `@media (width <= Xpx)`，这在部分浏览器/场景下可能表现不一致。建议统一改用标准写法：
```css
/* ❌ 非常规，可能在某些场景失效 */
@media (width <= 1100px) { ... }

/* ✅ 标准写法，兼容性最好 */
@media (max-width: 1100px) { ... }
```

---

## 调试记忆：el-tabs「纯导航」时给 `position: sticky` 吸顶不生效（对象详情 Tab 全局快速跳转）

### 问题现象
想让对象类型详情的 Tab 导航栏在滚动时「吸顶」，做成全局快速跳转。本以为给
`.el-tabs__header` 加 `position: sticky; top:0` 即可，实测：滚动后 header 直接跟着内容滚走了，**完全没有停靠**。

### 根因（关键）
在这个组件里，`<el-tabs>` 是**纯导航**：`el-tab-pane` 内容为空（没有真正的内容），
真正的分区内容是用 `v-if="page === '...'"` 写在 el-tabs **外面**的兄弟模板。

因此 `el-tabs` 根实际仅约 **47px** 高（只有头部导航条）。
`position: sticky` 的「行程」受限于**其父（containing block）的高度**——`el-tabs` 根太矮，
header 根本无处可停，所以一点都吸不住。

> 唯一例外：若给 sticky 元素设一个**更高的父级容器**（如把 sticky 作用在 el-tabs **根**上、
> 且根是滚动容器的直接子元素），就能吸住。

### 修复方案
必须给**整条 el-tabs 根**（`.ont-obj__tabs`）加 sticky，而不是给 `.el-tabs__header`：

```scss
/* 非 scoped；因为 `.ont-obj__tabs` 是 Element Plus 渲染的根，scoped data-v 不会命中 */
.ont-obj__tabs {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--el-bg-color);
}
```

- 前提：该 el-tabs 根必须是**滚动容器的直接子元素**（直接子元素才能相对滚动容器吸顶；
  实测把探针 div prepend 到 `.ont-obj`（滚动容器 `overflow:auto` 的直接子元素）时 sticky 生效，
  stuck gap=0；而嵌套在 el-tabs 内的 header 不生效）。

### 排查手法（可复用）
1. 先确认**哪个元素是真正的滚动容器**（`getComputedStyle` 看 `overflow:auto` + `scrollHeight>clientHeight`）。
2. 在页面里 `prepend` 一个 `position:sticky;top:0` 的探针 div 到滚动容器直接子层，滚动观察：
   - 探针能吸住 → 容器关系 OK，问题在目标元素层级太深/父太矮；
   - 探针也吸不住 → 容器或祖先 `overflow` 建立独立滚动上下文。
3. 检查目标元素祖先链的 `overflow`，以及**父容器高度**（`getBoundingClientRect().height`）。

### 相关文件
- `frontend/src/views/module_ai/ontology/components/OntObjectTypeView.vue` — 问题组件，新增
  `<style lang="scss">`（非 scoped）`.ont-obj__tabs { position: sticky; ... }`
- 决策记录：`docs/superpowers/plans/2026-10-20-ontology-p0-ui-plan.md` 第 11 项

---

## 调试记忆：后端热重载（reload）是陷阱，开发时禁止开

### 现象与代价（2026-10-18 实测，代价：约 1 小时的错误排查）

`main.py run --env=dev` 在 dev 下**硬编码** `reload=True`（`backend/main.py:99`）。它的 reloader 父进程持有端口 socket 并把 fd 交给子 worker，由此产生两个致命假象：

- **杀掉父进程后，孤儿 worker 会继续占着同一个端口、用旧代码服务**。实测：杀掉 reloader 后旧 worker 又跑了 1 小时，
  接口一律按**旧代码**返回 400「请先配置触发时间」，我据此误判「代码有 bug」，实际代码早已正确。
- **reload 失败时只记一行 `Reloading...` 然后静默保留旧进程**，后续改动也不再重载（`StatReload` 的检测日志会一起停）。

结论：**"我改了代码但接口行为没变"这类假象几乎无法从行为上分辨**，只能靠下面第 2 条的两步验证。

### 规矩（强制）

1. **开发时不要用 reload 启动**：`uv run main.py run --env=dev --no-reload`（等价 `RELOAD=false`）。
2. **改完后端代码必须彻底重启，并且必须验证新代码真的生效**（两步都做，缺一不可）：

```powershell
# 1) 按命令行精确杀干净（只杀监听 PID 是不够的，会留下孤儿 worker）
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*main.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 2) 确认端口已空（还有 OwningProcess 说明没杀干净）
Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
# 3) 重启（不开 reload）
cd backend; uv run main.py run --env=dev --no-reload
# 4) 验证新代码生效——不要只看"端口有响应"
curl http://127.0.0.1:8002/openapi.json   # 新字段/新路由是否出现？
```

3. **不要用「接口返回 400/404」直接推断代码有问题**：先用 `/openapi.json` 或启动日志确认在跑的是哪份代码。

---

## 调试记忆：asyncpg 读回的 `timestamptz` 一律是 UTC（差 8 小时）

`DateTime(timezone=True)` 的列用 asyncpg 读回来**永远是 UTC 的 tz-aware datetime**；而
`app/core/validator.py` 的 `DateTimeStr` 只做 `strftime`、**不做时区换算**。

于是由调度器写入的时间（值是 `Asia/Shanghai` 的 tz-aware）直接格式化会**早 8 小时**：
实测同一条定时任务，列表接口返回 `next_run_time = 2026-10-19 01:00:00`，而预览接口返回 `next_run = 2026-10-19 09:00:00`。

**规则**：凡是**来自调度器/APScheduler** 的时间（`next_run_time` / `last_run_time`），
出接口前必须 `.astimezone(ZoneInfo(TriggerUtil.TIMEZONE))` —— 统一走 `TriggerUtil.to_local_str()`，
不要各处自己 `strftime`。应用自己写入的 `created_time` 一类（naive 本地时间）不适用本条。

---

## 调试记忆：`v-hasPerm` 的值必须是**字符串表达式**（漏引号 = 整页白屏）

给 Vue 模板批量插按钮权限时，**值要带内层单引号**：

```html
<!-- ✅ 正确：指令拿到的是字符串 'module_ai:ontology:manage' -->
<el-button v-hasPerm="'module_ai:ontology:manage'" @click="save">保存</el-button>

<!-- ❌ 错误：裸标识符带冒号，vue-tsc 报 TS1005（',' expected），页面白屏 -->
<el-button v-hasPerm="module_ai:ontology:manage" @click="save">保存</el-button>
```

实测代价：脚本化批量插入（约 68 处）第一次写成后者，`pnpm run type-check` 报一堆 `TS1005`、
e2e 连 `auth.setup` 都挂（前端编译不过），排查了一轮才发现是引号问题 —— **不是插入位置的问题**。

排查提示：`TS1005: ',' expected` 出现在 `.vue` 的模板行上，优先怀疑**属性值不是合法 JS 表达式**
（漏引号、裸冒号标识符），而不是模板结构被改坏。

---

## 调试记忆：dev server 会静默死掉，e2e 失败先查端口

实测：前端 5181 / 后端 8002 都可能**无声无息地没了**（日志无 traceback）。此时 Playwright 报
`net::ERR_CONNECTION_REFUSED`（连 `auth.setup` 登录都失败），很容易误判成"我刚改的代码坏了"。

规矩：**e2e 报连接被拒时，先确认两个端口**，再怀疑代码：

```powershell
Invoke-WebRequest http://127.0.0.1:5181/web/ -TimeoutSec 10      # 前端
Invoke-WebRequest http://127.0.0.1:8002/api/v1/system/auth/auto-login/users -TimeoutSec 10  # 后端
```

后端重启后**要等约 60-90 秒**（含模型焐热）才算就绪，别在 30 秒时就断言"起不来"。

---

## 调试记忆：不要擅自启动前端/后端服务（用户原话："我啥时候要你在5182上启动前端的？"）

2026-10-19 实测踩坑：我为跑 e2e 自己执行了 `pnpm dev`，而 **5181 上本来就有用户在跑的服务**。
vite 发现 5181 被占不会报错，而是**静默跳到 5182**，于是我白开一个实例、占掉一个端口。

更荒唐的是：我所有 e2e 命令都显式指定了 `E2E_BASE_URL=http://127.0.0.1:5181/web`，
**全部打在原有服务上**——5182 那个实例从头到尾没有任何用处。

### 规矩（强制）

1. **不主动启动任何服务**。需要前端/后端时，**先探测端口、确认目标是否已在跑**：
   ```powershell
   Get-NetTCPConnection -LocalPort 5181,8002 -State Listen -ErrorAction SilentlyContinue |
     Select-Object LocalPort, OwningProcess
   ```
2. 只在**用户明确要求**、或探测确认**确实没有可用服务**时才启动。
3. 启动前先确认端口：**不要让 vite 自己跳端口**（跳到别的端口 = 后续所有请求都打错地方）。
   若必须启动，先确认目标端口空闲，否则说明已有服务在跑、不该再起。
4. e2e 的 `E2E_BASE_URL` / `E2E_API_URL` 要与**实际在跑的服务端口**一致，
   不要默认写死——端口对不上时用例会连到无关实例，结果无法解释。
5. 用完服务后**不要留孤儿进程**。起过的要收尾，探测确认已释放。
6. 已有的服务是**别人的**，不要杀、不要重启、不要覆盖；需要改动时先说明再动。

---

## OCR 模型规格（pytorch-ocr）

### PP-OCRv6 det 规格（configs/det/PP-OCRv6/*.yml）

| 规格 | Backbone | Neck | out | dilated | Head aux | EMA | box_thresh |
|------|----------|------|-----|---------|----------|-----|-----------|
| tiny | PPLCNetV4 tiny | RepLKFPN | 64 | 5 | aux_in 64 | 0.9998 | 0.4 |
| small | PPLCNetV4 small | RepLKFPN | 96 | 7 | aux_in 96 | 0.9997 | 0.45 |
| medium | PPLCNetV4 medium | **RepLKPAN** | 256 | - | aux_in 256 | 0.9996 | 0.45 |

- DBLoss: `main_loss_type=DiceFocalLoss`, alpha=5, beta=10, focal_alpha=0.25, focal_gamma=2.5, aux_weight p4/p3/p2 = 0.2/0.3/0.4
- CLI: `train-det --model-size {tiny,small,medium} --neck {rep_lk_fpn,rep_lk_pan} --pretrained <det_converted.pt> [--freeze-backbone]`

### PP-OCRv6 rec 规格（configs/rec/PP-OCRv6/*.yml）

| 规格 | Backbone | CTCHead neck | dims | mlp_ratio | NRTR dim | dict |
|------|----------|-------------|------|-----------|----------|------|
| tiny | PPLCNetV4 tiny | reshape (use_guide+mid80) | - | - | 384 | ppocrv6_tiny_dict (6904) |
| small | PPLCNetV4 small | **lightsvtr** | 120 | 2.0 | 384 | ppocrv6_dict (18707) |
| medium | PPLCNetV4 medium | **lightsvtr** | 192 | 4.0 | **512** | ppocrv6_dict (18707) |

- CTC 词表 = dict + space + blank（tiny: 6904+1+1=6906；small/medium: 18707+1+1≈18710）
- NRTR 词表 = CTC 词表 + 4 特殊 token（tiny 6910, small/medium 18714）——转换加载时这 2 层 shape 不匹配会被跳过（可接受，NRTR 是辅助头）
- CLI: `train-rec --model-size {tiny,small,medium} --dict <dict.txt> --pretrained <rec_converted.pt>`

### 权重转换

- det: `convert_ppocr_v6_det(paddle_state, model_size, fpn_out_channels, neck, dilated_kernel_size, intracl, aux_in_channels)` → 官方 .pdparams 语义名映射
- rec: `convert_ppocr_v6_rec(paddle_state, model_size, out_channels, neck)` → lightsvtr 需 `neck="lightsvtr"`
- 官方权重 URL: `https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_{size}_{det|rec}_pretrained.pdparams`
- 注意 det/rec 权重文件名需区分（如 `PP-OCRv6_small_det_converted.pt` / `PP-OCRv6_small_rec_converted.pt`），避免覆盖

### 训练要点（对照官方 PaddleOCR 发现）

- **DBLoss shrink 通道必须用 DiceFocalLoss（Dice + mask 内 Focal）**，纯 BCE 在文字占 2% 时梯度被背景稀释 → 模型全零崩溃
- **EMA**（ema_decay 0.9996-0.9998）抑制小数据集梯度噪声（BN bias 梯度可到 1212 量级）
- **eval 用官方 DetResizeForTest**（limit_side_len=736 min + round 32 → 实际近原尺寸），640×640 会低估 hmean 0.13-0.17
- 微调小数据集 det 时 **freeze-backbone**（BN 梯度爆炸会摧毁预训练权重）
- PP-OCRv5 det 用 PPLCNetV3+RSEFPN+DiceLoss，与 v6 架构不同，无法直接对比数字

### pytorch-ocr 训练对齐经验（2026-08 深入排查）

**结论**：逐行对照官方 PaddleOCR config + train.py 做了 15 轮对齐，pytorch det 训练从 0.79 提升到 **0.82**（v18 配置），但无法达到 PaddleX 训练的 0.93。剩余差距是 Paddle 框架级数值行为，代码层面无法完全复现。

**v18 最佳 det 训练配置**（`cfg_small_v6_full.json`）：
- `lr=0.001`（官方 small，不是 0.0005！medium 才是 0.0005）
- `ema_decay=0.9997`（small；tiny 0.9998，medium 0.9996）
- `RandomCropV6`（官方 v6 用 RandomCrop，不是 EastRandomCropData！v5 才用 EastRandomCropData）
- `IaaAugment`: Affine rotate[-45,45] fit_output, Resize[0.1,2]
- `use_color_jitter=false`（官方 small 无 ColorJitter）
- 移除 grad clip（官方 train.py 无 clip）
- eval 用直接拉伸 DetResizeForTest（非 letterbox！之前 letterbox 导致 eval 低估 0.13）
- shrink_ratio 动态 0.4+0.2*epoch/total_epoch（total_epoch 用官方 500 或 100 均可，100 略好）

**关键坑**：
1. **推理 `_preprocess` 必须直接拉伸**（官方 DetResizeForTest），letterbox 会让同一权重 eval 从 0.935 掉到 0.847
2. **MakeShrinkMap mask 是全图**（有效区域，只排除 ignore），不是文字区域！之前当文字区域导致 loss 计算范围错误
3. **DBLoss thresh 用 MaskL1**（mask 内平均），不是 smooth_l1——修后 DBLoss 与官方逐位一致
4. **官方 small det lr=0.001**，medium=0.0005，rec 都是 0.0005
5. **官方 eval 每 N step 用 val 数据**，但本项目 val 15 张与 train 重叠，全图 eval 选 best 反而更好

**权重转换已验证逐位一致**（backbone 118/118），**前向 maps 一致**（mean 0.0161 vs 0.0164）。DBLoss 逐位一致（loss 18.969619 完全相同）。数据流统计对齐（shrink>0.5, mask>0, thresh_mask>0）。

**PaddleX 官方训练方法**（本机 `paddlex:latest` 镜像，内置 PaddleOCR 插件）：
```
docker run --gpus all -w /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR \
  -v <det_dataset>:/data/det -v <weights>:/weights -v <out>:/output \
  paddlex:latest python tools/train.py \
  -c configs/det/PP-OCRv6/PP-OCRv6_small_det.yml \
  -o Global.epoch_num=100 Global.save_model_dir=/output/det \
     Global.pretrained_model=/weights/PP-OCRv6_small_det_pretrained.pdparams \
     Train.dataset.data_dir=/data/det 'Train.dataset.label_file_list=["/data/det/train.txt"]' \
     Train.loader.batch_size_per_card=8 Eval.dataset.data_dir=/data/det 'Eval.dataset.label_file_list=["/data/det/val.txt"]'
```
PaddleX 官方 small det 训练 100 轮 hmean **0.926**（recall 0.968），rec small 训练 acc **0.9975**。这是 pytorch-ocr 训练无法企及的。
```

## PaddleX 训练框架（已恢复，2026-08）

### 架构

- `TrainFramework.PADDLEX = "paddlex"`（PG enum `trainframework` 一直含 PADDLEX，无需迁移）
- 镜像 `paddlex:latest`（内置 PaddleOCR，`/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR`）
- det/rec 区分：`hyperparams.mode`（"det"/"rec"），模型规格 `hyperparams.model_size`（tiny/small/medium）
- 训练命令：`_build_paddlex_ocr_cmd`（scheduler.py）→ `bash -c "cd ... && python tools/train.py -c configs/{det,rec}/PP-OCRv6/PP-OCRv6_{size}_{mode}.yml -o <单个 -o + 空格分隔 opts>"`
- 执行器：`PaddleXOCRDet/RecExecutor`（paddlex_executor.py），det/rec 用 mode 派发
- 数据导出：`_export_paddle_ocr`（exporter.py）→ `<out>/{det,rec}/dataset/{train,val}.txt + images/`（PaddleX JSON `[{"transcription","points"}]`，label 带 `images/` 前缀）
- 产物：`<out>/{det,rec}/{best_accuracy,latest}.pdparams` + `config.yml`（export_model 支持查找）
- eval：容器内脚本 `_PADDLEX_EVAL_SCRIPT`（eval_scheduler.py）加载 .pdparams 跑 `program.eval` → `EVAL_METRIC_JSON {precision,recall,hmean}`
- predict：`infer_det.py`/`infer_rec.py`（`Global.pretrained_model=.pdparams`）
- deploy：`_generate_paddlex_server_script`（deploy_executor.py）FastAPI det+rec，需 rec_model_path

### 关键坑

1. **PaddleOCR `-o` 用 `nargs='+'`，多个 `-o` 时 argparse 只保留最后一个**！必须单个 `-o` + 所有 key=value 空格分隔。label_file_list 用单引号包裹（bash -c 内）。
2. **DataLoader 需要大 /dev/shm**：`run_container` 加 `shm_size="4g"`（PaddleOCR num_workers>0 时 BUS error）。
3. **eval loader 默认 batch_size_per_card=1**（det 图 shape 不同无法 batch），不要覆盖成 >1。
4. **rec MultiHead 需要 `out_channels_list`**（从 character_dict 算 char_num），build_model 前注入（对齐 tools/eval.py）。det 不需要。
5. **rec 用官方默认词表** `ppocr/utils/dict/ppocrv6_dict.txt`（与官方预训练权重匹配），不要覆盖 character_dict_path。
6. `program.preprocess(is_train=False)` 的 `sys.argv` 需含 `-c` + `-o`；容器内脚本要先 `os.chdir(PaddleOCR目录)` + sys.path 加 PaddleOCR。
7. 预训练权重 URL：`https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_{size}_{det|rec}_pretrained.pdparams`（executor 下载到 pretrained_host）。

### 验证结果（真实容器）

- det small 从头 3ep：loss 14.8→13.5，`save model`，`best metric hmean: 0`（ep 太少）
- det small pretrained 1ep：`load pretrain successful`，loss 4.35（权重生效）
- rec tiny 从头 2ep：acc 指标正常记录
- eval det（15 val 图）：hmean **0.795**，precision 0.695，recall 0.928
- deploy server：det 模型加载 + 单图 75 框 + rec 模型加载

### 测试

`backend/tests/test_paddlex_removal.py` 已改为 PaddleX 支持测试（枚举/权重规格/cmd 构建），64 测试全通过。

## AI 管理模块（v2，进行中）

- 位置：后端 `backend/app/plugin/module_ai/`（自动发现，容器前缀 `/ai`）；前端 `frontend/src/views/module_ai/`。
- 工作台（2026-10 改版）：只服务**智能体家族**（传统智能体 + 工作流编排）；原顶部类型 tab 已废弃，
  类别筛选并入工具栏下拉（全部/传统智能体/工作流，「新建」随类别联动）。**卡片模板参照能力市场**
  （`MarketCard.vue`）：图标 + 名称（单行 ellipsis）+ 副行（类型 tag / agent_role / 分类名）+
  **固定两行描述区**（无描述显示「暂无描述」，保证各卡等高）+ 能力标签行（min-height 24px）+
  footer（创建时间 + 对话/更多）。卡片行内高度实测完全一致（224px）。**布局区域隔离**（参照
  「个人工作空间」）：左「分类」独立 el-card（树 + 新建分类）＋ 右内容独立 el-card（工具栏 + 卡片网格 +
  分页），不再挤在同一面板。卡片开关**真实落库**（agent → `PUT /ai/agents/batch/status`；workflow →
  `PUT /ai/workflows/update/{id}` 部分更新）。
  应用归「AI应用」菜单；**定时任务为独立模块 `/ai/cron`**（`module_ai/cron/index`，**卡片网格**：
  信息模板统一 = 描述区固定两行 + 触发/下次/上次各一行 + 目标行，各卡高度完全一致；操作
  新建/编辑（TriggerEditor）/启停/立即执行/删除）。cron 接口仍挂 `/ai/workspace/cron/*` 前缀，
  但权限独立为 `module_ai:cron:*`（`_ensure_ai_menus` 注册菜单+按钮权限，存量库重启生效）；
  「立即执行」= `POST /cron/{id}/run`，只入队（BackgroundTasks），执行与调度器同走
  `run_scheduled_workspace_cron`。触发预览仍复用 `/ai/workspace/trigger/preview`。
- **调度执行目标**（`WorkspaceService._run_target`）：workflow 走 `run_schedule`；agent/app **真执行**
  （没有非流式入口，消费各自 `run_ui_stream` 的完整流；`auth=None` + `session_id=None`，
  不落用户会话、调用日志照记；固定调度消息「按你的配置执行」，因为 agent guardrail 拒绝空输入）。
- **工作流分类**：`AiWorkflowModel.category_id` 已由 Create/Update schema 暴露（此前只有列、无字段 →
  分类树对工作流空转）；入口在 `WorkflowEditor` 基础信息「分类」下拉（读工作台分类树，`\u3000` 缩进层级）。
  update 传 `category_id: null` = **显式清空**（与其它字段 None=不修改区分）。
- **AI 菜单分组**（2026-10）：`_ensure_ai_menu_groups()`（幂等，必须在 `_ensure_ai_menus` +
  `_ensure_develop_menus` **之后**调用）：**工作台、定时任务是顶层独立模块**（order 5/6，不放进分组）；
  其余页面挂到 3 个目录：知识与本体（本体/知识库/提示词）、应用与集成（AI应用/无代码应用/能力市场/AI集成）、
  平台与运维（模型配置/模型供应商/调用日志/空间扩容审核/个人工作空间）。顶层另有控制台（hidden，
  父菜单 redirect 到它）+ 智能问数目录。`AI_RETIRED_GROUPS`（AiGroupBuild）会被幂等清理（子菜单回顶层、
  删目录与授权）。目录 type=1 的 route_path/redirect 必须非空。
- 历史菜单行若 `client` 为空或**目录缺 route_path**，`GET /system/menu/tree` 会 400/500（校验失败），
  表现为「菜单管理页打不开」；修数据即可（client 补 'pc'，目录补 route_path=redirect）。
- **知识库向量检索 agno 化**（2026-10）：生产主路径走 `agno.vectordb.pgvector.PgVector`（`search/agno_engine.py`，
  `public.ai_kb_vectors` 原生表，`schema="public"` + 构造后**必须 `await async_create()`** 建表；Embedder =
  `OpenAILikeEmbedder(dimensions=...)`（dimensions 传给 embedder 而非 PgVector））。入库链路在
  `persist.write_vectors` **双写**（chunks 表存详情/标注 + agno 表存向量，meta_data 带 kb_id/chunk_id/file_name）；
  检索 `engines.vector_search` 先 agno、失败回退旧 pgvector SQL → Python 手算余弦（**回退仅测试/降级**，
  SQLite pytest 走此路径）。存量数据点一次「重建索引」即迁移。坑：日志输出 `ai.` schema 前缀=未传 `schema`。
- **对话流协议边界**（2026-10，勿再混）：两条 SSE 协议各有疆界——
  - **workflow 端点**（`/ai/workflows/{id}/run/stream` 等）= AI SDK UI Message Stream 帧
    （编辑器/分享页/HITL 依赖 `node-status` / `data-run` / `data-finish`），**不改**。
  - **assistant / agent / app 的 run 端点** = Agno 原生事件流（`RunStarted/RunContent/
    ToolCall*/RunError/RunCompleted`），controller 用 `agno_stream_response`，前端
    `AgnoChatTransport` 只认 `event: Run*` 帧——**误发 UI 帧会被静默丢弃**（错误提示/回复
    全丢，曾真实发生：guardrail 拦截、kb 应用、委托工作流三条路径）。
  - agent/app **委托工作流**时经 `assistant/agno_service.ui_stream_to_agno` 转译（编排帧丢弃）；
    错误路径一律 `agno_error_frame`；委托时 finally **跳过** `persist_session_exchange`
    （工作流引擎已自己落会话，重复会多一条 user 消息）。
  - 前端 `useAiChat` 按 `protocol` 选 transport：workflow kind 用 SDK 原生
    `DefaultChatTransport`（`protocol: "ui"`），其余用 `AgnoChatTransport`。
- **知识库分类树**（2026-10）：新建 `ai_knowledge_categories` 表（插件表自建：`knowledge/schema_check.py`
  的 `ensure_knowledge_schema` 启动幂等建表 + 给 `ai_knowledge_bases` 补 `category_id` 列，
  **不走 alembic autogenerate**）。接口 `/ai/knowledge/categories/{tree,create,update,delete}`（权限
  沿用 `module_ai:knowledge:*`）；`bases/list?category_id=` 含子分类过滤；前端左侧分类树
  （根节点「全部」+ 计数徽章），新建/编辑知识库可选分类。
- **分类树统一视觉**（工作台 + 知识库共用）：全局 `.ai-tree`（`styles/element-plus.scss`）——
  文件夹图标 + 名称（title 提示）+ 计数徽章，选中浅蓝高亮；树默认 `default-expand-all`；
  左栏统一 240px。工作台计数为「分类及子孙分类下的智能体/工作流数」（前端统计）。
- e2e：`trigger-workspace.spec.ts`（打 `/ai/cron` 卡片）**必须清理**（afterAll 按名称删除本次创建的
  定时任务，否则 dev 库会被 `e2e-*` 垃圾淹没——曾累积 44 条）；`ai-workspace.spec.ts` 锁类别下拉只剩
  智能体家族 + 左右两个独立卡片容器。e2e 直连 dev 后端，运行需 `E2E_API_URL=http://127.0.0.1:8002/api/v1`（清理用）。
- 结构：
  - `providers/` 提供商 CRUD + `GET /ai/providers/remote-models/{id}`（拉远端模型列表）
  - `provider/` 模型配置 CRUD（归属 provider、usage/capabilities/context_window、自定义请求头）+ `/ai/model/test` 连接测试
  - `assistant/` 工具调用助手：`POST /ai/assistant/chat`（非流式）、`POST /ai/assistant/stream`（SSE：`reasoning`/`delta`/`tool`/`done`）
  - `overview/` 调用日志 `ai_call_logs` + `GET /ai/overview/stats`
  - `report/` AI 报告
- 新控制台（旧 Agno 聊天/记忆页已 hidden 下线，父菜单 redirect `/ai/overview`）：
  - `/ai/overview` 控制台、`/ai/playground` 运行台、`/ai/provider`、`/ai/model`、`/ai/report`
- 运行时模型解析：模型 → 所属 provider → env（`OPENAI_*`）；`usage` 为空视为通用（兼容旧数据）。
- opencode 网关（`opencode.ai`）需 `x-opencode-session` 头：`provider/service.build_headers` 自动注入，另支持模型/提供商自定义头。

### 前端视觉约束（重要）
- AI 页面**必须与既有模块风格一致**（参考 `module_system/param`）：直接复用 Element Plus 组件（`el-card/el-descriptions/el-table/el-form/el-tag/el-statistic`）与 `--el-*` 变量；**不要自造主题化外壳/自定义配色**（`styles/ai-console.css` 的自定义观感曾被否定，需按框架组件重做）。
- 完成界面后**用无头浏览器截图 + 视觉分析**（`vision-recognition` 技能）核对，避免与框架割裂。

### 能力市场（工具/技能/MCP/插件统一橱窗，2026-10）

- 位置：后端 `backend/app/plugin/module_ai/{market,mcp,plugins}/`；前端 `frontend/src/views/module_ai/{market,mcp,plugin}/`；
  文档 `docs/ai-capability-market.md`。
- 核心语义：**市场是橱窗，安装 = 把商品 `payload` 复制成自己的真实资产**（`ai_tools`/`ai_skills`/
  `ai_mcp_servers`/`ai_plugins`）；幂等靠 `ai_market_relations(kind=installed)`，真实资产 id 存在该行 `description`。
  Agent 绑定零侵入（仍绑自己的 `tool_ids`/`skill_ids`/`mcp_ids`）。
- 五张新表：`ai_market_items` / `ai_market_relations` / `ai_market_shares` / `ai_mcp_servers` / `ai_plugins`；
  增列 `ai_tools.code|timeout`、`ai_agents.mcp_ids`。
- 权限码：`module_ai:market:{query,install,submit,share,review}`、`module_ai:mcp:*`、`module_ai:plugin:*`；
  菜单/权限由 `init_app._ensure_ai_menus()` **启动时幂等补齐**（存量库重启即生效，无需手工 INSERT）。
- **迁移必须手写**：本项目 dev 库有 400+ 张未被模型覆盖的历史/影子表（`ont_*`），`autogenerate`
  会把它们判成待 DROP（灾难）。手写迁移时对**插件表**（`ai_agents`/`ai_tools`，不由迁移链创建）
  增列要先 `sa.inspect(bind).has_table()` 判断，否则空库全链重放（SQLite 回归）会失败。
- 脚本工具沙箱（`tools_catalog/script_executor.py`）：AST 白名单（导入白名单模块、禁 dunder/`eval`/`open`/`getattr`、
  禁 `with/async`）+ 受限 builtins（含白名单 `__import__`，否则脚本内 `import` 会报 "not found"）+
  `sys.settrace` 行计数超时（Windows 无 `signal.alarm`）。**创建时静态拒绝**非法脚本。
  注意 `io` 模块**不可**加入白名单（`io.open` 可读写文件）。
- MCP：agno 原生 `MCPTools`（stdio 用 `StdioServerParameters`，http 用 `url`+`headers`；`tool_name_prefix`
  防重名）；`run_agno_tool_stream(mcp_tools=...)` 内连接/关闭，连不上只跳过（降级）。测试只做可达性探测。
- 依赖变更：`mcp>=2.1,<3`（清华源）连带 **`pyjwt` 2.9→2.15、`uvicorn` 0.30→0.54**，并收紧
  `requires-python <3.14`（3.14 分支要求 starlette>=0.48，与 fastapi 0.115.2 冲突）。
- PG 特有坑：`GROUP BY` **不能按 select 别名**（SQLite 放行、PG 报 GroupingError）——
  分类计数类查询要 `group_by(<表达式>)`。

### 连接超时（QueuePool 耗尽）排查与修复
- 现象：长时运行或大量 e2e 后，登录/接口返回"请求超时"；日志 `QueuePool limit of size ... overflow ... reached, connection timed out`。
- 根因（2026-10 实测）：一个请求最多同时吃 **3 条**连接（服务层普遍自己开 `async_db_session()`，不复用请求会话），
  且**被取消的请求**（浏览器翻页/关闭）会把连接漏在 `idle in transaction`，池占满后**不自愈**。
- 修复：`setting.py` 默认 `POOL_SIZE=20`、`MAX_OVERFLOW=0`、`POOL_TIMEOUT=30`，`env/.env.dev` 覆盖为
  **`POOL_SIZE=48`**（`MAX_OVERFLOW` 保持 `0`：溢出连接归还即关闭，会反复建连，改用持久连接 + 启动预热），
  保留 `POOL_RECYCLE=1800`、`POOL_PRE_PING=true`、`DB_POOL_WARMUP=true`。
  另有连接泄漏看门狗 `db_leak_watchdog`（每 60s 回收空闲事务 >120s 的连接）作兜底。
- **请求作用域会话（2026-10）**：纯 ASGI `DBSessionMiddleware` 为每个 HTTP 请求建一条会话，
  `async_db_session` 是上下文感知包装器——请求内**同任务**透明复用该会话
  （全仓 761 处调用点零改动），**一请求 1 条连接**；`create_task`/`gather` 子任务与后台任务
  仍各自新建（ContextVar 带 owner-task 判定）。会话由中间件提交/回滚并在 `finally` 归还，
  取消路径也可靠。设计见 `docs/superpowers/specs/2026-10-10-request-scoped-session-design.md`。
- 详细排查记录见 `docs/connection-pool-leak-diagnosis.md`。
- 排查建议：关注流式接口/长事务是否长期占用会话；`OperationLogRoute` 会在响应后另开会话写日志。

## 工程原则：优先成熟第三方库（用户强制要求）

- **AI 调用一律走 agno（用户强制约束）**：本平台**整个建立在 agno 之上**，禁止"自成一体"。
  - 禁止为了性能/绕开问题而**替换 agno 的调用链路**（如直接用原始 OpenAI 客户端写平行实现）；
  - 禁止引入第二套 AI 框架（langchain / llamaindex / 自研 shim 等）与 agno 并存；
  - 优化只能用 **agno 自己的旋钮**：超时、streaming、`max_tokens`、reasoning/thinking 参数、
    Agent 配置等；或在 agno **之外**（调用前后）做我们自己的逻辑（重试、降级、缓存）。
  - 唯一例外：**排查问题时**可以做一次性探针脚本对照（如 `scripts/_probe_llm_latency.py`），
    但**不得**把探针里的调用方式变成生产代码路径。
- **能用成熟库就不要手撸**（网络/流式/解析/图表/编辑器/日期等通用能力）。
- **只选维护活跃**的项目，避免停更/僵尸库；引入前先调研（star/最近发布/issue 活跃度）。
- 选型要有依据并写进设计与账本；优先 Web 事实标准（如 Vercel AI SDK）。

### 流式（SSE）选型结论
- 浏览器原生 `EventSource` 仅支持 GET、无法带 body/自定义头 → **聊天类必须用 fetch POST + ReadableStream 解析 SSE**。
- **推荐：Vercel AI SDK**（`ai` v5 + `@ai-sdk/vue` 的 `useChat`）：负责传输/流式/消息状态/工具与推理分片，维护活跃、跨框架。
- 解析层备选：`eventsource-parser`（AI SDK 亦使用）。
- 不推荐：`@microsoft/fetch-event-source`（发布基本停滞）。
- 生产常见坑：压缩中间件/反向代理会**缓冲**导致"整块才到"；需 `Cache-Control: no-transform` + `X-Accel-Buffering: no`，并避免压缩 SSE。
- 现状：AI 聊天当前是手写 SSE 解析（`frontend/src/api/module_ai/assistant.ts`），**待迁移到 Vercel AI SDK**。

### 编辑器 / 表单构造类 UI 选型结论（用户强制要求）
- **凡“编辑器/构造器”类交互（条件树、规则/公式编辑器、代码编辑器、富文本、表格字段构造、查询构造等），必须采用成熟第三方组件，禁止手写实现**（用 `el-card`+`el-tree`+表单自己拼装也属手写，不允许）。
- 选型门槛：MIT/Apache 等宽松许可、维护活跃（近一年有发布）、Vue 3 原生、TypeScript 类型完整。
- 引入前必须在设计与账本写明候选对比（许可/最近发布/star/依赖洁净度）与落选原因。

#### SP5-a 规则编辑器（条件树）选型候选
| 包 | 许可 | 最近发布 | 评估 |
|----|------|----------|------|
| `@svar-ui/vue-filter`（FilterBuilder） | MIT | 2026-09（活跃） | Vue 3 原生 + 嵌套 AND/OR + JSON 进出 + TS；生态新（star 少），**首选** |
| `@syncfusion/ej2-vue-querybuilder` | 商业许可 | 2026-09（很活跃） | 最成熟（217 版本），但需商业授权，暂不采用 |
| `vue3-advanced-query-builder` | MIT | 2023-09（停更 ~3 年） | 违反“维护活跃”门槛，落选 |
| `@form-create/element-ui` | MIT | 2024-12 | 是表单构造器而非条件构造器，仍需自定义嵌套逻辑，备选 |

- 注意：多数第三方 query builder 只支持 AND/OR（不支持一元 NOT）→ 叶子层面的否定用算子表达（如 `attribute op=ge`），条件树的 `not` 仅在后端兼容。

#### 集成坑（SP5-a 实测）
- `@svar-ui/vue-filter` 的按钮是**无 `type` 的原生 `<button>`**；放进 Element Plus `el-form`（渲染裸 `<form>`）时点「Add filter/Apply」会触发表单提交导致**整页刷新、对话框数据全丢**。修复：在包裹元素上加 `@submit.prevent`。
- 该库 `all.css` 必须配 `<Willow :fonts="false">` 包裹，否则无样式；主题变量定义在 `.wx-willow-theme` 上，覆盖样式需用**非 scoped** 选择器。
- 该库**不支持自定义 value 编辑组件、不支持按字段禁用/限制算子**（算子由 field `type` 推导）；因此异构叶子参数统一放到「参数区」编辑，条件树只选 field + 算子 + 值。
- 画布（Konva）容器若用 `ResizeObserver` 观测**被 Konva 自身撑大**的元素会形成自反馈锁定尺寸 → 必须观测外层包裹容器。
