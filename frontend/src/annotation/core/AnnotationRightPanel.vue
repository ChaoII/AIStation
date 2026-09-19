<template>
  <aside class="ann-rightbar">
    <!-- 设置 -->
    <div class="acc" :class="{ open: open === 'settings' }">
      <div class="acc-head" @click="toggle('settings')">
        <span>设置</span>
        <el-icon :size="13"><component :is="open === 'settings' ? ArrowDown : ArrowRight" /></el-icon>
      </div>
      <div v-show="open === 'settings'" class="acc-body">
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
    </div>

    <!-- 图片列表 -->
    <div class="acc" :class="{ open: open === 'images' }">
      <div class="acc-head" @click="toggle('images')">
        <span>图片列表</span>
        <el-icon :size="13"><component :is="open === 'images' ? ArrowDown : ArrowRight" /></el-icon>
      </div>
      <div v-show="open === 'images'" class="acc-body">
        <el-radio-group :model-value="imageFilter" size="small" class="img-filter" @update:model-value="$emit('update-image-filter', $event)">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="annotated">已标</el-radio-button>
          <el-radio-button value="unannotated">未标</el-radio-button>
        </el-radio-group>
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
            <span class="img-meta">{{ img.updated_by?.name || "--" }}<template v-if="img.updated_time"> · {{ fmtTime(img.updated_time) }}</template></span>
          </div>
          <span class="dot" :class="img.status === 'annotated' ? 'dot-done' : 'dot-pending'" />
        </div>
        <div v-if="filteredImages.length === 0" class="empty-hint">暂无图片</div>
      </div>
    </div>

    <!-- 类别 -->
    <div class="acc" :class="{ open: open === 'classes' }">
      <div class="acc-head" @click="toggle('classes')">
        <span>类别</span>
        <span class="head-actions" @click.stop>
          <el-button link type="primary" size="small" @click="$emit('add-class')">+ 添加</el-button>
          <el-icon :size="13"><component :is="open === 'classes' ? ArrowDown : ArrowRight" /></el-icon>
        </span>
      </div>
      <div v-show="open === 'classes'" class="acc-body">
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

    <!-- 分类 (仅分类任务) -->
    <div v-if="pluginName === 'classification'" class="acc" :class="{ open: open === 'classification' }">
      <div class="acc-head" @click="toggle('classification')">
        <span>分类（{{ classificationMode === "multi" ? "多标签" : "单标签" }}）</span>
        <el-icon :size="13"><component :is="open === 'classification' ? ArrowDown : ArrowRight" /></el-icon>
      </div>
      <div v-show="open === 'classification'" class="acc-body">
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

    <!-- 标注列表 -->
    <div class="acc" :class="{ open: open === 'annotations' }">
      <div class="acc-head" @click="toggle('annotations')">
        <span>标注列表</span>
        <el-icon :size="13"><component :is="open === 'annotations' ? ArrowDown : ArrowRight" /></el-icon>
      </div>
      <div v-show="open === 'annotations'" class="acc-body">
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
import { ref } from "vue";
import { ArrowDown, ArrowRight } from "@element-plus/icons-vue";
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

// 手风琴：同一时间只展开一个，展开项占满剩余高度
const open = ref<string | null>("images");

function toggle(name: string) {
  open.value = open.value === name ? null : name;
}

function imagesIdx(id: number) {
  return props.images.findIndex((x) => x.id === id);
}

function fmtTime(ts: any) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    const p = (n: number) => String(n).padStart(2, "0");
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch {
    return "";
  }
}
</script>

<style scoped>
.ann-rightbar {
  width: 240px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.acc {
  flex: none;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--el-border-color-light);
}
.acc.open {
  flex: 1;
}
.acc-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 30px;
  padding: 0 8px;
  cursor: pointer;
  color: #606266;
  font-size: 13px;
  user-select: none;
}
.acc-head:hover {
  background: var(--el-fill-color-light);
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.acc-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 6px;
  scrollbar-width: thin;
}
.acc-body::-webkit-scrollbar {
  width: 6px;
}
.acc-body::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
}
.img-filter {
  margin-bottom: 4px;
}
.setting-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 0;
}
.setting-label {
  width: 44px;
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
.image-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 2px;
  cursor: pointer;
  font-size: 12px;
}
.image-item:hover {
  background: var(--el-fill-color-light);
}
.image-item.active {
  background: var(--el-color-primary-light-9);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-done {
  background: var(--el-color-success);
}
.dot-pending {
  background: var(--el-color-info);
}
.img-thumb {
  width: 24px;
  height: 24px;
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
  line-height: 1.2;
}
.img-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-meta {
  color: #c0c4cc;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.class-item,
.ann-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
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
  flex-shrink: 0;
}
.flex-1 {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.count-chip {
  color: #c0c4cc;
  font-size: 11px;
}
.tag-type {
  color: #c0c4cc;
  font-size: 11px;
}
.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 4px;
}
</style>
