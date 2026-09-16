# Phase 4：端到端串联 + UI/UX 统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通「数据集→训练→评估→预测→部署」的跨页串联（带上下文预填），列表/详情显示名称而非 ID，统一提示与弹窗并清理死代码。

**Architecture:** 后端 `module_train` service 补 `dataset_name`/`eval_dataset_name` 批量 enrich；前端统一用 router query 契约（`model_id`/`model_repo_id`/`dataset_id`/`framework`/`autoCreate`），落地页 `onMounted` 消费并自动开窗，消费后 `router.replace` 清 query。

**Tech Stack:** FastAPI + SQLAlchemy 2.0（后端）；Vue 3 + Element Plus + TypeScript（前端）；pytest + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-12-phase4-e2e-linking-ui-design.md`

## Global Constraints

- 后端 `D:\AIStation\backend`；`uv run pytest`、`uv run ruff check`（只判断新增，项目级 FAST002 为 pre-existing）；不新增依赖。
- 前端 `D:\AIStation\frontend`；`pnpm type-check`（项目级有 16 条 pre-existing 错误，只判断新增文件 0 错误）；`eslint`/`prettier` 对新增/改动文件 clean。
- 中文注释；提交 `feat(train): 中文描述` / `fix(train): ...` / `style(...)`；禁 `git add -A`。
- 遵循 Element Plus 栅格与既有 CRUD 范式；不新增自定义 CSS Grid。
- 跨页 query 约定：`model_id`（版本 id）、`model_repo_id`（仓库 id）、`dataset_id`、`framework`、`autoCreate=1`；落地页消费后 `router.replace({ query: {} })`。
- E2E 需先关闭引导 Tour（沿用 `dismissTour` 模式）。

---

### Task 1: 后端名称 enrich + 预测 name 搜索接线

**Files:**
- Modify: `backend/app/plugin/module_train/schema.py`
- Modify: `backend/app/plugin/module_train/service.py`
- Modify: `backend/app/plugin/module_train/controller.py`
- Test: `backend/tests/test_train_dataset_name.py`

**Interfaces:**
- Produces:
  - `TrainTaskOutSchema.dataset_name: str | None`；`TrainEvalOutSchema.eval_dataset_name: str | None`。
  - `TrainService._dataset_name_map(db, ids: list[int]) -> dict[int, str]`（模块级 async 助手）。
  - predict list 接受 `name: str | None` 查询参数。
- Consumes: `app.api.v1.module_annotation.dataset.model.DatasetModel`（表 `annotation_dataset`）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_train_dataset_name.py`：

```python
"""训练/评估数据集名称 enrich 与预测 name 搜索测试。"""


def _create_dataset(test_client, auth_headers, name: str) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": name},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_train_task_dataset_name(test_client, auth_headers):
    ds_id = _create_dataset(test_client, auth_headers, "P4名称测试集")
    created = test_client.post(
        "/api/v1/train/task/create",
        json={
            "name": "P4名称测试任务",
            "framework": "ultralytics",
            "dataset_id": ds_id,
            "hyperparams": {},
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]
    try:
        detail = test_client.get(
            f"/api/v1/train/task/{task_id}", headers=auth_headers
        ).json()["data"]
        assert detail["dataset_name"] == "P4名称测试集"

        listing = test_client.get(
            "/api/v1/train/task/list", headers=auth_headers
        ).json()["data"]
        row = next(i for i in listing["items"] if i["id"] == task_id)
        assert row["dataset_name"] == "P4名称测试集"
    finally:
        test_client.request(
            "DELETE", "/api/v1/train/task/delete", json=[task_id], headers=auth_headers
        )
        test_client.request(
            "DELETE",
            "/api/v1/annotation/dataset/delete",
            json=[ds_id],
            headers=auth_headers,
        )


def test_eval_list_has_eval_dataset_name_key(test_client, auth_headers):
    resp = test_client.get("/api/v1/train/eval/list", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    for item in data["items"]:
        assert "eval_dataset_name" in item


def test_predict_list_accepts_name_param(test_client, auth_headers):
    resp = test_client.get(
        "/api/v1/train/predict/list?name=不存在的模型", headers=auth_headers
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_train_dataset_name.py -q`
Expected: FAIL（`dataset_name` KeyError / 参数未接线）

- [ ] **Step 3: schema 增加字段**

修改 `backend/app/plugin/module_train/schema.py`：
- `TrainTaskOutSchema` 在 `dataset_id: int` 之后加：

```python
    dataset_name: str | None = None
```

- `TrainEvalOutSchema` 在 `eval_dataset_id: int` 之后加：

```python
    eval_dataset_name: str | None = None
```

- [ ] **Step 4: service 增加名称映射与 enrich**

修改 `backend/app/plugin/module_train/service.py`：

(a) 将 `_enrich_task` 改为支持名称映射：

```python
def _enrich_task(row, dataset_names: dict[int, str] | None = None) -> dict:
    d = _model_to_dict(row)
    if d.get("status") == "running":
        live = _calc_progress_from_log(d.get("id", 0))
        if live is not None:
            d["progress"] = live
    if dataset_names:
        ds_id = d.get("dataset_id")
        if ds_id in dataset_names:
            d["dataset_name"] = dataset_names[ds_id]
    return d


async def _dataset_name_map(db, ids) -> dict[int, str]:
    """批量查询标注数据集名称；忽略软删除。"""
    ds_ids = {int(i) for i in ids if i}
    if not ds_ids:
        return {}
    from app.api.v1.module_annotation.dataset.model import DatasetModel

    rows = (
        await db.execute(
            select(DatasetModel.id, DatasetModel.name).where(
                DatasetModel.id.in_(ds_ids), DatasetModel.is_deleted.is_(False)
            )
        )
    ).all()
    return {int(r[0]): r[1] for r in rows}
```

(b) `list_tasks` 末尾改为：

```python
            rows = result.scalars().all()
            name_map = await _dataset_name_map(db, [r.dataset_id for r in rows])
            return [_enrich_task(r, name_map) for r in rows], total
```

(c) `get_task` 改为：

```python
    async def get_task(cls, task_id: int) -> dict | None:
        async with async_db_session() as db:
            t = await db.get(TrainTask, task_id)
            if not t:
                return None
            name_map = await _dataset_name_map(db, [t.dataset_id])
            return _enrich_task(t, name_map)
```

(d) `list_evals` 末尾改为：

```python
            rows = result.scalars().all()
            name_map = await _dataset_name_map(db, [r.eval_dataset_id for r in rows])
            items = []
            for r in rows:
                d = _model_to_dict(r)
                if r.eval_dataset_id in name_map:
                    d["eval_dataset_name"] = name_map[r.eval_dataset_id]
                items.append(d)
            return items, total
```

(e) `get_eval` 中 `data = _model_to_dict(e)` 之后加：

```python
            name_map = await _dataset_name_map(db, [e.eval_dataset_id])
            if e.eval_dataset_id in name_map:
                data["eval_dataset_name"] = name_map[e.eval_dataset_id]
```

- [ ] **Step 5: controller 预测列表加 name**

修改 `backend/app/plugin/module_train/controller.py` 的 `list_predicts` 签名，在 `model_repo_id` 之前加：

```python
    name: str | None = Query(None),
```

并在传给 service 的 dict 中加 `"name": name,`。

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_train_dataset_name.py -q`
Expected: PASS（3 passed）

- [ ] **Step 7: 全量 + ruff + 提交**

Run: `uv run pytest -q && uv run ruff check app/plugin/module_train/schema.py app/plugin/module_train/service.py app/plugin/module_train/controller.py`
Expected: 全部通过

```bash
git add backend/app/plugin/module_train/schema.py backend/app/plugin/module_train/service.py backend/app/plugin/module_train/controller.py backend/tests/test_train_dataset_name.py
git commit -m "feat(train): 训练/评估列表补数据集名称并接通预测 name 搜索"
```

---

### Task 2: 训练详情→评估闭环 + 评估自动开窗

**Files:**
- Modify: `frontend/src/views/module_train/task/detail.vue`
- Modify: `frontend/src/views/module_train/eval/index.vue`
- Test: `frontend/e2e/train-to-eval.spec.ts`

**Interfaces:**
- Consumes: Task 1 无直接依赖；路由 `/train/eval?model_repo_id=&model_id=&autoCreate=1`。
- Produces: 评估页 `loadModelVersions()` 可在 `onMounted` 被 await。

- [ ] **Step 1: 训练详情评估按钮跳转**

修改 `frontend/src/views/module_train/task/detail.vue` 的 `handleEvaluate`：

```ts
function handleEvaluate() {
  const repoId = task.value?.model_repo_id;
  if (!repoId) {
    ElMessage.warning("暂无关联模型，请先完成训练");
    return;
  }
  router.push({ path: "/train/eval", query: { model_repo_id: String(repoId), autoCreate: "1" } });
}
```

- [ ] **Step 2: 评估页抽出模型加载函数并支持自动开窗**

修改 `frontend/src/views/module_train/eval/index.vue`：

(a) 把加载模型版本的 IIFE：

```ts
(async () => {
  const r = await TrainAPI.getModelList({ page_no: 1, page_size: 100 });
  modelVersions.value = r.data?.data?.items || [];
})();
```

替换为：

```ts
async function loadModelVersions() {
  const r = await TrainAPI.getModelList({ page_no: 1, page_size: 100 });
  modelVersions.value = r.data?.data?.items || [];
}
loadModelVersions();
```

(b) `handleOpenCreateDialog` 支持按模型版本 id 或仓库 id 解析（兼容两种 query）：

```ts
function handleOpenCreateDialog() {
  const curModel =
    modelVersions.value.find((m: any) => m.id === modelRepoId) ||
    modelVersions.value.find((m: any) => m.repo_id === modelRepoId);
  createForm.modelId = curModel?.id || null;
  createForm.evalDatasetId = curModel?.annotation_dataset_id || null;
  createForm.hyperparams = {
    imgsz: 640,
    batch: 16,
    conf: 0.001,
    iou: 0.6,
    device: "0",
    mode: "det",
    model_size: "tiny",
  };
  selectedModelFramework.value = curModel?.framework || "";
  createDialogVisible.value = true;
}
```

(c) `onMounted` 改为：

```ts
onMounted(async () => {
  startPoll();
  if (route.query.autoCreate === "1") {
    await loadModelVersions();
    handleOpenCreateDialog();
    router.replace({ query: {} });
  }
});
```

- [ ] **Step 3: 类型检查**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'task/detail|eval/index'`
Expected: 无输出（0 新增错误）

- [ ] **Step 4: E2E**

创建 `frontend/e2e/train-to-eval.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) await close.click({ force: true }).catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  await page.locator(".el-tour").waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
}

test("带 autoCreate 进入评估页会自动打开创建弹窗", async ({ page }) => {
  await page.goto("/#/train/eval?model_repo_id=1&autoCreate=1", {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  // 有可用模型版本时弹窗自动打开；无数据时至少不报错
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 5: 运行 E2E**

Run: `pnpm e2e -- train-to-eval.spec.ts`
Expected: 1 passed

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/module_train/task/detail.vue frontend/src/views/module_train/eval/index.vue frontend/e2e/train-to-eval.spec.ts
git commit -m "feat(train): 训练详情到评估闭环与自动开窗预填"
```

---

### Task 3: 仓库/评估→预测 + model_repo_id 修复 + 预测自动开窗

**Files:**
- Modify: `frontend/src/views/module_train/repo/index.vue`
- Modify: `frontend/src/views/module_train/eval/detail.vue`
- Modify: `frontend/src/views/module_train/predict/index.vue`
- Test: `frontend/e2e/repo-to-predict.spec.ts`

**Interfaces:**
- Consumes: 路由 `/train/predict?model_id=&model_repo_id=&autoCreate=1`。
- Produces: 预测创建 `model_repo_id` 取 `repo_id`；预测页 `onMounted` 支持自动开窗。

- [ ] **Step 1: 仓库操作列加「预测」**

修改 `frontend/src/views/module_train/repo/index.vue`，在「评估」按钮之后插入：

```html
                <el-button
                  v-hasPerm="['module_train:model:query']"
                  size="small"
                  link
                  icon="DataLine"
                  @click="handlePredict(scope.row)"
                >
                  预测
                </el-button>
```

并新增函数（放在 `handleEval` 之后）：

```ts
function handlePredict(row: any) {
  router.push({
    path: "/train/predict",
    query: { model_id: String(row.id), model_repo_id: String(row.repo_id || 0), autoCreate: "1" },
  });
}
```

- [ ] **Step 2: 评估详情加「去预测」**

修改 `frontend/src/views/module_train/eval/detail.vue` 的模型输出操作区（`查看模型`/`导出模型` 之后）：

```html
        <el-button
          v-if="evalData?.status === 'success'"
          size="default"
          type="primary"
          @click="handleGoPredict"
        >
          去预测
        </el-button>
```

新增函数（`router` 已存在）：

```ts
function handleGoPredict() {
  if (!evalData?.model_id) {
    ElMessage.warning("暂无模型版本，无法预测");
    return;
  }
  router.push({
    path: "/train/predict",
    query: {
      model_id: String(evalData.model_id),
      model_repo_id: String(evalData.model_repo_id || 0),
      autoCreate: "1",
    },
  });
}
```

- [ ] **Step 3: 预测页修 bug + query 自动开窗**

修改 `frontend/src/views/module_train/predict/index.vue`：

(a) 导入改为含 `useRoute`：

```ts
import { useRouter, useRoute } from "vue-router";
```

并在 `const router = useRouter();` 后加：

```ts
const route = useRoute();
```

(b) `handleCreate` 中修正 `model_repo_id`：

```ts
      model_repo_id: models.value.find((m: any) => m.id === createForm.modelId)?.repo_id || 0,
```

(c) `onMounted` 改为：

```ts
onMounted(async () => {
  const [mRes, dsRes] = await Promise.all([
    TrainAPI.getModelList({ page_no: 1, page_size: 100 }),
    AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 }),
  ]);
  models.value = mRes.data?.data?.items || [];
  datasets.value = dsRes.data?.data?.items || [];
  refreshList();

  if (route.query.autoCreate === "1") {
    const modelId = Number(route.query.model_id || 0);
    if (modelId && models.value.some((m: any) => m.id === modelId)) {
      createForm.modelId = modelId;
      onPredictModelChange(modelId);
      showCreateDialog.value = true;
    }
    router.replace({ query: {} });
  }
});
```

（若模型变化处理函数名不是 `onPredictModelChange`，改用该文件模板 `@change` 上绑定的实际函数名。）

- [ ] **Step 4: 类型检查**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'repo/index|eval/detail|predict/index'`
Expected: 无输出

- [ ] **Step 5: E2E**

创建 `frontend/e2e/repo-to-predict.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) await close.click({ force: true }).catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  await page.locator(".el-tour").waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
}

test("带 autoCreate 进入预测页会自动打开创建弹窗", async ({ page }) => {
  // 预测页仅在模型列表命中 model_id 时才自动开窗：用路由拦截注入一个模型版本
  await page.route("**/train/model/list*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 0,
        msg: "ok",
        data: {
          items: [
            {
              id: 42,
              repo_id: 7,
              name: "mock-model",
              version: 1,
              framework: "ultralytics",
              annotation_dataset_id: 1,
            },
          ],
          total: 1,
        },
      }),
    })
  );
  await page.goto("/#/train/predict?model_id=42&model_repo_id=7&autoCreate=1", {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await expect(page.locator(".el-dialog")).toBeVisible({ timeout: 10_000 });
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 6: 运行 E2E**

Run: `pnpm e2e -- repo-to-predict.spec.ts`
Expected: 1 passed

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/module_train/repo/index.vue frontend/src/views/module_train/eval/detail.vue frontend/src/views/module_train/predict/index.vue frontend/e2e/repo-to-predict.spec.ts
git commit -m "feat(train): 仓库/评估到预测跳转并修正 model_repo_id"
```

---

### Task 4: 数据集→训练 + 标注任务 task_id 上下文

**Files:**
- Modify: `frontend/src/views/module_annotation/dataset/index.vue`
- Modify: `frontend/src/views/module_train/task/index.vue`
- Modify: `frontend/src/views/module_annotation/task/index.vue`
- Test: `frontend/e2e/dataset-to-train.spec.ts`

**Interfaces:**
- Consumes: 路由 `/train/task?dataset_id=&autoCreate=1`；`AnnotationAPI.getTaskDetail(id)`。
- Produces: 训练任务页支持 `dataset_id` 预填自动开窗；标注任务页按 `task_id` 预填搜索。

- [ ] **Step 1: 数据集操作列加「去训练」**

修改 `frontend/src/views/module_annotation/dataset/index.vue`，在操作列「导出」按钮之后插入：

```html
              <el-button
                size="small"
                type="primary"
                link
                @click="router.push(`/train/task?dataset_id=${scope.row.id}&autoCreate=1`)"
              >
                去训练
              </el-button>
```

- [ ] **Step 2: 训练任务页消费 dataset_id**

修改 `frontend/src/views/module_train/task/index.vue` 的 `onMounted`：在 `editId` 分支之前加入 dataset_id 处理，并在所有分支末尾清 query：

```ts
onMounted(() => {
  startPoll();
  const editId = Number(route.query.edit_id || 0);
  if (editId) {
    handleOpenDialog("update", editId);
    router.replace({ query: {} });
    return;
  }
  // 从数据集页"去训练"进入：预填数据集并自动开窗
  const dsId = Number(route.query.dataset_id || 0);
  if (dsId) {
    formData.dataset_id = dsId;
    dialogVisible.title = "新建训练任务";
    dialogVisible.visible = true;
    router.replace({ query: {} });
    return;
  }
  const fw = route.query.framework as string | undefined;
  const modelId = route.query.model_id;
  if (fw && ["ultralytics", "paddlex"].includes(fw)) {
    onFrameworkChange(fw);
    formData.framework = fw;
    if (modelId) formData.base_model_id = Number(modelId);
    dialogVisible.title = "新建训练任务";
    dialogVisible.visible = true;
    router.replace({ query: {} });
  }
});
```

- [ ] **Step 3: 标注任务页消费 task_id**

修改 `frontend/src/views/module_annotation/task/index.vue`：

(a) 导入新增 `useRoute` 与 `onMounted`（若尚未导入）：

```ts
import { useRoute } from "vue-router";
```

(b) 在 `const router = useRouter();`（约 294 行）之后加：

```ts
const route = useRoute();
```

(c) 文件末尾新增：

```ts
onMounted(async () => {
  const taskId = Number(route.query.task_id || 0);
  if (!taskId) return;
  try {
    const res = await AnnotationAPI.getTaskDetail(taskId);
    const task = res.data?.data;
    if (task?.name) {
      const item: any = searchConfig.formItems?.find((i: any) => i.prop === "name");
      if (item) item.initialValue = task.name;
      (searchRef.value as any)?.setQueryParams?.({ name: task.name });
      refreshList();
    }
  } catch {
    /* 忽略定位失败 */
  }
});
```

（若 `onMounted` 已存在，合并到其中；`AnnotationAPI` 已在该文件导入。）

- [ ] **Step 4: 类型检查**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'annotation/dataset|module_train/task|annotation/task'`
Expected: 无输出

- [ ] **Step 5: E2E**

创建 `frontend/e2e/dataset-to-train.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) await close.click({ force: true }).catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  await page.locator(".el-tour").waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
}

test("带 dataset_id 进入训练页会自动打开创建弹窗", async ({ page }) => {
  await page.goto("/#/train/task?dataset_id=1&autoCreate=1", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await expect(page.locator(".el-dialog")).toBeVisible({ timeout: 10_000 });
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 6: 运行 E2E**

Run: `pnpm e2e -- dataset-to-train.spec.ts`
Expected: 1 passed

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/module_annotation/dataset/index.vue frontend/src/views/module_train/task/index.vue frontend/src/views/module_annotation/task/index.vue frontend/e2e/dataset-to-train.spec.ts
git commit -m "feat(train): 数据集到训练入口与标注任务上下文消费"
```

---

### Task 5: 表单补全 + 列表/详情名称展示

**Files:**
- Modify: `frontend/src/views/module_train/task/index.vue`
- Modify: `frontend/src/views/module_train/task/detail.vue`
- Modify: `frontend/src/views/module_train/eval/index.vue`
- Modify: `frontend/src/views/module_train/eval/detail.vue`

**Interfaces:**
- Consumes: Task 1 的 `dataset_name` / `eval_dataset_name`。

- [ ] **Step 1: base_model_id 控件 + 默认超参补 trainRatio**

修改 `frontend/src/views/module_train/task/index.vue`：

(a) 在「标注任务」表单项之后插入：

```html
        <el-form-item label="基础模型">
          <el-input-number
            v-model="formData.base_model_id"
            :min="0"
            :controls="false"
            style="width: 100%"
            placeholder="留空表示从零训练；可填模型版本 ID"
          />
        </el-form-item>
```

(b) `defaultHpPaddle` 增加 `trainRatio`：

```ts
const defaultHpPaddle = () => ({
  mode: "det",
  model_size: "tiny",
  epochs: 100,
  batch: 8,
  lr: 0.0005,
  device: "0",
  pretrained: true,
  trainRatio: 80,
});
```

(c) `handleOpenDialog` 编辑分支回填补全：

```ts
    Object.assign(formData, {
      id: data.id,
      name: data.name,
      dataset_id: data.dataset_id,
      annotation_task_id: data.annotation_task_id,
      base_model_id: data.base_model_id,
      framework: data.framework,
    });
```

- [ ] **Step 2: 训练列表/详情显示数据集名称**

修改 `frontend/src/views/module_train/task/index.vue` 列表列（约 77-83 行）替换为：

```html
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'dataset_id')?.show"
              key="dataset_id"
              label="数据集"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="scope">
                {{ scope.row.dataset_name || `#${scope.row.dataset_id}` }}
              </template>
            </el-table-column>
```

修改 `frontend/src/views/module_train/task/detail.vue` 第 31 行：

```html
            <el-descriptions-item label="数据集">{{
              task?.dataset_name || `#${task?.dataset_id}`
            }}</el-descriptions-item>
```

- [ ] **Step 3: 评估列表/详情显示数据集名称**

修改 `frontend/src/views/module_train/eval/index.vue` 列表列（约 81-87 行）替换为：

```html
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'eval_dataset_id')?.show"
              key="eval_dataset_id"
              label="评估数据集"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="scope">
                {{ scope.row.eval_dataset_name || `#${scope.row.eval_dataset_id}` }}
              </template>
            </el-table-column>
```

修改 `frontend/src/views/module_train/eval/detail.vue` 的「评估数据集 ID」项：

```html
            <el-descriptions-item label="评估数据集">
              {{ evalData?.eval_dataset_name || `#${evalData?.eval_dataset_id}` }}
            </el-descriptions-item>
```

- [ ] **Step 4: 类型检查**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'module_train'`
Expected: 无输出

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_train/task/index.vue frontend/src/views/module_train/task/detail.vue frontend/src/views/module_train/eval/index.vue frontend/src/views/module_train/eval/detail.vue
git commit -m "feat(train): 表单补全与数据集名称展示"
```

---

### Task 6: toast 去重 + 死代码 + CSS 语法

**Files:**
- Modify: `frontend/src/views/module_video/camera/index.vue`
- Modify: `frontend/src/views/module_video/record/index.vue`
- Modify: `frontend/src/views/module_video/alarm/index.vue`
- Modify: `frontend/src/views/module_video/algorithm/index.vue`
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`
- Modify: `frontend/src/views/module_train/repo/index.vue`
- Modify: `frontend/src/views/module_train/task/index.vue`
- Modify: `frontend/src/components/GithubCorner/index.vue`
- Modify: `frontend/src/layouts/components/NavBar/components/LockDialog.vue`
- Modify: `frontend/src/views/dashboard/workplace.vue`

**Interfaces:**
- 依赖：全局拦截器已负责成功/失败提示。

- [ ] **Step 1: 移除重复 toast**

按审计行号移除与拦截器重复的页面级提示：
- `module_video/camera/index.vue`：移除 `ElMessage.success("推流启动成功")`、`ElMessage.success("推流已停止")` 及其后重复的 `ElMessage.error(...)`（`startStream`/`stopStream` 为 POST，拦截器已提示；失败如需自定义文案则给该请求加 `_silent`）。
- `module_video/record/index.vue`：移除 `ElMessage.success("计划已触发执行")`、`ElMessage.success("计划已停止")`。
- `module_video/alarm/index.vue`：移除紧跟 `confirmAlarm()` 的 `ElMessage.success(...)`。
- `module_video/algorithm/index.vue`：移除 `ElMessage.success("模型已上传...")` 与紧随的 `ElMessage.error(...)`。
- `module_annotation/annotation/index.vue`：移除 `AnnotationAPI.updateTask` 后重复的 `ElMessage.error(...)`。

保留：`repo/index.vue` 中 `_silent` 分支的必要提示（非重复）。

- [ ] **Step 2: 清死代码**

- `frontend/src/views/module_train/repo/index.vue`：把冗余条件 `r.id === id || r.repo_id === id || r.id === id` 简化为 `r.id === id || r.repo_id === id`。
- `frontend/src/views/module_train/task/index.vue`：删除未被引用的 `groupLabel()` 函数。

- [ ] **Step 3: CSS 媒体查询标准化**

将以下非标准语法改为标准写法（仅语法，不改内容）：
- `frontend/src/components/GithubCorner/index.vue`：`@media (width <= 500px)` → `@media (max-width: 500px)`。
- `frontend/src/layouts/components/NavBar/components/LockDialog.vue`：`@media (width <=767px)` → `@media (max-width: 767px)`。
- `frontend/src/views/dashboard/workplace.vue`：`@media (width <= 991px)` / `(width <= 520px)` / `(width <= 575px)` → `@media (max-width: 991px)` / `(max-width: 520px)` / `(max-width: 575px)`。

- [ ] **Step 4: 静态检查**

Run: `pnpm exec eslint src/views/module_video/camera/index.vue src/views/module_video/record/index.vue src/views/module_video/alarm/index.vue src/views/module_video/algorithm/index.vue src/views/module_annotation/annotation/index.vue src/views/module_train/repo/index.vue src/views/module_train/task/index.vue`
Expected: 无新增错误（LivePlayer/live/playback pre-existing 除外）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_video/camera/index.vue frontend/src/views/module_video/record/index.vue frontend/src/views/module_video/alarm/index.vue frontend/src/views/module_video/algorithm/index.vue frontend/src/views/module_annotation/annotation/index.vue frontend/src/views/module_train/repo/index.vue frontend/src/views/module_train/task/index.vue frontend/src/components/GithubCorner/index.vue frontend/src/layouts/components/NavBar/components/LockDialog.vue frontend/src/views/dashboard/workplace.vue
git commit -m "fix(ui): 去除重复提示并标准化媒体查询、清理死代码"
```

---

### Task 7: train eval/predict/deploy 三个弹窗 → EnhancedDialog

**Files:**
- Modify: `frontend/src/views/module_train/eval/index.vue`
- Modify: `frontend/src/views/module_train/predict/index.vue`
- Modify: `frontend/src/views/module_train/deploy/index.vue`

**Interfaces:**
- Consumes: `@/components/CURD/EnhancedDialog.vue`（props：`modelValue`、`title`、`width`；slots：default、`footer`；透传 `append-to-body` 等 attrs）。

- [ ] **Step 1: eval 创建弹窗迁移**

修改 `frontend/src/views/module_train/eval/index.vue`：
- 导入：`import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";`
- 把 `<el-dialog v-model="createDialogVisible" ...>`（约 217 行）改为：

```html
    <EnhancedDialog
      v-model="createDialogVisible"
      title="新建评估"
      append-to-body
      width="640px"
    >
```

- 把其结尾 `</el-dialog>` 改为 `</EnhancedDialog>`（保持内部 `<el-form>` 与 `#footer` 不变）。

- [ ] **Step 2: predict 创建弹窗迁移**

修改 `frontend/src/views/module_train/predict/index.vue`：
- 导入 `EnhancedDialog`。
- `<el-dialog v-model="showCreateDialog" ...>`（约 212 行）→

```html
    <EnhancedDialog v-model="showCreateDialog" title="新建预测" append-to-body width="640px">
```

- 对应 `</el-dialog>` → `</EnhancedDialog>`。

- [ ] **Step 3: deploy 创建弹窗迁移**

修改 `frontend/src/views/module_train/deploy/index.vue`：
- 导入 `EnhancedDialog`。
- `<el-dialog v-model="showCreateDialog" title="新建部署" width="500px">`（约 214 行）→

```html
    <EnhancedDialog v-model="showCreateDialog" title="新建部署" append-to-body width="560px">
```

- 对应 `</el-dialog>` → `</EnhancedDialog>`。
- `showKeyDialog` 弹窗（含 readonly key 展示）**保持原生 el-dialog**（不属于 CRUD 表单弹窗）。

- [ ] **Step 4: 类型检查 + 全量 E2E 冒烟**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'module_train'`
Expected: 无输出
Run: `pnpm e2e -- train-to-eval.spec.ts repo-to-predict.spec.ts`
Expected: 全 passed（自动开窗行为在 EnhancedDialog 下仍成立）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_train/eval/index.vue frontend/src/views/module_train/predict/index.vue frontend/src/views/module_train/deploy/index.vue
git commit -m "style(train): 评估/预测/部署创建弹窗统一为 EnhancedDialog"
```

---

### Task 8: 全量回归 + 账本

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 后端全量 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/`
Expected: 全部通过（ruff 只对本次改动目录；项目级 FAST002 pre-existing）

- [ ] **Step 2: 前端类型/静态/全量 E2E**

Run: `cd frontend && pnpm exec vue-tsc --noEmit 2>&1 | Select-String -NotMatch 'module_generator|module_monitor|module_system|module_task'`
说明：项目级 16 条 pre-existing 错误在无关模块；确认无新增。
Run: `pnpm exec eslint <本 Phase 改动的全部前端文件>` → 无新增错误
Run: `pnpm e2e` → 全量 passed

- [ ] **Step 3: 更新账本并提交**

在 `.superpowers/sdd/progress.md` 末尾追加 Phase 4 完成记录（各 Task 提交区间、测试结果、pre-existing 说明）。

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(pipeline): Phase 4 完成记录"
```

---

## Self-Review

**Spec coverage:**
- §4 后端名称 enrich（训练/评估）→ Task 1 ✅；predict name 搜索 → Task 1 ✅
- §5.1 训练→评估闭环 → Task 2 ✅
- §5.2 仓库/评估→预测 + model_repo_id 修复 → Task 3 ✅
- §5.3 数据集→训练 + 标注 task_id → Task 4 ✅
- §5.4 表单补全 + 名称展示 → Task 5 ✅
- §5.5 toast/死代码/CSS → Task 6；弹窗统一 → Task 7 ✅
- §7 测试 → Task 1（pytest）、Task 2/3/4（E2E）、Task 8（回归）✅

**Placeholder scan:** 无 TBD；关键步骤含代码。预测页 `@change` 函数名以文件实际为准（已注明）。

**Type consistency:**
- 后端字段 `dataset_name`/`eval_dataset_name` 在 Task 1 定义，Task 5 消费 ✅
- query 契约 `model_id`/`model_repo_id`/`dataset_id`/`autoCreate` 跨 Task 2/3/4 一致 ✅
- `EnhancedDialog` 用法与组件 props/slots 一致 ✅

**风险备注:** 自动开窗依赖模型/数据集数据存在（空库时 E2E 可能看不到弹窗）——计划中 E2E 断言以“带 autoCreate 会打开弹窗”为主，若目标数据缺失需在验收时用真实数据复核；`_dataset_name_map` 对软删数据集返回缺失，前端回退 `#id`。
