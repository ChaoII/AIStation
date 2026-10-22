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
        <el-button size="small" :icon="Edit" @click="emit('edit')">编辑关系</el-button>
      </div>
    </div>

    <!-- ============ Overview ============ -->
    <template v-if="page === 'overview'">
      <section class="ont-sec">
        <div class="ont-sec__head"><span class="ont-sec__title">元数据</span></div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="关系名">{{ link.name || "—" }}</el-descriptions-item>
          <el-descriptions-item label="基数">
            <el-tag size="small" effect="plain">{{ cardLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="API 名">
            <span class="ont-mono">{{ link.api_name || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" effect="plain" :type="statusTagType(link.status)">
              {{ labelOf(ONT_STATUS, link.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="源对象类型">
            {{ srcObj?.name || link.source_object }}
            <span class="ont-mono">（{{ link.source_object }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="可见性">
            <el-tag size="small" effect="plain" :type="visibilityTagType(link.visibility)">
              {{ labelOf(ONT_VISIBILITY, link.visibility) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="源侧显示名">
            {{ link.source_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="源侧复数名">
            {{ link.source_plural_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="目标对象类型">
            {{ tgtObj?.name || link.target_object }}
            <span class="ont-mono">（{{ link.target_object }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="目标侧显示名">
            {{ link.target_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="目标侧复数名">
            {{ link.target_plural_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="所属本体">{{ domainLabel() }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            <span :class="{ 'ont-none': !link.description }">
              {{ link.description || "未填写" }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="info"
          :closable="false"
          class="ont-note"
          title="关系类型有方向：两侧各有独立的显示名、复数名与可见性（对齐官方）。ID / RID 由平台生成，暂未落地。"
        />
      </section>

      <!-- Configuration：Join method 三选一 + 端点属性 -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">配置</span>
        </div>
        <div class="ont-field">
          <div class="ont-field__label">连接方式</div>
          <el-radio-group v-model="form.join_method" @change="onJoinChange">
            <el-radio-button value="foreign_key">外键 Foreign key</el-radio-button>
            <el-radio-button value="dataset">连接表 Dataset</el-radio-button>
            <el-radio-button value="object_type">中间对象 Object type</el-radio-button>
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
              placeholder="选择属性"
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
                主键: {{ tgtObj.key_prop }}
              </el-tag>
            </div>
            <el-select
              v-model="form.target_field"
              size="small"
              placeholder="选择属性"
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
            {{ form.source_field || "源属性" }} → {{ form.target_field || "目标属性" }}
          </div>
        </div>

        <div class="ont-sec__head ont-sec__head--mt">
          <el-button type="primary" size="small" :loading="saving" @click="save">
            保存配置
          </el-button>
          <span class="ont-hint">关系来自数据库真实外键；此处可调整连接方式与关联字段</span>
        </div>
      </section>

      <!-- 关系自身的属性（官方 Link type 也可带属性） -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">关系属性</span>
          <el-tag size="small" type="info" effect="plain">0</el-tag>
        </div>
        <el-empty :image-size="50" description="关系类型自身的属性（object-backed link）暂未支持" />
      </section>
    </template>

    <!-- ============ Security ============ -->
    <section v-else-if="page === 'security'" class="ont-sec">
      <div class="ont-sec__head"><span class="ont-sec__title">安全</span></div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="关系权限随两端对象类型的 backing datasource 权限。字段级限制见各对象类型的「安全」子页。"
      />
      <el-table :data="[...srcProps, ...tgtProps]" size="small" border max-height="380" stripe>
        <template #empty><el-empty :image-size="50" description="暂无属性" /></template>
        <el-table-column prop="name" label="属性" min-width="150" show-overflow-tooltip />
        <el-table-column
          prop="object_code"
          label="所属对象类型"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column label="敏感" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive" size="small" type="danger" effect="plain">是</el-tag>
            <span v-else class="ont-none">否</span>
          </template>
        </el-table-column>
        <el-table-column label="可见角色" min-width="200">
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
            <span v-else class="ont-none">公开</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============ Datasources ============ -->
    <section v-else-if="page === 'datasources'" class="ont-sec">
      <div class="ont-sec__head"><span class="ont-sec__title">数据源</span></div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="连接方式">{{ joinLabel }}</el-descriptions-item>
        <el-descriptions-item label="源字段">
          <span v-if="link.source_field" class="ont-mono">
            {{ link.source_object }}.{{ link.source_field }}
          </span>
          <span v-else class="ont-none">未设置</span>
        </el-descriptions-item>
        <el-descriptions-item label="目标字段">
          <span v-if="link.target_field" class="ont-mono">
            {{ link.target_object }}.{{ link.target_field }}
          </span>
          <span v-else class="ont-none">未设置</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="many-to-many 必须由连接表数据集支撑；object-backed link 需要中间对象类型。相关配置当前版本尚未支持齐。"
      />
    </section>

    <!-- ============ Usage ============ -->
    <section v-else class="ont-sec">
      <div class="ont-sec__head"><span class="ont-sec__title">使用量</span></div>
      <el-empty :image-size="60" description="用量统计暂未接入" />
    </section>
  </div>
  <el-empty v-else description="未找到该关系类型" />
</template>

<script setup lang="ts">
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
  one_to_one: "一对一关系类型",
  one_to_many: "一对多关系类型",
  many_to_one: "多对一关系类型",
  many_to_many: "多对多关系类型",
};
const cardLabel = computed(() => CARD_LABEL[link.value?.card] || link.value?.card || "—");

const JOIN_LABEL: Record<string, string> = {
  foreign_key: "外键（Foreign key）",
  dataset: "连接表（Dataset）",
  object_type: "中间对象（Object type）",
};
const joinLabel = computed(() => JOIN_LABEL[form.join_method] || form.join_method);
const joinHint = computed(() => {
  if (form.join_method === "foreign_key")
    return "一侧持有指向另一侧主键的外键属性。适用于一对多 / 多对一。";
  if (form.join_method === "dataset")
    return "用一张连接表数据集承载关系。多对多必须使用此方式，也是唯一支持用户编辑与回写的方式。";
  return "用中间对象类型承载关系，可附加额外元数据与受限视图。";
});

/** 所属本体：显示**中文名**而不是原始 code（与对象类型详情的 `domainName()` 同口径）。
 *  原先这里直接回显 `domain_code`（如 `data_table`），同一概念在另一处却显示中文名。 */
function domainName(code?: string): string {
  if (!code) return "未分组";
  const hit = (domains.value || []).find((d: any) => d.code === code);
  return hit?.name || code;
}

function domainLabel() {
  const a = srcObj.value?.domain_code;
  const b = tgtObj.value?.domain_code;
  if (!a && !b) return "未分组";
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
    return ElMessage.warning("多对多关系必须使用「连接表 Dataset」连接方式");
  }
  saving.value = true;
  try {
    await stage("link", "update", { ...form, id: link.value.id });
    ElMessage.success("已暂存（点右上角「保存」才生效）");
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "暂存失败");
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
