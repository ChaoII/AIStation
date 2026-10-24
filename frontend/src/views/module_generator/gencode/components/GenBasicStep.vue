<template>
  <el-form ref="formRef" class="gen-basic-step" :model="info" :rules="rules" label-width="120px">
    <!-- 顶部：生成回显 -->
    <el-row :gutter="12" class="mb-3">
      <el-col :span="24">
        <el-card shadow="never" class="gen-echo-card">
          <div class="gen-echo-card__title">{{ t("generator.echoTitle") }}</div>
          <div class="gen-echo-grid">
            <div class="gen-echo-item">
              <div class="gen-echo-item__k">{{ t("generator.backendPath") }}</div>
              <code class="gen-echo-item__v">{{ backendModuleDirPreview }}</code>
            </div>
            <div class="gen-echo-item">
              <div class="gen-echo-item__k">{{ t("generator.frontendViewPath") }}</div>
              <code class="gen-echo-item__v">{{ frontendViewDirPreview }}</code>
            </div>
            <div class="gen-echo-item">
              <div class="gen-echo-item__k">{{ t("generator.frontendApiFile") }}</div>
              <code class="gen-echo-item__v">{{ frontendApiFilePreview }}</code>
            </div>
            <div class="gen-echo-item">
              <div class="gen-echo-item__k gen-echo-item__k--with-tip">
                {{ t("generator.permission") }}
                <el-tooltip :content="t('generator.permissionTip')" placement="top">
                  <el-icon class="gen-echo-item__tip"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <code class="gen-echo-item__v">{{ permissionPreview }}</code>
            </div>
          </div>
          <div
            v-if="info.sub_table_name && info.sub_table_fk_name && !info.master_sub_hint"
            class="gen-echo-warn"
          >
            {{ t("generator.subTableExtra") }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="gen-layout-row">
      <el-col :span="24" class="gen-layout-left">
        <el-card shadow="never" class="gen-form-card">
          <template #header>
            <div class="gen-form-card__header">
              <span class="font-medium">{{ t("generator.basicInfo") }}</span>
              <span class="gen-form-card__hint">{{ t("generator.stepSaveHint") }}</span>
            </div>
          </template>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('generator.tableName')" prop="table_name">
                <el-input v-model="info.table_name" :placeholder="t('generator.inputTableName')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('generator.tableComment')" prop="table_comment">
                <el-input
                  v-model="info.table_comment"
                  :placeholder="t('generator.inputTableComment')"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('generator.entityName')" prop="class_name">
                <el-input
                  v-model="info.class_name"
                  :placeholder="t('generator.inputPlaceholder')"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item prop="package_name">
                <template #label>
                  {{ t("generator.packageName") }}
                  <el-tooltip :content="t('generator.packageTip')" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <div class="gen-package-row">
                  <el-input
                    v-model="info.package_name"
                    class="gen-package-row__input"
                    :placeholder="t('generator.packagePlaceholder')"
                    clearable
                  />
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item prop="module_name">
                <template #label>
                  {{ t("generator.moduleName") }}
                  <el-tooltip :content="t('generator.moduleTip')" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input
                  v-model="info.module_name"
                  :placeholder="t('generator.modulePlaceholder')"
                  clearable
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item prop="business_name">
                <template #label>
                  {{ t("generator.businessName") }}
                  <el-tooltip :content="t('generator.businessTip')" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input
                  v-model="info.business_name"
                  :placeholder="t('generator.businessPlaceholder')"
                  clearable
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item prop="function_name">
                <template #label>
                  {{ t("generator.functionName") }}
                  <el-tooltip :content="t('generator.functionTip')" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input
                  v-model="info.function_name"
                  :placeholder="t('generator.functionPlaceholder')"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item>
                <template #label>
                  {{ t("generator.parentMenu") }}
                  <el-tooltip :content="t('generator.parentMenuTip')" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-tree-select
                  v-model="info.parent_menu_id"
                  :data="menuOptions"
                  :placeholder="t('generator.parentMenuPlaceholder')"
                  check-strictly
                  filterable
                  default-expand-all
                  :render-after-expand="false"
                  clearable
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item :label="t('generator.remark')" prop="description">
                <el-input v-model="info.description" type="textarea" :rows="3"></el-input>
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-card shadow="never" class="master-sub-card mb-4">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item prop="sub_table_name">
                      <template #label>
                        {{ t("generator.subTableName") }}
                        <el-tooltip :content="t('generator.subTableNameTip')" placement="top">
                          <el-icon><QuestionFilled /></el-icon>
                        </el-tooltip>
                      </template>
                      <el-input
                        v-model="info.sub_table_name"
                        :placeholder="t('generator.subTableNameMasterSubPlaceholder')"
                        clearable
                        @blur="emit('master-sub-blur')"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item prop="sub_table_fk_name">
                      <template #label>
                        {{ t("generator.subFkColumn") }}
                        <el-tooltip :content="t('generator.subFkColumnTip')" placement="top">
                          <el-icon><QuestionFilled /></el-icon>
                        </el-tooltip>
                      </template>
                      <el-input
                        v-model="info.sub_table_fk_name"
                        :placeholder="t('generator.subFkColumnPlaceholder')"
                        clearable
                        @blur="emit('master-sub-blur')"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-alert
                  v-if="info.master_sub_hint"
                  class="mt-1"
                  type="warning"
                  :closable="false"
                  show-icon
                  :title="info.master_sub_hint"
                />
                <el-alert
                  v-else-if="info.sub && info.sub_table_name && info.sub_table_fk_name"
                  class="mt-1"
                  type="success"
                  :closable="false"
                  show-icon
                  :title="t('generator.masterSubLoaded')"
                />
              </el-card>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </el-form>
</template>

<script setup lang="ts">
import { computed, inject, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance, FormRules } from "element-plus";
import { QuestionFilled } from "@element-plus/icons-vue";
import type { GenTableSchema } from "@/api/module_generator/gencode";
import { GENCODE_BASIC_FORM_KEY } from "../gencodeInjectionKeys";

defineOptions({ name: "GenBasicStep" });

const { t } = useI18n();

const props = defineProps<{
  info: GenTableSchema;
  rules: FormRules;
  menuOptions: OptionType[];
}>();

function findOptionByValue(options: OptionType[], value: number | string): any | null {
  for (const opt of options) {
    if (String(opt.value) === String(value)) return opt as any;
    if (opt.children?.length) {
      const hit = findOptionByValue(opt.children, value);
      if (hit) return hit;
    }
  }
  return null;
}

function inferPackageNameFromParentMenu(): string | null {
  const pid = props.info.parent_menu_id;
  if (pid == null) return null;
  const node = findOptionByValue(props.menuOptions || [], pid);
  const routePath = (node?.route_path ?? "").toString().trim();
  if (!routePath) return null;
  const seg = routePath.replace(/^\/+/, "").split("/", 1)[0]?.trim();
  if (!seg) return null;
  return seg.startsWith("module_") ? seg : `module_${seg}`;
}

const effectivePackageName = computed(() => {
  return inferPackageNameFromParentMenu() || (props.info.package_name || "").trim();
});

const permissionPreview = computed(() => {
  const pkg = effectivePackageName.value;
  const mod = (props.info.module_name || "").trim();
  if (!pkg || !mod) return t("generator.permissionPlaceholder");
  // 与后端 permission_prefix + 模板一致；第三段为操作类型，示例用 query
  return `${pkg}:${mod}:query`;
});

const backendModuleDirPreview = computed(() => {
  const pkg = effectivePackageName.value;
  const mod = (props.info.module_name || "").trim();
  if (!pkg || !mod) return "backend/app/plugin/<module_xxx>/<module>/";
  return `backend/app/plugin/${pkg}/${mod}/`;
});

const frontendViewDirPreview = computed(() => {
  const pkg = effectivePackageName.value;
  const mod = (props.info.module_name || "").trim();
  if (!pkg || !mod) return "frontend/src/views/<module_xxx>/<module>/";
  return `frontend/src/views/${pkg}/${mod}/`;
});

const frontendApiFilePreview = computed(() => {
  const pkg = effectivePackageName.value;
  const mod = (props.info.module_name || "").trim();
  if (!pkg || !mod) return "frontend/src/api/<module_xxx>/<module>.ts";
  return `frontend/src/api/${pkg}/${mod}.ts`;
});

const emit = defineEmits<{
  "clear-master-sub": [];
  "master-sub-blur": [];
}>();

const formRef = ref<FormInstance>();
const injected = inject(GENCODE_BASIC_FORM_KEY, undefined);

/** 表名 → 合法目录片段（小写、下划线），用于无模块名时推导包名 */
function slugFromTableName(table: string): string {
  let s = table.trim().toLowerCase();
  if (!s) return "";
  if (s.startsWith("gen_")) s = s.slice(4);
  else if (s.startsWith("tb_")) s = s.slice(3);
  s = s
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  return s || "table";
}

watch(
  () => [props.info.parent_menu_id, props.info.module_name, props.info.table_name] as const,
  () => {
    if (props.info.parent_menu_id != null) return;
    const current = (props.info.package_name || "").trim();
    if (current && current !== "gencode" && current !== "module_gencode") return;
    const mod = (props.info.module_name || "").trim();
    const tn = (props.info.table_name || "").trim();
    const slug = tn ? slugFromTableName(tn) : "";
    const next = mod
      ? mod.startsWith("module_")
        ? mod
        : `module_${mod}`
      : slug
        ? `module_${slug}`
        : "";
    if (next) props.info.package_name = next;
  },
  { immediate: true }
);

watch(
  formRef,
  (v) => {
    if (injected) injected.value = v;
  },
  { immediate: true }
);

onUnmounted(() => {
  if (injected) injected.value = undefined;
});
</script>

<style scoped lang="scss">
.gen-basic-step {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
}

.gen-basic-step :deep(.el-col) {
  min-width: 0;
}

.gen-basic-step :deep(.el-form-item__content) {
  min-width: 0;
}

.gen-basic-step :deep(.el-input-group) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
}

.gen-package-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.gen-package-row__input {
  flex: 1;
  min-width: 0;
}

.master-sub-card {
  border: 1px solid var(--el-border-color-lighter);
}

.master-sub-card :deep(.el-card__header) {
  padding: 8px 10px;
}

.master-sub-card :deep(.el-card__body) {
  padding: 10px;
}

.gen-form-card {
  overflow-x: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.gen-form-card :deep(.el-card__body) {
  overflow-x: hidden;
}

.gen-form-card__header {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
}

.gen-form-card__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.gen-echo-card {
  border: 1px solid var(--el-border-color-lighter);
}

.gen-echo-card__title {
  padding: 6px 8px;
  font-size: 11px;
  font-weight: 600;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.gen-echo-card :deep(.el-card__body) {
  padding: 6px 8px;
}

.gen-echo-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  padding: 6px 8px;
}

.gen-echo-item {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.gen-echo-item__k {
  flex: 0 0 auto;
  margin-bottom: 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.gen-echo-item__k--with-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.gen-echo-item__tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  cursor: help;
}

.gen-echo-item__v {
  display: block;
  flex: 1;
  min-width: 0;
  padding: 1px 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  white-space: nowrap;
  background: var(--el-fill-color);
  border-radius: 3px;
}

.gen-echo-warn {
  padding: 0 8px 6px;
  font-size: 11px;
  color: var(--el-color-warning);
}
</style>
