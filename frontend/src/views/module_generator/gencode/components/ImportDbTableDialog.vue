<template>
  <EnhancedDialog
    ref="dialogRef"
    v-model="open"
    :title="t('generator.importTable')"
    width="min(960px, 96vw)"
    append-to-body
    @fullscreen-change="onFullscreenChange"
  >
    <el-form ref="importQueryRef" :model="query" :inline="true">
      <el-form-item :label="t('generator.tableName')" prop="table_name">
        <el-input
          v-model="query.table_name"
          :placeholder="t('generator.inputTableName')"
          clearable
          style="width: 180px"
          @keyup.enter="emit('query')"
        />
      </el-form-item>
      <el-form-item :label="t('generator.tableComment')" prop="table_comment">
        <el-input
          v-model="query.table_comment"
          :placeholder="t('generator.inputTableComment')"
          clearable
          style="width: 180px"
          @keyup.enter="emit('query')"
        />
      </el-form-item>
      <el-form-item>
        <el-button
          v-hasPerm="['module_generator:dblist:query']"
          type="primary"
          icon="Search"
          @click="emit('query')"
        >
          {{ t("generator.search") }}
        </el-button>
        <el-button
          v-hasPerm="['module_generator:dblist:query']"
          icon="Refresh"
          @click="emit('reset')"
        >
          {{ t("generator.reset") }}
        </el-button>
      </el-form-item>
    </el-form>
    <el-row>
      <el-table
        ref="tableRef"
        stripe
        :data="data"
        :height="tableHeight"
        border
        @row-click="onRowClick"
        @selection-change="onSelectionChange"
      >
        <template #empty>
          <el-empty :image-size="80" :description="t('generator.noData')" />
        </template>
        <el-table-column type="selection" width="55"></el-table-column>
        <el-table-column
          :label="t('generator.serial')"
          type="index"
          min-width="30"
          align="center"
          fixed
        >
          <template #default="scope">
            <span>
              {{ ((query.page_no ?? 1) - 1) * (query.page_size ?? 10) + scope.$index + 1 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="database_name"
          :label="t('generator.databaseName')"
          :show-overflow-tooltip="true"
        ></el-table-column>
        <el-table-column
          prop="table_name"
          :label="t('generator.tableName')"
          :show-overflow-tooltip="true"
        ></el-table-column>
        <el-table-column
          prop="table_comment"
          :label="t('generator.tableComment')"
          :show-overflow-tooltip="true"
        ></el-table-column>
        <el-table-column prop="table_type" :label="t('generator.tableType')"></el-table-column>
      </el-table>
      <pagination
        v-model:page="query.page_no"
        v-model:limit="query.page_size"
        :total="total"
        @pagination="emit('fetch')"
      />
    </el-row>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="confirmLoading" @click="emit('confirm')">
          {{ t("generator.confirm") }}
        </el-button>
        <el-button @click="open = false">{{ t("generator.cancelConfirm") }}</el-button>
      </div>
    </template>
  </EnhancedDialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance, TableInstance } from "element-plus";
import type { DBTableSchema, GenTablePageQuery } from "@/api/module_generator/gencode";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

defineOptions({ name: "ImportDbTableDialog" });

const { t } = useI18n();

defineProps<{
  data: DBTableSchema[];
  total: number;
  confirmLoading: boolean;
}>();

const open = defineModel<boolean>({ required: true });
const query = defineModel<GenTablePageQuery>("query", { required: true });

const emit = defineEmits<{
  query: [];
  reset: [];
  confirm: [];
  fetch: [];
  "selection-change": [rows: { table_name: string; table_comment: string }[]];
}>();

const importQueryRef = ref<FormInstance>();
const tableRef = ref<TableInstance>();
const isFullscreen = ref(false);

// 根据全屏状态计算表格高度
const tableHeight = computed(() => {
  return isFullscreen.value ? "calc(100vh - 320px)" : "300px";
});

function onFullscreenChange(fullscreen: boolean) {
  isFullscreen.value = fullscreen;
}

function onRowClick(row: DBTableSchema) {
  tableRef.value?.toggleRowSelection(row);
}

function onSelectionChange(selection: DBTableSchema[]) {
  emit(
    "selection-change",
    selection.map((item) => ({
      table_name: item.table_name || "",
      table_comment: item.table_comment || "",
    }))
  );
}

defineExpose({
  resetQueryForm: () => importQueryRef.value?.resetFields(),
});
</script>
