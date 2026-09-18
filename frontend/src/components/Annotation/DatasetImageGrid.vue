<template>
  <div class="dataset-image-grid">
    <el-dialog
      :model-value="modelValue"
      title="数据集图片"
      width="900px"
      append-to-body
      @update:model-value="(v: boolean) => emit('update:modelValue', v)"
      @open="load(1)"
    >
      <div class="grid-toolbar">
        <el-radio-group v-model="filter" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="unannotated">未标注</el-radio-button>
          <el-radio-button value="annotated">已标注</el-radio-button>
        </el-radio-group>
        <div class="grid-toolbar-right">
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="someSelected"
            :disabled="filtered.length === 0"
            @change="(v: any) => toggleAll(!!v)"
          >
            全选本页
          </el-checkbox>
          <el-button
            v-hasPerm="['module_annotation:dataset:image:delete']"
            type="danger"
            size="small"
            plain
            :disabled="selectedIds.length === 0"
            @click="deleteSelected"
          >
            删除所选（{{ selectedIds.length }}）
          </el-button>
          <el-button
            v-hasPerm="['module_annotation:dataset:image:delete']"
            type="danger"
            size="small"
            :disabled="filtered.length === 0"
            @click="deleteByFilter"
          >
            删除当前筛选
          </el-button>
        </div>
      </div>
      <div v-loading="loading" class="grid-body">
        <el-row :gutter="8">
          <el-col v-for="img in filtered" :key="img.id" :xs="12" :sm="8" :md="6" :lg="6">
            <div class="grid-cell">
              <el-checkbox
                class="grid-check"
                :model-value="selectedIds.includes(img.id)"
                @change="(v: any) => toggle(img.id, !!v)"
                @click.stop
              />
              <div class="grid-click" @click="emit('open-workbench', img)">
                <img
                  v-if="img.thumbnail_url"
                  :src="img.thumbnail_url"
                  class="grid-img"
                  loading="lazy"
                  alt=""
                />
                <div v-else class="grid-img grid-img--empty">无缩略图</div>
                <div class="grid-name" :title="img.filename">{{ img.filename }}</div>
                <el-tag
                  class="grid-badge"
                  size="small"
                  :type="img.status === 'annotated' ? 'success' : 'info'"
                >
                  {{ img.status === "annotated" ? "已标注" : "未标注" }}
                </el-tag>
                <el-tag v-if="img.locked_by" class="grid-lock" size="small" type="warning">
                  锁定
                </el-tag>
              </div>
            </div>
          </el-col>
        </el-row>
        <el-empty v-if="!loading && filtered.length === 0" description="暂无图片" />
      </div>
      <template #footer>
        <el-pagination
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="load"
        />
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { AnnotationAPI } from "@/api/module_annotation";
import { ElMessage, ElMessageBox } from "element-plus";

defineOptions({ name: "DatasetImageGrid" });

const props = defineProps<{ modelValue: boolean; datasetId: number | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "open-workbench", img: any): void;
  (e: "deleted"): void;
}>();

const page = ref(1);
const pageSize = 24;
const total = ref(0);
const loading = ref(false);
const images = ref<any[]>([]);
const filter = ref<"all" | "unannotated" | "annotated">("all");
const selectedIds = ref<number[]>([]);

const filtered = computed(() => {
  if (filter.value === "all") return images.value;
  return images.value.filter((i) => i.status === filter.value);
});
const allSelected = computed(
  () => filtered.value.length > 0 && filtered.value.every((i) => selectedIds.value.includes(i.id))
);
const someSelected = computed(
  () => selectedIds.value.length > 0 && !allSelected.value
);

function toggle(id: number, checked: boolean) {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id];
  } else {
    selectedIds.value = selectedIds.value.filter((x) => x !== id);
  }
}
function toggleAll(checked: boolean) {
  selectedIds.value = checked ? filtered.value.map((i) => i.id) : [];
}

async function load(p: number) {
  if (!props.datasetId) return;
  page.value = p;
  loading.value = true;
  try {
    const r = await AnnotationAPI.getImages(props.datasetId, undefined, p, pageSize);
    images.value = r.data?.data?.items || [];
    total.value = r.data?.data?.total || 0;
    selectedIds.value = [];
  } catch {
    images.value = [];
  } finally {
    loading.value = false;
  }
}

async function doDelete(payload: { image_ids?: number[]; status?: string }) {
  if (!props.datasetId) return;
  loading.value = true;
  try {
    const r = await AnnotationAPI.deleteDatasetImages(props.datasetId, payload);
    const d = r.data?.data || { deleted: 0, skipped_locked: 0 };
    if (d.skipped_locked) {
      ElMessage.warning(`已删除 ${d.deleted} 张；${d.skipped_locked} 张因被锁定已跳过`);
    } else {
      ElMessage.success(`已删除 ${d.deleted} 张图片`);
    }
    await load(page.value);
    emit("deleted");
  } catch {
    /* 提示由请求拦截器统一处理 */
  } finally {
    loading.value = false;
  }
}

async function deleteSelected() {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(
      `将删除所选 ${selectedIds.value.length} 张图片及其标注，且不可恢复。`,
      "删除图片",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  await doDelete({ image_ids: [...selectedIds.value] });
}

async function deleteByFilter() {
  const label =
    filter.value === "all" ? "全部" : filter.value === "annotated" ? "已标注" : "未标注";
  try {
    await ElMessageBox.confirm(
      `将删除该数据集下「${label}」的全部图片及其标注，且不可恢复。`,
      "按筛选删除",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  await doDelete({ status: filter.value });
}
</script>

<style scoped>
.grid-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.grid-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.grid-body {
  min-height: 200px;
}
.grid-cell {
  position: relative;
  margin-bottom: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}
.grid-check {
  position: absolute;
  top: 2px;
  left: 4px;
  z-index: 2;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 2px;
  padding: 0 2px;
}
.grid-click {
  position: relative;
  cursor: pointer;
}
.grid-img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  display: block;
  background: var(--el-fill-color-light);
}
.grid-img--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.grid-name {
  padding: 2px 4px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grid-badge {
  position: absolute;
  top: 4px;
  right: 4px;
}
.grid-lock {
  position: absolute;
  bottom: 22px;
  right: 4px;
}
</style>
