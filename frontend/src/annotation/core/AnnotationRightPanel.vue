<template>
  <aside class="ann-rightbar">
    <div class="panel-section">
      <div class="section-title-row">设置</div>
      <div class="setting-row">
        <span class="setting-label">标签字号</span>
        <el-slider v-model="annSettings.labelFontSize" :min="4" :max="16" size="small" />
      </div>
      <div class="setting-row">
        <span class="setting-label">框线</span>
        <el-slider v-model="annSettings.strokeWidth" :min="0.5" :max="4" :step="0.5" size="small" />
      </div>
      <div class="setting-row">
        <span class="setting-label">选中框线</span>
        <el-slider v-model="annSettings.selStrokeWidth" :min="0.5" :max="5" :step="0.5" size="small" />
      </div>
    </div>
    <div class="panel-section">
      <div class="section-title-row">图片列表</div>
      <el-radio-group :model-value="imageFilter" size="small" class="img-filter" @update:model-value="$emit('update-image-filter', $event)">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="annotated">已标</el-radio-button>
        <el-radio-button value="unannotated">未标</el-radio-button>
      </el-radio-group>
      <div class="scroll-area img-list">
        <div
          v-for="img in filteredImages"
          :key="img.id"
          class="image-item"
          :class="{ active: img.id === currentImageId }"
          @click="$emit('go-image', imagesIdx(img.id))"
        >
          <img v-if="img.thumbnail_url" :src="img.thumbnail_url" class="img-thumb" alt="" />
          <span v-else class="img-thumb img-thumb--placeholder" />
          <div class="img-info">
            <span class="img-name">{{ img.filename }}</span>
            <span class="img-meta">{{ img.updated_by?.name || "--" }}</span>
          </div>
          <span class="dot" :class="img.status === 'annotated' ? 'dot-done' : 'dot-pending'" />
        </div>
        <div v-if="filteredImages.length === 0" class="empty-hint">暂无图片</div>
      </div>
    </div>
    <div class="panel-section">
      <div class="section-title-row">
        <span>类别</span>
        <el-button link type="primary" size="small" @click="$emit('add-class')">+ 添加</el-button>
      </div>
      <div class="scroll-area">
        <div
          class="class-item"
          :class="{ active: selectedClassId === c.id }"
          v-for="c in taskClasses"
          :key="c.id"
          @click="$emit('select-class', c.id)"
        >
          <span class="dot-color" :style="{ background: c.color }" />
          <span class="flex-1">{{ c.name }}</span>
          <span class="count-chip">{{ clsCount(c.id) }}</span>
          <el-popconfirm title="确定删除该类别？" confirm-button-text="删除" cancel-button-text="取消" @confirm="$emit('remove-class', c.id)">
            <template #reference>
              <el-button text size="small">×</el-button>
            </template>
          </el-popconfirm>
        </div>
        <div v-if="taskClasses.length === 0" class="empty-hint">请添加类别</div>
      </div>
    </div>
    <div v-if="pluginName === 'classification'" class="panel-section">
      <div class="section-title-row">
        分类（{{ classificationMode === "multi" ? "多标签" : "单标签" }}）
      </div>
      <div class="scroll-area">
        <div
          v-for="c in taskClasses"
          :key="c.id"
          class="class-item"
          :class="{ active: isClsSelected(c.id) }"
          @click="$emit('toggle-classification', c.id)"
        >
          <span class="dot-color" :style="{ background: c.color }" />
          <span class="flex-1">{{ c.name }}</span>
          <el-checkbox :model-value="isClsSelected(c.id)" @click.stop />
        </div>
      </div>
    </div>
    <div class="panel-section">
      <div class="section-title-row">标注列表</div>
      <div class="scroll-area">
        <div
          v-for="a in annotations"
          :key="a.id"
          class="ann-item"
          :class="{ active: a.id === selectedAnnotationId }"
          @click="$emit('select-annotation', a.id)"
          @dblclick="$emit('edit-annotation', a)"
          @contextmenu.prevent.stop="$emit('contextmenu-annotation', $event, a)"
        >
          <span class="dot-color" :style="{ background: clsColor(a) }" />
          <span class="flex-1">{{ clsName(a) }}</span>
          <span class="tag-type">{{ a.type }}</span>
          <el-popconfirm title="确定删除该标注？" confirm-button-text="删除" cancel-button-text="取消" @confirm="$emit('delete-annotation', a.id)">
            <template #reference>
              <el-button text size="small">×</el-button>
            </template>
          </el-popconfirm>
        </div>
        <div v-if="annotations.length === 0" class="empty-hint">暂无标注</div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { Annotation } from "./types";

const props = defineProps<{
  annSettings: any;
  imageFilter: any;
  filteredImages: any[];
  images: any[];
  currentImageId: number | null;
  taskClasses: any[];
  selectedClassId: number | null;
  pluginName: string;
  classificationMode: string;
  annotations: Annotation[];
  selectedAnnotationId: string;
  clsColor: (a: Annotation) => string;
  clsName: (a: Annotation) => string;
  clsCount: (id: number) => number;
  isClsSelected: (id: number) => boolean;
}>();

const emit = defineEmits<{
  (e: "update-image-filter", v: any): void;
  (e: "go-image", index: number): void;
  (e: "add-class"): void;
  (e: "select-class", id: number): void;
  (e: "remove-class", id: number): void;
  (e: "toggle-classification", id: number): void;
  (e: "select-annotation", id: string): void;
  (e: "edit-annotation", ann: Annotation): void;
  (e: "contextmenu-annotation", ev: MouseEvent, ann: Annotation): void;
  (e: "delete-annotation", id: string): void;
}>();

function imagesIdx(id: number) {
  return props.images.findIndex((x) => x.id === id);
}
</script>

<style scoped>
.ann-rightbar {
  width: 240px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}
.panel-section {
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 8px;
}
.section-title-row {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
}
.scroll-area {
  max-height: 240px;
  overflow: auto;
}
.img-list {
  max-height: 320px;
}
.img-filter {
  margin-bottom: 6px;
}
.image-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  cursor: pointer;
  font-size: 12px;
}
.image-item.active {
  background: var(--el-color-primary-light-9);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-done {
  background: var(--el-color-success);
}
.dot-pending {
  background: var(--el-color-info);
}
.img-thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  flex-shrink: 0;
}
.img-thumb--placeholder {
  display: block;
}
.img-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.img-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-meta {
  color: #c0c4cc;
  font-size: 11px;
}
.class-item,
.ann-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  font-size: 12px;
  cursor: pointer;
}
.class-item:hover,
.ann-item:hover {
  background: var(--el-fill-color-light);
}
.class-item.active,
.ann-item.active {
  background: var(--el-color-primary-light-9);
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.flex-1 {
  flex: 1;
}
.count-chip {
  color: #c0c4cc;
  font-size: 11px;
}
.tag-type {
  color: #c0c4cc;
  font-size: 11px;
}
.setting-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.setting-label {
  width: 60px;
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 4px;
}
</style>
