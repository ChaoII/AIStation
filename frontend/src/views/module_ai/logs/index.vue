<!-- AI 调用日志 -->
<template>
  <div class="app-container ai-logs-page">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            :data="data"
            height="100%"
            border
            stripe
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无调用日志" />
            </template>
            <el-table-column fixed label="序号" min-width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              prop="created_time"
              label="时间"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column prop="model_name" label="模型" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.model_name || "—" }}</template>
            </el-table-column>
            <el-table-column prop="usage" label="用途" min-width="100" align="center" />
            <el-table-column prop="latency_ms" label="耗时" min-width="100" align="center">
              <template #default="{ row }">{{ row.latency_ms }} ms</template>
            </el-table-column>
            <el-table-column label="结果" min-width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.result === "success" ? "成功" : "失败" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="error" label="错误" min-width="240" show-overflow-tooltip>
              <template #default="{ row }">{{ row.error || "—" }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { getAiLogList } from "@/api/module_ai/logs";

defineOptions({
  name: "AiLogs",
  inheritAttrs: false,
});

const { searchRef, contentRef, handleQueryClick, handleResetClick } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:assistant",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "usage",
      label: "用途",
      type: "select",
      options: [
        { label: "聊天", value: "chat" },
        { label: "应用", value: "app" },
      ],
      attrs: { placeholder: "请选择用途", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "result",
      label: "结果",
      type: "select",
      options: [
        { label: "成功", value: "success" },
        { label: "失败", value: "error" },
      ],
      attrs: { placeholder: "请选择结果", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "keyword",
      label: "关键字",
      type: "input",
      attrs: { placeholder: "模型名或错误信息", clearable: true },
    },
  ],
});

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:assistant",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAiLogList(params);
    return {
      total: res.data.data?.total ?? 0,
      list: res.data.data?.items ?? [],
    };
  },
});
</script>
