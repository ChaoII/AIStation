<!-- 资产版本管理：展示某表的版本历史，可发布、可回滚（复用后端 /assets/{table}/versions 等接口） -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="`资产版本 · ${table || ''}`"
    width="760px"
    append-to-body
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-loading="loading">
      <el-alert
        v-if="!releases.length"
        type="info"
        :closable="false"
        show-icon
        title="版本在每次「保存/维护」时自动生成；「发布」把某版本标记为对外发布版，「回滚」把该版本恢复为当前生效内容。"
        style="margin-bottom: 12px"
      />
      <div v-if="releases.length" class="av-releases">
        <span class="av-releases__label">已发布：</span>
        <el-tag
          v-for="r in releases"
          :key="r.id"
          size="small"
          type="success"
          effect="plain"
          style="margin: 0 2px"
        >
          V{{ r.version }}
        </el-tag>
      </div>
      <el-table :data="versions" size="small" border max-height="60vh">
        <template #empty>
          <el-empty description="暂无版本记录" :image-size="60" />
        </template>
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">V{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="中文名" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.snapshot?.alias || "-" }}</template>
        </el-table-column>
        <el-table-column label="业务域" width="90" show-overflow-tooltip>
          <template #default="{ row }">{{ row.snapshot?.domain || "-" }}</template>
        </el-table-column>
        <el-table-column label="描述" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.snapshot?.description || "-" }}</template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="80" />
        <el-table-column prop="time" label="时间" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="publish(row)">发布</el-button>
            <el-button link type="danger" size="small" @click="rollback(row)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  getAssetVersions,
  getAssetReleases,
  publishAsset,
  rollbackAssetVersion,
} from "@/api/module_ai/query";

defineOptions({ name: "AssetVersionsDialog" });

const props = defineProps<{ modelValue: boolean; table?: string }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

const loading = ref(false);
const versions = ref<any[]>([]);
const releases = ref<any[]>([]);

async function load() {
  loading.value = true;
  try {
    const [v, r] = await Promise.all([
      getAssetVersions(props.table || ""),
      getAssetReleases(props.table || ""),
    ]);
    versions.value = v.data?.data || [];
    releases.value = r.data?.data || [];
  } catch {
    versions.value = [];
    releases.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load();
  }
);

function publish(row: any) {
  ElMessageBox.confirm(`确认把 V${row.version} 发布为对外发布版？`, "发布确认", {
    confirmButtonText: "发布",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    await publishAsset(props.table || "", row.id);
    ElMessage.success("已发布");
    load();
  });
}

function rollback(row: any) {
  ElMessageBox.confirm(
    `确认回滚到 V${row.version}？当前表/字段内容将被该版本覆盖，且不可恢复。`,
    "回滚确认",
    { confirmButtonText: "回滚", cancelButtonText: "取消", type: "warning" }
  ).then(async () => {
    await rollbackAssetVersion(row.id);
    ElMessage.success("已回滚");
    load();
  });
}
</script>

<style lang="scss" scoped>
.av-releases {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
  font-size: 13px;
}
.av-releases__label {
  color: var(--el-text-color-secondary);
}
</style>
