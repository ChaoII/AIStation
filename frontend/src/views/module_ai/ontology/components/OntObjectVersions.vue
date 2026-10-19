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
        v-hasPerm="'module_ai:ontology:manage'"
        class="ont-sec__op"
        size="small"
        type="primary"
        link
        :icon="Upload"
        :loading="publishing"
        @click="publish"
      >
        发布新版本
      </el-button>
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
      <el-table-column label="说明" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.msg || row.note || row.description || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="showDiff(row)">对比</el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:edit'"
            link
            type="primary"
            size="small"
            :loading="restoringId === row.id"
            @click="restore(row)"
          >
            恢复
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            link
            type="danger"
            size="small"
            :loading="rollingId === row.id"
            @click="rollback(row)"
          >
            回滚
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 版本对比：与该版本相对当前定义的差异 -->
    <el-dialog
      v-model="diffVisible"
      :title="`版本对比 v${diffVersion}`"
      width="640px"
      append-to-body
    >
      <el-alert v-if="diffLoading" type="info" :closable="false" show-icon title="正在计算差异……" />
      <template v-else>
        <el-empty v-if="!diffItems.length && !diffRaw" :image-size="50" description="该版本与当前定义没有差异" />
        <el-table v-else :data="diffItems" size="small" border max-height="360">
          <el-table-column prop="kind" label="类型" width="90" />
          <el-table-column prop="target" label="对象" min-width="140" show-overflow-tooltip />
          <el-table-column prop="detail" label="变化" min-width="240" show-overflow-tooltip />
        </el-table>
        <pre v-if="diffRaw" class="ont-ver__raw">{{ diffRaw }}</pre>
      </template>
      <template #footer>
        <el-button @click="diffVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
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

/* ---------- 发布新版本 ---------- */
const publishing = ref(false);
async function publish() {
  await ElMessageBox.confirm(
    `将把「${objectLabel(props.code)}」的**当前定义**发布为一个新版本（生成不可变的版本快照，供日后对比/恢复/回滚）。确认发布？`,
    "发布新版本",
    { type: "warning", confirmButtonText: "发布", cancelButtonText: "取消" }
  );
  publishing.value = true;
  try {
    const r = await publishOntVersion(props.code);
    await reloadAll();
    if (r.data?.data?.ok === false) {
      // 非超管：发布进入审批队列，尚未生效
      ElMessage.warning(r.data?.data?.msg || r.data?.msg || "已提交发布审批");
    } else {
      ElMessage.success(r.data?.msg || "已发布");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "发布失败");
  } finally {
    publishing.value = false;
  }
}

/* ---------- 回滚（立即生效，不可逆） ---------- */
const rollingId = ref<number | null>(null);
async function rollback(v: any) {
  await ElMessageBox.confirm(
    `将把「${objectLabel(v.object_code)}」的定义**立即回滚**到版本 v${v.version}。` +
      "与「恢复」不同，回滚会**直接覆盖当前定义并立即生效**（不进待保存列表），且不可撤销。确认回滚？",
    "回滚到该版本",
    { type: "warning", confirmButtonText: "回滚", cancelButtonText: "取消" }
  );
  rollingId.value = v.id;
  try {
    const r = await rollbackOntVersion(v.id);
    await reloadAll();
    await refreshWip();
    ElMessage.success(r.data?.msg || "已回滚");
  } catch (e: any) {
    ElMessage.error(e?.msg || "回滚失败");
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
      diffRaw.value = d.msg || "无法计算差异";
      return;
    }
    const kindOf: [string, string][] = [
      ["added", "新增属性"],
      ["removed", "删除属性"],
      ["changed", "修改属性"],
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
    diffRaw.value = e?.msg || "对比失败";
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
