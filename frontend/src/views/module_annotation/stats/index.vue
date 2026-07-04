<template>
  <div class="app-container">
    <el-card shadow="hover">
      <template #header>
        <span class="text-base font-semibold">标注统计概览</span>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="8">
          <div class="stat-card">
            <div class="stat-card__label">数据集总数</div>
            <div class="stat-card__value">{{ stats.datasetCount }}</div>
            <div class="stat-card__hint">已注册数据集</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="stat-card stat-card--task">
            <div class="stat-card__label">标注任务</div>
            <div class="stat-card__value">{{ stats.taskCount }}</div>
            <div class="stat-card__hint">全部标注任务</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="stat-card stat-card--image">
            <div class="stat-card__label">已标注图片</div>
            <div class="stat-card__value">{{ stats.annotatedImageCount }}</div>
            <div class="stat-card__hint">已完成标注</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "AnnotationStats",
  inheritAttrs: false,
});

import { reactive, onMounted } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

const stats = reactive({
  datasetCount: 0,
  taskCount: 0,
  annotatedImageCount: 0,
});

onMounted(async () => {
  try {
    const r = await AnnotationAPI.getOverview();
    const d = r.data?.data;
    if (d) {
      stats.datasetCount = d.dataset_count || 0;
      stats.taskCount = d.task_count || 0;
      stats.annotatedImageCount = d.annotated_image_count || 0;
    }
  } catch {}
});
</script>

<style scoped lang="scss">
.stat-card {
  position: relative;
  padding: 20px 20px 18px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 4%);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;

  &::before {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    content: "";
    background: var(--el-color-primary);
    border-radius: 10px 10px 0 0;
  }

  &:hover {
    border-color: var(--el-color-primary-light-7);
    box-shadow: 0 8px 24px rgb(0 0 0 / 7%);
  }

  &--task::before {
    background: var(--el-color-success);
  }
  &--image::before {
    background: var(--el-color-warning);
  }

  &__label {
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-secondary);
  }

  &__value {
    font-size: 28px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.15;
    color: var(--el-color-primary);
    letter-spacing: -0.02em;
  }

  &__hint {
    margin-top: 8px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--el-text-color-placeholder);
  }

  &--task &__value {
    color: var(--el-color-success);
  }
  &--image &__value {
    color: var(--el-color-warning);
  }
}
</style>
