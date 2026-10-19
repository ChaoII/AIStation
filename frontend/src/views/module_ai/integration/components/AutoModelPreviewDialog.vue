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
    width="760px"
    append-to-body
    @open="runPreview"
    @closed="reset"
  >
    <el-alert v-if="loading" type="info" :closable="false" show-icon>
      正在调用大模型分析「{{ datasource }}」的前 {{ maxObjects }} 个对象，通常需要十几秒……
    </el-alert>

    <template v-else>
      <el-alert v-if="!items.length" type="warning" :closable="false" show-icon>
        {{ emptyHint }}
      </el-alert>

      <template v-else>
        <div class="am-head">
          <span>共 {{ items.length }} 条候选，已选 {{ selected.length }} 条</span>
          <el-button link type="primary" size="small" @click="toggleAll">全选 / 全不选</el-button>
        </div>

        <el-table
          ref="tableRef"
          :data="items"
          height="340"
          size="small"
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="42" />
          <template v-if="scope === 'metrics'">
            <el-table-column prop="name" label="指标名" min-width="140" show-overflow-tooltip />
            <el-table-column prop="key" label="标识" min-width="120" show-overflow-tooltip />
            <el-table-column
              prop="object_code"
              label="对象"
              min-width="110"
              show-overflow-tooltip
            />
            <el-table-column
              prop="property_code"
              label="属性"
              min-width="110"
              show-overflow-tooltip
            />
            <el-table-column prop="agg_fn" label="聚合" width="80" />
          </template>
          <template v-else>
            <el-table-column
              prop="object_name"
              label="对象"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              prop="object_code"
              label="标识"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              prop="description"
              label="描述"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column label="字段数" width="80">
              <template #default="{ row }">{{ (row.fields || []).length }}</template>
            </el-table-column>
          </template>
        </el-table>
      </template>

      <!-- 拒绝原因：**有候选（部分被拒）或没有候选（全被拒）都要显示** ——
           否则用户只看到"没有候选"，不知道是数据源不通、还是口径跑不过。 -->
      <div v-if="reasons.length" class="am-reasons">
        <div class="am-reasons__title">未通过校验的候选（不会落库）</div>
        <div v-for="(r, i) in reasons" :key="i" class="am-reasons__item">{{ r }}</div>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="applying" :disabled="!selected.length" @click="apply">
        应用选中 {{ selected.length }} 条
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";

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

const tableRef = ref();
const loading = ref(false);
const applying = ref(false);
const items = ref<any[]>([]);
const selected = ref<any[]>([]);
const reasons = ref<string[]>([]);

const title = computed(() =>
  props.scope === "metrics" ? "自动生成绑定型指标（预览）" : "自动生成对象/属性标注（预览）"
);
const emptyHint = computed(() =>
  props.scope === "metrics"
    ? "该数据源这批对象没有可用的指标候选（可能是对象没有可聚合的数值属性，或大模型未给出可验证的指标）"
    : "该数据源这批对象没有可用的标注候选"
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
    ElMessage.error(e?.message || "分析失败");
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
      ElMessage.warning(`已落库 ${saved} 条，${failed.length} 条失败：${failed[0]}`);
    } else {
      ElMessage.success(`已落库 ${saved} 条`);
    }
    emit("applied", data);
    visible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.message || "应用失败");
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
