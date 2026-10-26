<!--
  对象类型 → 清理建议 子页
  展示针对本对象类型的清理建议，可一键「标记弃用」
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">{{ i18nT("ai_ontology.cleanupSuggestions") }}</span>
      <el-tag size="small" type="info" effect="plain">{{ list.length }}</el-tag>
      <el-button
        class="ont-sec__op"
        size="small"
        type="primary"
        link
        :icon="RefreshLeft"
        :loading="loading"
        @click="load"
      >
        {{ i18nT("ai_ontology.refresh") }}
      </el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      class="ont-obj__note"
      :title="i18nT('ai_ontology.cleanupIntro')"
    />
    <div v-if="loading" class="ont-loading">{{ i18nT("ai_ontology.loadingCleanup") }}</div>
    <el-empty
      v-else-if="!list.length"
      :image-size="50"
      :description="i18nT('ai_ontology.noObjectsToClean')"
    />
    <div v-else>
      <div v-for="row in list" :key="row.object_code + row.msg" class="ont-clean__row">
        <div class="ont-clean__info">
          <div class="ont-clean__name">
            {{ row.object_name }}
            <el-tag size="small" effect="plain" class="ont-tag-gap">{{ row.object_code }}</el-tag>
          </div>
          <div class="ont-clean__msg">
            {{ row.msg || row.reason || i18nT("ai_ontology.cleanupSuggestClean") }}
          </div>
        </div>
        <el-button
          size="small"
          type="warning"
          :loading="deprecating === row.object_code"
          @click="deprecate(row)"
        >
          {{ i18nT("ai_ontology.markDeprecated") }}
        </el-button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { RefreshLeft } from "@element-plus/icons-vue";
import { getOntCleanup } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string }>();

const { objects, stage, reloadAll } = useOntologyData();

const all = ref<any[]>([]);
const loading = ref(false);
const deprecating = ref("");

const list = computed(() => all.value.filter((c: any) => c.object_code === props.code));

async function load() {
  loading.value = true;
  try {
    const r = await getOntCleanup();
    all.value = r.data?.data || [];
  } catch {
    all.value = [];
  } finally {
    loading.value = false;
  }
}

async function deprecate(row: any) {
  const obj = objects.value.find((o: any) => o.code === row.object_code);
  if (!obj) return ElMessage.error(i18nT("ai_ontology.objectTypeDoesNotExist"));
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deprecateConfirm", { name: row.object_name }),
    i18nT("ai_ontology.markDeprecated"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.markDeprecated"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  deprecating.value = row.object_code;
  try {
    await stage(
      "object",
      "update",
      { ...obj, status: "deprecated" },
      i18nT("ai_ontology.deprecationStaged")
    );
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.markFailed"));
  } finally {
    deprecating.value = "";
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.ont-obj__note {
  margin-bottom: 8px;
}
.ont-loading {
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-base);
}
.ont-clean__row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ont-clean__info {
  min-width: 0;
}
.ont-clean__name {
  font-size: var(--el-font-size-base);
  font-weight: 500;
}
.ont-clean__msg {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-tag-gap {
  margin-left: 6px;
}
</style>
