<!--
  关系类型视图（对齐 Palantir Ontology Manager 的 Link type 视图）
  子页：Overview（元数据 + Configuration：Join method 三选一）/ Security / Datasources / Usage
  关系类型是「并列于对象类型的一等资源」，但恰好关联两个对象类型，两侧各有独立语义。
-->
<template>
  <div v-if="link" class="ont-link">
    <!-- 资源头部：两端对象类型 + 基数描述 -->
    <div class="ont-link__head">
      <div class="ont-link__title">
        <el-icon class="ont-link__ico"><component :is="iconName(srcObj?.icon)" /></el-icon>
        <span class="ont-link__name">{{ srcObj?.name || link.source_object }}</span>
        <el-icon class="ont-link__arrow"><Switch /></el-icon>
        <el-icon class="ont-link__ico"><component :is="iconName(tgtObj?.icon)" /></el-icon>
        <span class="ont-link__name">{{ tgtObj?.name || link.target_object }}</span>
        <el-tag size="small" type="info" effect="plain">{{ cardLabel }}</el-tag>
      </div>
      <div class="ont-link__ops">
        <el-button size="small" :icon="Edit" @click="emit('edit')">
          {{ i18nT("ai_ontology.editRelation") }}
        </el-button>
      </div>
    </div>

    <!-- ============ Overview ============ -->
    <template v-if="page === 'overview'">
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.metadata") }}</span>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="i18nT('ai_ontology.relationName')">
            {{ link.name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.cardinality')">
            <el-tag size="small" effect="plain">{{ cardLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.apiName')">
            <span class="ont-mono">{{ link.api_name || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.status')">
            <el-tag size="small" effect="plain" :type="statusTagType(link.status)">
              {{ labelOf(ONT_STATUS, link.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.sourceObjectType')">
            {{ srcObj?.name || link.source_object }}
            <span class="ont-mono">（{{ link.source_object }}）</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.visibility')">
            <el-tag size="small" effect="plain" :type="visibilityTagType(link.visibility)">
              {{ labelOf(ONT_VISIBILITY, link.visibility) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.sourceDisplayName')">
            {{ link.source_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.sourcePluralName')">
            {{ link.source_plural_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.targetObjectType2')">
            {{ tgtObj?.name || link.target_object }}
            <span class="ont-mono">（{{ link.target_object }}）</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.targetDisplayName')">
            {{ link.target_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.targetPluralName')">
            {{ link.target_plural_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.owningOntology')">
            {{ domainLabel() }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.description')" :span="2">
            <span :class="{ 'ont-none': !link.description }">
              {{ link.description || i18nT("ai_ontology.notFilled") }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="info"
          :closable="false"
          class="ont-note"
          :title="i18nT('ai_ontology.relationTypeInfoAlert')"
        />
      </section>

      <!-- Configuration：Join method 三选一 + 端点属性 -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.config") }}</span>
        </div>
        <div class="ont-field">
          <div class="ont-field__label">{{ i18nT("ai_ontology.joinMode") }}</div>
          <el-radio-group v-model="form.join_method" @change="onJoinChange">
            <el-radio-button value="foreign_key">
              {{ i18nT("ai_ontology.joinForeignKey") }}
            </el-radio-button>
            <el-radio-button value="dataset">
              {{ i18nT("ai_ontology.joinDataset") }}
            </el-radio-button>
            <el-radio-button value="object_type">
              {{ i18nT("ai_ontology.joinObjectType") }}
            </el-radio-button>
          </el-radio-group>
        </div>
        <div class="ont-hint">{{ joinHint }}</div>

        <!-- 端点与字段 -->
        <div class="ont-endpoints">
          <div class="ont-endpoint">
            <div class="ont-endpoint__head">
              <el-icon><component :is="iconName(srcObj?.icon)" /></el-icon>
              <span>{{ srcObj?.name || link.source_object }}</span>
            </div>
            <el-select
              v-model="form.source_field"
              size="small"
              :placeholder="i18nT('ai_ontology.selectProperty')"
              class="ont-endpoint__sel"
            >
              <el-option
                v-for="p in srcProps"
                :key="p.code"
                :label="`${p.name}（${p.code}）`"
                :value="p.code"
              />
            </el-select>
          </div>
          <div class="ont-endpoint__link">
            <el-icon><Right /></el-icon>
          </div>
          <div class="ont-endpoint">
            <div class="ont-endpoint__head">
              <el-icon><component :is="iconName(tgtObj?.icon)" /></el-icon>
              <span>{{ tgtObj?.name || link.target_object }}</span>
              <el-tag v-if="tgtObj?.key_prop" size="small" type="warning" effect="plain">
                {{ i18nT("ai_ontology.primaryKeyColon", { name: tgtObj.key_prop }) }}
              </el-tag>
            </div>
            <el-select
              v-model="form.target_field"
              size="small"
              :placeholder="i18nT('ai_ontology.selectProperty')"
              class="ont-endpoint__sel"
            >
              <el-option
                v-for="p in tgtProps"
                :key="p.code"
                :label="`${p.name}（${p.code}）`"
                :value="p.code"
              />
            </el-select>
          </div>
        </div>

        <!-- 连接示意 -->
        <div class="ont-joinviz">
          <div class="ont-joinviz__side">
            <span v-for="i in sideCount" :key="i" class="ont-joinviz__dot" />
          </div>
          <div class="ont-joinviz__lines">
            <span v-for="i in sideCount" :key="i" class="ont-joinviz__line" />
          </div>
          <div class="ont-joinviz__side">
            <span class="ont-joinviz__dot" />
          </div>
          <div class="ont-joinviz__tip">
            {{ form.source_field || i18nT("ai_ontology.sourceProperty") }} →
            {{ form.target_field || i18nT("ai_ontology.targetProperty") }}
          </div>
        </div>

        <div class="ont-sec__head ont-sec__head--mt">
          <el-button type="primary" size="small" :loading="saving" @click="save">
            {{ i18nT("ai_ontology.saveConfig") }}
          </el-button>
          <span class="ont-hint">
            {{
              i18nT(
                "ai_ontology.relationsComeFromRealDatabaseForeignKeysAdjustJoinModeAndFieldsHere"
              )
            }}
          </span>
        </div>
      </section>

      <!-- 关系自身的属性（官方 Link type 也可带属性） -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.relationProperties") }}</span>
          <el-tag size="small" type="info" effect="plain">0</el-tag>
        </div>
        <el-empty
          :image-size="50"
          :description="i18nT('ai_ontology.relationOwnPropsNotSupported')"
        />
      </section>
    </template>

    <!-- ============ Security ============ -->
    <section v-else-if="page === 'security'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.security") }}</span>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.relationSecurityAlert')"
      />
      <el-table :data="[...srcProps, ...tgtProps]" size="small" border max-height="380" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noProperties')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.property')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="object_code"
          :label="i18nT('ai_ontology.owningObjectType')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.sensitive')" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive" size="small" type="danger" effect="plain">
              {{ i18nT("ai_ontology.yes") }}
            </el-tag>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.no") }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.visibleRoles')" min-width="200">
          <template #default="{ row }">
            <template v-if="row.roles?.length">
              <el-tag
                v-for="r in row.roles"
                :key="r"
                size="small"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ r }}
              </el-tag>
            </template>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.public") }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============ Datasources ============ -->
    <section v-else-if="page === 'datasources'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.dataSource") }}</span>
      </div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item :label="i18nT('ai_ontology.joinMode')">
          {{ joinLabel }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.sourceField')">
          <span v-if="link.source_field" class="ont-mono">
            {{ link.source_object }}.{{ link.source_field }}
          </span>
          <span v-else class="ont-none">{{ i18nT("ai_ontology.notSet") }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.targetField')">
          <span v-if="link.target_field" class="ont-mono">
            {{ link.target_object }}.{{ link.target_field }}
          </span>
          <span v-else class="ont-none">{{ i18nT("ai_ontology.notSet") }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.datasourceAlert')"
      />
    </section>

    <!-- ============ Usage ============ -->
    <section v-else class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.usage") }}</span>
      </div>
      <el-empty :image-size="60" :description="i18nT('ai_ontology.usageStatsNotConnectedYet')" />
    </section>
  </div>
  <el-empty v-else :description="i18nT('ai_ontology.relationTypeNotFound')" />
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Right, Switch } from "@element-plus/icons-vue";
import { getOntObjectFull } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";
import {
  ONT_STATUS,
  ONT_VISIBILITY,
  labelOf,
  statusTagType,
  visibilityTagType,
} from "../constants";

const { t: i18nT } = useI18n();

const props = defineProps<{ id: number; page: string }>();
const emit = defineEmits<{
  (e: "edit"): void;
  (e: "refresh"): void;
}>();

const { links, domains, objectByCode, stage } = useOntologyData();

const link = computed(() => links.value.find((l: any) => l.id === props.id) || null);
const srcObj = computed(() => (link.value ? objectByCode(link.value.source_object) : null));
const tgtObj = computed(() => (link.value ? objectByCode(link.value.target_object) : null));

const CARD_LABEL: Record<string, string> = {
  one_to_one: i18nT("ai_ontology.oneToOneRelationType"),
  one_to_many: i18nT("ai_ontology.oneToManyRelationType"),
  many_to_one: i18nT("ai_ontology.manyToOneRelationType"),
  many_to_many: i18nT("ai_ontology.manyToManyRelationType"),
};
const cardLabel = computed(() => CARD_LABEL[link.value?.card] || link.value?.card || "—");

const JOIN_LABEL: Record<string, string> = {
  foreign_key: i18nT("ai_ontology.joinForeignKey"),
  dataset: i18nT("ai_ontology.joinDataset"),
  object_type: i18nT("ai_ontology.joinObjectType"),
};
const joinLabel = computed(() => JOIN_LABEL[form.join_method] || form.join_method);
const joinHint = computed(() => {
  if (form.join_method === "foreign_key") return i18nT("ai_ontology.foreignKeyJoinHint");
  if (form.join_method === "dataset")
    return i18nT(
      "ai_ontology.useAJoinTableDatasetForRelationsRequiredForManyToManyTheOnlyEditableWritebackWay"
    );
  return i18nT(
    "ai_ontology.useAnIntermediateObjectTypeForRelationsWithExtraMetadataAndRestrictedViews"
  );
});

/** 所属本体：显示**中文名**而不是原始 code（与对象类型详情的 `domainName()` 同口径）。
 *  原先这里直接回显 `domain_code`（如 `data_table`），同一概念在另一处却显示中文名。 */
function domainName(code?: string): string {
  if (!code) return i18nT("ai_ontology.uncategorized");
  const hit = (domains.value || []).find((d: any) => d.code === code);
  return hit?.name || code;
}

function domainLabel() {
  const a = srcObj.value?.domain_code;
  const b = tgtObj.value?.domain_code;
  if (!a && !b) return i18nT("ai_ontology.uncategorized");
  return a && a === b ? domainName(a) : `${domainName(a)} / ${domainName(b)}`;
}
function iconName(raw?: string) {
  const s = (raw || "Box").trim();
  return s.startsWith("el-icon-") ? s.slice("el-icon-".length) : s;
}

/* ---------- 配置表单 ---------- */
const form = reactive<any>({
  id: 0,
  source_object: "",
  target_object: "",
  name: "",
  card: "",
  join_method: "foreign_key",
  source_field: "",
  target_field: "",
  description: "",
});
const saving = ref(false);

watch(
  link,
  (l: any) => {
    if (l) Object.assign(form, { ...l });
  },
  { immediate: true }
);

// 端点属性（用于字段选择器）
const srcProps = ref<any[]>([]);
const tgtProps = ref<any[]>([]);
async function loadProps() {
  if (!link.value) return;
  const [a, b] = await Promise.all([
    getOntObjectFull(link.value.source_object),
    getOntObjectFull(link.value.target_object),
  ]);
  srcProps.value = (a.data?.data?.properties || []).map((p: any) => ({
    ...p,
    object_code: link.value.source_object,
  }));
  tgtProps.value = (b.data?.data?.properties || []).map((p: any) => ({
    ...p,
    object_code: link.value.target_object,
  }));
}
watch(() => props.id, loadProps, { immediate: true });

/** 连接示意图的左侧行数：多对一显示多行汇聚到一行 */
const sideCount = computed(() => (link.value?.card === "many_to_one" ? 3 : 1));

function onJoinChange() {
  // object_type / dataset 不再用简单字段外键，清空以示意
  if (form.join_method !== "foreign_key") {
    // 保留已有值，仅提示；不擅自清空用户数据
  }
}

async function save() {
  if (!link.value) return;
  // 官方约束：多对多必须由连接表数据集支撑
  if (form.card === "many_to_many" && form.join_method !== "dataset") {
    return ElMessage.warning(i18nT("ai_ontology.manyToManyJoinDatasetWarning"));
  }
  saving.value = true;
  try {
    await stage("link", "update", { ...form, id: link.value.id });
    ElMessage.success(i18nT("ai_ontology.stagedClickSaveAtTopRightToApply"));
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.stagingFailed"));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped lang="scss">
.ont-link__head {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ont-link__title {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}
.ont-link__ico {
  font-size: var(--el-font-size-extra-large);
  color: var(--el-color-primary);
}
.ont-link__name {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-link__arrow {
  font-size: var(--el-font-size-large);
  color: var(--el-text-color-secondary);
}
.ont-link__ops {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}
.ont-sec {
  padding: 12px;
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.ont-sec__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-sec__head--mt {
  margin-top: 12px;
}
.ont-sec__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-field {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 6px;
}
.ont-field__label {
  width: 80px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-note {
  margin-top: 8px;
}
.ont-endpoints {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}
.ont-endpoint {
  flex: 1 1 0;
  min-width: 0;
  padding: 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.ont-endpoint__head {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  font-size: var(--el-font-size-base);
  font-weight: 600;
}
.ont-endpoint__sel {
  width: 100%;
}
.ont-endpoint__link {
  flex-shrink: 0;
  font-size: var(--el-font-size-large);
  color: var(--el-text-color-secondary);
}
.ont-joinviz {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.ont-joinviz__side {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ont-joinviz__dot {
  width: 8px;
  height: 8px;
  background: var(--el-color-primary);
  border-radius: 50%;
}
.ont-joinviz__lines {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 90px;
}
.ont-joinviz__line {
  height: 1px;
  background: var(--el-border-color);
}
.ont-joinviz__tip {
  margin-left: 12px;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-mono {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-extra-small);
}
.ont-tag-gap {
  margin-right: 4px;
}
.ont-none {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-placeholder);
}
</style>
