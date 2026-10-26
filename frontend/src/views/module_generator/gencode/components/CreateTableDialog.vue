<template>
  <EnhancedDialog
    v-model="visible"
    :title="t('generator.createDataTable')"
    width="min(800px, 94vw)"
    append-to-body
    dialog-class="create-table-dialog"
    @opened="onDialogOpened"
  >
    <el-alert type="info" :closable="false" show-icon class="mb-3 !items-start">
      <template #title>
        <span class="text-sm leading-relaxed">
          <template v-if="editMode === 'visual'">
            {{ t("generator.visualHint") }}
          </template>
          <template v-else>{{ t("generator.sqlHint") }}</template>
        </span>
      </template>
    </el-alert>

    <div class="create-table-toolbar mb-3 flex flex-wrap items-center gap-2">
      <span class="text-sm text-[var(--el-text-color-regular)] shrink-0">
        {{ t("generator.modeLabel") }}
      </span>
      <el-radio-group v-model="editMode" size="small">
        <el-radio-button value="visual">{{ t("generator.tableStructure") }}</el-radio-button>
        <el-radio-button value="sql">{{ t("generator.writeSql") }}</el-radio-button>
      </el-radio-group>
    </div>

    <div v-show="editMode === 'sql'" class="sql-pane">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <el-dropdown trigger="click" @command="onSqlPresetCommand">
          <el-button type="primary" size="small">
            {{ t("generator.insertExample") }}
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="single-mysql">
                {{ t("generator.singleMysql") }}
              </el-dropdown-item>
              <el-dropdown-item command="single-postgres">
                {{ t("generator.singlePostgres") }}
              </el-dropdown-item>
              <el-dropdown-item command="master-mysql" divided>
                {{ t("generator.masterMysql") }}
              </el-dropdown-item>
              <el-dropdown-item command="master-postgres">
                {{ t("generator.masterPostgres") }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="text-xs text-[var(--el-text-color-secondary)]">
          {{ t("generator.fromTemplateTip") }}
        </span>
      </div>
      <el-scrollbar max-height="min(52vh, 420px)" class="sql-editor-scroll">
        <div class="absolute z-36 right-5 top-2">
          <el-link type="primary" @click="copySql">
            <el-icon><CopyDocument /></el-icon>
            {{ t("generator.copy") }}
          </el-link>
        </div>
        <CodeEditor
          ref="sqlRef"
          v-model="sqlText"
          language="sql"
          :theme="codeTheme"
          height="360px"
          border
        />
      </el-scrollbar>
    </div>

    <div v-show="editMode === 'visual'" class="visual-pane">
      <el-scrollbar max-height="min(58vh, 520px)" class="visual-pane-scroll">
        <div class="visual-structure max-w-3xl">
          <el-descriptions :column="1" border size="small" class="visual-desc">
            <template #title>
              <span class="text-sm font-medium text-[var(--el-text-color-primary)]">
                {{ t("generator.options") }}
              </span>
            </template>
            <el-descriptions-item
              :label="t('generator.database')"
              label-class-name="visual-desc-label"
            >
              <el-radio-group v-model="visual.dialect" size="small">
                <el-radio-button value="mysql">MySQL</el-radio-button>
                <el-radio-button value="postgres">PostgreSQL</el-radio-button>
              </el-radio-group>
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('generator.tableKind')"
              label-class-name="visual-desc-label"
            >
              <el-radio-group v-model="templateKind" size="small">
                <el-radio-button value="single">{{ t("generator.singleOnly") }}</el-radio-button>
                <el-radio-button value="masterSub">
                  {{ t("generator.masterSubDetail") }}
                </el-radio-button>
              </el-radio-group>
            </el-descriptions-item>
          </el-descriptions>

          <el-descriptions :column="1" border size="small" class="visual-desc mt-3">
            <template #title>
              <span class="text-sm font-medium text-[var(--el-text-color-primary)]">
                {{ t("generator.masterTable") }}
              </span>
            </template>
            <el-descriptions-item label-class-name="visual-desc-label">
              <template #label>
                <span class="text-[var(--el-color-danger)]">*</span>
                {{ t("generator.tableName") }}
              </template>
              <el-input
                v-model="visual.mainTableName"
                :placeholder="t('generator.mainTableNamePlaceholder')"
                clearable
              />
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('generator.comment')"
              label-class-name="visual-desc-label"
            >
              <el-input
                v-model="visual.mainComment"
                :placeholder="t('generator.commentPlaceholder')"
                clearable
              />
            </el-descriptions-item>
          </el-descriptions>

          <el-descriptions
            v-if="visual.subEnabled"
            :column="1"
            border
            size="small"
            class="visual-desc mt-3"
          >
            <template #title>
              <span class="text-sm font-medium text-[var(--el-text-color-primary)]">
                {{ t("generator.subTable") }}
              </span>
            </template>
            <el-descriptions-item label-class-name="visual-desc-label">
              <template #label>
                <span class="text-[var(--el-color-danger)]">*</span>
                {{ t("generator.tableName") }}
              </template>
              <el-input
                v-model="visual.subTableName"
                :placeholder="t('generator.subTableNamePlaceholder')"
                clearable
              />
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('generator.comment')"
              label-class-name="visual-desc-label"
            >
              <el-input
                v-model="visual.subComment"
                :placeholder="t('generator.commentPlaceholder')"
                clearable
              />
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('generator.fkColumn')"
              label-class-name="visual-desc-label"
            >
              <el-input
                v-model="visual.fkColumn"
                :placeholder="t('generator.fkColumnPlaceholder')"
                clearable
              />
            </el-descriptions-item>
            <el-descriptions-item
              :label="t('generator.fkRefColumn')"
              label-class-name="visual-desc-label"
            >
              <el-input
                v-model="visual.fkRefColumn"
                :placeholder="t('generator.fkRefColumnPlaceholder')"
                clearable
              />
            </el-descriptions-item>
          </el-descriptions>

          <div class="mt-3">
            <el-link type="primary" :underline="false" @click="syncVisualToSql">
              {{ t("generator.needManualAdjust") }}
            </el-link>
          </div>
        </div>
        <p class="mb-1 mt-2 text-xs text-[var(--el-text-color-secondary)]">
          {{ t("generator.execSql") }}
        </p>
        <el-input
          v-model="visualPreviewSql"
          type="textarea"
          :rows="6"
          readonly
          class="font-mono text-xs visual-sql-preview"
          :placeholder="t('generator.autoGenPlaceholder')"
        />
      </el-scrollbar>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="loading" @click="handleConfirm">
          {{ t("generator.createTableBtn") }}
        </el-button>
        <el-button @click="handleCancel">{{ t("generator.cancel") }}</el-button>
      </div>
    </template>
  </EnhancedDialog>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from "vue";
import { useI18n } from "vue-i18n";
import CodeEditor from "@/components/CodeEditor/index.vue";
import { ElMessage } from "element-plus";
import { ArrowDown, CopyDocument } from "@element-plus/icons-vue";
import { useClipboard } from "@vueuse/core";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useSettingsStore } from "@/store";
import { ThemeMode } from "@/enums/settings/theme.enum";
import { buildSqlFromVisual } from "../utils/buildCreateTableSql";
import type { SqlDialect, VisualBuildState } from "../utils/buildCreateTableSql";
import {
  applySubColumns,
  mergeGenTableLinkIntoVisual,
  visualPresetMasterSub,
  visualPresetSingle,
  type GenTableCreateLink,
} from "../utils/createTableVisualPresets";
import {
  getExampleFromPresetMasterSub,
  getExampleFromPresetSingle,
} from "../utils/createTableSqlExamples";

defineOptions({ name: "CreateTableDialog" });

const { t } = useI18n();

const visible = defineModel<boolean>({ default: false });

export interface CreateTableSubmitMeta {
  fromVisual: boolean;
  visualSnapshot?: VisualBuildState;
}

const props = withDefaults(
  defineProps<{
    loading?: boolean;
    /** 代码生成抽屉第三步打开时传入，用于预填「表结构」主/子表名 */
    linkFromGen?: GenTableCreateLink | null;
  }>(),
  { loading: false, linkFromGen: null }
);

const emit = defineEmits<{
  submit: [sql: string, meta?: CreateTableSubmitMeta];
}>();

const { copy } = useClipboard();
const settingsStore = useSettingsStore();

const editMode = ref<"sql" | "visual">("visual");
const sqlText = ref("");
const sqlRef = ref();
const visual = ref<VisualBuildState>(visualPresetSingle("mysql"));
const visualPreviewSql = ref("");

const templateKind = computed({
  get: (): "single" | "masterSub" => (visual.value.subEnabled ? "masterSub" : "single"),
  set: (v: string) => {
    if (v === "single" || v === "masterSub") applyVisualPreset(v);
  },
});

const codeTheme = computed(() => (settingsStore.theme === ThemeMode.DARK ? "one-dark" : "default"));

function onDialogOpened() {
  dialectWatchSkip = true;
  editMode.value = "visual";
  sqlText.value = "";
  visual.value = visualPresetSingle("mysql");
  visualPreviewSql.value = "";
  dialectWatchSkip = false;
  void nextTick(() => {
    applyLinkFromGenIfAny();
  });
}

/** 第三步已填主表/子表时：切到表结构模式并带入名称，减少重复输入 */
function applyLinkFromGenIfAny() {
  const link = props.linkFromGen;
  if (!link) return;
  const touched =
    (link.table_name || "").trim() ||
    (link.table_comment || "").trim() ||
    ((link.sub_table_name || "").trim() && (link.sub_table_fk_name || "").trim());
  if (!touched) return;
  visual.value = mergeGenTableLinkIntoVisual(link, visual.value.dialect);
  editMode.value = "visual";
  visualPreviewSql.value = buildSqlFromVisual(applySubColumns(visual.value));
  ElMessage.info({
    message: t("generator.linkedFromGen"),
    duration: 2800,
  });
}

watch(
  visual,
  () => {
    if (editMode.value !== "visual" || !visible.value) return;
    visualPreviewSql.value = buildSqlFromVisual(applySubColumns(visual.value));
  },
  { deep: true }
);

watch(editMode, (m) => {
  if (m === "sql") {
    sqlText.value = buildSqlFromVisual(applySubColumns(visual.value));
  } else {
    visualPreviewSql.value = buildSqlFromVisual(applySubColumns(visual.value));
  }
});

let dialectWatchSkip = false;
watch(
  () => visual.value.dialect,
  (_d, prev) => {
    if (dialectWatchSkip) return;
    if (prev === undefined) return;
    const d = visual.value.dialect;
    visual.value = visual.value.subEnabled
      ? applySubColumns(visualPresetMasterSub(d))
      : visualPresetSingle(d);
  }
);

function applyVisualPreset(kind: "single" | "masterSub") {
  const d = visual.value.dialect;
  visual.value =
    kind === "single" ? visualPresetSingle(d) : applySubColumns(visualPresetMasterSub(d));
}

function syncVisualToSql() {
  if (!validateVisual()) return;
  sqlText.value = buildSqlFromVisual(applySubColumns(visual.value));
  editMode.value = "sql";
  void nextTick(() => {
    ElMessage.success(t("generator.switchedToSql"));
  });
}

function onSqlPresetCommand(cmd: string) {
  switch (cmd) {
    case "single-mysql":
      loadPresetSql("single", "mysql");
      break;
    case "single-postgres":
      loadPresetSql("single", "postgres");
      break;
    case "master-mysql":
      loadPresetSql("masterSub", "mysql");
      break;
    case "master-postgres":
      loadPresetSql("masterSub", "postgres");
      break;
    default:
      break;
  }
}

/** 表结构模式提交前校验，避免无效请求 */
function validateVisual(): boolean {
  const v = applySubColumns(visual.value);
  if (!(v.mainTableName || "").trim()) {
    ElMessage.warning(t("generator.fillMainTableName"));
    return false;
  }
  if (v.subEnabled) {
    if (!(v.subTableName || "").trim()) {
      ElMessage.warning(t("generator.fillSubTableName"));
      return false;
    }
    if (!(v.fkColumn || "").trim()) {
      ElMessage.warning(t("generator.fillFkColumn"));
      return false;
    }
    if (!(v.fkRefColumn || "").trim()) {
      ElMessage.warning(t("generator.fillFkRefColumn"));
      return false;
    }
  }
  return true;
}

function loadPresetSql(kind: "single" | "masterSub", dialect: SqlDialect) {
  sqlText.value =
    kind === "single"
      ? getExampleFromPresetSingle(dialect)
      : getExampleFromPresetMasterSub(dialect);
}

function copySql() {
  if (!sqlText.value) {
    ElMessage.warning(t("generator.noCopyContent"));
    return;
  }
  copy(sqlText.value);
  ElMessage.success(t("generator.copied"));
}

function handleConfirm() {
  if (editMode.value === "visual" && !validateVisual()) return;
  const sql =
    editMode.value === "sql"
      ? sqlText.value.trim()
      : buildSqlFromVisual(applySubColumns(visual.value)).trim();
  if (!sql) {
    ElMessage.error(t("generator.fillTableOrSql"));
    return;
  }
  if (editMode.value === "visual") {
    emit("submit", sql, {
      fromVisual: true,
      visualSnapshot: applySubColumns(visual.value),
    });
  } else {
    emit("submit", sql);
  }
}

function handleCancel() {
  visible.value = false;
}
</script>

<style scoped lang="scss">
.sql-pane {
  position: relative;
}

.visual-pane :deep(.el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.visual-sql-preview {
  margin-top: 10px;
}

/* 表结构：描述列表表格化，标签列对齐、内容区可伸缩 */
.visual-structure {
  .visual-desc {
    :deep(.el-descriptions__label) {
      width: 108px;
      vertical-align: middle;
    }

    :deep(.el-descriptions__cell) {
      vertical-align: middle;
    }

    :deep(.el-descriptions__content) {
      min-width: 0;
    }

    :deep(.el-descriptions__title) {
      margin-bottom: 8px;
    }
  }
}
</style>
