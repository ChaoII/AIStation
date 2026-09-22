<template>
  <aside class="text-ner-bar">
    <!-- 实体列表 -->
    <div class="tacc" :class="{ open: open === 'entities' }">
      <div class="tacc-head" @click="toggle('entities')">
        <span>实体（{{ entities.length }}）</span>
        <el-icon :size="13"><component :is="open === 'entities' ? ArrowDown : ArrowRight" /></el-icon>
      </div>
      <div v-show="open === 'entities'" class="tacc-body">
        <div
          v-for="e in entities"
          :key="e.id"
          class="titem"
          :class="{ active: e.id === selectedId }"
          @click="$emit('select-entity', e.id)"
          @dblclick="$emit('select-entity', e.id)"
        >
          <span class="dot-color" :style="{ background: entityColor(e) }" />
          <span class="titem-text">{{ entityText(e) }}</span>
          <span class="titem-type">{{ entityName(e) }}</span>
          <el-button text size="small" class="titem-del" @click.stop="$emit('delete-entity', e.id)">
            ×
          </el-button>
        </div>
        <div v-if="entities.length === 0" class="empty-hint">拖动文本选区生成实体</div>
      </div>
    </div>

    <!-- 关系列表 -->
    <div class="tacc" :class="{ open: open === 'relations' }">
      <div class="tacc-head" @click="toggle('relations')">
        <span>关系（{{ relations.length }}）</span>
        <span class="head-actions" @click.stop>
          <el-button link type="primary" size="small" @click="$emit('new-relation')">+ 新建</el-button>
          <el-icon :size="13">
            <component :is="open === 'relations' ? ArrowDown : ArrowRight" />
          </el-icon>
        </span>
      </div>
      <div v-show="open === 'relations'" class="tacc-body">
        <div
          v-for="r in relations"
          :key="r.id"
          class="titem"
          :class="{ active: r.id === activeRelationId }"
          @mouseenter="$emit('click-relation', r.id)"
          @mouseleave="$emit('click-relation', '')"
          @click="$emit('click-relation', r.id)"
        >
          <span class="rel-node">{{ entityById(r.from) }}</span>
          <span class="rel-arrow">→</span>
          <span class="rel-node">{{ entityById(r.to) }}</span>
          <span class="titem-type">{{ relationName(r) }}</span>
          <el-button text size="small" class="titem-del" @click.stop="$emit('delete-relation', r.id)">
            ×
          </el-button>
        </div>
        <div v-if="relations.length === 0" class="empty-hint">暂无关系，点击「+ 新建」创建</div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ArrowDown, ArrowRight } from "@element-plus/icons-vue";
import type { EntitySpan, Relation } from "@/api/module_annotation/document";

const props = defineProps<{
  entities: EntitySpan[];
  relations: Relation[];
  entityClasses: any[];
  relationClasses: any[];
  selectedId: string;
  activeRelationId: string;
}>();

defineEmits<{
  (e: "select-entity", id: string): void;
  (e: "new-relation"): void;
  (e: "delete-entity", id: string): void;
  (e: "delete-relation", id: string): void;
  (e: "click-relation", id: string): void;
}>();

const open = ref<string | null>("entities");

function toggle(name: string) {
  open.value = open.value === name ? null : name;
}

function entityName(e: EntitySpan): string {
  return props.entityClasses.find((c) => c.id === e.label_id)?.name ?? `#${e.label_id}`;
}

function entityColor(e: EntitySpan): string {
  return props.entityClasses.find((c) => c.id === e.label_id)?.color || "#909399";
}

function entityText(e: EntitySpan): string {
  return e.text || "";
}

function entityById(id: string): string {
  const e = props.entities.find((x) => x.id === id);
  return e ? (e.text || "…") : "…";
}

function relationName(r: Relation): string {
  return props.relationClasses.find((c) => c.id === r.relation_type)?.name ?? `#${r.relation_type}`;
}
</script>

<style scoped>
.text-ner-bar {
  width: 260px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.tacc {
  flex: none;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--el-border-color-light);
}
.tacc.open {
  flex: 1;
}
.tacc-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 8px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  user-select: none;
}
.tacc-head:hover {
  background: var(--el-fill-color-light);
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tacc-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 6px;
  scrollbar-width: thin;
}
.tacc-body::-webkit-scrollbar {
  width: 6px;
}
.titem {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 2px;
}
.titem:hover {
  background: var(--el-color-primary-light-9);
}
.titem.active {
  background: var(--el-color-primary-light-8);
}
.titem.active .titem-text,
.titem.active .rel-node {
  color: var(--el-color-primary);
  font-weight: 500;
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.titem-text,
.rel-node {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.titem-type {
  color: var(--el-color-info);
  font-size: 11px;
  flex-shrink: 0;
}
.titem-del {
  flex-shrink: 0;
  padding: 0 2px;
}
.rel-arrow {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
.empty-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  padding: 4px;
}
</style>
