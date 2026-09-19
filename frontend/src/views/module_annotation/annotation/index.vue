<template>
  <div class="annotation-workbench-page">
    <AnnotationWorkbench
      ref="wbRef"
      :plugins="plugins"
      :api="api"
      :config="config"
      :task-id="taskId"
      :collab="collab"
      @open-history="openHistory"
    />
    <AnnotationHistoryDrawer ref="historyRef" @restored="onHistoryRestored" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import AnnotationWorkbench from "@/annotation/core/AnnotationWorkbench.vue";
import {
  detectionPlugin,
  rotatedBoxPlugin,
  segmentationPlugin,
  keypointPlugin,
  ocrPlugin,
  classificationPlugin,
} from "@/annotation";
import type { WorkbenchApi, WorkbenchConfig } from "@/annotation/core/annotationTypes";
import { AnnotationAPI } from "@/api/module_annotation";
import { useCollab } from "@/composables/useCollab";
import AnnotationHistoryDrawer from "@/components/Annotation/AnnotationHistoryDrawer.vue";

const route = useRoute();
const taskId = Number(route.params.id || route.query.id || 0);
const wbRef = ref();
const historyRef = ref();
const collab = useCollab();

const plugins = [
  detectionPlugin,
  rotatedBoxPlugin,
  segmentationPlugin,
  keypointPlugin,
  ocrPlugin,
  classificationPlugin,
];

// 极简 api 适配：把项目 AnnotationAPI 适配到组件库 WorkbenchApi 接口
const api: WorkbenchApi = {
  getTaskDetail: (id) => AnnotationAPI.getTaskDetail(id),
  listImages: (params: any) =>
    AnnotationAPI.getImages(params.dataset_id, params.task_id, params.page_no, params.page_size),
  getImages: (datasetId, taskId, page, pageSize, opts) =>
    AnnotationAPI.getImages(datasetId, taskId, page, pageSize, opts),
  getPresignedUrl: (imageId, taskId) => AnnotationAPI.getPresignedUrl(imageId, taskId),
  loadAnnotations: (taskId, imageId) => AnnotationAPI.getAnnotations(taskId, imageId),
  saveAnnotations: (taskId, imageId, data) =>
    AnnotationAPI.saveAnnotations(imageId, { task_id: taskId, annotation_data: data }),
  lockImage: (imageId, taskId) => AnnotationAPI.lockImage(imageId, taskId),
  unlockImage: (imageId, taskId) => AnnotationAPI.unlockImage(imageId, taskId),
  updateTask: (id, patch) => AnnotationAPI.updateTask(id, patch),
  getTaskProgress: (id) => AnnotationAPI.getTaskProgress(id),
};

const config = ref<WorkbenchConfig>({ taskType: "detection", classes: [], classificationMode: "single" });

async function loadConfig() {
  try {
    const dr = await AnnotationAPI.getTaskDetail(taskId);
    const t = dr?.data?.data;
    if (!t) return;
    config.value = {
      taskType: t.task_type || "detection",
      classes: t.classes || [],
      classificationMode: t.classification_mode || "single",
    };
  } catch {
    /* 提示由拦截器处理 */
  }
}

function openHistory() {
  const imgId = wbRef.value?.getCurrentImageId();
  if (imgId) historyRef.value?.open(taskId, imgId);
}
function onHistoryRestored() {
  wbRef.value?.refreshCurrent();
}

onMounted(loadConfig);
</script>

<style scoped>
.annotation-workbench-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.annotation-workbench-page :deep(.ann-workbench) {
  flex: 1;
  min-height: 0;
}
</style>
