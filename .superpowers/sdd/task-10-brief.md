# Task 10: 前端评估页面 — 增强列表 + 新建详情页

## 要修改/创建的文件
- Modify: `frontend/src/views/module_train/eval/index.vue`（增强）
- Create: `frontend/src/views/module_train/eval/detail.vue`（新建）

## 要求

### A. 增强 `eval/index.vue`

**1. 添加导入**
在 `import { TrainAPI } from "@/api/module_train"` 旁边添加：
```typescript
import { useRouter } from "vue-router";
const router = useRouter();
```

**2. 添加响应式数据**
```typescript
const createDialogVisible = ref(false);
const modelVersions = ref<any[]>([]);
const createForm = reactive({
  modelId: null as number | null,
  evalDatasetId: null as number | null,
  hyperparams: { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6 },
});

// 加载模型版本列表
(async () => {
  const r = await TrainAPI.getModelList();
  modelVersions.value = r.data?.data || [];
})();
```

**3. 添加操作方法**
```typescript
async function handleStartEval(id: number) {
  await TrainAPI.startEval(id);
  ElMessage.success("评估已开始");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}

async function handleStopEval(id: number) {
  await TrainAPI.stopEval(id);
  ElMessage.success("评估已停止");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}

async function handleDeleteEval(ids: number[]) {
  await TrainAPI.deleteEval(ids);
  ElMessage.success("已删除");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}
```

**4. 修改创建评估逻辑**
替换现有 `handleCreateEval` 函数，使用对话框中的参数：
```typescript
async function handleCreateEval() {
  if (!createForm.modelId || !createForm.evalDatasetId) {
    ElMessage.warning("请选择模型版本和评估数据集");
    return;
  }
  creating.value = true;
  try {
    await TrainAPI.createEval({
      model_repo_id: modelRepoId,
      model_id: createForm.modelId,
      eval_dataset_id: createForm.evalDatasetId,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success("评估任务已创建");
    createDialogVisible.value = false;
    createForm.modelId = null;
    createForm.evalDatasetId = null;
    createForm.hyperparams = { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6 };
    await reloadEvalData();
    contentRef.value?.fetchPageData({}, true);
  } finally {
    creating.value = false;
  }
}
```

**5. 添加操作列表**
在 `<el-table>` 中添加操作列：
```vue
<el-table-column label="操作" width="200" fixed="right">
  <template #default="{ row }">
    <el-button text size="small" type="primary" @click="router.push(`/train/eval/${row.id}`)">详情</el-button>
    <el-button v-if="row.status === 'pending'" text size="small" type="success" @click="handleStartEval(row.id)">开始</el-button>
    <el-button v-if="row.status === 'running'" text size="small" type="danger" @click="handleStopEval(row.id)">停止</el-button>
    <el-popconfirm title="确定删除？" @confirm="handleDeleteEval([row.id])">
      <template #reference><el-button text size="small" type="danger">删除</el-button></template>
    </el-popconfirm>
  </template>
</el-table-column>
```

**6. 修改创建按钮为对话框触发**
将现有 `创建评估` 按钮改为：
```vue
<el-button type="primary" size="small" @click="createDialogVisible = true">创建评估</el-button>
```

**7. 添加创建对话框**
在 `</PageContent>` 之后添加：
```vue
<el-dialog v-model="createDialogVisible" title="创建评估" width="500px">
  <el-form label-width="100px">
    <el-form-item label="模型版本">
      <el-select v-model="createForm.modelId" filterable style="width:100%">
        <el-option v-for="m in modelVersions" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="评估数据集">
      <el-select v-model="createForm.evalDatasetId" filterable style="width:100%">
        <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="imgsz"><el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" /></el-form-item>
    <el-form-item label="batch"><el-input-number v-model="createForm.hyperparams.batch" :min="1" :max="128" /></el-form-item>
    <el-form-item label="conf"><el-input-number v-model="createForm.hyperparams.conf" :min="0.001" :max="1" :step="0.01" /></el-form-item>
    <el-form-item label="iou"><el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" /></el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="createDialogVisible = false">取消</el-button>
    <el-button type="primary" :loading="creating" @click="handleCreateEval">创建</el-button>
  </template>
</el-dialog>
```

### B. 创建 `eval/detail.vue`

File content:

```vue
<template>
  <div class="app-container train-detail-page">
    <div class="detail-header">
      <el-button text size="small" @click="router.back()"><el-icon><ArrowLeft /></el-icon></el-button>
      <span class="task-name">评估 #{{ evalData?.id }}</span>
      <el-tag :type="(tagType(evalData?.status || '') as any)" size="small">{{ tagLabel(evalData?.status || '') }}</el-tag>
    </div>

    <div class="info-cards">
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">评估信息</span></template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="模型仓库 ID">{{ evalData?.model_repo_id }}</el-descriptions-item>
          <el-descriptions-item label="模型版本 ID">{{ evalData?.model_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="评估数据集 ID">{{ evalData?.eval_dataset_id }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ evalData?.created_time }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ evalData?.finished_at || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">评估参数</span></template>
        <div class="hp-grid">
          <div class="hp-item"><span class="hp-label">imgsz</span><span class="hp-value">{{ evalData?.hyperparams?.imgsz ?? 640 }}</span></div>
          <div class="hp-item"><span class="hp-label">batch</span><span class="hp-value">{{ evalData?.hyperparams?.batch ?? 16 }}</span></div>
          <div class="hp-item"><span class="hp-label">conf</span><span class="hp-value">{{ evalData?.hyperparams?.conf ?? 0.001 }}</span></div>
          <div class="hp-item"><span class="hp-label">iou</span><span class="hp-value">{{ evalData?.hyperparams?.iou ?? 0.6 }}</span></div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">评估指标</span></template>
      <div v-if="evalData?.metrics" class="metric-grid">
        <div class="metric-item"><span class="metric-val metric-green">{{ fmtPct(evalData.metrics.precision) }}</span><span class="metric-lbl">Precision</span></div>
        <div class="metric-item"><span class="metric-val metric-blue">{{ fmtPct(evalData.metrics.recall) }}</span><span class="metric-lbl">Recall</span></div>
        <div class="metric-item"><span class="metric-val metric-orange">{{ fmtPct(evalData.metrics.map50) }}</span><span class="metric-lbl">mAP@50</span></div>
        <div class="metric-item"><span class="metric-val metric-purple">{{ fmtPct(evalData.metrics.map5095) }}</span><span class="metric-lbl">mAP@50:95</span></div>
      </div>
      <el-empty v-else :image-size="40" description="暂无评估指标" />
    </el-card>

    <!-- Per-class metrics table -->
    <el-card v-if="evalData?.metrics?.classes" shadow="never" class="section-card">
      <template #header><span class="card-title">各类别指标</span></template>
      <el-table :data="classTableData" border size="small" style="width:100%">
        <el-table-column prop="cls" label="类别" width="100" />
        <el-table-column label="Precision"><template #default="{row}">{{ fmtPct(row.precision) }}</template></el-table-column>
        <el-table-column label="Recall"><template #default="{row}">{{ fmtPct(row.recall) }}</template></el-table-column>
        <el-table-column label="mAP@50"><template #default="{row}">{{ fmtPct(row.map50) }}</template></el-table-column>
        <el-table-column label="mAP@50:95"><template #default="{row}">{{ fmtPct(row.map5095) }}</template></el-table-column>
      </el-table>
    </el-card>

    <!-- Log area -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">评估日志</span></template>
      <div ref="logRef" class="log-container">
        <pre class="log-text">{{ logText || '等待日志...' }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const evalData = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
let ws: WebSocket | null = null;

function tagType(s: string) { return ({ pending: "info", running: "warning", success: "success", failed: "danger" } as any)[s] || "info"; }
function tagLabel(s: string) { return ({ pending: "待开始", running: "评估中", success: "已完成", failed: "失败" } as any)[s] || s; }
function fmtPct(v: number | undefined) { return v != null ? (v * 100).toFixed(1) + "%" : "—"; }

const classTableData = computed(() => {
  const cls = evalData.value?.metrics?.classes;
  if (!cls) return [];
  return Object.entries(cls).map(([k, v]: [string, any]) => ({ cls: k, precision: v.precision, recall: v.recall, map50: v.map50, map5095: v.map5095 }));
});

function connectWs(evalId: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/eval/logs?eval_id=${evalId}`);
  ws.onmessage = (e: MessageEvent) => {
    logText.value += e.data + "\n";
  };
  ws.onclose = () => {};
  ws.onerror = () => {};
}

onMounted(async () => {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getEvalDetail(id);
  evalData.value = r.data?.data;
  if (evalData.value?.status === "running") {
    connectWs(id);
  }
  if (evalData.value?.log) {
    logText.value = evalData.value.log;
  }
});

onBeforeUnmount(() => { ws?.close(); });
</script>

<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>

<style scoped lang="scss">
.detail-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 10px 16px; background: #fff; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
.task-name { font-size: 15px; font-weight: 600; margin-right: 4px; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.info-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.info-card { height: 100%; }
.hp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.hp-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f2f3f5; }
.hp-label { color: #909399; font-size: 13px; }
.hp-value { color: #303133; font-size: 13px; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.metric-item { background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 16px 12px; text-align: center; transition: box-shadow .2s; &:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); } }
.metric-val { display: block; font-size: 18px; font-weight: 700; font-family: "Cascadia Code",monospace; color: #303133; }
.metric-lbl { display: block; font-size: 12px; color: #909399; margin-top: 4px; }
.metric-green { color: #67c23a; }
.metric-blue { color: #409eff; }
.metric-orange { color: #e6a23c; }
.metric-purple { color: #9b59b6; }
.log-container { height: 500px; min-height: 200px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code","Fira Code",monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
```

## 前置条件
- 现有文件 `frontend/src/views/module_train/eval/index.vue`（136 行）
- `TrainAPI` 已有 `createEval`, `getEvalList`, `deleteEval`, 新增 `getEvalDetail`, `startEval`, `stopEval`（Task 9）

## 提交信息
```bash
git add frontend/src/views/module_train/eval/
git commit -m "feat(train): enhance eval list page, add eval detail page"
```
