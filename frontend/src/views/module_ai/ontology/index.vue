<!--
  本体（Ontology）—— 对齐 Palantir Ontology Manager 的信息架构

  左栏双模式：
    · 未选资源 → 资源清单（Object types ⊃ Properties / Link types / Action types / …），计数徽标
    · 已选资源 → 该资源的子导航 + 顶部「返回」
  右栏：对应资源清单页，或选中资源的视图（对象类型 / 关系类型 / 动作类型）
-->
<template>
  <div class="app-container ai-mod ai-ontology-page">
    <el-row class="ont-row" :gutter="12">
      <!-- ================= 左栏：本体列表 ================= -->
      <el-col :xs="24" :sm="8" :md="6" :lg="5" class="ont-col">
        <el-card shadow="never" class="ont-side">
          <template #header>
            <div class="ont-side__head">
              <span class="ont-side__title">{{ i18nT("ai_ontology.ontologyDomain") }}</span>
              <div class="ont-side__head-ops">
                <el-button
                  v-hasPerm="'module_ai:ontology:edit'"
                  class="ont-side__add"
                  size="small"
                  type="primary"
                  plain
                  :icon="Plus"
                  :loading="domainSaving"
                  @click="openDomainForm()"
                >
                  {{ i18nT("ai_ontology.newOntologyDomain") }}
                </el-button>
                <el-button
                  class="ont-side__collapse"
                  size="small"
                  text
                  :icon="domainPanelCollapsed ? Expand : Fold"
                  :title="
                    domainPanelCollapsed
                      ? i18nT('ai_ontology.expandDomain')
                      : i18nT('ai_ontology.collapseDomain')
                  "
                  @click="domainPanelCollapsed = !domainPanelCollapsed"
                />
              </div>
            </div>
          </template>

          <div v-show="!domainPanelCollapsed" class="ont-domains">
            <div
              v-for="d in domains"
              :key="d.code"
              class="ont-dom-item"
              :class="{ 'is-active': currentDomain === d.code }"
              @click="onDomain(d.code)"
            >
              <el-icon class="ont-dom-item__icon"><Box /></el-icon>
              <span class="ont-dom-item__name" :title="d.name">{{ d.name }}</span>
              <el-dropdown
                class="ont-dom-item__ops"
                trigger="click"
                @command="(c: string) => onDomainCmd(c, d)"
                @click.stop
              >
                <el-icon class="ont-dom-item__more" @click.stop><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item icon="EditPen" command="rename">
                      {{ i18nT("ai_ontology.rename") }}
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-hasPerm="'module_ai:ontology:edit'"
                      icon="delete"
                      command="remove"
                      divided
                    >
                      {{ i18nT("ai_ontology.delete2") }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div v-if="!domains.length" class="ont-domains__empty">
              <el-empty
                :image-size="50"
                :description="i18nT('ai_ontology.noOntologyDomainsYetClickNewDomainToCreate')"
              />
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- ================= 右栏 ================= -->
      <el-col :xs="24" :sm="16" :md="18" :lg="19" class="ont-col">
        <el-card shadow="never" class="ont-main">
          <template #header>
            <div class="ont-main__head">
              <div class="ont-main__crumb">
                <span class="ont-crumb">
                  {{ i18nT("ai_ontology.ontology") }} / {{ i18nT("ai_ontology.graph2") }}
                </span>
                <el-tag size="small" type="info" effect="plain">
                  {{ currentDomainName }}
                </el-tag>
              </div>
              <div class="ont-main__ops">
                <el-tooltip
                  v-if="wipCount"
                  :content="i18nT('ai_ontology.wipNotSaved', { count: wipCount })"
                  placement="bottom"
                >
                  <el-badge :value="wipCount" :max="99" type="warning" class="ont-wip-badge">
                    <el-button
                      v-hasPerm="'module_ai:ontology:edit'"
                      size="small"
                      type="primary"
                      :icon="Check"
                      :loading="wipSaving"
                      @click="openReview"
                    >
                      {{ i18nT("ai_ontology.save") }}
                    </el-button>
                  </el-badge>
                </el-tooltip>
                <el-button
                  v-if="wipCount"
                  size="small"
                  :icon="RefreshLeft"
                  :disabled="wipSaving"
                  @click="discardWip"
                >
                  {{ i18nT("ai_ontology.discard") }}
                </el-button>
                <el-button size="small" :icon="Promotion" @click="goQuery">
                  {{ i18nT("ai_ontology.verifyWithAskData") }}
                </el-button>
                <el-button size="small" :icon="DataAnalysis" @click="overviewDrawer = true">
                  {{ i18nT("ai_ontology.overview") }}
                </el-button>
                <el-dropdown trigger="click" @command="onMaint">
                  <el-button v-hasPerm="'module_ai:ontology:edit'" size="small" :icon="Tools">
                    {{ i18nT("ai_ontology.maintain") }}
                    <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="enrich" :disabled="enrichLoading">
                        {{ i18nT("ai_ontology.enrichBusinessSemantic") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="seed" :disabled="seedLoading">
                        {{ i18nT("ai_ontology.writeSampleCapabilities") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="assign" divided>
                        {{ i18nT("ai_ontology.batchAssignDomain", { count: selected.length }) }}
                      </el-dropdown-item>
                      <el-dropdown-item command="pending">
                        {{
                          i18nT("ai_ontology.pendingVersionPublishCount", {
                            count: pendingVersions.length,
                          })
                        }}
                      </el-dropdown-item>
                      <el-dropdown-item command="analyze" divided>
                        {{ i18nT("ai_ontology.modelingAnalysisStructureDiagnosisSuggestions") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="derived">
                        {{ i18nT("ai_ontology.derivedPropertyProblemScan") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="syncviews">
                        {{ i18nT("ai_ontology.backfillDefaultObjectViews") }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </template>

          <!-- 维护动作（回填/写入示例）的**结果回显**：原先只写进 maintMsg 却从不渲染，
               用户点完"成功"却看不到任何反馈（实测缺口感） -->
          <el-alert
            v-if="maintMsg"
            type="success"
            :closable="true"
            show-icon
            class="ont-maint-msg"
            @close="maintMsg = ''"
          >
            {{ maintMsg }}
          </el-alert>

          <!-- ============ 图谱工作区 ============ -->
          <OntGraphWorkspace
            @node-tap="onGraphNodeTap"
            @link-draw="onGraphLinkDraw"
            @edge-ctx="onGraphEdgeCtx"
            @create-object="openObjectEdit()"
            @edit-object="onGraphEditObject"
            @delete-object="onGraphDeleteObject"
            @materialize-object="onGraphMaterializeObject"
            @maintain="onMaintain"
            @batch-delete="batchDeleteObjects"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- ================= 对象类型详情右侧抽屉（点图谱节点打开） ================= -->
    <el-drawer
      v-model="objectDrawer"
      :size="'50%'"
      :with-header="true"
      :title="i18nT('ai_ontology.objectTypeDetails')"
      destroy-on-close
      class="ont-obj-drawer"
    >
      <OntObjectTypeView
        v-if="selObject"
        :key="`objdetail-${selKey}`"
        :code="selKey"
        :page="objPage"
        :view-code="objectViewCode"
        :view-key="objectViewKey"
        @update:page="objPage = $event"
        @edit-object="openObjectEdit(selObject)"
        @new-action="openActionEdit()"
        @new-link="openLinkEdit()"
        @go-properties="goObjectProperties"
        @open-object="onGraphNodeTap"
        @open-link="openLinkDetail"
        @open-action="openActionDetail"
        @refresh="reloadAll"
      />
    </el-drawer>

    <!-- ================= 关系类型详情（此前 OntLinkTypeView 无任何入口） ================= -->
    <el-drawer
      v-model="linkDrawer"
      :size="'48%'"
      :with-header="true"
      :title="i18nT('ai_ontology.relationTypeDetails')"
      destroy-on-close
    >
      <el-tabs v-model="linkPage" class="ont-detail-tabs">
        <el-tab-pane :label="i18nT('ai_ontology.overview')" name="overview" />
        <el-tab-pane :label="i18nT('ai_ontology.security')" name="security" />
        <el-tab-pane :label="i18nT('ai_ontology.dataSource')" name="datasources" />
      </el-tabs>
      <OntLinkTypeView
        v-if="linkDrawer && selLinkId"
        :id="selLinkId"
        :key="`linkdetail-${selLinkId}`"
        :page="linkPage"
        @edit="editCurrentLink"
        @refresh="reloadAll"
      />
    </el-drawer>

    <!-- ================= 动作类型详情（此前 OntActionTypeView 无任何入口） ================= -->
    <el-drawer
      v-model="actionDrawer"
      :size="'48%'"
      :with-header="true"
      :title="i18nT('ai_ontology.actionTypeDetails')"
      destroy-on-close
    >
      <el-tabs v-model="actionPage" class="ont-detail-tabs">
        <el-tab-pane :label="i18nT('ai_ontology.overview')" name="overview" />
        <el-tab-pane :label="i18nT('ai_ontology.rule')" name="rules" />
        <el-tab-pane :label="i18nT('ai_ontology.parameter')" name="parameters" />
      </el-tabs>
      <OntActionTypeView
        v-if="actionDrawer && selActionCode"
        :key="`actdetail-${selActionCode}`"
        :code="selActionCode"
        :page="actionPage"
        @edit="editCurrentAction"
        @refresh="reloadAll"
      />
    </el-drawer>

    <!-- ================= 概览弹窗 ================= -->
    <EnhancedDialog
      v-model="overviewDrawer"
      :title="i18nT('ai_ontology.ontologyOverview')"
      width="600px"
    >
      <OntOverviewDrawer />
    </EnhancedDialog>

    <!-- ================= 维护弹窗（按面板切换） ================= -->
    <EnhancedDialog v-model="maintenanceDrawer" :title="maintPanelLabel" width="720px">
      <OntMaintenanceDrawer :panel="maintPanel" />
    </EnhancedDialog>

    <!-- ================= 弹窗 ================= -->
    <!-- 建模分析：结构诊断（对象/属性/关系统计 + 中心度 + 建议） -->
    <el-dialog
      v-model="analyzeDialog"
      :title="i18nT('ai_ontology.ontologyModelingAnalysis')"
      width="900px"
      append-to-body
    >
      <el-alert
        v-if="analyzeLoading"
        type="info"
        :closable="false"
        show-icon
        :title="i18nT('ai_ontology.analyzing')"
      />
      <template v-else-if="analyze">
        <el-descriptions :column="4" size="small" border>
          <el-descriptions-item :label="i18nT('ai_ontology.objectType')">
            {{ analyze.objects }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.property')">
            {{ analyze.properties }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.relation')">
            {{ analyze.links }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.action')">
            {{ analyze.actions }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.orphanObjects')">
            {{ analyze.isolated }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.missingPK')">
            {{ analyze.no_pk }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.connectedComponents')">
            {{ analyze.components }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.relationDensity')">
            {{ analyze.density }}
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          type="warning"
          :closable="false"
          show-icon
          class="ont-note"
          :title="i18nT('ai_ontology.modelingSuggestions')"
        >
          <ul class="ont-analyze__recs">
            <li v-for="(r, i) in analyze.recommendations || []" :key="i">{{ r }}</li>
          </ul>
        </el-alert>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.highestCentralityObjects") }}</span>
          <span class="ont-hint">
            {{ i18nT("ai_ontology.higherDegreeMeansMoreWorthDefiningActionsAndGovernance") }}
          </span>
        </div>
        <el-table :data="analyze.top_central || []" size="small" border max-height="240" stripe>
          <template #empty>
            <el-empty :image-size="50" :description="i18nT('ai_ontology.noObjectTypesYet')" />
          </template>
          <el-table-column
            :label="i18nT('ai_ontology.object')"
            min-width="200"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ row.name }}
              <span class="ont-mono">（{{ row.code }}）</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="degree"
            :label="i18nT('ai_ontology.degree')"
            width="80"
            align="center"
          />
          <el-table-column prop="in" :label="i18nT('ai_ontology.in')" width="70" align="center" />
          <el-table-column prop="out" :label="i18nT('ai_ontology.out')" width="70" align="center" />
        </el-table>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">
            {{ i18nT("ai_ontology.relationCardinalityDistribution") }}
          </span>
        </div>
        <el-tag
          v-for="(n, k) in analyze.card_dist || {}"
          :key="k"
          size="small"
          effect="plain"
          class="ont-tag-gap"
        >
          {{ k }}：{{ n }}
        </el-tag>
      </template>
      <template #footer>
        <el-button @click="analyzeDialog = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 派生属性问题扫描 -->
    <el-dialog
      v-model="derivedDialog"
      :title="i18nT('ai_ontology.derivedPropertyProblemScan')"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="
          i18nT('ai_ontology.scanAllDerivedPropertiesForConfigIssuesMissingRefsInvalidExpressions')
        "
      />
      <el-table :data="derivedIssues" size="small" border max-height="380" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noConfigIssuesFound')" />
        </template>
        <el-table-column
          :label="i18nT('ai_ontology.objectType')"
          min-width="170"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
        </el-table-column>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.property')"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.questions')" min-width="260">
          <template #default="{ row }">
            <div v-for="(e, i) in row.errors || []" :key="i">{{ e }}</div>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="derivedDialog = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 对象类型 -->
    <el-dialog
      v-model="objDialog"
      :title="i18nT('ai_ontology.objectType')"
      width="600px"
      append-to-body
    >
      <el-form :model="objForm" label-width="130px">
        <el-form-item :label="i18nT('ai_ontology.displayName')" required>
          <el-input v-model="objForm.name" :placeholder="i18nT('ai_ontology.eGCameraTable')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.codeId')" required>
          <el-input
            v-model="objForm.code"
            :disabled="!!objForm.id"
            :placeholder="i18nT('ai_ontology.codePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.pluralDisplayName')" required>
          <el-input v-model="objForm.plural_name" :placeholder="pluralHint" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.apiName')" required>
          <el-input v-model="objForm.api_name" :placeholder="apiHint" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.status')">
          <el-select v-model="objForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.visibility')">
          <el-select v-model="objForm.visibility" style="width: 100%">
            <el-option
              v-for="v in ONT_VISIBILITY"
              :key="v.value"
              :label="v.label"
              :value="v.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.alias')">
          <el-select
            v-model="objForm.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            :placeholder="i18nT('ai_ontology.searchHitsTheseWordsPressEnterToAdd')"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.owningOntology')">
          <el-select
            v-model="objForm.domain_code"
            clearable
            :placeholder="i18nT('ai_ontology.selectNoneUnassigned')"
            style="width: 100%"
          >
            <el-option v-for="d in domains" :key="d.code" :label="d.name" :value="d.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.primaryKeyProperty')" required>
          <el-input v-model="objForm.key_prop" placeholder="id" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.titleProperty')" required>
          <el-input v-model="objForm.name_prop" placeholder="name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.contact')">
          <el-input
            v-model="objForm.point_of_contact"
            :placeholder="i18nT('ai_ontology.ownerOptional')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.backingTable')">
          <el-input
            v-model="objForm.backing_table"
            :placeholder="i18nT('ai_ontology.leaveEmptyToReuseCode')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.editable')">
          <el-switch v-model="objForm.edits_enabled" />
          <span class="ont-hint">
            {{ i18nT("ai_ontology.allowEndUsersToEditThisObjectTypeWritebackWhenEnabled") }}
          </span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.icon')">
          <el-input v-model="objForm.icon" placeholder="Box" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.description')">
          <el-input v-model="objForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="objDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="savingObj"
          @click="saveObj"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 关系类型 -->
    <el-dialog
      v-model="linkDialog"
      :title="i18nT('ai_ontology.relationType')"
      width="600px"
      append-to-body
    >
      <el-form :model="linkForm" label-width="130px">
        <el-form-item :label="i18nT('ai_ontology.sourceObjectType')" required>
          <el-select v-model="linkForm.source_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetObjectType2')" required>
          <el-select v-model="linkForm.target_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.relationName')">
          <el-input v-model="linkForm.name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.apiName')">
          <el-input
            v-model="linkForm.api_name"
            :placeholder="i18nT('ai_ontology.leaveEmptyToAutoDeriveByRelationName')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.sourceDisplayName')">
          <el-input
            v-model="linkForm.source_name"
            :placeholder="i18nT('ai_ontology.nameFromSourceSideEGOwningGroup')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.sourcePluralName')">
          <el-input v-model="linkForm.source_plural_name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetDisplayName')">
          <el-input
            v-model="linkForm.target_name"
            :placeholder="i18nT('ai_ontology.nameFromTargetSideEGContainsDevices')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetPluralName')">
          <el-input v-model="linkForm.target_plural_name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.joinMode')">
          <el-select v-model="linkForm.join_method" style="width: 100%">
            <el-option
              v-for="j in ONT_JOIN_METHOD"
              :key="j.value"
              :label="j.label"
              :value="j.value"
              :disabled="linkForm.card === 'many_to_many' && j.value !== 'dataset'"
            />
          </el-select>
          <span v-if="linkForm.card === 'many_to_many'" class="ont-hint">
            {{ i18nT("ai_ontology.manyToManyJoinDatasetHint") }}
          </span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.cardinality')">
          <el-select v-model="linkForm.card" style="width: 100%">
            <el-option
              v-for="c in ONT_CARDINALITY"
              :key="c.value"
              :label="c.label"
              :value="c.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.sourceField')">
          <el-input v-model="linkForm.source_field" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetField')">
          <el-input v-model="linkForm.target_field" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.status')">
          <el-select v-model="linkForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.visibility')">
          <el-select v-model="linkForm.visibility" style="width: 100%">
            <el-option
              v-for="v in ONT_VISIBILITY"
              :key="v.value"
              :label="v.label"
              :value="v.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.description')">
          <el-input v-model="linkForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="savingObj"
          @click="saveLink"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 动作类型 -->
    <el-dialog
      v-model="actionDialog"
      :title="i18nT('ai_ontology.actionType')"
      width="600px"
      append-to-body
    >
      <el-form :model="actionForm" label-width="140px">
        <el-form-item :label="i18nT('ai_ontology.actionName')" required>
          <el-input v-model="actionForm.name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.code')" required>
          <el-input v-model="actionForm.code" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetObjectType')" required>
          <el-select v-model="actionForm.object_code" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.writebackTarget')">
          <el-input v-model="actionForm.target_table" placeholder="video_cameras" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.mode')">
          <el-select v-model="actionForm.method" style="width: 100%">
            <el-option :label="i18nT('ai_ontology.actionUpdate')" value="update" />
            <el-option :label="i18nT('ai_ontology.actionInsert')" value="insert" :disabled="true" />
            <el-option :label="i18nT('ai_ontology.actionDelete')" value="delete" :disabled="true" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.approvalGate')">
          <el-switch v-model="actionForm.approval" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.writableFields')">
          <el-select
            v-model="actionForm.white_fields"
            multiple
            allow-create
            filterable
            :placeholder="i18nT('ai_ontology.fieldWhitelist')"
            style="width: 100%"
          >
            <el-option v-for="p in propsForForm" :key="p.code" :label="p.name" :value="p.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.status')">
          <el-select v-model="actionForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.description')">
          <el-input v-model="actionForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Tool description">
          <el-input
            v-model="actionForm.tool_description"
            type="textarea"
            :rows="2"
            :placeholder="i18nT('ai_ontology.toolDescriptionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.paramsJson')">
          <el-input
            v-model="actionForm.parametersText"
            type="textarea"
            :rows="3"
            :placeholder="i18nT('ai_ontology.paramsPlaceholder')"
          />
          <span class="ont-hint">{{ i18nT("ai_ontology.paramsJsonSchemaHint") }}</span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.sideEffectsJson')">
          <el-input
            v-model="actionForm.sideEffectsText"
            type="textarea"
            :rows="2"
            :placeholder="i18nT('ai_ontology.sideEffectsPlaceholder')"
          />
          <span class="ont-hint">
            {{ i18nT("ai_ontology.sideEffectsHint") }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="savingObj"
          @click="saveAction"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 保存前的改动审核（对齐官方 Review changes） -->
    <el-dialog
      v-model="reviewDialog"
      :title="i18nT('ai_ontology.reviewChanges')"
      width="600px"
      append-to-body
    >
      <div class="ont-review">
        <div class="ont-review__sum">
          {{ i18nT("ai_ontology.total") }}
          <b>{{ review.count }}</b>
          {{ i18nT("ai_ontology.changesPendingSave") }}
          <el-tag v-if="review.errors.length" size="small" type="danger" effect="plain">
            {{ i18nT("ai_ontology.errorsCount", { count: review.errors.length }) }}
          </el-tag>
          <el-tag v-if="review.warnings.length" size="small" type="warning" effect="plain">
            {{ i18nT("ai_ontology.warningsCount", { count: review.warnings.length }) }}
          </el-tag>
        </div>

        <el-table :data="review.changes" size="small" border max-height="200" stripe>
          <el-table-column prop="label" :label="i18nT('ai_ontology.type')" width="100" />
          <el-table-column :label="i18nT('ai_ontology.changes2')" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="actionTagType(row.action)" effect="plain">
                {{ actionLabel(row.action) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" :label="i18nT('ai_ontology.entity')" show-overflow-tooltip />
        </el-table>

        <el-alert
          v-if="review.errors.length"
          type="error"
          :closable="false"
          class="ont-review__box"
          :title="i18nT('ai_ontology.theFollowingErrorsWillBlockSaving')"
        >
          <ul class="ont-review__list">
            <li v-for="(e, i) in review.errors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>

        <el-alert
          v-if="review.warnings.length"
          type="warning"
          :closable="false"
          class="ont-review__box"
          :title="i18nT('ai_ontology.theFollowingWarningsWonTBlockSaving')"
        >
          <ul class="ont-review__list">
            <li v-for="(w, i) in review.warnings" :key="i">{{ w }}</li>
          </ul>
        </el-alert>

        <div v-if="review.destructive.length" class="ont-review__danger">
          <el-alert
            type="error"
            :closable="false"
            :title="i18nT('ai_ontology.destructiveChangesExistEnterEntityNameToConfirm')"
          >
            <ul class="ont-review__list">
              <li v-for="(d, i) in review.destructive" :key="i">{{ d.name }}：{{ d.reason }}</li>
            </ul>
          </el-alert>
          <el-input
            v-model="confirmName"
            class="ont-review__confirm"
            :placeholder="
              i18nT('ai_ontology.enterEntityNameConfirm', {
                name: review.destructive[0]?.name || '',
              })
            "
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="reviewDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="danger"
          plain
          :disabled="wipSaving"
          @click="discardWip"
        >
          {{ i18nT("ai_ontology.discardAllChanges") }}
        </el-button>
        <el-button
          type="primary"
          :loading="wipSaving"
          :disabled="review.errors.length > 0"
          @click="doSaveWip"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 本体（domain）新建 / 重命名 -->
    <el-dialog
      v-model="domainDialog"
      :title="domainForm.id ? i18nT('ai_ontology.renameDomain') : i18nT('ai_ontology.newDomain')"
      width="520px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item :label="i18nT('ai_ontology.name')" required>
          <el-input
            v-model="domainForm.name"
            :placeholder="i18nT('ai_ontology.domainName')"
            maxlength="60"
          />
        </el-form-item>
        <el-form-item v-if="!domainForm.id" :label="i18nT('ai_ontology.code')" required>
          <el-input
            v-model="domainForm.code"
            :placeholder="i18nT('ai_ontology.uniqueCodePlaceholder')"
            maxlength="40"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="domainDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="domainSaving"
          @click="saveDomain"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量归属 -->
    <el-dialog
      v-model="assignDialog"
      :title="i18nT('ai_ontology.batchAssignOntology')"
      width="520px"
      append-to-body
    >
      <div class="ont-hint">
        {{ i18nT("ai_ontology.selectedObjectTypesHint", { count: selected.length }) }}
        <template v-for="(o, i) in selected.slice(0, 6)" :key="o.code">
          {{ i ? "、" : "" }}{{ o.name }}
        </template>
        {{ selected.length > 6 ? i18nT("ai_ontology.etc") : "" }}
      </div>
      <el-form label-width="90px" class="ont-home__mt">
        <el-form-item :label="i18nT('ai_ontology.targetOntology')">
          <el-select
            v-model="assignTarget"
            clearable
            :placeholder="i18nT('ai_ontology.selectNoneUnassigned')"
            style="width: 100%"
          >
            <el-option v-for="d in domains" :key="d.code" :label="d.name" :value="d.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="assignLoading" @click="doAssign">
          {{ i18nT("ai_ontology.confirmAssign") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 待审批版本 -->
    <el-dialog
      v-model="pendingDialog"
      :title="i18nT('ai_ontology.pendingVersionPublishing')"
      width="600px"
      append-to-body
    >
      <el-table :data="pendingVersions" size="small" border stripe>
        <template #empty>
          <el-empty :description="i18nT('ai_ontology.noPendingPublishRequests')" :image-size="50" />
        </template>
        <el-table-column
          :label="i18nT('ai_ontology.objectType')"
          min-width="170"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
        </el-table-column>
        <el-table-column
          prop="created_time"
          :label="i18nT('ai_ontology.appliedTime')"
          min-width="170"
        />
        <el-table-column :label="i18nT('ai_ontology.operations')" width="100" align="center">
          <template #default="{ row }">
            <el-button
              icon="Check"
              link
              type="primary"
              size="small"
              :loading="approveLoading"
              @click="doApprove(row)"
            >
              {{ i18nT("ai_ontology.approvePublish") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="pendingDialog = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElLoading, ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowDown,
  Box,
  Check,
  DataAnalysis,
  Expand,
  Fold,
  MoreFilled,
  Plus,
  Promotion,
  RefreshLeft,
  Tools,
} from "@element-plus/icons-vue";
import {
  approveOntVersion,
  assignOntDomain,
  discardOntWip,
  enrichOntology,
  getOntAnalyze,
  getOntDerivedIssues,
  getOntProperties,
  getOntVersionPending,
  materializeOntObject,
  removeOntDomain,
  saveOntDomain,
  saveOntWip,
  seedOntologyExamples,
  syncDefaultOntObjectViews,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "./composables/useOntologyData";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import OntGraphWorkspace from "./components/OntGraphWorkspace.vue";
import OntOverviewDrawer from "./components/OntOverviewDrawer.vue";
import OntMaintenanceDrawer from "./components/OntMaintenanceDrawer.vue";
import OntObjectTypeView from "./components/OntObjectTypeView.vue";
const { t: i18nT } = useI18n();

// 关系类型 / 动作类型详情：这两个组件此前**全仓无人引用**（孤儿），
// 导致关系与动作只能新建、看不了详情、也删不掉。
import OntLinkTypeView from "./components/OntLinkTypeView.vue";
import OntActionTypeView from "./components/OntActionTypeView.vue";
import { getOntObjectView } from "@/api/module_ai/ontology";
import {
  ONT_CARDINALITY,
  ONT_JOIN_METHOD,
  ONT_STATUS,
  ONT_VISIBILITY,
  deriveApiName,
  derivePluralName,
} from "./constants";

const router = useRouter();

/** 双向闭环：本体 → 问数（用刚定义/改动的语义去验证一次真实问数）。 */
function goQuery() {
  router.push("/ai/query");
}

const {
  domains,
  objects,
  pendingVersions,
  currentDomain,
  currentDomainName,
  scopedLinks,
  actions,
  wip,
  refreshWip,
  stage,
  reloadAll,
  objectLabel,
  objectByCode,
} = useOntologyData();

/* ---------------- 导航状态 ---------------- */
/** 维护抽屉各面板标签 */
const MAINT_PANELS: Record<string, { label: string }> = {
  index: { label: i18nT("ai_ontology.index") },
  proposals: { label: i18nT("ai_ontology.proposal") },
  scenarios: { label: i18nT("ai_ontology.scenario") },
  decisions: { label: i18nT("ai_ontology.decision") },
  explore: { label: i18nT("ai_ontology.objectExplorer") },
  groups: { label: i18nT("ai_ontology.objectTypeGroup") },
  valueTypes: { label: i18nT("ai_ontology.valueType") },
  shared: { label: i18nT("ai_ontology.sharedProperty") },
  interfaces: { label: i18nT("ai_ontology.interface") },
};
// 深链里带过来的对象主键（?objectview=<code>&objectkey=<key>）
const objectViewKey = ref("");
// 深链指定的视图编码（?objectview=<code>）
const objectViewCode = ref("");
const selKey = ref(""); // 对象类型 / 动作类型的 code
const objPage = ref("overview"); // 对象类型详情当前子页
const objectDrawer = ref(false); // 图谱点节点 → 对象详情抽屉
const overviewDrawer = ref(false); // 概览抽屉
const maintenanceDrawer = ref(false); // 维护抽屉
const maintPanel = ref("index"); // 维护抽屉当前面板
const maintPanelLabel = computed(
  () => MAINT_PANELS[maintPanel.value]?.label || i18nT("ai_ontology.maintain")
);

/** 本体选择器：'__all__' 代表全部本体 */

const selObject = computed(() => objectByCode(selKey.value));

/** 左栏导航项（资源清单与资源子导航共用） */

/* ---------------- 本体（domain）管理 ---------------- */
function onDomain(code: string) {
  // 选中某个本体；图谱随 scoped 数据自动重绘
  currentDomain.value = code;
}

/* ---------------- 图谱交互（阶段 2/3 完善） ---------------- */
function onGraphNodeTap(objectCode: string) {
  // 点图谱节点 → 打开对象详情抽屉；对象不存在（数据过期）则提示并关闭
  if (!objectByCode(objectCode)) {
    objectDrawer.value = false;
    return ElMessage.warning(i18nT("ai_ontology.thisObjectTypeNoLongerExistsOrIsOutOfScope"));
  }
  selKey.value = objectCode;
  objPage.value = "overview";
  objectDrawer.value = true;
}
function goObjectProperties() {
  // 「管理」属性 → 切到属性子页
  objPage.value = "properties";
}
function onGraphLinkDraw(sourceCode: string, targetCode: string) {
  // 阶段 2：拖拽建边 → 关系编辑，预填源/目标对象类型
  openLinkEdit();
  linkForm.source_object = sourceCode;
  linkForm.target_object = targetCode;
}
function onGraphEdgeCtx(sourceCode: string, targetCode: string) {
  // 点边编辑现有关系：按源/目标反查关系并打开编辑（同名取第一个）
  const link = scopedLinks.value.find(
    (l: any) => l.source_object === sourceCode && l.target_object === targetCode
  );
  if (link) {
    openLinkEdit(link);
  } else {
    ElMessage.warning(i18nT("ai_ontology.correspondingRelationTypeNotFound"));
  }
}
function onGraphEditObject(objectCode: string) {
  const obj = objectByCode(objectCode);
  if (obj) openObjectEdit(obj);
  else ElMessage.warning(i18nT("ai_ontology.thisObjectTypeNoLongerExists"));
}
function onGraphDeleteObject(objectCode: string) {
  const obj = objectByCode(objectCode);
  if (obj) removeObj(obj);
  else ElMessage.warning(i18nT("ai_ontology.thisObjectTypeNoLongerExists"));
}
function onGraphMaterializeObject(objectCode: string) {
  materialize(objectByCode(objectCode) || { code: objectCode });
}

/** 工作室顶部「维护面板」图标按钮 → 打开对应维护抽屉 */
function onMaintain(panel: string) {
  maintPanel.value = panel;
  maintenanceDrawer.value = true;
}

/** 多选批量删除对象类型 → 逐个暂存删除 */
async function batchDeleteObjects(codes: string[]) {
  if (!codes.length) return;
  const names = codes
    .map((c) => objectByCode(c)?.name || c)
    .slice(0, 6)
    .join("、");
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.batchDeleteObjectTypesConfirm", {
        count: codes.length,
        names: `${names}${codes.length > 6 ? i18nT("ai_ontology.etc") : ""}`,
      }),
      i18nT("ai_ontology.batchDeleteObjectTypes"),
      {
        type: "warning",
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
      }
    );
  } catch {
    return;
  }
  for (const code of codes) {
    const obj = objectByCode(code);
    if (obj) await stage("object", "delete", { id: obj.id, code: obj.code, name: obj.name });
  }
}

function onDomainCmd(cmd: string, d: any) {
  if (cmd === "rename") {
    domainForm.id = d.id;
    domainForm.code = d.code;
    domainForm.name = d.name;
    domainDialog.value = true;
  } else if (cmd === "remove") {
    removeDomain(d);
  }
}

function openDomainForm() {
  domainForm.id = null;
  domainForm.code = "";
  domainForm.name = "";
  domainDialog.value = true;
}

async function saveDomain() {
  const name = (domainForm.name || "").trim();
  const code = (domainForm.code || "").trim();
  if (!name) return ElMessage.warning(i18nT("ai_ontology.pleaseEnterOntologyName"));
  if (!code && !domainForm.id)
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterOntologyCode"));
  domainSaving.value = true;
  try {
    const payload: any = { name };
    if (domainForm.id) {
      payload.id = domainForm.id;
      payload.code = domainForm.code;
    } else {
      payload.code = code;
    }
    const r = await saveOntDomain(payload);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.saved"));
    domainDialog.value = false;
    await reloadAll();
    if (!domainForm.id && code) {
      currentDomain.value = code;
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    domainSaving.value = false;
  }
}

async function removeDomain(d: any) {
  const cnt = objects.value.filter((o: any) => (o.domain_code || "") === d.code).length;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.deleteDomainConfirm", { name: d.name, count: cnt }),
      i18nT("ai_ontology.deleteOntology"),
      {
        type: "warning",
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
      }
    );
  } catch {
    return;
  }
  const r = await removeOntDomain(d.id);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.deleted"));
  await reloadAll();
  // 删除当前本体后，自动选中剩余的第一个本体（左侧没有「全部」入口）
  if (currentDomain.value === d.code && domains.value.length) {
    currentDomain.value = domains.value[0].code;
  }
}

const selected = ref<any[]>([]);

/* ---------------- 维护菜单 ---------------- */
const enrichLoading = ref(false);
const seedLoading = ref(false);
const maintMsg = ref("");
const assignDialog = ref(false);
const assignTarget = ref("");
const assignLoading = ref(false);
const approveLoading = ref(false);
const pendingDialog = ref(false);
const domainDialog = ref(false);
const domainSaving = ref(false);
const domainPanelCollapsed = ref(false); // 本体域面板可折叠（小屏省空间）
const domainForm = reactive({ id: null as number | null, code: "", name: "" });

async function onMaint(cmd: string) {
  if (cmd === "enrich") return doEnrich();
  if (cmd === "seed") return doSeed();
  if (cmd === "analyze") return openAnalyze();
  if (cmd === "derived") return openDerived();
  if (cmd === "syncviews") return doSyncViews();
  if (cmd === "assign") {
    if (!selected.value.length) {
      return ElMessage.warning(
        i18nT("ai_ontology.selectObjectsInTheObjectTypeListBeforeBatchAssigning")
      );
    }
    assignDialog.value = true;
    return;
  }
  if (cmd === "pending") {
    const r = await getOntVersionPending();
    pendingVersions.value = r.data?.data || [];
    pendingDialog.value = true;
  }
  if (cmd.startsWith("maintain-")) {
    maintPanel.value = cmd.slice("maintain-".length);
    maintenanceDrawer.value = true;
  }
}
/* ---------------- 本体级工具：建模分析 / 派生问题扫描 / 补齐默认视图 ---------------- */
const analyzeDialog = ref(false);
const analyzeLoading = ref(false);
const analyze = ref<any>(null);

async function openAnalyze() {
  analyzeDialog.value = true;
  analyzeLoading.value = true;
  analyze.value = null;
  try {
    const r = await getOntAnalyze();
    analyze.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.analyzeFailed"));
  } finally {
    analyzeLoading.value = false;
  }
}

const derivedDialog = ref(false);
const derivedIssues = ref<any[]>([]);

async function openDerived() {
  derivedDialog.value = true;
  derivedIssues.value = [];
  try {
    const r = await getOntDerivedIssues();
    derivedIssues.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.scanFailed"));
  }
}

async function doSyncViews() {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.backfillViewsConfirm") +
      i18nT("ai_ontology.withManyObjectTypesThisMayTakeTensOfSecondsDonTCloseThePageExecute"),
    i18nT("ai_ontology.backfillDefaultObjectViews"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.backfill"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  // 这是全量批处理（421 个对象 × 2 种形态），必须给出加载态，否则用户以为"点了没反应"
  const loading = ElLoading.service({
    fullscreen: true,
    text: i18nT("ai_ontology.backfillingViews"),
  });
  try {
    const r = await syncDefaultOntObjectViews();
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.defaultViewsBackfilled"));
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.backfillFailed2"));
  } finally {
    loading.close();
  }
}

async function doEnrich() {
  enrichLoading.value = true;
  maintMsg.value = "";
  try {
    const r = await enrichOntology();
    maintMsg.value = r.data?.msg || i18nT("ai_ontology.backfillComplete");
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.backfillFailed"));
  } finally {
    enrichLoading.value = false;
  }
}
async function doSeed() {
  seedLoading.value = true;
  maintMsg.value = "";
  try {
    const r = await seedOntologyExamples();
    maintMsg.value = r.data?.msg || i18nT("ai_ontology.sampleCapabilitiesWritten");
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.writeFailed"));
  } finally {
    seedLoading.value = false;
  }
}
async function doAssign() {
  if (!selected.value.length)
    return ElMessage.warning(i18nT("ai_ontology.pleaseSelectObjectTypesFirst"));
  assignLoading.value = true;
  try {
    const r = await assignOntDomain(
      assignTarget.value || "",
      selected.value.map((o: any) => o.code)
    );
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.assigned"));
    assignDialog.value = false;
    selected.value = [];
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.assignFailed"));
  } finally {
    assignLoading.value = false;
  }
}
async function doApprove(row: any) {
  // 发布是**不可逆**动作：先二次确认（原先点了就直接发，无确认、无 loading、无失败处理）
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.publishVersionConfirm", { code: row.object_code, version: row.version }),
      i18nT("ai_ontology.approvePublish"),
      {
        type: "warning",
        confirmButtonText: i18nT("ai_ontology.approvePublish"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
      }
    );
  } catch {
    return;
  }
  approveLoading.value = true;
  try {
    const r = await approveOntVersion(row.id);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.approved"));
    const p = await getOntVersionPending();
    pendingVersions.value = p.data?.data || [];
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.approveFailed"));
  } finally {
    approveLoading.value = false;
  }
}
/* ---------------- 对象类型 CRUD ---------------- */
const objDialog = ref(false);
const savingObj = ref(false);
const objBlank = () => ({
  id: null,
  name: "",
  code: "",
  plural_name: "",
  api_name: "",
  aliases: [] as string[],
  status: "experimental",
  visibility: "normal",
  index_status: "not_started",
  edits_enabled: false,
  datasource_id: null,
  backing_table: "",
  point_of_contact: "",
  contributors: [] as string[],
  rid: "",
  icon: "Box",
  key_prop: "id",
  name_prop: "name",
  description: "",
  enabled: true,
  domain_code: "",
});
const objForm = reactive<any>(objBlank());
// 官方必填项的实时推导提示
const pluralHint = computed(
  () => derivePluralName(objForm.name) || i18nT("ai_ontology.pluralExampleHint")
);
const apiHint = computed(() => deriveApiName(objForm.code) || i18nT("ai_ontology.apiExampleHint"));

function openObjectEdit(o?: any) {
  Object.assign(objForm, objBlank(), o ? { ...o } : { domain_code: currentDomain.value || "" });
  objDialog.value = true;
}
async function saveObj() {
  // 官方必填：ID(code) / 显示名 / 复数显示名 / API 名
  if (!objForm.code?.trim() || !objForm.name?.trim())
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterDisplayNameAndCode"));
  const payload = {
    ...objForm,
    plural_name: objForm.plural_name?.trim() || derivePluralName(objForm.name),
    api_name: objForm.api_name?.trim() || deriveApiName(objForm.code),
  };
  savingObj.value = true;
  try {
    const ok = await stage("object", payload.id ? "update" : "create", payload);
    if (ok) objDialog.value = false;
  } finally {
    savingObj.value = false;
  }
}
async function removeObj(o: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deleteObjectTypeConfirm", { name: o.name }),
    i18nT("ai_ontology.deleteObjectType"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await stage(
    "object",
    "delete",
    { id: o.id, code: o.code, name: o.name },
    i18nT("ai_ontology.deleteStaged")
  );
}
async function materialize(o: any) {
  const r = await materializeOntObject(o.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](r.data?.msg || d.msg || i18nT("ai_ontology.materialized"));
}

/* ---------------- 关系类型 CRUD ---------------- */
const linkDialog = ref(false);
const linkBlank = () => ({
  id: null,
  source_object: selKey.value || "",
  target_object: "",
  name: "",
  api_name: "",
  card: "many_to_one",
  join_method: "foreign_key",
  source_field: "",
  target_field: "",
  source_name: "",
  source_plural_name: "",
  target_name: "",
  target_plural_name: "",
  status: "experimental",
  visibility: "normal",
  description: "",
});
const linkForm = reactive<any>(linkBlank());
/* ---------- 关系类型 / 动作类型详情抽屉（承接 OntObjectTypeView 的「详情」上抛） ---------- */
const linkDrawer = ref(false);
const selLinkId = ref<number | null>(null);
const linkPage = ref("overview");
const actionDrawer = ref(false);
const selActionCode = ref("");
const actionPage = ref("overview");

function openLinkDetail(id: number) {
  selLinkId.value = id;
  linkPage.value = "overview";
  linkDrawer.value = true;
}

function openActionDetail(code: string) {
  selActionCode.value = code;
  actionPage.value = "overview";
  actionDrawer.value = true;
}

/** 详情里的「编辑」→ 复用既有编辑弹窗（两者都接受整行对象做回填） */
function editCurrentLink() {
  const row = (scopedLinks.value || []).find((l: any) => l.id === selLinkId.value);
  if (row) openLinkEdit({ ...row });
}

function editCurrentAction() {
  const row = (actions.value || []).find((a: any) => a.code === selActionCode.value);
  if (row) openActionEdit({ ...row });
}

function openLinkEdit(l?: any) {
  Object.assign(linkForm, linkBlank(), l ? { ...l } : {});
  linkDialog.value = true;
}
async function saveLink() {
  if (!linkForm.source_object || !linkForm.target_object)
    return ElMessage.warning(i18nT("ai_ontology.selectSourceTargetObjectType"));
  // 官方约束：多对多必须由连接表数据集支撑
  if (linkForm.card === "many_to_many" && linkForm.join_method !== "dataset")
    return ElMessage.warning(i18nT("ai_ontology.manyToManyJoinDatasetWarning"));
  savingObj.value = true;
  try {
    const payload = {
      ...linkForm,
      api_name: linkForm.api_name?.trim() || deriveApiName(linkForm.name),
    };
    const ok = await stage("link", payload.id ? "update" : "create", payload);
    if (ok) linkDialog.value = false;
  } finally {
    savingObj.value = false;
  }
}

/* ---------------- 动作类型 CRUD ---------------- */
const actionDialog = ref(false);
const actionBlank = () => ({
  id: null,
  object_code: selKey.value || "",
  name: "",
  code: "",
  target_table: "",
  method: "update",
  approval: false,
  white_fields: [] as string[],
  status: "experimental",
  description: "",
  tool_description: "",
  parametersText: "",
  sideEffectsText: "",
});
const actionForm = reactive<any>(actionBlank());
const propsForForm = ref<any[]>([]);

/** JSON 文本框解析（空 → []，非法 → 抛错由调用方提示） */
function parseJsonList(text: string, label: string): any[] {
  const s = (text || "").trim();
  if (!s) return [];
  let v: any;
  try {
    v = JSON.parse(s);
  } catch {
    throw new Error(i18nT("ai_ontology.notValidJson", { label }));
  }
  if (!Array.isArray(v)) throw new Error(i18nT("ai_ontology.mustBeJsonArray", { label }));
  return v;
}

async function openActionEdit(a?: any) {
  Object.assign(actionForm, actionBlank(), a ? { ...a } : {});
  actionForm.parametersText = a?.parameters?.length ? JSON.stringify(a.parameters, null, 2) : "";
  actionForm.sideEffectsText = a?.side_effects?.length
    ? JSON.stringify(a.side_effects, null, 2)
    : "";
  actionDialog.value = true;
  // 可写字段候选取自作用对象类型的属性（按对象类型按需加载，不依赖全量缓存）
  if (actionForm.object_code) {
    const r = await getOntProperties(actionForm.object_code);
    propsForForm.value = r.data?.data || [];
  } else {
    propsForForm.value = [];
  }
}
async function saveAction() {
  if (!actionForm.code?.trim() || !actionForm.name?.trim() || !actionForm.object_code)
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterActionNameCodeAndTargetObjectType"));
  let parameters: any[] = [];
  let side_effects: any[] = [];
  try {
    parameters = parseJsonList(actionForm.parametersText, i18nT("ai_ontology.parameter"));
    side_effects = parseJsonList(actionForm.sideEffectsText, i18nT("ai_ontology.sideEffects"));
  } catch (e: any) {
    return ElMessage.error(e.message);
  }
  savingObj.value = true;
  try {
    // 剔除仅用于编辑的 JSON 文本框，其余字段原样提交
    const payload: Record<string, any> = {};
    Object.keys(actionForm).forEach((k) => {
      if (k !== "parametersText" && k !== "sideEffectsText") payload[k] = actionForm[k];
    });
    payload.parameters = parameters;
    payload.side_effects = side_effects;
    const ok = await stage("action", payload.id ? "update" : "create", payload);
    if (ok) actionDialog.value = false;
  } finally {
    savingObj.value = false;
  }
}

/* ---------------- 工作副本（改动先入草稿，保存才落库） ----------------
 * 状态与 stage() 来自共享 composable：任何子组件暂存改动都会刷新这里的角标。
 */
const reviewDialog = ref(false);
const wipSaving = ref(false);
const confirmName = ref("");
const review = wip; // 直接复用共享状态
const wipCount = computed(() => review.value.count);

function actionLabel(a: string) {
  return (
    {
      create: i18nT("ai_ontology.new"),
      update: i18nT("ai_ontology.modify"),
      delete: i18nT("ai_ontology.delete2"),
      restore: i18nT("ai_ontology.restore"),
    }[a] || a
  );
}
function actionTagType(a: string) {
  return { create: "success", update: "primary", delete: "danger", restore: "warning" }[a] as any;
}

async function openReview() {
  await refreshWip();
  confirmName.value = "";
  reviewDialog.value = true;
}

async function doSaveWip() {
  wipSaving.value = true;
  try {
    const r = await saveOntWip(confirmName.value);
    const d = r.data?.data || {};
    if (d.ok) {
      ElMessage.success(d.msg || i18nT("ai_ontology.saved"));
      reviewDialog.value = false;
      await reloadAll();
      await refreshWip();
    } else {
      // 后端返回的审核结果覆盖本地，让用户看到真正的原因
      review.value.errors = d.errors || review.value.errors;
      review.value.destructive = d.destructive || review.value.destructive;
      await refreshWip();
      ElMessage.error(d.msg || i18nT("ai_ontology.saveFailed"));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    wipSaving.value = false;
  }
}

async function discardWip() {
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.discardWipConfirm", { count: review.value.count }),
      i18nT("ai_ontology.discardChanges"),
      {
        type: "warning",
        confirmButtonText: i18nT("ai_ontology.discard"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
      }
    );
  } catch {
    return;
  }
  const r = await discardOntWip();
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.discarded"));
  reviewDialog.value = false;
  await reloadAll();
  await refreshWip();
}

/* ---------------- 初始化 ---------------- */
/* ---------------- 深链：?objectview=<code>&objectkey=<key>（官方 generate-urls） ---------------- */
async function openDeepLink() {
  const raw = location.hash.includes("?") ? location.hash.split("?")[1] : location.search.slice(1);
  if (!raw) return false;
  const q = new URLSearchParams(raw);
  const viewCode = q.get("objectview");
  if (!viewCode) return false;
  try {
    const r = await getOntObjectView(viewCode);
    const v = r.data?.data;
    if (!v) return false;
    // 深链：选中该对象 → 打开对象详情抽屉
    selKey.value = v.object_code;
    objPage.value = "objectviews";
    objectDrawer.value = true;
    objectViewCode.value = viewCode;
    if (q.get("objectkey")) objectViewKey.value = q.get("objectkey") as string;
    ElMessage.success(i18nT("ai_ontology.openedViewMsg", { name: v.name }));
    return true;
  } catch {
    return false;
  }
}
onMounted(async () => {
  await reloadAll();
  // 默认选中第一个本体（左侧没有「全部」入口）
  if (currentDomain.value === undefined && domains.value.length) {
    currentDomain.value = domains.value[0].code;
  }
  await openDeepLink();
  await refreshWip();
});
</script>

<style scoped lang="scss">
.ont-side__head {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ont-side__dom {
  width: 100%;
}
.ont-side__res {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0 10px;
}
.ont-side__resicon {
  font-size: var(--el-font-size-extra-large);
  color: var(--el-color-primary);
}
.ont-side__restext {
  min-width: 0;
}
.ont-side__resname {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
.ont-side__ressub {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.ont-nav {
  border-right: none;
}
.ont-nav__child {
  padding-left: 32px !important;
}
.ont-nav__count {
  margin-left: auto;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
/* 左栏：本体列表 */
.ont-side__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-side__add {
  margin-left: auto;
}
.ont-side__head-ops {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-left: auto;
}
.ont-side__collapse {
  padding: 4px;
}
.ont-domains {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
  overflow: auto;
  gap: 4px;
}
.ont-dom-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.ont-dom-item:hover {
  background: var(--el-fill-color-light);
}
.ont-dom-item.is-active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.ont-dom-item__icon {
  font-size: var(--el-font-size-medium);
  flex-shrink: 0;
}
.ont-dom-item__name {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  white-space: nowrap;
}
.ont-dom-item__ops {
  flex-shrink: 0;
}
.ont-dom-item__more {
  color: var(--el-text-color-secondary);
}
.ont-dom-item.is-active .ont-dom-item__more {
  color: var(--el-color-primary);
}
.ont-domains__empty {
  padding-top: 24px;
}
.ont-main__head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.ont-main__crumb {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.ont-crumb {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
.ont-main__ops {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}
.ont-tabs {
  flex: 0 0 auto;
}
.ont-tabs > .el-tabs__header {
  margin: 0 0 12px;
}
.ont-tabs > .el-tabs__content {
  display: none;
}
.ont-tablabel {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.ont-tablabel__icon {
  font-size: var(--el-font-size-base);
}
.ont-home {
  height: 100%;
}
.ont-home__mt {
  margin-top: 12px;
}
.ont-statcard {
  padding: 12px;
  margin-bottom: 12px;
  text-align: center;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.ont-statcard:hover {
  background: var(--el-fill-color-light);
}
.ont-statcard__num {
  font-size: var(--el-font-size-extra-large);
  font-weight: 600;
  color: var(--el-color-primary);
}
.ont-statcard__label {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-sec {
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
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
.ont-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-bar__search {
  width: 200px;
}
.ont-bar__search-lg {
  width: 300px;
}
.ont-bar__sel {
  width: 130px;
}
.ont-pager {
  justify-content: flex-end;
  margin-top: 8px;
}
.ont-tpl {
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ont-tpl__head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.ont-tpl__name {
  font-size: var(--el-font-size-base);
  font-weight: 600;
}
.ont-tag-gap {
  margin: 0 4px 4px 0;
}
.ont-analyze__recs {
  margin: 0;
  padding-left: 18px;
}
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
/* 区块标题后面的说明文字要与标题留出间距（否则「变更记录谁在什么时候改了什么」会黏在一起） */
.ont-sec__head .ont-hint {
  margin-left: 8px;
}
.ont-note {
  margin-bottom: 8px;
}
.ont-none {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-placeholder);
}

.ont-demo__grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 10px;
}

.ont-demo__item {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.ont-demo__k {
  color: var(--el-text-color-secondary);
}

.ont-demo__v {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>

<style lang="scss">
/* ===========================================================================
   本体页布局：左右两张白卡（左=资源导航，右=资源视图），各自内部滚动、
   页面自身不出现滚动条；蓝灰底色只在 padding 与 gutter 里露出作间隔。
   刻意放在非 scoped 块中，避免 scoped 的 data-v 哈希在 keep-alive / HMR 下失效。
   =========================================================================== */
.app-container.ai-ontology-page {
  box-sizing: border-box;
  height: 100% !important;
  padding: 16px !important;
  overflow: hidden !important;
}

/* 两张白卡的高度链：row → col → card → body */
.ai-ontology-page .ont-row {
  flex-wrap: nowrap;
  gap: 12px;
  height: 100%;
  margin: 0 !important;
  min-height: 0;
}
.ai-ontology-page .ont-row > .el-col {
  height: 100%;
  min-height: 0;
  padding: 0 !important;
}
/* 左栏固定 240px（与工作台/个人工作空间统一，不用栅格百分比，避免各页左宽不一致） */
.ai-ontology-page .ont-row > .el-col:first-child {
  flex: 0 0 240px;
  max-width: 240px;
}
.ai-ontology-page .ont-row > .el-col:last-child {
  flex: 1 1 auto;
  max-width: 100%;
}
.ai-ontology-page .ont-row > .el-col > .el-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.ai-ontology-page .ont-row > .el-col > .el-card > .el-card__header {
  flex-shrink: 0;
}
.ai-ontology-page .ont-row > .el-col > .el-card > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

/* 左卡：资源导航自己滚 */
.ai-ontology-page .ont-side .el-menu {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
/* 右侧内容区自己滚（资源视图内部分区较多） */
.ai-ontology-page .ont-main .ont-obj,
.ai-ontology-page .ont-main .ont-link,
.ai-ontology-page .ont-main .ont-act,
.ai-ontology-page .ont-main .ont-home {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

/* ---- 工作副本 / 导入导出 / 用量 ---- */
.ont-wip-badge {
  margin-right: 4px;
}
.ont-sub-title {
  margin: 12px 0 6px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-file {
  max-width: 260px;
}
.ont-stat {
  text-align: center;
}
.ont-stat__label {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-stat__value {
  margin-top: 4px;
  font-size: var(--el-font-size-extra-large);
  font-weight: 600;
  color: var(--el-color-primary);
}
.ont-review__sum {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-review__box {
  margin-top: 10px;
}
.ont-review__list {
  padding-left: 18px;
  margin: 0;
}
.ont-review__danger {
  margin-top: 10px;
}
.ont-review__confirm {
  margin-top: 8px;
}
.ont-builtins {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 120px;
  margin-top: 6px;
  overflow: auto;
}
.ont-run__out {
  padding: 8px;
  margin: 4px 0 0;
  overflow: auto;
  font-size: var(--el-font-size-extra-small);
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>

<style lang="scss">
/* 对象类型详情右侧抽屉：体内边距交给组件自身，撑满并滚动 */
.ont-obj-drawer .el-drawer__body {
  padding: 0 16px 16px;
  overflow: auto;
}
</style>
