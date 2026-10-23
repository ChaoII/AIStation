<!-- 用户管理 -->
<template>
  <div class="app-container">
    <el-row class="page-row" :gutter="12" justify="start">
      <el-col :span="4" class="dept-col">
        <DeptTree v-model="deptFilterId" class="w-full h-full" @node-click="handleDeptNodeClick" />
      </el-col>

      <el-col :span="20" class="right-col">
        <PageSearch
          ref="searchRef"
          :search-config="searchConfig"
          @query-click="handleQueryClick"
          @reset-click="handleResetClick"
        />

        <PageContent ref="contentRef" class="flex-1 min-h-0" :content-config="contentConfig">
          <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
            <CrudToolbarLeft
              :remove-ids="removeIds"
              :perm-create="['module_system:user:create']"
              :perm-delete="['module_system:user:delete']"
              :perm-patch="['module_system:user:patch']"
              :delete-loading="submitLoading"
              @add="handleOpenDialog('create')"
              @delete="onToolbar('delete')"
              @more="handleMoreClick"
            />
            <div class="data-table__toolbar--right">
              <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
                <template #prepend>
                  <el-tooltip :content="t('system.user.import')">
                    <el-button
                      v-hasPerm="['module_system:user:import']"
                      type="info"
                      icon="upload"
                      circle
                      @click="handleOpenImportDialog"
                    />
                  </el-tooltip>
                  <el-tooltip :content="t('system.user.export')">
                    <el-button
                      v-hasPerm="['module_system:user:export']"
                      type="warning"
                      icon="download"
                      circle
                      @click="handleOpenExportsModal"
                    />
                  </el-tooltip>
                </template>
              </CrudToolbarRight>
            </div>
          </template>

          <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
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
                  <el-empty :image-size="80" :description="t('system.user.noData')" />
                </template>
                <el-table-column type="selection" min-width="55" align="center" />
                <el-table-column fixed :label="t('system.user.serial')" min-width="60">
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  :label="t('system.user.avatar')"
                  prop="avatar"
                  min-width="80"
                  align="center"
                >
                  <template #default="scope">
                    <template v-if="normalizeAvatarUrl(scope.row.avatar)">
                      <el-avatar size="small" :src="normalizeAvatarUrl(scope.row.avatar)" />
                    </template>
                    <template v-else>
                      <el-avatar size="small" icon="UserFilled" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column
                  :label="t('system.user.username')"
                  prop="username"
                  min-width="100"
                />
                <el-table-column :label="t('system.user.name')" prop="name" min-width="100" />
                <el-table-column :label="t('system.user.status')" prop="status" min-width="100">
                  <template #default="scope">
                    <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                      {{
                        scope.row.status === "0"
                          ? t("system.user.enabled")
                          : t("system.user.disabled")
                      }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('system.user.dept')" prop="dept" min-width="100">
                  <template #default="scope">
                    {{ scope.row.dept ? scope.row.dept.name : "" }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('system.user.gender')" prop="gender" min-width="100">
                  <template #default="scope">
                    <el-tag v-if="scope.row.gender === '0'" type="success">
                      {{ t("system.user.male") }}
                    </el-tag>
                    <el-tag v-else-if="scope.row.gender === '1'" type="warning">
                      {{ t("system.user.female") }}
                    </el-tag>
                    <el-tag v-else type="info">{{ t("system.user.unknown") }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  :label="t('system.user.createdAt')"
                  prop="created_time"
                  min-width="160"
                />
                <el-table-column
                  :label="t('system.user.updatedAt')"
                  prop="updated_time"
                  min-width="160"
                />
                <el-table-column
                  :label="t('system.user.action')"
                  fixed="right"
                  align="center"
                  min-width="280"
                >
                  <template #default="scope">
                    <el-button
                      v-hasPerm="['module_system:user:update']"
                      type="warning"
                      icon="RefreshLeft"
                      size="small"
                      link
                      :disabled="scope.row.is_superuser === true"
                      @click="hancleResetPassword(scope.row)"
                    >
                      {{ t("system.user.resetPassword") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_system:user:detail']"
                      type="info"
                      size="small"
                      link
                      icon="View"
                      @click="handleOpenDialog('detail', scope.row.id)"
                    >
                      {{ t("system.user.detail") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_system:user:update']"
                      type="primary"
                      size="small"
                      link
                      icon="edit"
                      :disabled="scope.row.is_superuser === true"
                      @click="handleOpenDialog('update', scope.row.id)"
                    >
                      {{ t("system.user.edit") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_system:user:delete']"
                      type="danger"
                      size="small"
                      link
                      icon="delete"
                      :disabled="scope.row.is_superuser === true"
                      @click="handleRowDelete(scope.row.id)"
                    >
                      {{ t("system.user.delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </el-col>
    </el-row>

    <EnhancedDrawer
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      :size="drawerSize"
      @close="handleCloseDialog"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('system.user.id')" :span="2">
            {{ detailFormData.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.avatar')" :span="2">
            <template v-if="normalizeAvatarUrl(detailFormData.avatar)">
              <el-avatar :src="normalizeAvatarUrl(detailFormData.avatar)" size="small"></el-avatar>
            </template>
            <template v-else>
              <el-avatar icon="UserFilled" size="small"></el-avatar>
            </template>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.username')" :span="2">
            {{ detailFormData.username }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.name')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.gender')" :span="2">
            <el-tag v-if="detailFormData.gender === '0'" type="success">
              {{ t("system.user.male") }}
            </el-tag>
            <el-tag v-else-if="detailFormData.gender === '1'" type="warning">
              {{ t("system.user.female") }}
            </el-tag>
            <el-tag v-else type="info">{{ t("system.user.unknown") }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.dept')" :span="2">
            {{ detailFormData.dept ? detailFormData.dept.name : "" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.role')" :span="2">
            {{
              detailFormData.roles ? detailFormData.roles.map((item) => item.name).join("、") : ""
            }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.position')" :span="2">
            {{
              detailFormData.positions
                ? detailFormData.positions.map((item) => item.name).join("、")
                : ""
            }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.email')" :span="2">
            {{ detailFormData.email }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.mobile')" :span="2">
            {{ detailFormData.mobile }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.isSuperuser')" :span="2">
            <el-tag :type="detailFormData.is_superuser ? 'success' : 'info'">
              {{ detailFormData.is_superuser ? t("system.user.yes") : t("system.user.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.status')" :span="2">
            <el-tag :type="detailFormData.status === '0' ? 'success' : 'danger'">
              {{
                detailFormData.status === "0" ? t("system.user.enabled") : t("system.user.disabled")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.lastLogin')" :span="2">
            {{ detailFormData.last_login }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.creator')" :span="2">
            {{ detailFormData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.updater')" :span="2">
            {{ detailFormData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.createdAt')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.updatedAt')" :span="2">
            {{ detailFormData.updated_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.user.description')" :span="4">
            {{ detailFormData.description }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template v-else>
        <el-form
          ref="dataFormRef"
          :model="formData"
          :rules="rules"
          label-suffix=":"
          label-width="auto"
          label-position="right"
        >
          <el-form-item :label="t('system.user.username')" prop="username">
            <el-input
              v-model="formData.username"
              :disabled="!!formData.id"
              :placeholder="t('system.user.inputUsername')"
            />
          </el-form-item>

          <el-form-item :label="t('system.user.name')" prop="name">
            <el-input v-model="formData.name" :placeholder="t('system.user.inputName')" />
          </el-form-item>

          <el-form-item :label="t('system.user.gender')" prop="gender">
            <el-select v-model="formData.gender" :placeholder="t('system.user.selectGender')">
              <el-option :label="t('system.user.male')" value="0" />
              <el-option :label="t('system.user.female')" value="1" />
              <el-option :label="t('system.user.unknown')" value="2" />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('system.user.mobile')" prop="mobile">
            <el-input
              v-model="formData.mobile"
              :placeholder="t('system.user.inputMobile')"
              maxlength="11"
            />
          </el-form-item>

          <el-form-item :label="t('system.user.email')" prop="email">
            <el-input
              v-model="formData.email"
              :placeholder="t('system.user.inputEmail')"
              maxlength="50"
            />
          </el-form-item>

          <el-form-item :label="t('system.user.dept')" prop="dept_id">
            <el-tree-select
              v-model="formData.dept_id"
              :placeholder="t('system.user.selectParentDept')"
              :data="deptOptions"
              :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
              filterable
              check-strictly
              :render-after-expand="false"
            />
          </el-form-item>

          <el-form-item :label="t('system.user.role')" prop="role_ids">
            <el-select
              v-model="formData.role_ids"
              multiple
              :placeholder="t('system.user.selectRole')"
            >
              <el-option
                v-for="item in roleOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
                :disabled="item.disabled"
              />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('system.user.position')" prop="position_ids">
            <el-select
              v-model="formData.position_ids"
              multiple
              :placeholder="t('system.user.selectPosition')"
            >
              <el-option
                v-for="item in positionOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
                :disabled="item.disabled"
              />
            </el-select>
          </el-form-item>

          <el-form-item v-if="!formData.id" :label="t('system.user.password')" prop="password">
            <el-input
              v-model="formData.password"
              :placeholder="t('system.user.inputPassword')"
              type="password"
              show-password
              clearable
            />
          </el-form-item>

          <el-form-item :label="t('system.user.isSuperuser')" prop="is_superuser">
            <el-switch v-model="formData.is_superuser" />
          </el-form-item>

          <el-form-item :label="t('system.user.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.user.enabled") }}</el-radio>
              <el-radio value="1">{{ t("system.user.disabled") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('system.user.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.user.inputDescription')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.user.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type === 'create' || dialogVisible.type === 'update'"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.user.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.user.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDrawer>

    <ImportModal
      v-model="importDialogVisible"
      :content-config="curdContentConfig"
      :loading="uploadLoading"
      @upload="handleUpload"
    />

    <ExportModal
      v-model="exportsDialogVisible"
      :content-config="curdContentConfig"
      :query-params="exportQueryParams"
      :page-data="exportPageData"
      :selection-data="exportSelectionData"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "User",
  inheritAttrs: false,
});

import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { useAppStore } from "@/store/modules/app.store";
import { DeviceEnum } from "@/enums/settings/device.enum";
import { ResultEnum } from "@/enums/api/result.enum";

import UserAPI, {
  type UserForm,
  type UserInfo,
  type UserPageQuery,
} from "@/api/module_system/user";
import { formatTree } from "@/utils/common";
import PositionAPI from "@/api/module_system/position";
import DeptAPI from "@/api/module_system/dept";
import RoleAPI from "@/api/module_system/role";

import DeptTree from "./components/DeptTree.vue";
import UserTableSelect from "./components/UserTableSelect.vue";
import { useUserStore } from "@/store";
import ImportModal from "@/components/CURD/ImportModal.vue";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDrawer from "@/components/CURD/EnhancedDrawer.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { ref, reactive, computed, markRaw, nextTick, unref } from "vue";
import { fetchAllPages } from "@/utils/fetchAllPages";
import { normalizeAvatarUrl } from "@/utils";

const appStore = useAppStore();

const { t } = useI18n();

const searchRef = ref<InstanceType<typeof PageSearch>>();
const contentRef = ref<InstanceType<typeof PageContent>>();
const dataFormRef = ref();
const submitLoading = ref(false);
const uploadLoading = ref(false);
const deptFilterId = ref<number | undefined>(undefined);

const drawerSize = computed(() => (appStore.device === DeviceEnum.DESKTOP ? "450px" : "90%"));
const deptOptions = ref<OptionType[]>();
const roleOptions = ref<Array<{ value: number; label: string; disabled?: boolean }>>();
const positionOptions = ref<Array<{ value: number; label: string; disabled?: boolean }>>();
const importDialogVisible = ref(false);
const exportsDialogVisible = ref(false);
const detailFormData = ref<UserInfo>({});

function triggerUserSearch() {
  nextTick(() => {
    contentRef.value?.fetchPageData(getMergedListParams(), true);
  });
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:user",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "username",
      label: t("system.user.username"),
      type: "input",
      attrs: { placeholder: t("system.user.inputUsername"), clearable: true },
    },
    {
      prop: "name",
      label: t("system.user.name"),
      type: "input",
      attrs: { placeholder: t("system.user.inputName"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.user.status"),
      type: "select",
      options: [
        { label: t("system.user.enabled"), value: "0" },
        { label: t("system.user.disabled"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.user.selectStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_id",
      label: t("system.user.creator"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
  ],
  customComponents: {
    "user-table-select": markRaw(UserTableSelect),
  },
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: t("system.user.selection"), show: true },
  { prop: "index", label: t("system.user.serial"), show: true },
  { prop: "avatar", label: t("system.user.avatar"), show: true },
  { prop: "username", label: t("system.user.username"), show: true },
  { prop: "name", label: t("system.user.name"), show: true },
  { prop: "status", label: t("system.user.status"), show: true },
  { prop: "dept", label: t("system.user.dept"), show: true },
  { prop: "gender", label: t("system.user.gender"), show: true },
  { prop: "created_time", label: t("system.user.createdAt"), show: true },
  { prop: "updated_time", label: t("system.user.updatedAt"), show: true },
  { prop: "operation", label: t("system.user.action"), show: true },
]);

const contentConfig = reactive<IContentConfig<UserPageQuery>>({
  permPrefix: "module_system:user",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  initialFetch: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await UserAPI.listUser(params as UserPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await UserAPI.deleteUser(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    const userStore = useUserStore();
    const idSet = ids.split(",").map((s) => Number(s.trim()));
    if (userStore.basicInfo.id && idSet.includes(userStore.basicInfo.id)) {
      userStore.clearUserInfo();
    }
  },
  deleteConfirm: {
    title: t("system.user.warning"),
    message: t("system.user.deleteConfirmMessage"),
    type: "warning",
  },
});

function getMergedListParams(): UserPageQuery {
  const base = searchRef.value?.getQueryParams() ?? {};
  return {
    ...base,
    dept_id: deptFilterId.value,
  } as UserPageQuery;
}

function handleQueryClick() {
  contentRef.value?.fetchPageData(getMergedListParams(), true);
}

function handleResetClick() {
  deptFilterId.value = undefined;
  contentRef.value?.fetchPageData(getMergedListParams(), true);
}

function handleDeptNodeClick() {
  contentRef.value?.fetchPageData(getMergedListParams(), true);
}

function refreshList() {
  contentRef.value?.fetchPageData(getMergedListParams(), true);
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const exportQueryParams = computed(() => getMergedListParams());

const exportPageData = computed(() => (unref(contentRef.value?.pageData) ?? []) as UserInfo[]);

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as UserInfo[]
);

const formData = reactive<UserForm>({
  id: undefined,
  username: undefined,
  name: undefined,
  dept_id: undefined,
  dept_name: undefined,
  role_ids: undefined,
  role_names: undefined,
  position_ids: undefined,
  position_names: undefined,
  password: undefined,
  gender: undefined,
  email: undefined,
  mobile: undefined,
  is_superuser: false,
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  username: [{ required: true, message: t("system.user.inputUsername"), trigger: "blur" }],
  name: [{ required: true, message: t("system.user.inputName"), trigger: "blur" }],
  password: [{ required: true, message: t("system.user.inputPassword"), trigger: "blur" }],
  gender: [{ required: false, message: t("system.user.selectGender"), trigger: "blur" }],
  email: [
    {
      pattern: /\w[-\w.+]*@([A-Za-z0-9][-A-Za-z0-9]+\.)+[A-Za-z]{2,14}/,
      message: t("system.user.emailInvalid"),
      trigger: "blur",
    },
  ],
  mobile: [
    {
      pattern: /^1[3|4|5|6|7|8|9][0-9]\d{8}$/,
      message: t("system.user.mobileInvalid"),
      trigger: "blur",
    },
  ],
  is_superuser: [{ required: true, message: t("system.user.selectSuperuser"), trigger: "blur" }],
  status: [{ required: true, message: t("system.user.selectStatus"), trigger: "blur" }],
});

const exportColumns = [
  { prop: "username", label: t("system.user.username") },
  { prop: "name", label: t("system.user.exportName") },
  { prop: "status", label: t("system.user.status") },
  { prop: "gender", label: t("system.user.gender") },
  { prop: "email", label: t("system.user.email") },
  { prop: "mobile", label: t("system.user.mobile") },
  { prop: "is_superuser", label: t("system.user.isSuperuser") },
  { prop: "description", label: t("system.user.description") },
  { prop: "created_time", label: t("system.user.createdAt") },
  { prop: "updated_time", label: t("system.user.updatedAt") },
];

const curdContentConfig = {
  permPrefix: "module_system:user",
  cols: exportColumns as unknown as IContentConfig["cols"],
  importTemplate: () => UserAPI.downloadTemplateUser(),
  exportsAction: async (params: Record<string, unknown>) => {
    const query: Record<string, unknown> = { ...params };
    if (typeof query.status === "string") {
      query.status = query.status === "true";
    }
    return fetchAllPages<UserInfo>({
      pageSize: 9999,
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await UserAPI.listUser(q as unknown as UserPageQuery);
        return {
          total: res.data?.data?.total ?? 0,
          list: res.data?.data?.items ?? [],
        };
      },
    });
  },
} as unknown as IContentConfig;

function hancleResetPassword(row: UserInfo) {
  ElMessageBox.prompt(
    t("system.user.resetPasswordPrompt", { username: row.username }),
    t("system.user.resetPassword"),
    {
      confirmButtonText: t("system.user.confirm"),
      cancelButtonText: t("system.user.cancel"),
    }
  ).then(
    async ({ value }) => {
      if (!value || value.length < 6) {
        ElMessage.warning(t("system.user.passwordMinLength"));
        return false;
      }
      await UserAPI.resetUserPassword({ id: row.id!, password: value });
      ElMessage.success(t("system.user.operationSuccess"));
    },
    () => {
      ElMessageBox.close();
    }
  );
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

const initialFormData: UserForm = {
  id: undefined,
  username: undefined,
  name: undefined,
  dept_id: undefined,
  dept_name: undefined,
  role_ids: undefined,
  role_names: undefined,
  position_ids: undefined,
  position_names: undefined,
  password: undefined,
  gender: undefined,
  email: undefined,
  mobile: undefined,
  is_superuser: false,
  status: "0",
  description: undefined,
};

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await UserAPI.detailUser(id);
    if (type === "detail") {
      dialogVisible.title = t("system.user.userDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.user.updateUser");
      Object.assign(formData, response.data.data);
      formData.role_ids = (response.data.data.roles || []).map((item) => item.id as number);
      formData.position_ids = (response.data.data.positions || []).map((item) => item.id as number);
    }
  } else {
    dialogVisible.title = t("system.user.createUser");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
  await nextTick();
  if (dataFormRef.value) {
    dataFormRef.value.clearValidate();
  }

  const deptResponse = await DeptAPI.listDept({});
  deptOptions.value = formatTree(deptResponse.data.data);

  const roleResponse = await RoleAPI.listRole();
  roleOptions.value = roleResponse.data.data.items
    .filter((item) => item.id !== undefined && item.name !== undefined)
    .map((item) => ({
      value: item.id as number,
      label: item.name as string,
      disabled: item.status === "1",
    }))
    .filter((opt) => !opt.disabled);

  const positionResponse = await PositionAPI.listPosition();
  positionOptions.value = positionResponse.data.data.items
    .filter((item) => item.id !== undefined && item.name !== undefined)
    .map((item) => ({
      value: item.id as number,
      label: item.name as string,
      disabled: item.status === "1",
    }))
    .filter((opt) => !opt.disabled);
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          await UserAPI.updateUser(id, { id, ...formData });
        } else {
          await UserAPI.createUser(formData);
        }
        ElMessage.success(t("system.user.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        const userStore = useUserStore();
        if (id === userStore.basicInfo.id) {
          await userStore.getUserInfo();
        }
      } catch (error: unknown) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as UserInfo[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.user.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(t("system.user.confirmEnableOrDisable"), t("system.user.warning"), {
    confirmButtonText: t("system.user.confirm"),
    cancelButtonText: t("system.user.cancel"),
    type: "warning",
  })
    .then(async () => {
      try {
        submitLoading.value = true;
        await UserAPI.batchUser({ ids, status });
        ElMessage.success(t("system.user.operationSuccess"));
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}

function handleOpenImportDialog() {
  importDialogVisible.value = true;
}

function handleOpenExportsModal() {
  exportsDialogVisible.value = true;
}

const emit = defineEmits(["import-success"]);

const handleUpload = async (formDataUpload: FormData) => {
  try {
    uploadLoading.value = true;
    const response = await UserAPI.importUser(formDataUpload);
    if (response.data.code === ResultEnum.SUCCESS) {
      ElMessage.success(`${response.data.msg}，${response.data.data}`);
      importDialogVisible.value = false;
      await refreshList();
      emit("import-success");
    }
  } catch (error: unknown) {
    console.error(error);
    ElMessage.error(t("system.user.uploadFailed", { error }));
  } finally {
    uploadLoading.value = false;
  }
};

onMounted(() => {
  nextTick(() => {
    contentRef.value?.fetchPageData(getMergedListParams(), true);
  });
});
</script>

<style lang="scss" scoped>
.page-row {
  flex: 1;
  align-items: stretch;
  min-height: 0;
}

.dept-col {
  display: flex;
}

.right-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.right-col :deep(.data-table) {
  flex: 1;
  min-height: 0;
}

.right-col :deep(.data-table__content) {
  min-height: 0;
}

.el-row {
  height: 100%;
}

.el-col {
  height: 100%;
}

.h-full {
  height: 100%;
}

.w-full {
  width: 100%;
}
</style>
