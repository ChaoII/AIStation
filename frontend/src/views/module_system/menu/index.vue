<!-- 菜单管理 -->
<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_system:menu:create']"
          :perm-delete="['module_system:menu:delete']"
          :perm-patch="['module_system:menu:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
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
            stripe
            row-key="id"
            :data="data"
            :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
            height="100%"
            border
            @selection-change="onSelectionChange"
            @row-click="handleRowClick"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('system.menu.empty')" />
            </template>
            <el-table-column type="selection" min-width="55" align="center" />
            <el-table-column type="index" fixed :label="t('system.menu.index')" min-width="60" />
            <el-table-column :label="t('system.menu.menuName')" prop="name" min-width="240" />
            <el-table-column
              :label="t('system.menu.icon')"
              prop="icon"
              min-width="80"
              align="center"
            >
              <template #default="scope">
                <template v-if="scope.row.icon && scope.row.icon.startsWith('el-icon')">
                  <el-icon style="vertical-align: -0.15em">
                    <component :is="scope.row.icon.replace('el-icon-', '')" />
                  </el-icon>
                </template>
                <template v-else-if="scope.row.icon">
                  <div :class="`i-svg:${scope.row.icon}`" />
                </template>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('system.menu.status')"
              prop="status"
              min-width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0" ? t("system.menu.enable") : t("system.menu.disable")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('system.menu.type')"
              prop="type"
              min-width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.type === MenuTypeEnum.CATALOG" type="warning">
                  {{ t("system.menu.catalog") }}
                </el-tag>
                <el-tag v-if="scope.row.type === MenuTypeEnum.MENU" type="success">
                  {{ t("system.menu.menu") }}
                </el-tag>
                <el-tag v-if="scope.row.type === MenuTypeEnum.BUTTON" type="danger">
                  {{ t("system.menu.button") }}
                </el-tag>
                <el-tag v-if="scope.row.type === MenuTypeEnum.EXTLINK" type="info">
                  {{ t("system.menu.extlink") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('system.menu.order')" prop="order" min-width="80" />
            <el-table-column
              :label="t('system.menu.routeName')"
              prop="route_name"
              show-overflow-toolti
              min-width="100"
            />
            <el-table-column
              :label="t('system.menu.routePath')"
              prop="route_path"
              show-overflow-tooltip
              min-width="200"
            />
            <el-table-column
              :label="t('system.menu.permission')"
              prop="permission"
              show-overflow-tooltip
              min-width="220"
            />
            <el-table-column
              :label="t('system.menu.componentPath')"
              prop="component_path"
              show-overflow-tooltip
              min-width="200"
            />
            <el-table-column
              :label="t('system.menu.redirect')"
              prop="redirect"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column :label="t('system.menu.keepAlive')" prop="keep_alive" min-width="100">
              <template #default="scope">
                <el-tag :type="scope.row.keep_alive ? 'success' : 'danger'">
                  {{ scope.row.keep_alive ? t("system.menu.yes") : t("system.menu.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('system.menu.hidden')" prop="hidden" min-width="100">
              <template #default="scope">
                <el-tag :type="scope.row.hidden ? 'success' : 'danger'">
                  {{ scope.row.hidden ? t("system.menu.yes") : t("system.menu.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('system.menu.showRootRoute')"
              prop="always_show"
              min-width="120"
            >
              <template #default="scope">
                <el-tag :type="scope.row.always_show ? 'success' : 'danger'">
                  {{ scope.row.always_show ? t("system.menu.yes") : t("system.menu.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('system.menu.affix')" prop="affix" min-width="100">
              <template #default="scope">
                <el-tag :type="scope.row.affix ? 'success' : 'danger'">
                  {{ scope.row.affix ? t("system.menu.yes") : t("system.menu.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('system.menu.title')"
              prop="title"
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column :label="t('system.menu.params')" prop="params" min-width="100" />
            <el-table-column
              :label="t('system.menu.description')"
              prop="description"
              show-overflow-tooltip
              min-width="200"
            />
            <el-table-column
              :label="t('system.menu.createdTime')"
              prop="created_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('system.menu.updatedTime')"
              prop="updated_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              fixed="right"
              :label="t('system.menu.action')"
              align="center"
              min-width="260"
            >
              <template #default="scope">
                <el-button
                  v-if="
                    scope.row.type == MenuTypeEnum.CATALOG || scope.row.type == MenuTypeEnum.MENU
                  "
                  v-hasPerm="['module_system:menu:create']"
                  type="success"
                  link
                  size="small"
                  icon="plus"
                  @click.stop="handleOpenDialog('create', undefined, scope.row)"
                >
                  {{ t("system.menu.add") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:menu:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.menu.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:menu:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.menu.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:menu:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.menu.delete") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDrawer
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      :size="drawerSize"
      @close="handleCloseDialog"
    >
      <!-- 详情 -->
      <template v-if="dialogVisible.type === 'detail'">
        <el-descriptions :column="4" border>
          <el-descriptions-item :label="t('system.menu.id')" :span="2">
            {{ detailFormData.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.menuName')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.menuType')" :span="2">
            <el-tag v-if="detailFormData.type === MenuTypeEnum.CATALOG" type="warning">
              {{ t("system.menu.catalog") }}
            </el-tag>
            <el-tag v-if="detailFormData.type === MenuTypeEnum.MENU" type="success">
              {{ t("system.menu.menu") }}
            </el-tag>
            <el-tag v-if="detailFormData.type === MenuTypeEnum.BUTTON" type="danger">
              {{ t("system.menu.button") }}
            </el-tag>
            <el-tag v-if="detailFormData.type === MenuTypeEnum.EXTLINK" type="info">
              {{ t("system.menu.extlink") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.icon')" :span="2">
            <template #default>
              <template v-if="detailFormData.icon && detailFormData.icon.startsWith('el-icon')">
                <el-icon style="vertical-align: -0.15em">
                  <component :is="detailFormData.icon.replace('el-icon-', '')" />
                </el-icon>
              </template>
              <template v-else-if="detailFormData.icon">
                <div :class="`i-svg:${detailFormData.icon}`" />
              </template>
            </template>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.order')" :span="2">
            {{ detailFormData.order }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.permission')" :span="2">
            {{ detailFormData.permission }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.routeName')" :span="2">
            {{ detailFormData.route_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.routePath')" :span="2">
            {{ detailFormData.route_path }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.componentPath')" :span="2">
            {{ detailFormData.component_path }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.redirect')" :span="2">
            {{ detailFormData.redirect }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.parentId')" :span="2">
            {{ detailFormData.parent_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.parentMenu')" :span="2">
            {{ detailFormData.parent_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.keepAlive')" :span="2">
            <el-tag :type="detailFormData.keep_alive ? 'success' : 'danger'">
              {{ detailFormData.keep_alive ? t("system.menu.yes") : t("system.menu.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.isShow')" :span="2">
            <el-tag :type="detailFormData.hidden ? 'success' : 'danger'">
              {{ detailFormData.hidden ? t("system.menu.yes") : t("system.menu.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.showRootRoute')" :span="2">
            <el-tag :type="detailFormData.always_show ? 'success' : 'danger'">
              {{ detailFormData.always_show ? t("system.menu.yes") : t("system.menu.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.title')" :span="2">
            {{ detailFormData.title }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.params')" :span="2">
            {{ detailFormData.params }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.isAffix')" :span="2">
            <el-tag :type="detailFormData.affix ? 'success' : 'danger'">
              {{ detailFormData.affix ? t("system.menu.yes") : t("system.menu.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.status')" :span="2">
            <el-tag :type="detailFormData.status === '0' ? 'success' : 'danger'">
              {{
                detailFormData.status === "0" ? t("system.menu.enable") : t("system.menu.disable")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.order')" :span="2">
            {{ detailFormData.order }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.updatedTime')" :span="2">
            {{ detailFormData.updated_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.menu.description')" :span="4">
            {{ detailFormData.description }}
          </el-descriptions-item>
        </el-descriptions>
      </template>

      <!-- 新增、编辑表单 -->
      <template v-else>
        <el-form
          ref="dataFormRef"
          :model="formData"
          :rules="rules"
          label-suffix=":"
          label-width="auto"
          label-position="right"
        >
          <el-form-item
            v-if="formData.type !== MenuTypeEnum.CATALOG"
            :label="t('system.menu.parentMenu')"
            prop="parent_id"
          >
            <el-tree-select
              v-model="formData.parent_id"
              :placeholder="t('system.menu.parentMenuPlaceholder')"
              :data="menuOptions"
              filterable
              check-strictly
              :render-after-expand="false"
              :disabled="createParentLocked"
            />
            <el-text v-if="createParentLocked" type="info" size="small" class="block mt-1">
              {{ t("system.menu.parentLockedTip") }}
            </el-text>
          </el-form-item>

          <el-form-item :label="t('system.menu.menuName')" prop="name">
            <el-input v-model="formData.name" :placeholder="t('system.menu.menuNamePlaceholder')" />
          </el-form-item>

          <el-form-item :label="t('system.menu.title')" prop="title">
            <el-input v-model="formData.title" :placeholder="t('system.menu.titlePlaceholder')" />
          </el-form-item>

          <el-form-item :label="t('system.menu.menuType')" prop="type">
            <el-radio-group v-model="formData.type" @change="handleMenuTypeChange">
              <el-radio
                v-if="allowedMenuTypeValues.includes(MenuTypeEnum.CATALOG)"
                :value="MenuTypeEnum.CATALOG"
              >
                {{ t("system.menu.catalog") }}
              </el-radio>
              <el-radio
                v-if="allowedMenuTypeValues.includes(MenuTypeEnum.MENU)"
                :value="MenuTypeEnum.MENU"
              >
                {{ t("system.menu.menu") }}
              </el-radio>
              <el-radio
                v-if="allowedMenuTypeValues.includes(MenuTypeEnum.BUTTON)"
                :value="MenuTypeEnum.BUTTON"
              >
                {{ t("system.menu.button") }}
              </el-radio>
              <el-radio
                v-if="allowedMenuTypeValues.includes(MenuTypeEnum.EXTLINK)"
                :value="MenuTypeEnum.EXTLINK"
              >
                {{ t("system.menu.extlink") }}
              </el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="formData.type == MenuTypeEnum.EXTLINK"
            :label="t('system.menu.extlinkAddress')"
            prop="path"
          >
            <el-input
              v-model="formData.route_path"
              :placeholder="t('system.menu.extlinkPlaceholder')"
            />
          </el-form-item>

          <el-form-item v-if="formData.type !== MenuTypeEnum.BUTTON" prop="route_name">
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.routeName") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    {{ t("system.menu.routeNameTooltip") }}
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>
            <el-input
              v-model="formData.route_name"
              :placeholder="t('system.menu.routeNamePlaceholder')"
            />
          </el-form-item>

          <el-form-item
            v-if="formData.type == MenuTypeEnum.CATALOG || formData.type == MenuTypeEnum.MENU"
            prop="route_path"
          >
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.routePath") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    {{ t("system.menu.routePathTooltip") }}
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>
            <el-input
              v-model="formData.route_path"
              :placeholder="t('system.menu.routePathPlaceholder')"
            />
          </el-form-item>

          <el-form-item v-if="formData.type == MenuTypeEnum.MENU" prop="component">
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.componentPath") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    {{ t("system.menu.componentPathTooltip") }}
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>

            <el-input
              v-model="formData.component_path"
              :placeholder="t('system.menu.componentPathPlaceholder')"
              style="width: 95%"
            >
              <template v-if="formData.type == MenuTypeEnum.MENU" #prepend>src/views/</template>
              <template v-if="formData.type == MenuTypeEnum.MENU" #append>.vue</template>
            </el-input>
          </el-form-item>

          <el-form-item v-if="formData.type == MenuTypeEnum.MENU">
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.params") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    {{ t("system.menu.paramsTooltip") }}
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>

            <div
              v-if="
                !formData.params || (Array.isArray(formData.params) && formData.params.length === 0)
              "
            >
              <el-button type="success" plain @click="formData.params = [{ key: '', value: '' }]">
                {{ t("system.menu.addParam") }}
              </el-button>
            </div>

            <div v-else>
              <div v-for="(item, index) in formData.params" :key="index">
                <el-input
                  v-model="item.key"
                  :placeholder="t('system.menu.paramName')"
                  style="width: 100px"
                />

                <span class="mx-1">=</span>

                <el-input
                  v-model="item.value"
                  :placeholder="t('system.menu.paramValue')"
                  style="width: 100px"
                />

                <el-icon
                  v-if="formData.params.indexOf(item) === formData.params.length - 1"
                  class="ml-2 cursor-pointer color-[var(--el-color-success)]"
                  style="vertical-align: -0.15em"
                  @click="formData.params.push({ key: '', value: '' })"
                >
                  <CirclePlusFilled />
                </el-icon>
                <el-icon
                  class="ml-2 cursor-pointer color-[var(--el-color-danger)]"
                  style="vertical-align: -0.15em"
                  @click="formData.params.splice(formData.params.indexOf(item), 1)"
                >
                  <DeleteFilled />
                </el-icon>
              </div>
            </div>
          </el-form-item>

          <el-form-item v-if="formData.type !== MenuTypeEnum.BUTTON">
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.hidden") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    <span style="white-space: pre-line">{{ t("system.menu.hiddenTooltip") }}</span>
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>

            <el-radio-group v-model="formData.hidden">
              <el-radio :value="true">{{ t("system.menu.yes") }}</el-radio>
              <el-radio :value="false">{{ t("system.menu.no") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="formData.type === MenuTypeEnum.CATALOG || formData.type === MenuTypeEnum.MENU"
          >
            <template #label>
              <div class="flex-y-center">
                {{ t("system.menu.alwaysShow") }}
                <el-tooltip placement="bottom" effect="light">
                  <template #content>
                    <span style="white-space: pre-line">
                      {{ t("system.menu.alwaysShowTooltip") }}
                    </span>
                  </template>
                  <el-icon class="ml-1 cursor-pointer">
                    <QuestionFilled />
                  </el-icon>
                </el-tooltip>
              </div>
            </template>

            <el-radio-group v-model="formData.always_show">
              <el-radio :value="true">{{ t("system.menu.yes") }}</el-radio>
              <el-radio :value="false">{{ t("system.menu.no") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="formData.type === MenuTypeEnum.MENU"
            :label="t('system.menu.cachePage')"
          >
            <el-radio-group v-model="formData.keep_alive">
              <el-radio :value="true">{{ t("system.menu.open") }}</el-radio>
              <el-radio :value="false">{{ t("system.menu.close") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('system.menu.order')" prop="order">
            <el-input-number v-model="formData.order" controls-position="right" :min="1" />
          </el-form-item>

          <!-- 权限标识 -->
          <el-form-item
            v-if="formData.type == MenuTypeEnum.BUTTON || formData.type === MenuTypeEnum.MENU"
            :label="t('system.menu.permission')"
            prop="perm"
          >
            <el-input
              v-model="formData.permission"
              :placeholder="t('system.menu.permissionPlaceholder')"
            />
          </el-form-item>

          <el-form-item
            v-if="formData.type !== MenuTypeEnum.BUTTON"
            :label="t('system.menu.icon')"
            prop="icon"
          >
            <!-- 图标选择器 -->
            <icon-select v-model="formData.icon" />
          </el-form-item>

          <el-form-item
            v-if="formData.type == MenuTypeEnum.CATALOG || formData.type === MenuTypeEnum.MENU"
            :label="t('system.menu.redirect')"
            prop="redirect"
            :required="formData.type === MenuTypeEnum.CATALOG"
          >
            <el-input
              v-model="formData.redirect"
              :placeholder="
                formData.type === MenuTypeEnum.CATALOG
                  ? t('system.menu.redirectCatalogPlaceholder')
                  : t('system.menu.redirectPlaceholder')
              "
            />
          </el-form-item>

          <el-form-item
            v-if="formData.type != MenuTypeEnum.BUTTON"
            :label="t('system.menu.affixLabel')"
            prop="affix"
          >
            <el-radio-group v-model="formData.affix">
              <el-radio :value="true">{{ t("system.menu.yes") }}</el-radio>
              <el-radio :value="false">{{ t("system.menu.no") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('system.menu.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.menu.enable") }}</el-radio>
              <el-radio value="1">{{ t("system.menu.disabled") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('system.menu.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.menu.descriptionPlaceholder')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <!-- 详情弹窗不需要确定按钮的提交逻辑 -->
          <el-button v-if="dialogVisible.type !== 'detail'" type="primary" @click="handleSubmit">
            {{ t("system.menu.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.menu.confirm") }}
          </el-button>
          <el-button @click="handleCloseDialog">{{ t("system.menu.cancel") }}</el-button>
        </div>
      </template>
    </EnhancedDrawer>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "SysMenu",
  inheritAttrs: false,
});

import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { ref, reactive, computed, watch, nextTick } from "vue";
import { useAppStore } from "@/store/modules/app.store";
import { useUserStore } from "@/store/modules/user.store";
import { DeviceEnum } from "@/enums/settings/device.enum";

import MenuAPI, { MenuPageQuery, MenuForm, MenuTable } from "@/api/module_system/menu";
import { MenuTypeEnum } from "@/enums/system/menu.enum";
import { formatTree } from "@/utils/common";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDrawer from "@/components/CURD/EnhancedDrawer.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";

const { t } = useI18n();

const appStore = useAppStore();
const userStore = useUserStore();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const submitLoading = ref(false);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:menu",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("system.menu.menuName"),
      type: "input",
      attrs: { placeholder: t("system.menu.menuNamePlaceholder"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.menu.status"),
      type: "select",
      options: [
        { label: t("system.menu.enable"), value: "0" },
        { label: t("system.menu.disable"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.menu.statusPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.menu.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.menu.rangeSeparator"),
        startPlaceholder: t("system.menu.startDate"),
        endPlaceholder: t("system.menu.endDate"),
        style: { width: "340px" },
      },
    },
  ],
});

const contentCols = reactive([{ prop: "name", label: t("system.menu.menuName"), show: true }]);

// 详情表单
const detailFormData = ref<MenuTable>({});

// 编辑表单
const formData = reactive<MenuForm>({
  id: undefined,
  name: undefined,
  type: MenuTypeEnum.CATALOG,
  icon: undefined,
  order: 999,
  permission: "",
  route_name: "",
  route_path: "",
  component_path: undefined,
  redirect: undefined,
  parent_id: undefined,
  keep_alive: false,
  hidden: false,
  always_show: false,
  title: "",
  params: undefined,
  affix: false,
  status: "0",
  description: undefined,
});

// 弹窗状态
const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const drawerSize = computed(() => (appStore.device === DeviceEnum.DESKTOP ? "600px" : "90%"));

// 顶级菜单下拉选项（仅目录、菜单可作为父级）
const menuOptions = ref<OptionType[]>([]);
/** 完整树，用于根据 parent_id 解析父级类型 */
const fullMenuTree = ref<MenuTable[]>([]);
/** 从表格「在菜单下新增」进入时锁定父级（仅允许按钮） */
const createParentLocked = ref(false);

/** 目录下：目录、菜单、外链；菜单下：仅按钮 */
function typesAllowedUnderParent(parentType: MenuTypeEnum): MenuTypeEnum[] {
  switch (parentType) {
    case MenuTypeEnum.CATALOG:
      return [MenuTypeEnum.CATALOG, MenuTypeEnum.MENU, MenuTypeEnum.EXTLINK];
    case MenuTypeEnum.MENU:
      return [MenuTypeEnum.BUTTON];
    case MenuTypeEnum.BUTTON:
    case MenuTypeEnum.EXTLINK:
      return [];
    default:
      return [MenuTypeEnum.CATALOG, MenuTypeEnum.MENU, MenuTypeEnum.EXTLINK];
  }
}

function findMenuNodeById(
  id: number | undefined,
  nodes: MenuTable[] = fullMenuTree.value
): MenuTable | null {
  if (id == null) return null;
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children?.length) {
      const f = findMenuNodeById(id, n.children);
      if (f) return f;
    }
  }
  return null;
}

/** 新增/编辑表单项：当前父级下允许的菜单类型 */
const allowedMenuTypeValues = computed((): MenuTypeEnum[] => {
  if (dialogVisible.type === "detail") {
    return [MenuTypeEnum.CATALOG, MenuTypeEnum.MENU, MenuTypeEnum.BUTTON, MenuTypeEnum.EXTLINK];
  }
  const pid = formData.parent_id;
  if (pid == null || pid === undefined) {
    return [MenuTypeEnum.CATALOG, MenuTypeEnum.MENU, MenuTypeEnum.EXTLINK];
  }
  const parentNode = findMenuNodeById(pid);
  if (!parentNode?.type) {
    return [MenuTypeEnum.CATALOG, MenuTypeEnum.MENU, MenuTypeEnum.EXTLINK];
  }
  return typesAllowedUnderParent(parentNode.type as MenuTypeEnum);
});

watch(
  () => [formData.parent_id, dialogVisible.visible, dialogVisible.type],
  () => {
    if (!dialogVisible.visible || dialogVisible.type === "detail") return;
    const allowed = allowedMenuTypeValues.value;
    if (!allowed.length) return;
    const currentType = formData.type as MenuTypeEnum;
    if (!allowed.includes(currentType)) {
      formData.type = allowed[0] as MenuForm["type"];
    }
  },
  { flush: "post" }
);

function filterMenuTypes(nodes: MenuTable[]) {
  return nodes
    .filter((node) => node.type === MenuTypeEnum.CATALOG || node.type === MenuTypeEnum.MENU)
    .map((node: any): any => ({
      ...node,
      children: node.children ? filterMenuTypes(node.children) : [],
    }));
}

const contentConfig = reactive<IContentConfig<MenuPageQuery>>({
  permPrefix: "module_system:menu",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: false,
  indexAction: async (params) => {
    const res = await MenuAPI.listMenu(params as MenuPageQuery);
    const tree = res.data.data || [];
    fullMenuTree.value = tree;
    menuOptions.value = formatTree(filterMenuTypes(tree));
    return tree;
  },
  deleteAction: async (ids) => {
    await MenuAPI.deleteMenu(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    await userStore.getUserInfo();
  },
  deleteConfirm: {
    title: t("system.menu.warning"),
    message: t("system.menu.deleteConfirmMessage"),
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

// 表单验证规则
const rules = reactive({
  name: [
    { required: true, message: t("system.menu.menuNameRequired"), trigger: "blur" },
    {
      min: 2,
      max: 50,
      message: t("system.menu.lengthBetween", { min: 2, max: 50 }),
      trigger: "blur",
    },
  ],
  parent_id: [{ required: true, message: t("system.menu.parentMenuRequired"), trigger: "blur" }],
  type: [{ required: true, message: t("system.menu.typeRequired"), trigger: "blur" }],
  order: [{ required: true, message: t("system.menu.orderRequired"), trigger: "blur" }],
  permission: [{ required: true, message: t("system.menu.permissionRequired"), trigger: "blur" }],
  route_name: [{ required: true, message: t("system.menu.routeNameRequired"), trigger: "blur" }],
  route_path: [
    { required: true, message: t("system.menu.routePathRequired"), trigger: "blur" },
    {
      validator: (rule: any, value: string, callback: any) => {
        if (value && !value.startsWith("/")) {
          callback(new Error(t("system.menu.routePathStartSlash")));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
  component_path: [
    { required: true, message: t("system.menu.componentPathRequired"), trigger: "blur" },
  ],
  title: [
    { required: true, message: t("system.menu.titleRequired"), trigger: "blur" },
    {
      min: 2,
      max: 50,
      message: t("system.menu.lengthBetween", { min: 2, max: 50 }),
      trigger: "blur",
    },
  ],
  keep_alive: [{ required: true, message: t("system.menu.keepAliveRequired"), trigger: "change" }],
  hidden: [{ required: true, message: t("system.menu.hiddenRequired"), trigger: "change" }],
  always_show: [
    { required: true, message: t("system.menu.alwaysShowRequired"), trigger: "change" },
  ],
  status: [{ required: true, message: t("system.menu.statusRequired"), trigger: "change" }],
  redirect: [
    {
      validator: (_rule: unknown, value: string | undefined, callback: (e?: Error) => void) => {
        if (formData.type === MenuTypeEnum.CATALOG) {
          if (value === undefined || value === null || String(value).trim() === "") {
            callback(new Error(t("system.menu.redirectCatalogRequired")));
            return;
          }
        }
        callback();
      },
      trigger: "blur",
    },
  ],
});

// 选择表格的行菜单ID
const selectedMenuId = ref<number | undefined>();

// 定义初始表单数据常量
const initialFormData: MenuForm = {
  id: undefined,
  name: undefined,
  type: MenuTypeEnum.MENU,
  icon: undefined,
  order: 1,
  permission: "",
  route_name: "",
  route_path: "",
  component_path: "",
  redirect: "",
  parent_id: undefined,
  keep_alive: false,
  hidden: false,
  always_show: false,
  title: "",
  params: [] as { key: string; value: string }[],
  affix: false,
  status: "0",
  description: undefined,
};

// 重置表单
async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  // 完全重置 formData 为初始状态
  Object.assign(formData, initialFormData);
}

// 行点击事件
async function handleRowClick(row: MenuTable) {
  selectedMenuId.value = row.id;
}

// 关闭弹窗
async function handleCloseDialog() {
  dialogVisible.visible = false;
  createParentLocked.value = false;
  resetForm();
}

//打开弹窗
async function handleOpenDialog(
  type: "create" | "update" | "detail",
  id?: number,
  parentRow?: MenuTable
) {
  dialogVisible.type = type;
  createParentLocked.value = false;
  if (id) {
    const response = await MenuAPI.detailMenu(id);
    if (type === "detail") {
      dialogVisible.title = t("system.menu.menuDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.menu.updateMenu");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.menu.createMenu");
    Object.assign(formData, initialFormData);
    if (parentRow?.id != null) {
      formData.parent_id = parentRow.id;
      if (parentRow.type === MenuTypeEnum.MENU) {
        createParentLocked.value = true;
        formData.type = MenuTypeEnum.BUTTON;
      } else if (parentRow.type === MenuTypeEnum.CATALOG) {
        formData.type = MenuTypeEnum.MENU;
      }
    }
  }
  dialogVisible.visible = true;
}

// 菜单类型切换
function handleMenuTypeChange() {
  if (formData.type === MenuTypeEnum.MENU) {
    formData.component_path = "";
  }
  nextTick(() => {
    dataFormRef.value?.clearValidate("redirect");
    if (formData.type === MenuTypeEnum.CATALOG) {
      dataFormRef.value?.validateField("redirect").catch(() => {});
    }
  });
}

// 提交表单
async function handleSubmit() {
  const allowed = allowedMenuTypeValues.value;
  if (!allowed.includes(formData.type as MenuTypeEnum)) {
    ElMessage.warning(t("system.menu.typeNotAllowed"));
    return;
  }
  dataFormRef.value.validate(async (valid: any) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          await MenuAPI.updateMenu(id, formData);
        } else {
          await MenuAPI.createMenu(formData);
        }
        ElMessage.success(t("system.menu.operationSuccess"));
        await userStore.getUserInfo();
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch (error: any) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as MenuTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.menu.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(
    t("system.menu.batchStatusConfirm", {
      action: status === "0" ? t("system.menu.enable") : t("system.menu.disable"),
    }),
    t("system.menu.warning"),
    {
      confirmButtonText: t("system.menu.confirm"),
      cancelButtonText: t("system.menu.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await MenuAPI.batchMenu({ ids, status });
        ElMessage.success(t("system.menu.operationSuccess"));
        refreshList();
      } catch (error: any) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}
</script>
