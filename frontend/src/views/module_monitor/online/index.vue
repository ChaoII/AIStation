<!-- 在线用户 -->
<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <!-- eslint-disable-next-line vue/no-unused-vars -- 与 demo 同源解构，本页无批删逻辑 -->
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft>
          <el-button
            v-hasPerm="['module_monitor:online:delete']"
            type="danger"
            icon="delete"
            @click="handleClear"
          >
            {{ t("monitor.onlineForceAll") }}
          </el-button>
        </CrudToolbarLeft>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('monitor.noData')" />
            </template>

            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              min-width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              type="index"
              fixed
              :label="t('monitor.serial')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'session_id')?.show"
              key="session_id"
              :label="t('monitor.onlineSessionId')"
              prop="session_id"
              min-width="250"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'login_type')?.show"
              key="login_type"
              :label="t('monitor.onlineLoginType')"
              prop="login_type"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'ipaddr')?.show"
              key="ipaddr"
              :label="t('monitor.onlineIp')"
              prop="ipaddr"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-text>{{ scope.row.ipaddr }}</el-text>
                <CopyButton
                  v-if="scope.row.ipaddr"
                  :text="scope.row.ipaddr"
                  :style="{ marginLeft: '2px' }"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('monitor.onlineUser')"
              prop="name"
              min-width="80"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'user_name')?.show"
              key="user_name"
              :label="t('monitor.onlineAccount')"
              prop="user_name"
              min-width="80"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'login_location')?.show"
              key="login_location"
              :label="t('monitor.onlineLoginLocation')"
              prop="login_location"
              min-width="280"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'os')?.show"
              key="os"
              :label="t('monitor.os')"
              prop="os"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'login_time')?.show"
              key="login_time"
              :label="t('monitor.onlineLoginTime')"
              prop="login_time"
              min-width="180"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              key="operation"
              fixed="right"
              :label="t('monitor.operation')"
              min-width="100"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_monitor:online:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleSubmit(scope.row.session_id)"
                >
                  {{ t("monitor.onlineForceLogout") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>
  </div>
</template>

<script lang="ts" setup>
defineOptions({
  name: "OnlineUser",
  inheritAttrs: false,
});

import OnlineAPI, { type OnlineUserPageQuery } from "@/api/module_monitor/online";
import { reactive } from "vue";
import { useI18n } from "vue-i18n";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";

const { t } = useI18n();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_monitor:online",
  colon: true,
  isExpandable: false,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "ipaddr",
      label: t("monitor.onlineIp"),
      type: "input",
      attrs: { placeholder: t("monitor.onlineInputIp"), clearable: true },
    },
    {
      prop: "name",
      label: t("monitor.onlineUser"),
      type: "input",
      attrs: { placeholder: t("monitor.onlineInputUser"), clearable: true },
    },
    {
      prop: "login_location",
      label: t("monitor.onlineLoginLocation"),
      type: "input",
      attrs: { placeholder: t("monitor.onlineInputLocation"), clearable: true },
    },
  ],
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: t("monitor.onlineSelection"), show: true },
  { prop: "index", label: t("monitor.serial"), show: true },
  { prop: "session_id", label: t("monitor.onlineSessionId"), show: true },
  { prop: "login_type", label: t("monitor.onlineLoginType"), show: true },
  { prop: "name", label: t("monitor.onlineLoginName"), show: true },
  { prop: "user_name", label: t("monitor.onlineUserAccount"), show: true },
  { prop: "ipaddr", label: t("monitor.onlineHost"), show: true },
  { prop: "login_location", label: t("monitor.onlineLoginPlace"), show: true },
  { prop: "os", label: t("monitor.os"), show: true },
  { prop: "login_time", label: t("monitor.onlineLoginTime"), show: true },
  { prop: "operation", label: t("monitor.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<OnlineUserPageQuery>>({
  permPrefix: "module_monitor:online",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await OnlineAPI.listOnline(params as OnlineUserPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
});

async function handleSubmit(session_id: string) {
  ElMessageBox.confirm(
    t("monitor.onlineForceSessionConfirm", { id: session_id }),
    t("monitor.warn"),
    {
      confirmButtonText: t("monitor.confirm"),
      cancelButtonText: t("monitor.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await OnlineAPI.deleteOnline(session_id);
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}

async function handleClear() {
  ElMessageBox.confirm(t("monitor.onlineForceAllConfirm"), t("monitor.warn"), {
    confirmButtonText: t("monitor.confirm"),
    cancelButtonText: t("monitor.cancel"),
    type: "warning",
  })
    .then(async () => {
      try {
        await OnlineAPI.clearOnline();
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}
</script>

<style lang="scss" scoped></style>
