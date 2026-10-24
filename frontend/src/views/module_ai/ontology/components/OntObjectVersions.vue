<!--
  对象类型 → 版本历史 子页
  展示本对象类型的已发布版本，支持恢复到历史版本（改动进入待保存列表）
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">{{ i18nT("ai_ontology.versionHistory") }}</span>
      <el-tag size="small" type="info" effect="plain">{{ list.length }}</el-tag>
      <el-button
        v-hasPerm="'module_ai:ontology:manage'"
        class="ont-sec__op"
        size="small"
        type="primary"
        link
        :icon="Upload"
        :loading="publishing"
        @click="publish"
      >
        {{ i18nT("ai_ontology.publishNewVersion") }}
      </el-button>
      <el-button
        class="ont-sec__op"
        size="small"
        type="primary"
        link
        :icon="RefreshLeft"
        @click="emit('refresh')"
      >
        {{ i18nT("ai_ontology.refresh") }}
      </el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      class="ont-obj__note"
      :title="i18nT('ai_ontology.versionInfoAlert')"
    />
    <el-table :data="list" size="small" border max-height="460" class="ont-ver__table" stripe>
      <template #empty>
        <el-empty :image-size="50" :description="i18nT('ai_ontology.noVersionRecords')" />
      </template>
      <el-table-column :label="i18nT('ai_ontology.version')" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="primary" effect="plain">v{{ row.version }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="created_time"
        :label="i18nT('ai_ontology.publishedTime')"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        :label="i18nT('ai_ontology.publishedBy')"
        min-width="110"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.created_by || row.author || "—" }}</template>
      </el-table-column>
      <el-table-column :label="i18nT('ai_ontology.note')" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.msg || row.note || row.description || "—" }}</template>
      </el-table-column>
      <el-table-column :label="i18nT('ai_ontology.operations')" width="180" align="center">
        <template #default="{ row }">
          <el-button icon="Switch" link type="primary" size="small" @click="showDiff(row)">
            {{ i18nT("ai_ontology.compare") }}
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:edit'"
            icon="RefreshLeft"
            link
            type="primary"
            size="small"
            :loading="restoringId === row.id"
            @click="restore(row)"
          >
            {{ i18nT("ai_ontology.restore") }}
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            icon="RefreshLeft"
            link
            type="danger"
            size="small"
            :loading="rollingId === row.id"
            @click="rollback(row)"
          >
            {{ i18nT("ai_ontology.rollback") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 版本对比：与该版本相对当前定义的差异 -->
    <el-dialog
      v-model="diffVisible"
      :title="i18nT('ai_ontology.versionCompareTitle', { version: diffVersion })"
      width="600px"
      append-to-body
    >
      <el-alert
        v-if="diffLoading"
        type="info"
        :closable="false"
        show-icon
        :title="i18nT('ai_ontology.computingDiff')"
      />
      <template v-else>
        <el-empty
          v-if="!diffItems.length && !diffRaw"
          :image-size="50"
          :description="i18nT('ai_ontology.thisVersionHasNoDiffFromCurrentDefinition')"
        />
        <el-table v-else :data="diffItems" size="small" border max-height="360" stripe>
          <el-table-column prop="kind" :label="i18nT('ai_ontology.type')" width="90" />
          <el-table-column
            prop="target"
            :label="i18nT('ai_ontology.object')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column
            prop="detail"
            :label="i18nT('ai_ontology.change')"
            min-width="240"
            show-overflow-tooltip
          />
        </el-table>
        <pre v-if="diffRaw" class="ont-ver__raw">{{ diffRaw }}</pre>
      </template>
      <template #footer>
        <el-button @click="diffVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { RefreshLeft, Upload } from "@element-plus/icons-vue";
import {
  getOntVersionDiff,
  publishOntVersion,
  rollbackOntVersion,
  stageOntRestore,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string }>();
const emit = defineEmits<{ (e: "refresh"): void }>();

const { versions, objectLabel, reloadAll, refreshWip } = useOntologyData();

const list = computed(() => versions.value.filter((v: any) => v.object_code === props.code));

const restoringId = ref<number | null>(null);
async function restore(v: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.restoreVersionConfirm", {
      name: objectLabel(v.object_code),
      version: v.version,
    }),
    i18nT("ai_ontology.restoreHistoricalVersion"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.restore"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  restoringId.value = v.id;
  try {
    const r = await stageOntRestore(v.id);
    await reloadAll();
    await refreshWip();
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.restoreStaged"));
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.restoreFailed"));
  } finally {
    restoringId.value = null;
  }
}

/* ---------- 发布新版本 ---------- */
const publishing = ref(false);
async function publish() {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.publishCurrentConfirm", { name: objectLabel(props.code) }),
    i18nT("ai_ontology.publishNewVersion"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.publish"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  publishing.value = true;
  try {
    const r = await publishOntVersion(props.code);
    await reloadAll();
    if (r.data?.data?.ok === false) {
      // 非超管：发布进入审批队列，尚未生效
      ElMessage.warning(
        r.data?.data?.msg || r.data?.msg || i18nT("ai_ontology.publishApprovalSubmitted")
      );
    } else {
      ElMessage.success(r.data?.msg || i18nT("ai_ontology.published"));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.publishFailed"));
  } finally {
    publishing.value = false;
  }
}

/* ---------- 回滚（立即生效，不可逆） ---------- */
const rollingId = ref<number | null>(null);
async function rollback(v: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.rollbackVersionConfirm", {
      name: objectLabel(v.object_code),
      version: v.version,
    }),
    i18nT("ai_ontology.rollbackToThisVersion"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.rollback"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  rollingId.value = v.id;
  try {
    const r = await rollbackOntVersion(v.id);
    await reloadAll();
    await refreshWip();
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.rolledBack"));
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.rollbackFailed"));
  } finally {
    rollingId.value = null;
  }
}

/* ---------- 版本对比 ---------- */
const diffVisible = ref(false);
const diffLoading = ref(false);
const diffVersion = ref<number | string>("");
const diffItems = ref<{ kind: string; target: string; detail: string }[]>([]);
const diffRaw = ref("");
async function showDiff(v: any) {
  diffVisible.value = true;
  diffLoading.value = true;
  diffVersion.value = v.version;
  diffItems.value = [];
  diffRaw.value = "";
  try {
    const r = await getOntVersionDiff(v.id);
    // 注意：项目 request() 返回的是 axios response，业务数据在 response.data.data 里
    const d: any = r.data?.data ?? r.data ?? {};
    if (d.ok === false) {
      diffRaw.value = d.msg || i18nT("ai_ontology.cannotComputeDiff");
      return;
    }
    const kindOf: [string, string][] = [
      ["added", i18nT("ai_ontology.addProperty")],
      ["removed", i18nT("ai_ontology.deleteProperty")],
      ["changed", i18nT("ai_ontology.modifyProperty")],
    ];
    const rows: { kind: string; target: string; detail: string }[] = [];
    for (const [key, label] of kindOf) {
      for (const code of d[key] || []) {
        rows.push({ kind: label, target: String(code), detail: "" });
      }
    }
    // 未知形状（后端将来扩展字段）时，兜底把原始 JSON 展示出来，避免"看起来没差异"
    if (!rows.length && !("added" in d) && !("removed" in d) && !("changed" in d)) {
      diffRaw.value = JSON.stringify(d, null, 2);
    }
    diffItems.value = rows;
  } catch (e: any) {
    diffRaw.value = e?.msg || i18nT("ai_ontology.compareFailed");
  } finally {
    diffLoading.value = false;
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
.ont-ver__raw {
  margin: 8px 0 0;
  max-height: 240px;
  overflow: auto;
  padding: 8px;
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-light);
  font-size: 12px;
  white-space: pre-wrap;
}
</style>
