<!--
  大模型自动建模「预览 → 勾选 → 应用」对话框。

  为什么要有它：原先集成页的建模是「确认 → 直接落库」，用户看不到大模型要写什么、
  也没法剔除个别不满意的候选；一旦落库就要回本体里逐条清理。
  这里改成两段式：**预览**只生成不落库（后端 `dry=True`），用户勾选后**精确落库**那批，
  应用阶段不重跑大模型（重跑结果会漂移，用户勾的就不是落库的那批）。
-->
<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="900px"
    append-to-body
    @open="runPreview"
    @closed="reset"
  >
    <el-alert v-if="loading" type="info" :closable="false" show-icon>
      {{ t("ai_workflow.ig_modelingLoading", { datasource, maxObjects: props.maxObjects }) }}
    </el-alert>

    <template v-else>
      <el-alert v-if="!items.length" type="warning" :closable="false" show-icon>
        {{ emptyHint }}
      </el-alert>

      <template v-else>
        <div class="am-head">
          <span>
            {{
              t("ai_workflow.ig_candidateCount", {
                total: items.length,
                selected: selected.length,
              })
            }}
          </span>
          <el-button link type="primary" size="small" @click="toggleAll">
            {{ t("ai_workflow.ig_selectAllNone") }}
          </el-button>
        </div>

        <el-table
          ref="tableRef"
          :data="items"
          height="340"
          size="small"
          border
          stripe
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="42" />
          <template v-if="scope === 'metrics'">
            <el-table-column
              prop="name"
              :label="t('ai_workflow.ig_metricName')"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              prop="key"
              :label="t('ai_workflow.ig_identifier')"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              prop="object_code"
              :label="t('ai_workflow.ig_object')"
              min-width="110"
              show-overflow-tooltip
            />
            <el-table-column
              prop="property_code"
              :label="t('ai_workflow.ig_property')"
              min-width="110"
              show-overflow-tooltip
            />
            <el-table-column prop="agg_fn" :label="t('ai_workflow.ig_agg')" width="80" />
          </template>
          <template v-else>
            <el-table-column
              prop="object_name"
              :label="t('ai_workflow.ig_object')"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              prop="object_code"
              :label="t('ai_workflow.ig_identifier')"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              prop="description"
              :label="t('ai_workflow.ig_description')"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_workflow.ig_columnCount')" width="80">
              <template #default="{ row }">{{ (row.fields || []).length }}</template>
            </el-table-column>
          </template>
        </el-table>
      </template>

      <!-- 拒绝原因：**有候选（部分被拒）或没有候选（全被拒）都要显示** ——
           否则用户只看到"没有候选"，不知道是数据源不通、还是口径跑不过。 -->
      <div v-if="reasons.length" class="am-reasons">
        <div class="am-reasons__title">{{ t("ai_workflow.ig_invalidCandidates") }}</div>
        <div v-for="(r, i) in reasons" :key="i" class="am-reasons__item">{{ r }}</div>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
      <el-button type="primary" :loading="applying" :disabled="!selected.length" @click="apply">
        {{ t("ai_workflow.ig_applySelected", { count: selected.length }) }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";

import { autoModelApply, autoModelPreview } from "@/api/module_ai/ontology";

interface Props {
  /** 数据源代码，形如 `ds:4` */
  datasource: string;
  scope: "metrics" | "annotations";
  maxObjects: number;
}
const props = defineProps<Props>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ (e: "applied", result: any): void }>();
const { t } = useI18n();

const tableRef = ref();
const loading = ref(false);
const applying = ref(false);
const items = ref<any[]>([]);
const selected = ref<any[]>([]);
const reasons = ref<string[]>([]);

const title = computed(() =>
  props.scope === "metrics"
    ? t("ai_workflow.ig_autoModelTitleMetric")
    : t("ai_workflow.ig_autoModelTitleAnnotation")
);
const emptyHint = computed(() =>
  props.scope === "metrics"
    ? t("ai_workflow.ig_emptyHintMetric")
    : t("ai_workflow.ig_emptyHintAnnotation")
);

function onSelectionChange(rows: any[]) {
  selected.value = rows;
}

function toggleAll() {
  const all = selected.value.length === items.value.length;
  items.value.forEach((row) => tableRef.value?.toggleRowSelection(row, !all));
}

async function runPreview() {
  loading.value = true;
  items.value = [];
  selected.value = [];
  reasons.value = [];
  try {
    const res: any = await autoModelPreview({
      datasource: props.datasource,
      scope: props.scope,
      max_objects: props.maxObjects,
    });
    const data = res?.data ?? res;
    items.value = data?.items || [];
    reasons.value = data?.reasons || [];
    // 默认全选：预览的全部候选都是已通过校验的，用户只需剔掉不要的
    items.value.forEach((row) => tableRef.value?.toggleRowSelection(row, true));
  } catch (e: any) {
    ElMessage.error(e?.message || t("ai_workflow.ig_analysisFail"));
  } finally {
    loading.value = false;
  }
}

async function apply() {
  applying.value = true;
  try {
    const res: any = await autoModelApply({
      datasource: props.datasource,
      scope: props.scope,
      items: selected.value,
    });
    const data = res?.data ?? res;
    const saved = data?.saved ?? 0;
    const failed: string[] = data?.reasons || [];
    if (failed.length) {
      ElMessage.warning(
        t("ai_workflow.ig_applyMixed", { saved, failed: failed.length, first: failed[0] })
      );
    } else {
      ElMessage.success(t("ai_workflow.ig_applySuccess", { saved }));
    }
    emit("applied", data);
    visible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.message || t("ai_workflow.ig_applyFail"));
  } finally {
    applying.value = false;
  }
}

function reset() {
  items.value = [];
  selected.value = [];
  reasons.value = [];
}

// 数据源/范围在弹窗打开期间被改（父级切换）时，重新预览，避免「标题说指标、表格是标注」
watch(
  () => [props.datasource, props.scope, props.maxObjects],
  () => {
    if (visible.value) void runPreview();
  }
);
</script>

<style scoped>
.am-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.am-reasons {
  margin-top: 10px;
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
}
.am-reasons__title {
  margin-bottom: 4px;
}
.am-reasons__item {
  line-height: 1.6;
}
</style>
