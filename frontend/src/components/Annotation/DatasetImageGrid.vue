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
      </div>
      <div v-loading="loading" class="grid-body">
        <el-row :gutter="8">
          <el-col v-for="img in filtered" :key="img.id" :xs="12" :sm="8" :md="6" :lg="6">
            <div class="grid-cell" @click="emit('open-workbench', img)">
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

defineOptions({ name: "DatasetImageGrid" });

const props = defineProps<{ modelValue: boolean; datasetId: number | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "open-workbench", img: any): void;
}>();

const page = ref(1);
const pageSize = 24;
const total = ref(0);
const loading = ref(false);
const images = ref<any[]>([]);
const filter = ref<"all" | "unannotated" | "annotated">("all");

const filtered = computed(() => {
  if (filter.value === "all") return images.value;
  return images.value.filter((i) => i.status === filter.value);
});

async function load(p: number) {
  if (!props.datasetId) return;
  page.value = p;
  loading.value = true;
  try {
    const r = await AnnotationAPI.getImages(props.datasetId, undefined, p, pageSize);
    images.value = r.data?.data?.items || [];
    total.value = r.data?.data?.total || 0;
  } catch {
    images.value = [];
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.grid-toolbar {
  margin-bottom: 8px;
}
.grid-body {
  min-height: 200px;
}
.grid-cell {
  position: relative;
  margin-bottom: 8px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
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
</style>
