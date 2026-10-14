<!--
  对象类型 → 版本历史 子页
  展示本对象类型的已发布版本，支持恢复到历史版本（改动进入待保存列表）
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">版本历史</span>
      <el-tag size="small" type="info" effect="plain">{{ list.length }}</el-tag>
      <el-button
        class="ont-sec__op"
        size="small"
        type="primary"
        link
        :icon="RefreshLeft"
        @click="emit('refresh')"
      >
        刷新
      </el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      class="ont-obj__note"
      title="版本在「保存」待保存改动时生成。恢复历史版本会把该对象类型的属性/关系/动作/函数定义覆盖为指定版本，改动先进入待保存列表，点「保存」后才生效。"
    />
    <el-table :data="list" size="small" border max-height="460" class="ont-ver__table">
      <template #empty><el-empty :image-size="50" description="暂无版本记录" /></template>
      <el-table-column label="版本" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="primary" effect="plain">v{{ row.version }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_time" label="发布时间" min-width="160" show-overflow-tooltip />
      <el-table-column label="发布人" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ row.created_by || row.author || "—" }}</template>
      </el-table-column>
      <el-table-column label="说明" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.msg || row.note || row.description || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            :loading="restoringId === row.id"
            @click="restore(row)"
          >
            恢复
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { RefreshLeft } from "@element-plus/icons-vue";
import { stageOntRestore } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const props = defineProps<{ code: string }>();
const emit = defineEmits<{ (e: "refresh"): void }>();

const { versions, objectLabel, reloadAll, refreshWip } = useOntologyData();

const list = computed(() => versions.value.filter((v: any) => v.object_code === props.code));

const restoringId = ref<number | null>(null);
async function restore(v: any) {
  await ElMessageBox.confirm(
    `将把「${objectLabel(v.object_code)}」的定义恢复到版本 v${v.version}（覆盖当前属性/关系/动作/函数定义）。` +
      "改动会先进入待保存列表，点「保存」后才生效。确认恢复？",
    "恢复历史版本",
    { type: "warning", confirmButtonText: "恢复", cancelButtonText: "取消" }
  );
  restoringId.value = v.id;
  try {
    const r = await stageOntRestore(v.id);
    await reloadAll();
    await refreshWip();
    ElMessage.success(r.data?.msg || "已暂存恢复");
  } catch (e: any) {
    ElMessage.error(e?.msg || "恢复失败");
  } finally {
    restoringId.value = null;
  }
}
</script>

<style scoped lang="scss">
.ont-ver__table {
  margin-top: 8px;
}
.ont-obj__note {
  margin-bottom: 8px;
}
</style>
