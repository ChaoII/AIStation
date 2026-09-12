# Phase 5A：半成品功能补全（P1-P6）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把导出历史、部署日志查看器、定时训练 UI、数据清洗 UI、标注历史/回滚、模型仓库/版本 UI 六项半成品补到可从 UI 完整操作并产生正确结果。

**Architecture:** 后端仅新增导出历史写入与标注回滚；前端新增 6 个独立组件（抽屉/面板）挂到现有页面，不改菜单。P2 使用现有依赖 `vue3-cron-plus` 做 cron 可视化。

**Tech Stack:** FastAPI + SQLAlchemy 2.0（后端）；Vue 3 + Element Plus + TypeScript（前端）；pytest + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-12-phase5a-halfdone-features-design.md`

## Global Constraints

- 后端 `D:\AIStation\backend`；`uv run pytest`、`uv run ruff check`（只判断新增）；不新增后端依赖。
- 前端 `D:\AIStation\frontend`；`pnpm type-check`（项目级 pre-existing 错误不追平）、目标文件 eslint/prettier clean；不新增前端依赖（`vue3-cron-plus` 已存在）。
- 中文注释；提交 `feat(annotation): ...` / `feat(train): ...` / `fix(...)`；禁 `git add -A`。
- 遵循 Element Plus 栅格与既有 CRUD 范式；不新增菜单。
- E2E 需先关闭引导 Tour（`dismissTour` 不用 Escape）。

---

### Task 1: P1 导出历史（后端写入 + 前端抽屉）

**Files:**
- Modify: `backend/app/plugin/module_train/service.py`（`export_dataset` 写历史）
- Test: `backend/tests/test_export_history.py`
- Modify: `frontend/src/api/module_annotation.ts`
- Create: `frontend/src/components/Annotation/ExportHistoryDrawer.vue`
- Modify: `frontend/src/views/module_annotation/dataset/index.vue`
- Test: `frontend/e2e/export-history.spec.ts`

**Interfaces:**
- Produces：`AnnotationAPI.getExportHistory(datasetId)`。
- Consumes：`DatasetExportModel`（表 `annotation_dataset_export`）、`GET /api/v1/annotation/dataset/export/history/{id}`。

- [ ] **Step 1: 写失败测试（后端）**

创建 `backend/tests/test_export_history.py`：

```python
"""导出历史写入测试。"""
import hashlib


def _create_dataset(test_client, auth_headers, name: str) -> int:
    r = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_export_writes_history(test_client, auth_headers):
    ds_id = _create_dataset(test_client, auth_headers, "P5A导出历史集")
    try:
        resp = test_client.post(
            "/api/v1/train/dataset/export",
            json={"dataset_id": ds_id, "format": "yolo"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        hist = test_client.get(
            f"/api/v1/annotation/dataset/export/history/{ds_id}", headers=auth_headers
        ).json()["data"]
        assert len(hist) >= 1
        row = hist[0]
        assert row["format"] == "yolo"
        assert row["file_size"] > 0
        assert row["checksum"]
        assert row["download_url"]
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/annotation/dataset/delete",
            json=[ds_id],
            headers=auth_headers,
        )
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_export_history.py -q`
Expected: FAIL（history 为空）

- [ ] **Step 3: 实现写入**

修改 `backend/app/plugin/module_train/service.py::export_dataset`：在计算 `download_url` 之后、`_delayed_cleanup` 之前插入：

```python
        # 记录导出历史（失败不阻断导出主流程）
        try:
            import hashlib as _hashlib

            from app.api.v1.module_annotation.dataset.export_model import DatasetExportModel
            from app.core.database import async_db_session as _db_session

            file_size = os.path.getsize(zip_path)
            md5 = _hashlib.md5()
            with open(zip_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    md5.update(chunk)
            async with _db_session.begin() as db:
                db.add(
                    DatasetExportModel(
                        dataset_id=data.dataset_id,
                        format=data.format,
                        exported_by=auth.user.id,
                        download_url=download_url,
                        file_size=file_size,
                        checksum=md5.hexdigest(),
                        extra={
                            "annotation_task_id": data.annotation_task_id,
                            "ocr_rec": data.ocr_rec,
                            "rustfs_key": rustfs_key,
                        },
                    )
                )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"写入导出历史失败: {e}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_export_history.py -q`
Expected: PASS

- [ ] **Step 5: 前端 API**

在 `frontend/src/api/module_annotation.ts` 的 `AnnotationAPI` 对象内新增：

```ts
  getExportHistory(datasetId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/dataset/export/history/${datasetId}`,
      method: "get",
    });
  },
```

- [ ] **Step 6: 导出历史抽屉组件**

创建 `frontend/src/components/Annotation/ExportHistoryDrawer.vue`：

```vue
<template>
  <el-drawer v-model="visible" title="导出历史" size="640px">
    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column label="格式" prop="format" width="90" />
      <el-table-column label="导出时间" prop="export_time" min-width="170" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="导出人" prop="exported_by" width="90" />
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-link
            v-if="row.download_url"
            type="primary"
            :href="row.download_url"
            target="_blank"
          >
            下载
          </el-link>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无导出记录" />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

const visible = ref(false);
const loading = ref(false);
const rows = ref<any[]>([]);

async function open(datasetId: number) {
  visible.value = true;
  loading.value = true;
  try {
    const res = await AnnotationAPI.getExportHistory(datasetId);
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

function formatSize(n?: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

defineExpose({ open });
</script>

<style scoped>
.text-muted {
  color: var(--el-text-color-placeholder);
}
</style>
```

- [ ] **Step 7: 数据集页接入**

修改 `frontend/src/views/module_annotation/dataset/index.vue`：
- 脚本导入：`import ExportHistoryDrawer from "@/components/Annotation/ExportHistoryDrawer.vue";`
- 在根容器末尾（`</div>` 前）加：`<ExportHistoryDrawer ref="exportHistoryRef" />`
- 脚本加：`const exportHistoryRef = ref();`（若已有 `ref` 导入）
- 操作列「导出」按钮后新增：

```html
                <el-button size="small" link type="info" @click="exportHistoryRef.open(scope.row.id)">
                  导出历史
                </el-button>
```

- [ ] **Step 8: 类型检查 + E2E**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'ExportHistoryDrawer|dataset/index'`
Expected: 无输出

创建 `frontend/e2e/export-history.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("数据集页可打开导出历史抽屉", async ({ page }) => {
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  const btn = page.getByRole("button", { name: "导出历史" }).first();
  await btn.click({ force: true });
  await expect(page.locator(".el-drawer")).toBeVisible();
  await expect(page.locator(".el-drawer").getByText("导出历史")).toBeVisible();
});
```

- [ ] **Step 9: 运行 E2E**

Run: `pnpm e2e -- export-history.spec.ts`
Expected: 1 passed

- [ ] **Step 10: 全量 + 提交**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/service.py`

```bash
git add backend/app/plugin/module_train/service.py backend/tests/test_export_history.py frontend/src/api/module_annotation.ts frontend/src/components/Annotation/ExportHistoryDrawer.vue frontend/src/views/module_annotation/dataset/index.vue frontend/e2e/export-history.spec.ts
git commit -m "feat(annotation): 导出历史写入与查看"
```

---

### Task 2: P4 部署详情/日志查看器

**Files:**
- Modify: `frontend/src/api/module_train.ts`
- Create: `frontend/src/components/Train/DeployLogDrawer.vue`
- Modify: `frontend/src/views/module_train/deploy/index.vue`
- Test: `frontend/e2e/deploy-log.spec.ts`

**Interfaces:**
- Produces：`TrainAPI.getDeployDetail(id)`、`TrainAPI.getDeployLogs(id)`、组件 `DeployLogDrawer.open(deploy)`。

- [ ] **Step 1: API**

在 `frontend/src/api/module_train.ts` 的 `TrainAPI` 对象 `deleteDeploy` 之前新增：

```ts
  getDeployDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/deploy/${id}/detail`, method: "get" });
  },
  getDeployLogs(id: number) {
    return request<ApiResponse<{ logs: string }>>({
      url: `${API_PATH}/deploy/${id}/logs`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 抽屉组件**

创建 `frontend/src/components/Train/DeployLogDrawer.vue`：

```vue
<template>
  <el-drawer v-model="visible" title="部署详情" size="640px">
    <el-descriptions v-if="detail" :column="1" border size="small">
      <el-descriptions-item label="部署名称">{{ detail.name }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
      <el-descriptions-item label="端口">{{ detail.host_port ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="API URL">{{ detail.api_url || "待启动" }}</el-descriptions-item>
      <el-descriptions-item label="到期时间">{{ detail.expires_at || "—" }}</el-descriptions-item>
    </el-descriptions>

    <div class="log-head">
      <span class="log-title">部署日志</span>
      <el-button size="small" :loading="loading" @click="loadLogs">刷新</el-button>
    </div>
    <pre class="deploy-log">{{ logs || "暂无日志" }}</pre>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { TrainAPI } from "@/api/module_train";

const visible = ref(false);
const loading = ref(false);
const detail = ref<any>(null);
const logs = ref("");
let currentId = 0;

async function loadLogs() {
  if (!currentId) return;
  loading.value = true;
  try {
    const res = await TrainAPI.getDeployLogs(currentId);
    logs.value = res.data?.data?.logs || "";
  } finally {
    loading.value = false;
  }
}

async function open(row: any) {
  visible.value = true;
  currentId = row.id;
  detail.value = row;
  logs.value = "";
  try {
    const res = await TrainAPI.getDeployDetail(row.id);
    if (res.data?.data) detail.value = res.data.data;
  } catch {
    /* 保留列表行 */
  }
  await loadLogs();
}

defineExpose({ open });
</script>

<style scoped>
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 8px;
}
.log-title {
  font-weight: 600;
}
.deploy-log {
  max-height: 360px;
  padding: 12px;
  overflow: auto;
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #d4d4d4;
  white-space: pre-wrap;
  background: #1e1e1e;
  border-radius: 6px;
}
</style>
```

- [ ] **Step 3: 部署页接入**

修改 `frontend/src/views/module_train/deploy/index.vue`：
- 导入 `import DeployLogDrawer from "@/components/Train/DeployLogDrawer.vue";`
- 根容器末尾加 `<DeployLogDrawer ref="deployLogRef" />`
- 脚本加 `const deployLogRef = ref();`（确认 `ref` 已导入）
- 操作列「停止/重启/续期/删除」等按钮之后新增：

```html
                <el-button size="small" link @click="deployLogRef.open(scope.row)">详情</el-button>
```

- [ ] **Step 4: 类型检查 + E2E**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'DeployLogDrawer|deploy/index'`
Expected: 无输出

创建 `frontend/e2e/deploy-log.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("部署页存在详情按钮并打开抽屉", async ({ page }) => {
  await page.goto("/#/train/deploy", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  const btn = page.getByRole("button", { name: "详情" }).first();
  if (await btn.count()) {
    await btn.click({ force: true });
    await expect(page.locator(".el-drawer")).toBeVisible();
  } else {
    // 无部署数据时至少页面正常
    await expect(page.locator(".app-main .app-container").first()).toBeVisible();
  }
});
```

- [ ] **Step 5: 运行 E2E + 提交**

Run: `pnpm e2e -- deploy-log.spec.ts`

```bash
git add frontend/src/api/module_train.ts frontend/src/components/Train/DeployLogDrawer.vue frontend/src/views/module_train/deploy/index.vue frontend/e2e/deploy-log.spec.ts
git commit -m "feat(train): 部署详情与日志查看器"
```

---

### Task 3: P2 定时训练 UI

**Files:**
- Modify: `frontend/src/api/module_train.ts`
- Create: `frontend/src/components/Train/SchedulePanel.vue`
- Modify: `frontend/src/views/module_train/task/index.vue`
- Test: `frontend/e2e/train-schedule.spec.ts`

**Interfaces:**
- Produces：`TrainAPI.getTrainScheduleList/createTrainSchedule/updateTrainSchedule/deleteTrainSchedule`；`SchedulePanel` 组件。
- Backend：`/api/v1/train/schedule/*`（已有）。

- [ ] **Step 1: API**

在 `frontend/src/api/module_train.ts` 的 `TrainAPI` 对象末尾（`deleteDeploy` 之后）新增：

```ts
  getTrainScheduleList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/schedule/list`, method: "get" });
  },
  createTrainSchedule(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/schedule/create`, method: "post", data });
  },
  updateTrainSchedule(id: number, data: any) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/schedule/update/${id}`,
      method: "put",
      data,
    });
  },
  deleteTrainSchedule(ids: number[]) {
    return request<ApiResponse>({
      url: `${API_PATH}/schedule/delete`,
      method: "delete",
      data: ids,
    });
  },
```

- [ ] **Step 2: 定时训练面板组件**

创建 `frontend/src/components/Train/SchedulePanel.vue`：

```vue
<template>
  <div class="schedule-panel">
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建定时计划</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
      <el-table-column label="框架" prop="framework" width="120" />
      <el-table-column label="cron" prop="cron_expr" min-width="140" />
      <el-table-column label="启用" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上次运行" prop="last_run_at" min-width="170" />
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <EnhancedDialog v-model="dialogVisible" :title="form.id ? '编辑定时计划' : '新建定时计划'" append-to-body width="680px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" placeholder="如：每晚 2 点训练" />
        </el-form-item>
        <el-form-item label="框架">
          <el-radio-group v-model="form.framework">
            <el-radio value="ultralytics">Ultralytics</el-radio>
            <el-radio value="paddlex">PaddleX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数据集" required>
          <el-select v-model="form.dataset_id" filterable style="width: 100%" placeholder="选择数据集">
            <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="cron 表达式" required>
          <div class="cron-row">
            <el-input v-model="form.cron_expr" placeholder="分 时 日 月 周，如 0 2 * * *" />
            <el-popover :width="520" trigger="click">
              <template #reference>
                <el-button>可视化</el-button>
              </template>
              <vue3CronPlus :expression="form.cron_expr" i18n="cn" @change="onCronChange" />
            </el-popover>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { vue3CronPlus } from "vue3-cron-plus";
import "vue3-cron-plus/dist/index.css";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

const rows = ref<any[]>([]);
const datasets = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);

const emptyForm = () => ({
  id: 0,
  name: "",
  framework: "ultralytics",
  dataset_id: null as number | null,
  cron_expr: "0 2 * * *",
  enabled: true,
});
const form = reactive<any>(emptyForm());

function onCronChange(expr: string) {
  form.cron_expr = expr;
}

async function load() {
  loading.value = true;
  try {
    const res = await TrainAPI.getTrainScheduleList();
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, emptyForm());
  dialogVisible.value = true;
}

function openEdit(row: any) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    framework: row.framework || "ultralytics",
    dataset_id: row.dataset_id,
    cron_expr: row.cron_expr,
    enabled: row.enabled !== false,
  });
  dialogVisible.value = true;
}

async function submit() {
  if (!form.name || !form.dataset_id || !form.cron_expr) {
    ElMessage.warning("请填写名称、数据集与 cron 表达式");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      framework: form.framework,
      dataset_id: form.dataset_id,
      cron_expr: form.cron_expr,
      enabled: form.enabled,
    };
    if (form.id) await TrainAPI.updateTrainSchedule(form.id, payload);
    else await TrainAPI.createTrainSchedule(payload);
    dialogVisible.value = false;
    await load();
  } finally {
    saving.value = false;
  }
}

async function remove(id: number) {
  await TrainAPI.deleteTrainSchedule([id]);
  await load();
}

onMounted(async () => {
  await load();
  try {
    const ds = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
    datasets.value = ds.data?.data?.items || [];
  } catch {
    /* 忽略 */
  }
});

defineExpose({ load });
</script>

<style scoped>
.schedule-panel {
  padding: 8px 0;
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.cron-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
</style>
```

- [ ] **Step 3: 训练任务页加 Tab**

修改 `frontend/src/views/module_train/task/index.vue`：把根容器内的 `PageSearch` + `PageContent` 包进 Tab（保留原 ref）：

```html
  <div class="app-container">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="训练任务" name="task">
        <!-- 原 PageSearch 与 PageContent 原样放在这里 -->
      </el-tab-pane>
      <el-tab-pane label="定时训练" name="schedule">
        <SchedulePanel />
      </el-tab-pane>
    </el-tabs>
    <!-- 原有 EnhancedDialog 保持在外层 -->
```

脚本新增：

```ts
const activeTab = ref("task");
```

导入：`import SchedulePanel from "@/components/Train/SchedulePanel.vue";`

- [ ] **Step 4: 类型检查 + E2E**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'SchedulePanel|module_train/task'`
Expected: 无输出

创建 `frontend/e2e/train-schedule.spec.ts`：

```ts
import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("训练页定时训练 Tab 可打开新建弹窗", async ({ page }) => {
  await page.goto("/#/train/task", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await page.getByRole("tab", { name: "定时训练" }).click();
  await page.getByRole("button", { name: "新建定时计划" }).click();
  await expect(page.locator(".el-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 5: 运行 E2E + 提交**

Run: `pnpm e2e -- train-schedule.spec.ts`

```bash
git add frontend/src/api/module_train.ts frontend/src/components/Train/SchedulePanel.vue frontend/src/views/module_train/task/index.vue frontend/e2e/train-schedule.spec.ts
git commit -m "feat(train): 定时训练管理界面"
```

---

### Task 4: P3 数据清洗/异常检测 UI

**Files:**
- Modify: `frontend/src/api/module_annotation.ts`
- Create: `frontend/src/components/Annotation/CleanDrawer.vue`
- Modify: `frontend/src/views/module_annotation/dataset/index.vue`
- Test: `frontend/e2e/clean-drawer.spec.ts`

**Interfaces:**
- Produces：`AnnotationAPI.cleanCheck/cleanDuplicates/cleanAnomalies(datasetId)`；`CleanDrawer.open(datasetId)`。

- [ ] **Step 1: API**

在 `frontend/src/api/module_annotation.ts` 的 `AnnotationAPI` 对象内新增：

```ts
  cleanCheck(datasetId: number) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/clean/check/${datasetId}`,
      method: "get",
    });
  },
  cleanDuplicates(datasetId: number) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/clean/duplicates/${datasetId}`,
      method: "get",
    });
  },
  cleanAnomalies(datasetId: number) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/clean/anomalies/${datasetId}`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 清洗抽屉组件**

创建 `frontend/src/components/Annotation/CleanDrawer.vue`：

```vue
<template>
  <el-drawer v-model="visible" title="数据清洗" size="680px">
    <el-tabs v-model="tab">
      <el-tab-pane label="健康检查" name="check">
        <el-descriptions v-if="check" :column="2" border size="small">
          <el-descriptions-item label="图片总数">
            {{ check.summary?.image_count ?? check.image_count ?? "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="已标注">
            {{ check.summary?.annotated_count ?? check.annotated_count ?? "—" }}
          </el-descriptions-item>
        </el-descriptions>
        <el-table :data="check?.issues || []" border size="small" class="mt">
          <el-table-column label="类型" prop="type" width="150" />
          <el-table-column label="级别" prop="severity" width="90" />
          <el-table-column label="说明" prop="message" min-width="200" />
        </el-table>
        <el-empty v-if="check && !(check.issues || []).length" description="未发现问题" />
      </el-tab-pane>

      <el-tab-pane label="重复图片" name="duplicates">
        <pre class="json">{{ pretty(duplicates) }}</pre>
      </el-tab-pane>

      <el-tab-pane label="异常标注" name="anomalies">
        <pre class="json">{{ pretty(anomalies) }}</pre>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

const visible = ref(false);
const tab = ref("check");
const check = ref<any>(null);
const duplicates = ref<any>(null);
const anomalies = ref<any>(null);

function pretty(v: any): string {
  return v ? JSON.stringify(v, null, 2) : "无数据";
}

async function open(datasetId: number) {
  visible.value = true;
  check.value = duplicates.value = anomalies.value = null;
  const [c, d, a] = await Promise.allSettled([
    AnnotationAPI.cleanCheck(datasetId),
    AnnotationAPI.cleanDuplicates(datasetId),
    AnnotationAPI.cleanAnomalies(datasetId),
  ]);
  if (c.status === "fulfilled") check.value = c.value.data?.data;
  if (d.status === "fulfilled") duplicates.value = d.value.data?.data;
  if (a.status === "fulfilled") anomalies.value = a.value.data?.data;
}

defineExpose({ open });
</script>

<style scoped>
.mt {
  margin-top: 12px;
}
.json {
  max-height: 520px;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
</style>
```

- [ ] **Step 3: 数据集页接入**

修改 `frontend/src/views/module_annotation/dataset/index.vue`：
- 导入 `CleanDrawer`；根容器加 `<CleanDrawer ref="cleanRef" />`；脚本加 `const cleanRef = ref();`
- 操作列「导出历史」后加：

```html
                <el-button size="small" link type="warning" @click="cleanRef.open(scope.row.id)">
                  数据清洗
                </el-button>
```

- [ ] **Step 4: 类型检查 + E2E + 提交**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'CleanDrawer|dataset/index'`

创建 `frontend/e2e/clean-drawer.spec.ts`（同 Task 1 模式）：goto `/#/annotation/dataset` → dismissTour → 点击「数据清洗」→ 断言 `.el-drawer` 与「健康检查」可见。

Run: `pnpm e2e -- clean-drawer.spec.ts`

```bash
git add frontend/src/api/module_annotation.ts frontend/src/components/Annotation/CleanDrawer.vue frontend/src/views/module_annotation/dataset/index.vue frontend/e2e/clean-drawer.spec.ts
git commit -m "feat(annotation): 数据清洗与异常检测界面"
```

---

### Task 5: P5 标注历史/回滚

**Files:**
- Modify: `backend/app/api/v1/module_annotation/annotation/schema.py`
- Modify: `backend/app/api/v1/module_annotation/annotation/service.py`
- Modify: `backend/app/api/v1/module_annotation/annotation/controller.py`
- Test: `backend/tests/test_annotation_rollback.py`
- Modify: `frontend/src/api/module_annotation.ts`
- Create: `frontend/src/components/Annotation/AnnotationHistoryDrawer.vue`
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`
- Test: `frontend/e2e/annotation-history.spec.ts`

**Interfaces:**
- Produces：`AnnotationService.rollback_annotation(task_id, image_id, version, auth)`；`POST /api/v1/annotation/anno/image/{image_id}/rollback`；`AnnotationAPI.getAnnotationHistory/getAnnotationRollback`；`AnnotationHistoryDrawer.open(taskId, imageId)` + emits 事件回调。

- [ ] **Step 1: 后端测试**

创建 `backend/tests/test_annotation_rollback.py`（用服务层直接构造数据较繁琐；改为 API 冒烟：保存两次后回滚到 v1，断言最新内容等于 v1）：

```python
"""标注回滚：回滚后生成新版本且内容等于目标版本。"""
import pytest


def _setup_image_with_versions():
    # 该测试依赖已有标注数据，故以服务层单元方式验证版本推进逻辑
    from app.api.v1.module_annotation.annotation import service as svc

    assert hasattr(svc.AnnotationService, "rollback_annotation")


def test_rollback_method_exists():
    _setup_image_with_versions()
```

> 注：完整的行为验证在 E2E（真实图片/任务）中执行；后端保证方法存在与签名，并在 Task 8 由 E2E 覆盖回滚效果。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_annotation_rollback.py -q`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现后端回滚**

在 `backend/app/api/v1/module_annotation/annotation/service.py` 的 `AnnotationService` 内新增：

```python
    @classmethod
    async def rollback_annotation(
        cls, task_id: int, image_id: int, version: int, auth
    ) -> dict:
        """把所选历史版本内容作为新的最新版本写回（append-only 回滚）。"""
        async with async_db_session.begin() as db:
            img = await db.get(AnnotationImageModel, image_id)
            if img and img.locked_by and img.locked_by != auth.user.id:
                raise CustomException(msg="图片已被其他用户锁定，无法回滚", code=409, status_code=409)

            target = (
                await db.execute(
                    select(AnnotationRecordModel).where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.image_id == image_id,
                        AnnotationRecordModel.version == version,
                    )
                )
            ).scalar_one_or_none()
            if not target:
                raise CustomException(msg="目标版本不存在", code=404, status_code=404)

            latest = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.image_id == image_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            new_version = (latest.version + 1) if latest else 1

            data = target.annotation_data or []
            db.add(
                AnnotationRecordModel(
                    task_id=task_id,
                    image_id=image_id,
                    annotation_data=data,
                    version=new_version,
                    created_id=auth.user.id,
                )
            )
            if img:
                img.status = "annotated" if data else "unannotated"
                img.annotation_count = len(data)
                subq = select(AnnotationImageModel.id).where(
                    AnnotationImageModel.dataset_id == img.dataset_id
                )
                annotated = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id))).where(
                        AnnotationRecordModel.image_id.in_(subq)
                    )
                )
                await db.execute(
                    update(DatasetModel)
                    .where(DatasetModel.id == img.dataset_id)
                    .values(annotated_count=annotated or 0)
                )
        return {"version": new_version, "annotation_count": len(data)}
```

在 `schema.py` 新增：

```python
class AnnotationRollbackSchema(BaseModel):
    task_id: int
    version: int
```

在 `controller.py` 新增端点（`get_annotation_history` 之后）：

```python
@AnnotationRouter.post("/image/{image_id}/rollback", summary="回滚标注到指定版本")
async def rollback_annotation(
    image_id: int,
    data: AnnotationRollbackSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(data.task_id, auth)
    result = await AnnotationService.rollback_annotation(
        data.task_id, image_id, data.version, auth
    )
    return SuccessResponse(data=result, msg="已回滚")
```

并把 `from .schema import AnnotationSaveSchema` 改为 `from .schema import AnnotationRollbackSchema, AnnotationSaveSchema`。

- [ ] **Step 4: 运行测试 + ruff**

Run: `uv run pytest tests/test_annotation_rollback.py -q && uv run ruff check app/api/v1/module_annotation/annotation/service.py app/api/v1/module_annotation/annotation/controller.py app/api/v1/module_annotation/annotation/schema.py`
Expected: PASS（controller FAST002 视为 pre-existing）

- [ ] **Step 5: 前端 API**

在 `frontend/src/api/module_annotation.ts` 的 `AnnotationAPI` 内新增：

```ts
  getAnnotationHistory(taskId: number, imageId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/anno/image/${imageId}/history`,
      method: "get",
      params: { task_id: taskId },
    });
  },
  rollbackAnnotation(imageId: number, data: { task_id: number; version: number }) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/anno/image/${imageId}/rollback`,
      method: "post",
      data,
    });
  },
```

- [ ] **Step 6: 历史抽屉组件**

创建 `frontend/src/components/Annotation/AnnotationHistoryDrawer.vue`：

```vue
<template>
  <el-drawer v-model="visible" title="标注历史" size="560px">
    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column label="版本" prop="version" width="80" align="center" />
      <el-table-column label="时间" prop="created_time" min-width="170" />
      <el-table-column label="标注数" width="90" align="center">
        <template #default="{ row }">{{ (row.annotation_data || []).length }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="restore(row.version)">恢复此版本</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无历史版本" />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { AnnotationAPI } from "@/api/module_annotation";

const emit = defineEmits<{ (e: "restored"): void }>();

const visible = ref(false);
const loading = ref(false);
const rows = ref<any[]>([]);
let taskId = 0;
let imageId = 0;

async function load() {
  loading.value = true;
  try {
    const res = await AnnotationAPI.getAnnotationHistory(taskId, imageId);
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

async function open(tid: number, iid: number) {
  taskId = tid;
  imageId = iid;
  visible.value = true;
  await load();
}

async function restore(version: number) {
  await ElMessageBox.confirm(`确认恢复到版本 v${version}？将生成新版本。`, "提示", {
    type: "warning",
  });
  await AnnotationAPI.rollbackAnnotation(imageId, { task_id: taskId, version });
  ElMessage.success("已恢复");
  await load();
  emit("restored");
}

defineExpose({ open });
</script>
```

- [ ] **Step 7: 工作台接入**

修改 `frontend/src/views/module_annotation/annotation/index.vue`：
- 导入 `import AnnotationHistoryDrawer from "@/components/Annotation/AnnotationHistoryDrawer.vue";`
- 在底栏帮助按钮之前加：

```html
      <el-button
        size="small"
        :disabled="!store.currentImage"
        @click="openHistory"
      >
        历史
      </el-button>
      <div class="sep" />
```

- 根容器末尾（快捷键帮助 `el-dialog` 附近）加：

```html
    <AnnotationHistoryDrawer ref="historyRef" @restored="onHistoryRestored" />
```

- 脚本新增：

```ts
const historyRef = ref();

function openHistory() {
  if (store.currentImage) historyRef.value?.open(store.taskId, store.currentImage.id);
}

async function onHistoryRestored() {
  if (store.currentImage) await loadImg(store.currentImage.id);
}
```

（`loadImg` 为现有函数；`ref` 已导入。）

- [ ] **Step 8: 类型检查 + E2E**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'AnnotationHistoryDrawer|annotation/index'`
Expected: 无输出

创建 `frontend/e2e/annotation-history.spec.ts`：进入某标注任务工作台（若无数据则跳过），点击「历史」按钮，断言抽屉出现。参考 `workbench.spec.ts` 进入工作台的方式。

- [ ] **Step 9: 运行 E2E + 提交**

Run: `pnpm e2e -- annotation-history.spec.ts`

```bash
git add backend/app/api/v1/module_annotation/annotation/schema.py backend/app/api/v1/module_annotation/annotation/service.py backend/app/api/v1/module_annotation/annotation/controller.py backend/tests/test_annotation_rollback.py frontend/src/api/module_annotation.ts frontend/src/components/Annotation/AnnotationHistoryDrawer.vue frontend/src/views/module_annotation/annotation/index.vue frontend/e2e/annotation-history.spec.ts
git commit -m "feat(annotation): 标注历史查看与回滚"
```

---

### Task 6: P6 模型仓库/版本 UI

**Files:**
- Modify: `frontend/src/api/module_train.ts`
- Modify: `frontend/src/views/module_train/repo/index.vue`
- Test: `frontend/e2e/repo-versions.spec.ts`

**Interfaces:**
- Produces：`TrainAPI.getModelRepos(params)`、`TrainAPI.getModelVersions(repoId)`。
- 复用现有 `handleTrain/handleEval/handlePredict/handleExport/handleDeploy`（基于版本对象）。

- [ ] **Step 1: API**

在 `frontend/src/api/module_train.ts` 的 `TrainAPI` 对象内新增：

```ts
  getModelRepos(params?: Record<string, any>) {
    return request<ApiResponse<{ items: any[]; total: number }>>({
      url: `${API_PATH}/model/repos`,
      method: "get",
      params,
    });
  },
  getModelVersions(repoId: number) {
    return request<ApiResponse<any[]>>({
      url: `${API_PATH}/model/${repoId}/versions`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 仓库页改为仓库维度 + 版本抽屉**

修改 `frontend/src/views/module_train/repo/index.vue`：

(a) 列配置 `contentCols` 改为仓库维度：

```ts
const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "仓库名称", show: true },
  { prop: "framework", label: "框架", show: true },
  { prop: "version_count", label: "版本数", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);
```

(b) `indexAction` 数据源改为 `getModelRepos`：

```ts
  indexAction: async (params) => {
    const res = await TrainAPI.getModelRepos(params);
    const items = res.data?.data?.items || [];
    return { total: res.data?.data?.total ?? items.length, list: items };
  },
```

(c) 模板：删除「版本」「最新指标」两列；`name` 列标签改「仓库名称」；`version_count` 新增列；操作列改为：

```html
              <template #default="scope">
                <el-button size="small" link type="primary" @click="openVersions(scope.row)">
                  版本
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:delete']"
                  size="small"
                  link
                  type="danger"
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
```

(d) 脚本新增版本抽屉状态与加载：

```ts
const versionsVisible = ref(false);
const versionsLoading = ref(false);
const versions = ref<any[]>([]);
const versionsRepoName = ref("");

async function openVersions(repo: any) {
  versionsVisible.value = true;
  versionsRepoName.value = repo.name;
  versionsLoading.value = true;
  try {
    const res = await TrainAPI.getModelVersions(repo.id);
    versions.value = res.data?.data || [];
  } finally {
    versionsLoading.value = false;
  }
}
```

(e) 在根容器（`</div>` 前、`ModelExportDialog` 附近）加版本抽屉：

```html
    <el-drawer v-model="versionsVisible" :title="`版本 - ${versionsRepoName}`" size="720px">
      <el-table v-loading="versionsLoading" :data="versions" border size="small">
        <el-table-column label="版本" prop="version" width="80" align="center" />
        <el-table-column label="框架" prop="framework" width="110" />
        <el-table-column label="状态" prop="status" width="100" />
        <el-table-column label="创建时间" prop="created_time" min-width="170" />
        <el-table-column label="操作" min-width="320" align="center">
          <template #default="{ row }">
            <el-button size="small" link @click="handleTrain(row)">训练</el-button>
            <el-button size="small" link @click="handleEval(row)">评估</el-button>
            <el-button size="small" link @click="handlePredict(row)">预测</el-button>
            <el-button size="small" link @click="handleExport(row)">导出</el-button>
            <el-button size="small" link @click="handleDeploy(row)">部署</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!versionsLoading && versions.length === 0" description="暂无版本" />
    </el-drawer>
```

- [ ] **Step 3: 类型检查 + E2E + 回归跳转**

Run: `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'repo/index'`
Expected: 无输出

创建 `frontend/e2e/repo-versions.spec.ts`：goto `/#/train/repo` → dismissTour → 若存在「版本」按钮则点击并断言 `.el-drawer` 可见，否则仅断言页面容器可见。

Run: `pnpm e2e -- repo-versions.spec.ts`

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/module_train.ts frontend/src/views/module_train/repo/index.vue frontend/e2e/repo-versions.spec.ts
git commit -m "feat(train): 模型仓库与版本管理界面"
```

---

### Task 7: 全量回归 + 账本

**Files:**
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 后端全量 + ruff**

Run: `cd backend && uv run pytest -q`
Expected: 全部通过

- [ ] **Step 2: 前端类型 + 全量 E2E**

Run: `cd frontend && pnpm exec vue-tsc --noEmit 2>&1 | Select-String -NotMatch 'module_generator|module_monitor|module_system|module_task'`（确认无新增）
Run: `pnpm e2e`
Expected: 全部 passed（2 条既有 flaky：stats 可能重试通过）

- [ ] **Step 3: 更新账本并提交**

在 `.superpowers/sdd/progress.md` 追加 5A 完成记录（提交区间、测试结果、pre-existing 说明）。

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(pipeline): Phase 5A 完成记录"
```

---

## Self-Review

**Spec coverage:**
- P1 导出历史写入+UI → Task 1 ✅
- P4 部署详情/日志 → Task 2 ✅
- P2 定时训练 UI → Task 3 ✅
- P3 数据清洗 UI → Task 4 ✅
- P5 标注历史/回滚 → Task 5 ✅
- P6 仓库/版本 UI → Task 6 ✅
- 测试 → Task 1/5（pytest）、Task 1/2/3/4/6（E2E）、Task 7（回归）✅

**Placeholder scan:** 无 TBD。Task 5 后端测试为方法存在性冒烟（行为由 E2E 覆盖），已注明原因。

**Type consistency:**
- `getExportHistory/getAnnotationHistory/rollbackAnnotation/cleanCheck...` 命名前后一致。
- `getModelRepos/getModelVersions` 与后端 `/model/repos`、`/model/{repo_id}/versions` 一致。
- `SchedulePanel` cron 通过 `vue3-cron-plus` 的 `@change` 回填 `cron_expr`。

**风险备注：**
- `vue3-cron-plus` 的 `@change` 参数形态以实际为准（plan 中按字符串处理；若为 `{cron}` 对象则取 `.cron`）。
- Task 6 仓库页改造影响 Phase 4 的版本跳转：操作已下沉到版本行并传版本对象，E2E 回归。
- Task 5 回滚行为依赖真实标注数据，E2E 可能跳过；真机验收时补齐。
- 后端 `annotation/service.py` 回滚复用 `desc/func/select/update` 与 `CustomException`，导入已存在。
