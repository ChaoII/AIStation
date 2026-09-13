<template>
  <div class="app-container">
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-delete="['module_ai:report:delete']"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无报告" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="标题" prop="title" min-width="240" show-overflow-tooltip />
            <el-table-column label="关联应用" width="110" align="center">
              <template #default="scope">
                <el-tag v-if="scope.row.app_id" size="small" type="info">
                  #{{ scope.row.app_id }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="关联会话" width="110" align="center">
              <template #default="scope">
                <el-tag v-if="scope.row.session_id" size="small" type="info">
                  #{{ scope.row.session_id }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="生成时间" prop="created_time" width="180" />
            <el-table-column label="操作" fixed="right" width="160" align="center">
              <template #default="scope">
                <el-button size="small" link type="primary" @click="handleView(scope.row)">
                  查看
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:report:delete']"
                  size="small"
                  link
                  type="danger"
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <el-drawer v-model="drawerVisible" :title="current?.title || '报告'" size="720px">
      <div class="report-actions">
        <el-button size="small" @click="download">导出 Markdown</el-button>
      </div>
      <div class="report-body" v-html="rendered"></div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import MarkdownIt from "markdown-it";
import { getAiReportList, getAiReportDetail, deleteAiReport } from "@/api/module_ai/report";
import type { IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

const md = new MarkdownIt({ breaks: true, linkify: true });
const { contentRef } = useCrudList();

const contentConfig = reactive<IContentConfig<any>>({
  permPrefix: "module_ai:report",
  pk: "id",
  cols: [] as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async () => {
    const res = await getAiReportList();
    const list = res.data?.data || [];
    return { total: list.length, list };
  },
  deleteAction: async (ids) => {
    await deleteAiReport(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除所选报告?", type: "warning" },
});

const drawerVisible = ref(false);
const current = ref<any>(null);
const rendered = computed(() => md.render(current.value?.content || ""));

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleView(row: any) {
  const res = await getAiReportDetail(row.id);
  current.value = res.data?.data || row;
  drawerVisible.value = true;
}

function download() {
  if (!current.value) return;
  const blob = new Blob([current.value.content || ""], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${current.value.title || "report"}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<style scoped>
.report-actions {
  margin-bottom: 12px;
  text-align: right;
}

.report-body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.report-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
}

.report-body :deep(th),
.report-body :deep(td) {
  padding: 6px 8px;
  border: 1px solid var(--el-border-color-lighter);
}
</style>
