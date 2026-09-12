<template>
  <el-drawer v-model="visible" title="数据清洗" size="680px">
    <el-tabs v-model="tab">
      <el-tab-pane label="健康检查" name="check">
        <el-descriptions v-if="check" :column="2" border size="small">
          <el-descriptions-item label="图片总数">
            {{ check.summary?.image_count ?? check.image_count ?? "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="已标注">
            {{ check.summary?.annotated_count ?? check.annotated_count ?? "—" }}
          </el-descriptions-item>
        </el-descriptions>
        <el-table :data="check?.issues || []" border size="small" class="mt">
          <el-table-column label="类型" prop="type" width="150" />
          <el-table-column label="级别" prop="severity" width="90" />
          <el-table-column label="说明" prop="message" min-width="200" />
        </el-table>
        <el-empty v-if="check && !(check.issues || []).length" description="未发现问题" />
      </el-tab-pane>

      <el-tab-pane label="重复图片" name="duplicates">
        <pre class="json">{{ pretty(duplicates) }}</pre>
      </el-tab-pane>

      <el-tab-pane label="异常标注" name="anomalies">
        <pre class="json">{{ pretty(anomalies) }}</pre>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

const visible = ref(false);
const tab = ref("check");
const check = ref<any>(null);
const duplicates = ref<any>(null);
const anomalies = ref<any>(null);

function pretty(v: any): string {
  return v ? JSON.stringify(v, null, 2) : "无数据";
}

async function open(datasetId: number) {
  visible.value = true;
  tab.value = "check";
  check.value = duplicates.value = anomalies.value = null;
  const [c, d, a] = await Promise.allSettled([
    AnnotationAPI.cleanCheck(datasetId),
    AnnotationAPI.cleanDuplicates(datasetId),
    AnnotationAPI.cleanAnomalies(datasetId),
  ]);
  if (c.status === "fulfilled") check.value = c.value.data?.data;
  if (d.status === "fulfilled") duplicates.value = d.value.data?.data;
  if (a.status === "fulfilled") anomalies.value = a.value.data?.data;
}

defineExpose({ open });
</script>

<style scoped>
.mt {
  margin-top: 12px;
}

.json {
  max-height: 520px;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
</style>
