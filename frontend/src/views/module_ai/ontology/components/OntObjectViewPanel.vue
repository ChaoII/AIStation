<!--
  对象视图面板（对象类型 → 对象视图）

  对齐官方 object-views：
  · Standard（自动生成）vs Configured（可配置），可切换
  · Full（完整）vs Panel（面板）两种形态
  · 配置模型 tabs → widgets
  · 默认视图自动创建；**一旦编辑就转为 user-managed**（不再跟随对象类型）
  · 版本管理；权限跟随对象类型
-->
<template>
  <section class="ont-ov">
    <div class="ont-sec__head">
      <span class="ont-sec__title">{{ i18nT("ai_ontology.objectView") }}</span>
      <el-radio-group v-model="formFactor" size="small" @change="reload">
        <el-radio-button value="full">{{ i18nT("ai_ontology.fullView") }}</el-radio-button>
        <el-radio-button value="panel">{{ i18nT("ai_ontology.panelView") }}</el-radio-button>
      </el-radio-group>
      <el-tag size="small" effect="plain" :type="current?.is_managed ? 'warning' : 'success'">
        {{
          current?.is_managed
            ? i18nT("ai_ontology.manualMaintenance")
            : i18nT("ai_ontology.followObjectType")
        }}
      </el-tag>
      <el-button class="ont-sec__op" size="small" type="primary" :icon="Plus" @click="openEditor()">
        {{ i18nT("ai_ontology.newView") }}
      </el-button>
      <el-dropdown class="ont-sec__op" @command="onViewMore">
        <el-button size="small">
          {{ i18nT("ai_ontology.more") }}
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="edit" :disabled="!current" :icon="Edit">
              {{ i18nT("ai_ontology.edit") }}
            </el-dropdown-item>
            <el-dropdown-item command="share" :disabled="!current" :icon="Share">
              {{ i18nT("ai_ontology.share") }}
            </el-dropdown-item>
            <el-dropdown-item command="link" :disabled="!current" :icon="Link">
              {{ i18nT("ai_ontology.copyLink") }}
            </el-dropdown-item>
            <el-dropdown-item command="refresh" :icon="Refresh">
              {{ i18nT("ai_ontology.refresh") }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="ont-note"
      :title="i18nT('ai_ontology.viewInfoAlert')"
    />

    <el-tabs v-model="activeTab" class="ont-ov__tabs">
      <el-tab-pane :label="i18nT('ai_ontology.configPreview')" name="config">
        <div class="ont-ov__switch">
          <span class="ont-hint">{{ i18nT("ai_ontology.compare2") }}</span>
          <el-radio-group v-model="previewMode" size="small">
            <el-radio-button value="configured">
              {{ i18nT("ai_ontology.configurableView") }}
            </el-radio-button>
            <el-radio-button value="standard">
              {{ i18nT("ai_ontology.standardViewAuto") }}
            </el-radio-button>
          </el-radio-group>
          <el-input
            v-model="objectKey"
            size="small"
            :placeholder="i18nT('ai_ontology.objectPrimaryKey')"
            style="width: 140px"
          />
          <el-button size="small" type="primary" :loading="rendering" @click="doRender">
            {{ i18nT("ai_ontology.render") }}
          </el-button>
        </div>

        <el-empty
          v-if="!tabsShown.length"
          :image-size="60"
          :description="i18nT('ai_ontology.noViewsYetClickNewViewOrLetTheSystemAutoGenerate')"
        />

        <el-tabs v-else v-model="activeRenderTab" type="border-card">
          <el-tab-pane v-for="t in tabsShown" :key="t.key" :label="t.label" :name="t.key">
            <el-alert
              v-if="t.filters && t.filters.length"
              type="warning"
              :closable="false"
              class="ont-note"
              :title="filterSummary(t.filters)"
            />
            <div v-for="(w, i) in t.widgets || []" :key="i" class="ont-ov__widget">
              <div class="ont-ov__whead">
                <span class="ont-ov__wtitle">{{ w.title || w.label }}</span>
                <el-tag size="small" effect="plain">{{ w.category_label || w.label }}</el-tag>
                <el-tag v-if="w.count != null" size="small" effect="plain" type="info">
                  {{ w.count }}
                </el-tag>
                <el-tag v-if="w.error" size="small" type="danger" effect="plain">
                  {{ w.error }}
                </el-tag>
              </div>
              <!-- 属性列表 -->
              <el-descriptions v-if="w.type === 'properties'" :column="2" border size="small">
                <el-descriptions-item v-for="it in w.items" :key="it.code" :label="it.name">
                  {{ it.value ?? "—" }}
                  <el-tag v-if="it.sensitive" size="small" type="danger" effect="plain">
                    {{ i18nT("ai_ontology.sensitive") }}
                  </el-tag>
                </el-descriptions-item>
              </el-descriptions>
              <!-- 关系 / 关联对象 -->
              <el-table
                v-else-if="w.type === 'links'"
                :data="w.items || []"
                size="small"
                border
                stripe
              >
                <el-table-column
                  prop="name"
                  :label="i18nT('ai_ontology.relation')"
                  min-width="140"
                />
                <el-table-column
                  prop="target_object"
                  :label="i18nT('ai_ontology.targetObjectType2')"
                  min-width="140"
                />
                <el-table-column prop="card" :label="i18nT('ai_ontology.cardinality')" width="90" />
              </el-table>
              <el-table
                v-else-if="w.type === 'related'"
                :data="w.rows || []"
                size="small"
                border
                stripe
              >
                <el-table-column
                  v-for="c in relatedCols(w)"
                  :key="c"
                  :prop="`props.${c}`"
                  :label="c"
                  min-width="120"
                  show-overflow-tooltip
                />
              </el-table>
              <!-- 指标卡 -->
              <el-statistic
                v-else-if="w.type === 'metric'"
                :value="Number(w.value) || 0"
                :title="w.label"
              >
                <template #suffix>{{ w.unit }}</template>
              </el-statistic>
              <!-- 图表 -->
              <div v-else-if="w.type === 'chart'" class="ont-ov__chart">
                <div v-for="s in w.series || []" :key="s.label" class="ont-ov__bar">
                  <span class="ont-ov__barlabel">{{ s.label }}</span>
                  <el-progress
                    :percentage="pct(s.value, w.series)"
                    :show-text="false"
                    :stroke-width="14"
                  />
                  <span class="ont-mono">{{ s.value }}</span>
                </div>
              </div>
              <!-- 对象表格（筛选器对它生效） -->
              <el-table
                v-else-if="w.type === 'table'"
                :data="w.rows || []"
                size="small"
                border
                max-height="320"
                stripe
              >
                <el-table-column
                  v-for="c in (w.columns || []).slice(0, 6)"
                  :key="c"
                  :label="c"
                  min-width="110"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{ row.props?.[c] ?? "—" }}</template>
                </el-table-column>
              </el-table>
              <!-- 动作 -->
              <div v-else-if="w.type === 'actions'">
                <el-tag
                  v-for="a in w.items || []"
                  :key="a.code"
                  size="small"
                  effect="plain"
                  class="ont-tag-gap"
                >
                  {{ a.name }}
                </el-tag>
              </div>
              <el-input
                v-else-if="w.type === 'text'"
                :model-value="w.markdown"
                type="textarea"
                :rows="3"
                readonly
              />
              <el-select
                v-else-if="w.type === 'scenario'"
                v-model="viewScen"
                size="small"
                clearable
                :placeholder="i18nT('ai_ontology.primaryOntology')"
                class="ont-ov__scen"
                @change="doRender"
              >
                <el-option
                  :label="i18nT('ai_ontology.primaryOntologyNoScenarioOverlay')"
                  value=""
                />
                <el-option
                  v-for="s in w.items || []"
                  :key="s.code"
                  :label="s.name || s.code"
                  :value="s.code"
                />
              </el-select>
              <!-- 筛选器：列出条件，并说明它作用于同标签页的数据组件 -->
              <div v-else-if="w.type === 'filter'" class="ont-ov__filters">
                <div v-for="(f, fi) in w.filters || []" :key="fi" class="ont-ov__frow">
                  <el-tag size="small" effect="plain">{{ f.prop }}</el-tag>
                  <span class="ont-mono">{{ f.op_label }}</span>
                  <span v-if="f.value !== undefined && f.value !== ''" class="ont-mono">
                    {{ f.value }}
                  </span>
                </div>
                <div class="ont-hint">
                  {{ w.applies_to }}
                  <el-tag
                    v-if="w.active"
                    size="small"
                    type="warning"
                    effect="plain"
                    class="ont-tag-gap"
                  >
                    {{ i18nT("ai_ontology.active") }}
                  </el-tag>
                </div>
              </div>
              <div v-else class="ont-hint">
                {{ i18nT("ai_ontology.noPreviewForThisComponentType") }}
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <el-tab-pane :label="i18nT('ai_ontology.viewList')" name="list">
        <el-table :data="views" size="small" border stripe>
          <template #empty>
            <el-empty :image-size="50" :description="i18nT('ai_ontology.noViews')" />
          </template>
          <el-table-column
            prop="name"
            :label="i18nT('ai_ontology.view')"
            min-width="200"
            show-overflow-tooltip
          />
          <el-table-column
            prop="code"
            :label="i18nT('ai_ontology.code')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="form_factor_label"
            :label="i18nT('ai_ontology.shape')"
            width="100"
          />
          <el-table-column :label="i18nT('ai_ontology.default')" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" size="small" type="success" effect="plain">
                {{ i18nT("ai_ontology.default") }}
              </el-tag>
              <span v-else class="ont-none">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="i18nT('ai_ontology.maintenanceMode')" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="row.is_managed ? 'warning' : 'success'">
                {{ row.is_managed ? i18nT("ai_ontology.manual") : i18nT("ai_ontology.auto") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="i18nT('ai_ontology.tabsWidgets')" width="110" align="center">
            <template #default="{ row }">{{ row.tab_count }} / {{ row.widget_count }}</template>
          </el-table-column>
          <el-table-column
            prop="version"
            :label="i18nT('ai_ontology.version')"
            width="70"
            align="center"
          />
          <el-table-column
            :label="i18nT('ai_ontology.operations')"
            width="220"
            align="center"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button icon="edit" link type="primary" size="small" @click="openEditor(row)">
                {{ i18nT("ai_ontology.edit") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:edit'"
                icon="Star"
                link
                type="primary"
                size="small"
                :disabled="row.is_default"
                @click="doSetDefault(row)"
              >
                {{ i18nT("ai_ontology.setAsDefault") }}
              </el-button>
              <el-button link type="primary" size="small" @click="openVersions(row)">
                {{ i18nT("ai_ontology.version") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:edit'"
                icon="delete"
                link
                type="danger"
                size="small"
                @click="doRemove(row)"
              >
                {{ i18nT("ai_ontology.delete2") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑器 -->
    <el-dialog
      v-model="editorVisible"
      :title="i18nT('ai_ontology.editObjectView')"
      width="900px"
      append-to-body
    >
      <el-form label-width="100px">
        <el-form-item :label="i18nT('ai_ontology.viewName')">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.shape')">
          <el-radio-group v-model="form.form_factor">
            <el-radio-button value="full">{{ i18nT("ai_ontology.fullView") }}</el-radio-button>
            <el-radio-button value="panel">{{ i18nT("ai_ontology.panelView") }}</el-radio-button>
          </el-radio-group>
          <span class="ont-hint">
            {{ i18nT("ai_ontology.panelViewHoldsKeyInfoForEmbeddingByOtherApps") }}
          </span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.setAsDefault')">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>

      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.tabsAndComponents") }}</span>
        <el-button class="ont-sec__op" size="small" :icon="Plus" @click="addTab">
          {{ i18nT("ai_ontology.addTab") }}
        </el-button>
      </div>
      <el-collapse v-model="openTabs">
        <el-collapse-item v-for="(t, ti) in form.tabs" :key="ti" :name="String(ti)">
          <template #title>
            <span>{{ t.label || t.key || i18nT("ai_ontology.tabIndex", { index: ti + 1 }) }}</span>
            <el-tag size="small" effect="plain" class="ont-tag-gap">
              {{ i18nT("ai_ontology.componentCount", { count: (t.widgets || []).length }) }}
            </el-tag>
          </template>
          <el-form label-width="80px" size="small">
            <el-form-item :label="i18nT('ai_ontology.title')">
              <el-input v-model="t.label" style="width: 220px" />
            </el-form-item>
          </el-form>
          <div v-for="(w, wi) in t.widgets || []" :key="wi" class="ont-ov__wedit">
            <el-select v-model="w.type" size="small" style="width: 150px">
              <el-option
                v-for="m in meta.widgets"
                :key="m.value"
                :label="m.label"
                :value="m.value"
              />
            </el-select>
            <el-input
              v-model="w.title"
              size="small"
              :placeholder="i18nT('ai_ontology.componentTitle')"
              style="width: 180px"
            />
            <el-select
              v-if="w.type === 'properties'"
              v-model="w.config.props"
              multiple
              filterable
              collapse-tags
              size="small"
              :placeholder="i18nT('ai_ontology.leaveEmptyAllProperties')"
              style="width: 260px"
            >
              <el-option v-for="p in props_" :key="p.code" :label="p.name" :value="p.code" />
            </el-select>
            <el-select
              v-else-if="w.type === 'links'"
              v-model="w.config.link_ids"
              multiple
              size="small"
              :placeholder="i18nT('ai_ontology.leaveEmptyAllRelations')"
              style="width: 220px"
            >
              <el-option v-for="l in links" :key="l.id" :label="l.name" :value="l.id" />
            </el-select>
            <el-select
              v-else-if="w.type === 'related'"
              v-model="w.config.link_id"
              size="small"
              :placeholder="i18nT('ai_ontology.pickARelation')"
              style="width: 200px"
            >
              <el-option v-for="l in links" :key="l.id" :label="l.name" :value="l.id" />
            </el-select>
            <template v-else-if="w.type === 'chart'">
              <el-select
                v-model="w.config.group_by"
                size="small"
                :placeholder="i18nT('ai_ontology.groupField')"
                style="width: 180px"
              >
                <el-option v-for="p in props_" :key="p.code" :label="p.name" :value="p.code" />
              </el-select>
            </template>
            <!-- 筛选器：作用于同一标签页的数据组件 -->
            <template v-else-if="w.type === 'filter'">
              <div class="ont-ov__filters">
                <div v-for="(f, fi) in w.config.filters || []" :key="fi" class="ont-ov__frow">
                  <el-select
                    v-model="f.prop"
                    size="small"
                    filterable
                    :placeholder="i18nT('ai_ontology.field')"
                    style="width: 150px"
                  >
                    <el-option v-for="p in props_" :key="p.code" :label="p.name" :value="p.code" />
                  </el-select>
                  <el-select v-model="f.op" size="small" style="width: 110px">
                    <el-option
                      v-for="o in filterOps"
                      :key="o.value"
                      :label="o.label"
                      :value="o.value"
                    />
                  </el-select>
                  <el-input
                    v-model="f.value"
                    size="small"
                    :placeholder="i18nT('ai_ontology.value')"
                    style="width: 130px"
                    :disabled="f.op === 'is_empty' || f.op === 'not_empty'"
                  />
                  <el-button
                    size="small"
                    :icon="Delete"
                    circle
                    @click="w.config.filters.splice(fi, 1)"
                  />
                </div>
                <el-button size="small" :icon="Plus" @click="addFilter(w)">
                  {{ i18nT("ai_ontology.addCondition") }}
                </el-button>
                <span class="ont-hint">{{ i18nT("ai_ontology.filterAppliesHint") }}</span>
              </div>
            </template>
            <template v-else-if="w.type === 'metric'">
              <el-input
                v-model="w.config.prop"
                size="small"
                :placeholder="i18nT('ai_ontology.attributeId')"
                style="width: 140px"
              />
              <el-select
                v-model="w.config.function_code"
                size="small"
                clearable
                :placeholder="i18nT('ai_ontology.orPickAFunction')"
                style="width: 180px"
              >
                <el-option v-for="f in funcs" :key="f.code" :label="f.name" :value="f.code" />
              </el-select>
            </template>
            <el-select
              v-else-if="w.type === 'actions'"
              v-model="w.config.action_codes"
              multiple
              size="small"
              :placeholder="i18nT('ai_ontology.leaveEmptyAllActions')"
              style="width: 220px"
            >
              <el-option v-for="a in actions" :key="a.code" :label="a.name" :value="a.code" />
            </el-select>
            <el-input
              v-else-if="w.type === 'text'"
              v-model="w.config.markdown"
              size="small"
              :placeholder="i18nT('ai_ontology.descriptionText')"
              style="width: 300px"
            />
            <el-button size="small" :icon="Delete" circle @click="t.widgets.splice(wi, 1)" />
          </div>
          <el-button size="small" :icon="Plus" @click="addWidget(t)">
            {{ i18nT("ai_ontology.addComponent") }}
          </el-button>
          <el-button size="small" type="danger" plain @click="form.tabs.splice(ti, 1)">
            {{ i18nT("ai_ontology.removeTab") }}
          </el-button>
        </el-collapse-item>
      </el-collapse>
      <template #footer>
        <el-button @click="editorVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="saving"
          @click="doSave"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 共享 -->
    <el-dialog
      v-model="shareVisible"
      :title="i18nT('ai_ontology.sharedView')"
      width="600px"
      append-to-body
    >
      <el-form label-width="110px">
        <el-form-item :label="i18nT('ai_ontology.shareMode')">
          <el-radio-group v-model="shareForm.share_mode">
            <el-radio-button value="inherit">
              {{ i18nT("ai_ontology.followObjectType") }}
            </el-radio-button>
            <el-radio-button value="roles">{{ i18nT("ai_ontology.shareByRole") }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="shareForm.share_mode === 'roles'"
          :label="i18nT('ai_ontology.visibleRoles')"
        >
          <el-select v-model="shareForm.share_roles" multiple filterable style="width: 100%">
            <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert
        type="warning"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.shareViewAlert')"
      />
      <template #footer>
        <el-button @click="shareVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="saving"
          @click="doShare"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>
    <!-- 版本 -->
    <el-dialog
      v-model="verVisible"
      :title="i18nT('ai_ontology.viewVersion')"
      width="600px"
      append-to-body
    >
      <el-table :data="versions" size="small" border stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noHistoricalVersions')" />
        </template>
        <el-table-column prop="version" :label="i18nT('ai_ontology.version')" width="80" />
        <el-table-column
          prop="note"
          :label="i18nT('ai_ontology.note')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column prop="created_by" :label="i18nT('ai_ontology.modifiedBy')" width="120" />
        <el-table-column prop="created_time" :label="i18nT('ai_ontology.time')" width="160" />
        <el-table-column :label="i18nT('ai_ontology.operations')" width="90" align="center">
          <template #default="{ row }">
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              icon="RefreshLeft"
              link
              type="primary"
              size="small"
              @click="doRestore(row)"
            >
              {{ i18nT("ai_ontology.rollback") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, Delete, Edit, Link, Plus, Refresh, Share } from "@element-plus/icons-vue";
import {
  getOntFilterOps,
  getOntObjectViewLink,
  getOntObjectViewMeta,
  getOntObjectViewVersions,
  getOntObjectViews,
  getOntProperties,
  getOntSecuritySubjects,
  getOntStandardView,
  removeOntObjectView,
  renderOntObjectView,
  restoreOntObjectView,
  saveOntObjectView,
  searchOntInstances,
  setDefaultOntObjectView,
  shareOntObjectView,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string; presetView?: string; presetKey?: string }>();

const { links: allLinks, actions: allActions, functions: allFuncs } = useOntologyData();
/** 本对象类型的属性列表（供「属性 / 图表分组 / 筛选字段」三个下拉使用）。
 *
 *  ⚠️ 不能用 composable 的 `scopedProperties`：它是**属性总数（number）**，
 *  拿它做 `v-for` 会渲染出 N 个「标签与值全空」的选项，等于配置对象视图时选不了任何属性
 *  （实测 bug）。这里按当前对象类型单独取真实属性列表。
 */
const propsList = ref<any[]>([]);
async function loadProperties() {
  try {
    const r = await getOntProperties(props.code);
    propsList.value = r.data?.data || [];
  } catch {
    propsList.value = [];
  }
}
const props_ = computed(() => propsList.value);
const links = computed(() =>
  (allLinks.value || []).filter((x: any) => x.source_object === props.code)
);
const actions = computed(() =>
  (allActions.value || []).filter((x: any) => x.object_code === props.code)
);
const funcs = computed(() =>
  (allFuncs.value || []).filter((x: any) => x.object_code === props.code)
);
const meta = ref<any>({ widgets: [], form_factors: [] });
const views = ref<any[]>([]);
const current = ref<any>(null);
const formFactor = ref("full");
const activeTab = ref("config");
const previewMode = ref("configured");
const objectKey = ref("1");
const rendering = ref(false);
const rendered = ref<any>(null);
// 场景（P5）：对象视图里切换场景后，渲染走「基线 + 场景差异」
const viewScen = ref("");
const stdView = ref<any>(null);
const activeRenderTab = ref("");

const tabsShown = ref<any[]>([]);

/** 取对象类型的第一个真实实例 key（替代默认硬编码 "1"） */
async function pickFirstKey() {
  try {
    const r = await searchOntInstances(props.code, { limit: 1 });
    const items = r.data?.data?.items || [];
    return items[0]?.key || "";
  } catch {
    return "";
  }
}

async function reload() {
  try {
    await loadProperties();
    const [v, m] = await Promise.all([
      getOntObjectViews({ object_code: props.code, form_factor: formFactor.value }),
      meta.value.widgets?.length ? Promise.resolve(null) : getOntObjectViewMeta(),
    ]);
    views.value = v.data?.data || [];
    if (m) meta.value = m.data?.data || meta.value;
    if (!filterOps.value.length) {
      try {
        const fo = await getOntFilterOps();
        filterOps.value = fo.data?.data || [];
      } catch {
        filterOps.value = [];
      }
    }
    // 深链指定的视图优先（官方 generate-urls）
    if (props.presetView) {
      const want = views.value.find((x: any) => x.code === props.presetView);
      if (want) current.value = want;
    }
    if (!current.value) {
      current.value = views.value.find((x: any) => x.is_default) || views.value[0] || null;
    }
    if (props.presetKey) objectKey.value = props.presetKey;
    else if (!objectKey.value || objectKey.value === "1") {
      // 默认 "1" 常常不存在：取第一个真实实例作为渲染对象
      const k = await pickFirstKey();
      if (k) objectKey.value = k;
    }
    await doRender();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadViewFailed"));
  }
}

async function doRender() {
  rendering.value = true;
  try {
    if (previewMode.value === "standard") {
      if (!stdView.value) {
        const r = await getOntStandardView(props.code, formFactor.value);
        stdView.value = r.data?.data || null;
      }
      tabsShown.value = stdView.value?.tabs || [];
      activeRenderTab.value = tabsShown.value[0]?.key || "";
    } else if (current.value) {
      const r = await renderOntObjectView(
        current.value.code,
        objectKey.value || "1",
        viewScen.value || ""
      );
      rendered.value = r.data?.data || null;
      tabsShown.value = rendered.value?.tabs || [];
      activeRenderTab.value = tabsShown.value[0]?.key || "";
    } else {
      tabsShown.value = [];
    }
  } catch (e: any) {
    const msg = e?.msg || "";
    ElMessage.error(
      msg.includes(i18nT("ai_ontology.doesNotExist"))
        ? i18nT("ai_ontology.noInstancesToPreviewForThisObjectType")
        : msg || i18nT("ai_ontology.renderFailed")
    );
  } finally {
    rendering.value = false;
  }
}

function relatedCols(w: any) {
  const first = (w.rows || [])[0];
  return first ? Object.keys(first.props || {}).slice(0, 5) : [];
}
function pct(v: number, series: any[]) {
  const max = Math.max(...(series || []).map((s) => s.value), 1);
  return Math.round((v / max) * 100);
}

/* ---------------- 编辑器 ---------------- */
const editorVisible = ref(false);
const saving = ref(false);
const openTabs = ref<string[]>([]);
const form = reactive<any>({
  code: "",
  name: "",
  form_factor: "full",
  is_default: false,
  tabs: [],
});

function openEditor(row?: any) {
  if (row) {
    Object.assign(form, {
      code: row.code,
      name: row.name,
      form_factor: row.form_factor,
      is_default: row.is_default,
      tabs: JSON.parse(JSON.stringify(row.tabs || [])),
    });
  } else {
    Object.assign(form, {
      code: "",
      name: i18nT("ai_ontology.customViewName", { code: props.code }),
      form_factor: formFactor.value,
      is_default: false,
      tabs: [{ key: "overview", label: i18nT("ai_ontology.overview"), widgets: [] }],
    });
  }
  form.tabs.forEach((t: any) => {
    t.widgets = t.widgets || [];
    t.widgets.forEach((w: any) => (w.config = w.config || {}));
  });
  openTabs.value = form.tabs.map((_: any, i: number) => String(i));
  editorVisible.value = true;
}

function addTab() {
  form.tabs.push({
    key: `tab${form.tabs.length + 1}`,
    label: i18nT("ai_ontology.newTab"),
    widgets: [],
  });
}
function addWidget(t: any) {
  t.widgets = t.widgets || [];
  t.widgets.push({ type: "properties", title: "", config: {} });
}

function addFilter(w: any) {
  w.config = w.config || {};
  w.config.filters = w.config.filters || [];
  w.config.filters.push({ prop: "", op: "eq", value: "" });
}

async function doSave() {
  saving.value = true;
  try {
    const r = await saveOntObjectView({
      ...form,
      object_code: props.code,
      _mode: form.code ? "update" : "create",
    });
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.saved"));
    editorVisible.value = false;
    stdView.value = null;
    await reload();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    saving.value = false;
  }
}

async function doSetDefault(row: any) {
  await setDefaultOntObjectView(row.code);
  ElMessage.success(i18nT("ai_ontology.setAsDefaultView"));
  await reload();
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deleteObjectViewConfirm", { name: row.name, count: row.version }),
    i18nT("ai_ontology.deleteView"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await removeOntObjectView(row.code);
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await reload();
}

/* ---------------- 版本 ---------------- */
const verVisible = ref(false);
const versions = ref<any[]>([]);
const verCode = ref("");

async function openVersions(row: any) {
  verCode.value = row.code;
  const r = await getOntObjectViewVersions(row.code);
  versions.value = r.data?.data || [];
  verVisible.value = true;
}

async function doRestore(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.rollbackViewConfirm", { version: row.version }),
    i18nT("ai_ontology.rollbackView"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.rollback"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await restoreOntObjectView(verCode.value, row.version);
  ElMessage.success(i18nT("ai_ontology.rolledBack"));
  verVisible.value = false;
  await reload();
}

/* ---------------- 筛选器摘要 ---------------- */
function filterSummary(filters: any[]) {
  const parts = (filters || []).map(
    (f: any) => `${f.prop} ${f.op}${f.value !== undefined && f.value !== "" ? " " + f.value : ""}`
  );
  return i18nT("ai_ontology.activeFiltersSummary", {
    filters: parts.join(i18nT("ai_ontology.and")),
  });
}

/* ---------------- 共享 ---------------- */
const shareVisible = ref(false);
const shareForm = reactive<{ share_mode: string; share_roles: string[] }>({
  share_mode: "inherit",
  share_roles: [],
});
const roles = ref<any[]>([]);
const filterOps = ref<any[]>([]);

async function openShare() {
  if (!current.value) return;
  shareForm.share_mode = current.value.share_mode || "inherit";
  shareForm.share_roles = [...(current.value.share_roles || [])];
  if (!roles.value.length) {
    try {
      const r = await getOntSecuritySubjects();
      roles.value = r.data?.data?.roles || [];
    } catch {
      roles.value = [];
    }
  }
  shareVisible.value = true;
}

async function doShare() {
  saving.value = true;
  try {
    const r = await shareOntObjectView(
      current.value.code,
      shareForm.share_mode,
      shareForm.share_roles
    );
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.set"));
    shareVisible.value = false;
    await reload();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.setFailed"));
  } finally {
    saving.value = false;
  }
}

/* ---------------- 复制链接 ---------------- */
async function copyLink() {
  if (!current.value) return;
  try {
    const r = await getOntObjectViewLink(current.value.code, objectKey.value || "");
    const url = r.data?.data?.url || "";
    const abs = `${location.origin}${location.pathname}${url}`;
    await navigator.clipboard.writeText(abs);
    ElMessage.success(i18nT("ai_ontology.linkCopied", { url: abs }));
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.generateLinkFailed"));
  }
}

/** 「更多」下拉菜单动作分发 */
function onViewMore(cmd: string) {
  if (cmd === "edit") openEditor(current.value);
  else if (cmd === "share") openShare();
  else if (cmd === "link") copyLink();
  else if (cmd === "refresh") reload();
}
onMounted(reload);
</script>

<style lang="scss" scoped>
.ont-sec__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-sec__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-sec__op {
  margin-left: auto;
}
.ont-ov__tabs {
  margin-top: 8px;
}

.ont-ov__switch {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.ont-ov__widget {
  margin-bottom: 14px;
}

.ont-ov__whead {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.ont-ov__wtitle {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ont-ov__chart {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ont-ov__bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ont-ov__barlabel {
  min-width: 110px;
  color: var(--el-text-color-regular);
}

.ont-ov__filters {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ont-ov__frow {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.ont-ov__wedit {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}
</style>
