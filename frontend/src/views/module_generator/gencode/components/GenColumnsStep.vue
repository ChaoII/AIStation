<template>
  <div class="elTableCustom">
    <el-alert
      v-if="info.sub && !info.master_sub_hint && info.sub_table_name"
      class="mb-3"
      type="success"
      :closable="false"
      show-icon
      :title="t('generator.masterSubEnabled')"
    />
    <el-alert
      v-else-if="info.master_sub_hint"
      class="mb-3"
      type="warning"
      :closable="false"
      show-icon
      :title="info.master_sub_hint"
    />
    <p class="gencode-columns-tip">
      {{ t("generator.columnsTip") }}
    </p>
    <el-alert
      v-if="columnKeyword.trim() && displayColumns.length === 0 && (info.columns?.length ?? 0) > 0"
      class="mb-2"
      type="warning"
      :closable="false"
      show-icon
      :title="t('generator.noMatchCols')"
    />
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <el-input
        v-model="columnKeyword"
        clearable
        :placeholder="t('generator.filterPlaceholder')"
        class="gencode-column-filter"
        :prefix-icon="Search"
      />
      <span class="gencode-bulk-hint">{{ t("generator.bulkSet") }}</span>
      <el-space size="small">
        <el-dropdown>
          <el-button size="small" type="primary" plain>{{ t("generator.query") }}</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="bulkSet('is_query', true)">
                {{ t("generator.allSelect") }}
              </el-dropdown-item>
              <el-dropdown-item @click="bulkSet('is_query', false)">
                {{ t("generator.noneSelect") }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown>
          <el-button size="small" type="success" plain>{{ t("generator.list") }}</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="bulkSet('is_list', true)">
                {{ t("generator.allSelect") }}
              </el-dropdown-item>
              <el-dropdown-item @click="bulkSet('is_list', false)">
                {{ t("generator.noneSelect") }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown>
          <el-button size="small" type="warning" plain>{{ t("generator.add") }}</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="bulkSet('is_insert', true)">
                {{ t("generator.allSelect") }}
              </el-dropdown-item>
              <el-dropdown-item @click="bulkSet('is_insert', false)">
                {{ t("generator.noneSelect") }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown>
          <el-button size="small" type="danger" plain>{{ t("generator.edit") }}</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="bulkSet('is_edit', true)">
                {{ t("generator.allSelect") }}
              </el-dropdown-item>
              <el-dropdown-item @click="bulkSet('is_edit', false)">
                {{ t("generator.noneSelect") }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-space>
    </div>
    <div class="data-table__content">
      <el-table
        ref="dragTable"
        v-loading="loading"
        :data="displayColumns"
        row-key="id"
        :height="tableHeight"
        highlight-current-row
        border
        stripe
      >
        <template #empty>
          <el-empty :image-size="80" :description="t('generator.noData')" />
        </template>
        <el-table-column :label="t('generator.drag')" width="56" fixed align="center">
          <template #default>
            <span
              class="gencode-drag-handle"
              :class="{ disabled: !!columnKeyword.trim() }"
              :title="t('generator.dragTip')"
            >
              <el-icon><Rank /></el-icon>
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.serial')" type="index" width="60" fixed />
        <el-table-column
          :label="t('generator.columnName')"
          prop="column_name"
          min-width="60"
          :show-overflow-tooltip="true"
        />
        <el-table-column
          :label="t('generator.columnType')"
          prop="column_type"
          min-width="60"
          :show-overflow-tooltip="true"
        />
        <el-table-column
          :label="t('generator.columnLength')"
          prop="column_length"
          width="80"
          :show-overflow-tooltip="true"
        >
          <template #default="scope">
            <el-input v-model="scope.row.column_length" :disabled="!!scope.row.is_pk" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.columnComment')" min-width="60">
          <template #default="scope">
            <el-input v-model="scope.row.column_comment"></el-input>
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.backendType')" min-width="60">
          <template #default="scope">
            <el-select v-model="scope.row.python_type">
              <el-option label="str" value="str" />
              <el-option label="int" value="int" />
              <el-option label="float" value="float" />
              <el-option label="Decimal" value="Decimal" />
              <el-option label="date" value="date" />
              <el-option label="time" value="time" />
              <el-option label="datetime" value="datetime" />
              <el-option label="bytes" value="bytes" />
              <el-option label="dict" value="dict" />
              <el-option label="list" value="list" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.backendField')" min-width="60">
          <template #default="scope">
            <el-input v-model="scope.row.python_field"></el-input>
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.add')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_insert" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.edit')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_edit" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.list')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_list" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.query')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_query" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.queryType')" min-width="60">
          <template #default="scope">
            <el-select v-model="scope.row.query_type">
              <el-option label="=" value="EQ" />
              <el-option label="!=" value="NE" />
              <el-option label=">" value="GT" />
              <el-option label=">=" value="GTE" />
              <el-option label="<" value="LT" />
              <el-option label="<=" value="LTE" />
              <el-option label="LIKE" value="LIKE" />
              <el-option label="BETWEEN" value="BETWEEN" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('generator.defaultVal')"
          prop="column_default"
          min-width="60"
          :show-overflow-tooltip="true"
        >
          <template #default="scope">
            <el-input v-model="scope.row.column_default" :disabled="!!scope.row.is_pk" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.autoInc')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_increment" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.nullable')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_nullable" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.unique')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_unique" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.pk')" width="60">
          <template #default="scope">
            <el-checkbox v-model="scope.row.is_pk" />
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.formType')">
          <template #default="scope">
            <el-select v-model="scope.row.html_type">
              <el-option :label="t('generator.input')" value="input" />
              <el-option :label="t('generator.textarea')" value="textarea" />
              <el-option :label="t('generator.select')" value="select" />
              <el-option :label="t('generator.radio')" value="radio" />
              <el-option :label="t('generator.checkbox')" value="checkbox" />
              <el-option :label="t('generator.datetime')" value="datetime" />
              <el-option :label="t('generator.imageUpload')" value="imageUpload" />
              <el-option :label="t('generator.fileUpload')" value="fileUpload" />
              <el-option :label="t('generator.editor')" value="editor" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('generator.dictType')" fixed="right">
          <template #default="scope">
            <el-select
              v-model="scope.row.dict_type"
              clearable
              filterable
              :placeholder="t('generator.selectPlaceholder')"
            >
              <el-option
                v-for="dict in dictOptions"
                :key="dict.dict_type"
                :label="dict.dict_name"
                :value="dict.dict_type || ''"
              >
                <span style="float: left">{{ dict.dict_name }}</span>
                <span class="dict-option-type">
                  {{ dict.dict_type }}
                </span>
              </el-option>
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { Search } from "@element-plus/icons-vue";
import { useDraggable } from "vue-draggable-plus";
import type { GenTableSchema } from "@/api/module_generator/gencode";
import type { DictTable } from "@/api/module_system/dict";

defineOptions({ name: "GenColumnsStep" });

const { t } = useI18n();

const props = defineProps<{
  info: GenTableSchema;
  dictOptions: DictTable[];
  loading: boolean;
  bulkSet: (field: string | string[], value: unknown) => void;
}>();

const columnKeyword = ref("");
const dragTable = ref<any>(null);
const dragContainer = ref<HTMLElement | null>(null);
let draggableApi: { destroy?: () => void; pause?: () => void; start?: () => void } | null = null;

// 计算表格高度：视口高度 - 顶部导航栏 - 步骤条 - 提示文字 - 筛选栏 - 底部按钮 - 边距
// 大约：60(顶部) + 60(步骤) + 30(提示) + 50(筛选) + 80(底部按钮) + 100(边距) = 380px
const tableHeight = computed(() => {
  return "calc(100vh - 300px)"; // -80 底部按钮
});

const columnsModel = computed({
  get: () => props.info.columns || [],
  set: (v) => {
    // props.info 是父组件传入的 reactive 对象，可以直接回写
    props.info.columns = v as any;
  },
});

const displayColumns = computed(() => {
  const cols = props.info.columns || [];
  const q = columnKeyword.value.trim().toLowerCase();
  if (!q) return cols;
  return cols.filter((c) => {
    const name = String(c.column_name ?? "").toLowerCase();
    const comment = String(c.column_comment ?? "").toLowerCase();
    return name.includes(q) || comment.includes(q);
  });
});

function syncSortNumbers() {
  const cols = columnsModel.value || [];
  cols.forEach((c: any, idx: number) => {
    c.sort = idx + 1;
  });
}

async function setupRowDraggable() {
  // 筛选状态下禁用拖拽：displayColumns 是子集，直接拖拽会导致索引映射混乱
  if (columnKeyword.value.trim()) {
    draggableApi?.destroy?.();
    draggableApi = null;
    dragContainer.value = null;
    return;
  }

  await nextTick();
  const el = dragTable.value?.$el as HTMLElement | undefined;
  const tbody = el?.querySelector?.(".el-table__body-wrapper tbody") as HTMLElement | null;
  if (!tbody) return;
  dragContainer.value = tbody;

  // 重新绑定
  draggableApi?.destroy?.();
  draggableApi = useDraggable(dragContainer, columnsModel, {
    animation: 150,
    draggable: "tr",
    handle: ".gencode-drag-handle:not(.disabled)",
    onEnd() {
      syncSortNumbers();
    },
  });
}

onMounted(() => {
  void setupRowDraggable();
});

watch(
  () => [columnKeyword.value, (props.info.columns || []).length],
  async () => {
    await setupRowDraggable();
  }
);

onBeforeUnmount(() => {
  draggableApi?.destroy?.();
  draggableApi = null;
});
</script>

<style scoped lang="scss">
.gencode-columns-tip {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.gencode-column-filter {
  width: 200px;
  max-width: 100%;
}

.gencode-bulk-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  user-select: none;
}

/* 下拉选项右侧的类型说明（替代内联 style，颜色改用主题变量） */
.dict-option-type {
  float: right;
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
}

.gencode-drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  font-size: 14px;
  line-height: 1;
  color: var(--el-text-color-secondary);
  cursor: grab;
  user-select: none;
}

.gencode-drag-handle.disabled {
  cursor: not-allowed;
  opacity: 0.35;
}
</style>
