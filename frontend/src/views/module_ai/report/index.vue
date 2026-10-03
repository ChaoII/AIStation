<!-- AI 报告：列表 + Markdown 详情预览 + 删除 -->
<template>
  <div class="app-container ai-report-page">
    <div class="report-toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索报告标题"
        clearable
        :prefix-icon="Search"
        style="width: 260px"
      />
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="filtered" border stripe>
      <template #empty><el-empty :image-size="80" description="暂无 AI 报告" /></template>
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row)">{{ row.title || "（未命名）" }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
      </el-table-column>
      <el-table-column prop="created_time" label="时间" min-width="180" />
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">查看</el-button>
          <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="detailVisible"
      :title="detail?.title || '报告详情'"
      width="760px"
      append-to-body
    >
      <div class="report-md" v-html="renderMd(detail?.content)"></div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import MarkdownIt from "markdown-it";
import { deleteAiReport, getAiReportDetail, getAiReportList } from "@/api/module_ai/report";

defineOptions({ name: "AiReport" });

const loading = ref(false);
const reports = ref<any[]>([]);
const keyword = ref("");
const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
function renderMd(text: string) {
  return md.render(text || "");
}
function sourceLabel(src: any) {
  if (!src) return "—";
  if (typeof src === "string") return src;
  return src.name || "—";
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return reports.value;
  return reports.value.filter((r) => (r.title || "").toLowerCase().includes(kw));
});

async function load() {
  loading.value = true;
  try {
    const r = await getAiReportList();
    reports.value = r.data?.data || [];
  } catch {
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
}

const detailVisible = ref(false);
const detail = ref<any>(null);
async function openDetail(row: any) {
  try {
    const r = await getAiReportDetail(row.id);
    detail.value = r.data?.data || row;
  } catch {
    detail.value = row;
  }
  detailVisible.value = true;
}

function remove(row: any) {
  ElMessageBox.confirm(`确定删除报告「${row.title}」吗？删除后不可恢复。`, "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiReport([row.id]);
      ElMessage.success("删除成功");
      load();
    })
    .catch(() => {});
}

onMounted(load);
</script>

<style scoped>
.ai-report-page {
  padding: 12px;
}
.report-toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.report-md {
  line-height: 1.8;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  word-break: break-word;
  max-height: 70vh;
  overflow: auto;
}
.report-md :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 6px;
  overflow: auto;
}
.report-md :deep(code) {
  font-family: var(--el-font-family-mono, monospace);
}
.report-md :deep(h1),
.report-md :deep(h2),
.report-md :deep(h3) {
  margin: 0.5em 0;
}
.report-md :deep(table) {
  border-collapse: collapse;
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
}
.report-md :deep(td),
.report-md :deep(th) {
  border: 1px solid var(--el-border-color-lighter);
  padding: 6px 10px;
}
</style>
