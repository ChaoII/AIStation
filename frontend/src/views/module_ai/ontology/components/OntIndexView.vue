<!--
  索引（对齐官方 object-indexing）

  · 索引 = 让数据可被快速检索；由流水线（batch / streaming / direct）编排
  · 状态：未开始 / 构建中 / 就绪（绿勾）/ 失败 / 已过期
  · 失败重试：瞬时错误约 5 分钟后自动重试；终态错误只等新数据
  · 我们的索引是**真的**——构建会在对象类型支撑表上执行 CREATE INDEX
-->
<template>
  <div class="ont-ix">
    <el-card shadow="never">
      <div class="ont-sec__head">
        <span class="ont-sec__title">索引</span>
        <el-tag size="small" effect="plain">{{ summary?.total || 0 }} 个</el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Plus" @click="openForm()">
          新建索引
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          :icon="MagicStick"
          @click="openSuggest"
        >
          索引建议
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          :loading="busy"
          @click="doBuildAll"
        >
          构建全部待建
        </el-button>
        <el-button v-hasPerm="'module_ai:ontology:manage'" size="small" @click="doRetry">
          执行到期重试
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="构建索引会在对象类型的支撑表上真的执行 CREATE INDEX。状态「就绪」表示可以走了（相当于官方的绿勾）。"
      />

      <el-row :gutter="10" class="ont-ix__stats">
        <el-col v-for="(v, k) in summary?.by_status || {}" :key="k" :xs="12" :sm="8" :md="4">
          <el-card shadow="never" class="ont-ix__stat">
            <div class="ont-ix__statv">{{ v }}</div>
            <div class="ont-ix__statl">{{ statusLabel(String(k)) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :md="4">
          <el-card shadow="never" class="ont-ix__stat">
            <div class="ont-ix__statv">{{ summary?.total_size_human || "0 B" }}</div>
            <div class="ont-ix__statl">占用</div>
          </el-card>
        </el-col>
      </el-row>

      <el-tabs v-model="tab">
        <el-tab-pane label="索引明细" name="list">
          <el-table v-loading="loading" :data="rows" size="small" border max-height="520">
            <template #empty><el-empty :image-size="60" description="还没有索引" /></template>
            <el-table-column label="对象类型" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
            </el-table-column>
            <el-table-column prop="index_kind_label" label="种类" width="100" />
            <el-table-column label="字段" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="ont-mono">{{ row.prop_code || "（主键）" }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="statusTag(row.status)">
                  {{ row.status_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="pipeline_label" label="流水线" width="110" />
            <el-table-column label="行数 / 占用" width="140" align="right">
              <template #default="{ row }">
                <span class="ont-mono">{{ row.row_count }} / {{ row.size_human }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="build_count" label="构建次数" width="90" align="center" />
            <el-table-column
              prop="last_built_at"
              label="最近构建"
              width="150"
              show-overflow-tooltip
            />
            <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.last_error" class="ont-ix__err">{{ row.last_error }}</span>
                <span v-else class="ont-none">—</span>
                <div v-if="row.auto_retry_at" class="ont-hint">
                  将于 {{ row.auto_retry_at }} 自动重试
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  link
                  type="primary"
                  size="small"
                  :loading="busy"
                  @click="doBuild(row)"
                >
                  构建
                </el-button>
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  link
                  type="danger"
                  size="small"
                  @click="doRemove(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="按对象类型" name="objects">
          <el-table :data="summary?.objects || []" size="small" border>
            <template #empty><el-empty :image-size="50" description="暂无" /></template>
            <el-table-column
              prop="object_name"
              label="对象类型"
              min-width="170"
              show-overflow-tooltip
            />
            <el-table-column label="就绪/总数" width="120" align="center">
              <template #default="{ row }">{{ row.ready }} / {{ row.total }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.all_ready ? 'success' : 'warning'">
                  {{ row.all_ready ? "全部就绪" : "部分未就绪" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="rows" label="行数" width="110" align="right" />
            <el-table-column prop="size_human" label="占用" width="110" align="right" />
            <el-table-column label="操作" width="180" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  link
                  type="primary"
                  size="small"
                  @click="doBuildObject(row)"
                >
                  全部构建
                </el-button>
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  link
                  type="warning"
                  size="small"
                  @click="doStale(row)"
                >
                  标记过期
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建索引 -->
    <el-dialog v-model="formVisible" title="索引" width="560px" append-to-body>
      <el-form label-width="110px">
        <el-form-item label="对象类型" required>
          <el-select v-model="form.object_code" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="索引种类">
          <el-select v-model="form.index_kind" style="width: 100%">
            <el-option
              v-for="k in summary?.kind_meta || []"
              :key="k.value"
              :label="k.label"
              :value="k.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.index_kind !== 'primary'" label="字段">
          <el-select v-model="form.prop_code" filterable clearable style="width: 100%">
            <el-option
              v-for="p in formProps"
              :key="p.code"
              :label="`${p.name}（${p.code}）`"
              :value="p.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="流水线">
          <el-select v-model="form.pipeline_kind" style="width: 100%">
            <el-option
              v-for="p in summary?.pipeline_meta || []"
              :key="p.value"
              :label="p.label"
              :value="p.value"
            />
          </el-select>
          <div class="ont-hint">官方：批量流水线 vs 流式流水线，按数据源与延迟要求选</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doSave"
        >
          保存并构建
        </el-button>
      </template>
    </el-dialog>

    <!-- 索引建议 -->
    <el-dialog v-model="sugVisible" title="索引建议" width="620px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="依据：主键/显示名、被行级策略引用的字段、关系关联字段、唯一约束字段"
      />
      <el-table :data="suggestions" size="small" border max-height="360">
        <template #empty><el-empty :image-size="50" description="暂无建议" /></template>
        <el-table-column label="字段" min-width="140">
          <template #default="{ row }">
            <span class="ont-mono">{{ row.prop_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="理由" min-width="240" show-overflow-tooltip />
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              :type="row.priority === 'high' ? 'danger' : 'warning'"
            >
              {{ row.priority === "high" ? "高" : "中" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="sugVisible = false">取消</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          :loading="busy"
          @click="doApplySuggestions(false)"
        >
          全部创建
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doApplySuggestions(true)"
        >
          只创建高优先级
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { MagicStick, Plus, Refresh } from "@element-plus/icons-vue";
import {
  applyOntIndexSuggestions,
  buildAllOntIndexes,
  buildOntIndex,
  getOntIndexes,
  getOntIndexSummary,
  getOntProperties,
  markOntIndexStale,
  removeOntIndex,
  retryOntIndexes,
  saveOntIndex,
  suggestOntIndexes,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { objects, objectLabel } = useOntologyData();

const loading = ref(false);
const busy = ref(false);
const rows = ref<any[]>([]);
const summary = ref<any>(null);
const tab = ref("list");

const STATUS_LABEL: Record<string, string> = {
  not_started: "未开始",
  building: "构建中",
  ready: "就绪",
  failed: "失败",
  stale: "已过期",
};
function statusLabel(s: string) {
  return STATUS_LABEL[s] || s;
}
function statusTag(s: string) {
  return ({
    ready: "success",
    failed: "danger",
    stale: "warning",
    building: "primary",
    not_started: "info",
  }[s] || "info") as any;
}

async function load() {
  loading.value = true;
  try {
    const [r, s] = await Promise.all([getOntIndexes({}), getOntIndexSummary()]);
    rows.value = r.data?.data || [];
    summary.value = s.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载索引失败");
  } finally {
    loading.value = false;
  }
}

/* ---------------- 新建 ---------------- */
const formVisible = ref(false);
const form = reactive<any>({
  object_code: "",
  prop_code: "",
  index_kind: "property",
  pipeline_kind: "batch",
});
const formProps = ref<any[]>([]);

async function openForm() {
  Object.assign(form, {
    object_code: objects.value[0]?.code || "",
    prop_code: "",
    index_kind: "property",
    pipeline_kind: "batch",
  });
  if (form.object_code) await loadProps(form.object_code);
  formVisible.value = true;
}
async function loadProps(code: string) {
  const r = await getOntProperties(code);
  formProps.value = r.data?.data || [];
}

async function doSave() {
  if (!form.object_code) return ElMessage.warning("请选择对象类型");
  busy.value = true;
  try {
    const r = await saveOntIndex({ ...form });
    ElMessage.success(r.data?.msg || "已保存");
    const id = r.data?.data?.id;
    formVisible.value = false;
    if (id) {
      const b = await buildOntIndex(id);
      ElMessage.success(b.data?.msg || "已构建");
    }
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    busy.value = false;
  }
}

/* ---------------- 构建 / 重试 / 过期 ---------------- */
async function doBuild(row: any) {
  busy.value = true;
  try {
    const r = await buildOntIndex(row.id);
    if (r.data?.data?.ok) ElMessage.success(r.data.msg);
    else ElMessage.warning(r.data?.msg || "构建失败");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "构建失败");
  } finally {
    busy.value = false;
  }
}

async function doBuildAll() {
  busy.value = true;
  try {
    const r = await buildAllOntIndexes("");
    ElMessage.success(r.data?.msg || "已处理");
    await load();
  } finally {
    busy.value = false;
  }
}

async function doBuildObject(row: any) {
  busy.value = true;
  try {
    const r = await buildAllOntIndexes(row.object_code);
    ElMessage.success(r.data?.msg || "已处理");
    await load();
  } finally {
    busy.value = false;
  }
}

async function doRetry() {
  busy.value = true;
  try {
    const r = await retryOntIndexes();
    ElMessage.success(r.data?.msg || "已处理");
    await load();
  } finally {
    busy.value = false;
  }
}

async function doStale(row: any) {
  await ElMessageBox.confirm(
    `将把「${row.object_name}」的 ${row.ready} 个就绪索引标记为过期，需要重新构建。确认？`,
    "标记过期",
    { type: "warning", confirmButtonText: "标记", cancelButtonText: "取消" }
  );
  const r = await markOntIndexStale(row.object_code);
  ElMessage.success(r.data?.msg || "已标记");
  await load();
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    `将删除索引「${row.index_kind_label} · ${row.prop_code || "主键"}」` +
      "，并**真的在数据库里 DROP 掉**该索引，且不可恢复。确认删除？",
    "删除索引",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  const r = await removeOntIndex(row.id);
  ElMessage.success(r.data?.msg || "已删除");
  await load();
}

/* ---------------- 建议 ---------------- */
const sugVisible = ref(false);
const suggestions = ref<any[]>([]);
const sugObject = ref("");

async function openSuggest() {
  const code =
    objects.value.find((o: any) => o.code === "video_cameras")?.code || objects.value[0]?.code;
  if (!code) return;
  sugObject.value = code;
  const r = await suggestOntIndexes(code);
  suggestions.value = r.data?.data?.suggestions || [];
  sugVisible.value = true;
}

async function doApplySuggestions(onlyHigh: boolean) {
  busy.value = true;
  try {
    const r = await applyOntIndexSuggestions(sugObject.value, onlyHigh);
    ElMessage.success(r.data?.msg || "已处理");
    sugVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "处理失败");
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-ix__stats {
  margin-bottom: 10px;
}

.ont-ix__stat {
  text-align: center;
}

.ont-ix__statv {
  font-size: var(--el-font-size-extra-large);
  font-weight: 600;
  color: var(--el-color-primary);
}

.ont-ix__statl {
  color: var(--el-text-color-secondary);
}

.ont-ix__err {
  color: var(--el-color-danger);
}
</style>
