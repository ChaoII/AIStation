<!-- 数据与集成：把「数据资产」合并进来，做成一条路 —— 选数据源 → 选表 → 就地维护元数据 -->
<template>
  <div class="app-container ai-mod ai-integration-page">
    <el-row :gutter="12" class="ig-fill">
      <!-- 左：数据源（纵向列表，仿「本体」左侧导航） -->
      <el-col v-if="tab !== 'gov'" :xs="24" :sm="8" :md="6" :lg="5" class="ig-fill">
        <el-card shadow="never" class="ig-card">
          <template #header>
            <div class="ig-head">
              <span class="ig-side-title">{{ t("ai_workflow.ig_datasource") }}</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openDs()">
                {{ t("ai_workflow.ig_new") }}
              </el-button>
            </div>
          </template>
          <div class="ig-ds-list">
            <div
              v-for="d in datasources"
              :key="d.id"
              class="ig-ds-item"
              :class="{ 'is-active': curDs && curDs.id === d.id }"
              @click="pickDs(d)"
            >
              <el-icon class="ig-ds-item__icon"><Coin /></el-icon>
              <div class="ig-ds-item__text">
                <div class="ig-ds-item__name" :title="d.name">{{ d.name }}</div>
                <div class="ig-ds-item__sub">
                  <el-tag size="small" type="info" effect="plain">{{ d.type }}</el-tag>
                  <span v-if="d.table_count != null" class="ig-ds-item__count">
                    {{ t("ai_workflow.ig_tableCount", { count: d.table_count }) }}
                  </span>
                </div>
              </div>
              <div class="ig-ds-item__ops" @click.stop>
                <el-tooltip :content="t('ai_workflow.ig_testConnection')" placement="left">
                  <el-button link type="primary" size="small" :icon="Refresh" @click="testDs(d)" />
                </el-tooltip>
                <el-tooltip :content="t('ai_workflow.ig_edit')" placement="left">
                  <el-button link type="primary" size="small" :icon="EditPen" @click="openDs(d)" />
                </el-tooltip>
                <el-tooltip :content="t('ai_workflow.ig_delete')" placement="left">
                  <el-button
                    v-hasPerm="['module_ai:query:ask']"
                    link
                    type="danger"
                    size="small"
                    :icon="Delete"
                    @click="removeDs(d)"
                  />
                </el-tooltip>
              </div>
            </div>
            <el-empty
              v-if="!datasources.length"
              :image-size="60"
              :description="t('ai_workflow.ig_dsEmpty')"
            />
          </div>
        </el-card>
      </el-col>

      <!-- 右：选中数据源的详情 -->
      <el-col
        :xs="24"
        :sm="tab === 'gov' ? 24 : 16"
        :md="tab === 'gov' ? 24 : 18"
        :lg="tab === 'gov' ? 24 : 19"
        class="ig-fill"
      >
        <el-card shadow="never" class="ig-card">
          <el-tabs v-model="tab" class="ig-tabs">
            <!-- 表与字段：核心——选表后就地维护 -->
            <el-tab-pane :label="t('ai_workflow.ig_tabTable')" name="table">
              <!-- 表清单：铺满 tab 高度，超出滚动 -->
              <div class="ig-tables">
                <div class="ig-bar">
                  <el-input
                    v-model="tableKw"
                    size="small"
                    :placeholder="t('ai_workflow.ig_searchTablePlaceholder')"
                    :prefix-icon="Search"
                    clearable
                    class="ig-bar__search"
                  />
                  <el-button
                    size="small"
                    :icon="Refresh"
                    :disabled="!curDs"
                    :loading="syncing"
                    @click="syncSchema"
                  >
                    {{ t("ai_workflow.ig_sync") }}
                  </el-button>
                  <el-button size="small" :icon="EditPen" @click="openBatch">
                    {{ t("ai_workflow.ig_batchMaintain") }}
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:query:ask'"
                    size="small"
                    :icon="MagicStick"
                    :loading="generatingDesc"
                    :title="t('ai_workflow.ig_genDescTitle')"
                    @click="runGenerateDesc"
                  >
                    {{ t("ai_workflow.ig_genDesc") }}
                  </el-button>
                  <el-switch v-model="hideSys" :active-text="t('ai_workflow.ig_onlyBizTable')" />
                  <el-switch
                    v-model="hideUnmaintained"
                    :active-text="t('ai_workflow.ig_onlyMaintained')"
                  />
                  <span class="ig-bar__gap" />
                  <el-select
                    v-model="importDomain"
                    size="small"
                    clearable
                    :placeholder="t('ai_workflow.ig_targetOntDomain')"
                    class="ig-bar__domain"
                  >
                    <el-option
                      v-for="dm in domains"
                      :key="dm.code"
                      :label="dm.name"
                      :value="dm.code"
                    />
                  </el-select>
                  <el-button
                    v-hasPerm="'module_ai:ontology:edit'"
                    size="small"
                    :icon="DataBoard"
                    :disabled="!curDs"
                    :loading="importingBatch"
                    @click="doBatchImport"
                  >
                    {{ t("ai_workflow.ig_batchImport") }}
                  </el-button>
                </div>
                <el-table
                  :data="filteredTables"
                  size="small"
                  border
                  height="100%"
                  row-key="table"
                  stripe
                >
                  <template #empty>
                    <el-empty :description="tableEmptyText" :image-size="50" />
                  </template>
                  <el-table-column
                    :label="t('ai_workflow.ig_tableName')"
                    min-width="200"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <div class="ig-tname">{{ row.table }}</div>
                      <div v-if="row.comment" class="ig-tcmt">{{ row.comment }}</div>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_chineseName')"
                    min-width="140"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">{{ row.alias || "-" }}</template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_businessDomain')"
                    min-width="120"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">{{ row.domain || "-" }}</template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_businessDesc')"
                    min-width="180"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">{{ row.description || "-" }}</template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_businessScenario')"
                    min-width="140"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">{{ row.business_scenarios || "-" }}</template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_columnCount')"
                    width="70"
                    align="center"
                  >
                    <template #default="{ row }">{{ row.column_count ?? "-" }}</template>
                  </el-table-column>
                  <el-table-column :label="t('ai_workflow.ig_included')" width="96" align="center">
                    <template #default="{ row }">
                      <!-- 三态：显式排除 / 同步过但未治理（默认纳入）/ 已纳入 -->
                      <el-tag v-if="row.included === false" size="small" type="info" effect="plain">
                        {{ t("ai_workflow.ig_no") }}
                      </el-tag>
                      <el-tag v-else-if="!row.governed" size="small" type="warning" effect="plain">
                        {{ t("ai_workflow.ig_yesUngov") }}
                      </el-tag>
                      <el-tag v-else size="small" type="success" effect="plain">
                        {{ t("ai_workflow.ig_yes") }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('ai_workflow.ig_sysBiz')" width="92" align="center">
                    <template #default="{ row }">
                      <el-tag
                        size="small"
                        :type="row.is_system ? 'warning' : 'success'"
                        effect="plain"
                      >
                        {{
                          row.is_system
                            ? t("ai_workflow.ig_systemTable")
                            : t("ai_workflow.ig_businessTable")
                        }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column
                    :label="t('ai_workflow.ig_action')"
                    width="224"
                    align="center"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <el-button
                        icon="Grid"
                        link
                        type="primary"
                        size="small"
                        @click="openFieldDrawer(row)"
                      >
                        {{ t("ai_workflow.ig_fields") }}
                      </el-button>
                      <el-button link type="primary" size="small" @click="openVersions(row)">
                        {{ t("ai_workflow.ig_version") }}
                      </el-button>
                      <el-button icon="Star" link type="primary" size="small" @click="addFav(row)">
                        {{ t("ai_workflow.ig_favorite") }}
                      </el-button>
                      <!-- 「分享」入口暂时下线：后端 share/create 会生成 /web#/ai/query?share=<token>，
                           但全前端**没有一处读这个参数**，点开就是普通问数页——
                           假闭环比没有更伤信任。恢复入口前请先实现 ?share= 的消费方。 -->
                    </template>
                  </el-table-column>
                </el-table>
              </div>

              <!-- 选中表：抽屉里做元数据 + 字段维护 -->
              <el-drawer
                v-model="fieldDrawer"
                :title="t('ai_workflow.ig_fieldMaintainTitle', { table: curTable || '' })"
                size="600px"
                append-to-body
                class="ig-field-drawer"
              >
                <div class="ig-detail ig-detail-drawer">
                  <div class="ig-bar">
                    <span class="ig-title">{{ curTable }}</span>
                    <el-tag
                      v-if="curTableSys !== undefined"
                      size="small"
                      :type="curTableSys ? 'warning' : 'success'"
                      effect="plain"
                    >
                      {{
                        curTableSys
                          ? t("ai_workflow.ig_systemTable")
                          : t("ai_workflow.ig_businessTable")
                      }}
                    </el-tag>
                    <el-button
                      size="small"
                      type="primary"
                      :loading="savingTable"
                      @click="saveTable"
                    >
                      {{ t("ai_workflow.ig_saveTableInfo") }}
                    </el-button>
                    <el-select
                      v-model="importDomain"
                      size="small"
                      clearable
                      :placeholder="t('ai_workflow.ig_targetOntDomain')"
                      class="ig-bar__domain"
                    >
                      <el-option
                        v-for="dm in domains"
                        :key="dm.code"
                        :label="dm.name"
                        :value="dm.code"
                      />
                    </el-select>
                    <el-button
                      v-hasPerm="'module_ai:ontology:edit'"
                      size="small"
                      :icon="DataBoard"
                      :loading="importing"
                      @click="doImport"
                    >
                      {{ t("ai_workflow.ig_importAsObject") }}
                    </el-button>
                  </div>
                  <el-form :model="tmeta" label-width="100px" size="small" class="ig-form">
                    <el-form-item :label="t('ai_workflow.ig_chineseName')">
                      <el-input
                        v-model="tmeta.alias"
                        :placeholder="t('ai_workflow.ig_aliasPlaceholder')"
                      />
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_businessDomain')">
                      <el-input
                        v-model="tmeta.domain"
                        :placeholder="t('ai_workflow.ig_domainPlaceholder')"
                      />
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_businessDesc')">
                      <el-input
                        v-model="tmeta.description"
                        type="textarea"
                        :rows="2"
                        :placeholder="t('ai_workflow.ig_descPlaceholder')"
                      />
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_businessScenario')">
                      <el-input
                        v-model="tmeta.business_scenarios"
                        :placeholder="t('ai_workflow.ig_bizScenarioPlaceholder')"
                      />
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_includeQuery')">
                      <el-switch v-model="tmeta.included" />
                    </el-form-item>
                    <el-divider content-position="left" class="ig-form__divider">
                      {{ t("ai_workflow.ig_objectModeling") }}
                    </el-divider>
                    <el-form-item :label="t('ai_workflow.ig_includeObject')">
                      <el-switch v-model="tmeta.object_enabled" />
                      <el-text size="small" type="info" style="margin-left: 8px">
                        {{ t("ai_workflow.ig_objectTypeHint") }}
                      </el-text>
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_keyCol')">
                      <el-input v-model="tmeta.object_key_col" :disabled="!tmeta.object_enabled" />
                    </el-form-item>
                    <el-form-item :label="t('ai_workflow.ig_nameCol')">
                      <el-input v-model="tmeta.object_name_col" :disabled="!tmeta.object_enabled" />
                    </el-form-item>
                  </el-form>

                  <div class="ig-bar">
                    <span class="ig-sub">
                      {{ t("ai_workflow.ig_fieldCount", { count: filteredColumns.length }) }}
                    </span>
                    <el-switch
                      v-model="hideAudit"
                      :active-text="t('ai_workflow.ig_onlyBizField')"
                    />
                    <el-tag size="small" type="info" effect="plain">
                      {{ t("ai_workflow.ig_auditHint") }}
                    </el-tag>
                  </div>
                  <div class="ig-fields-wrap">
                    <el-table :data="filteredColumns" size="small" border height="100%" stripe>
                      <template #empty>
                        <el-empty :description="t('ai_workflow.ig_noColEmpty')" :image-size="50" />
                      </template>
                      <el-table-column
                        prop="column_name"
                        :label="t('ai_workflow.ig_field')"
                        width="150"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">
                          <div class="ig-tname">{{ row.column_name }}</div>
                          <div class="ig-tcmt">
                            {{ row.type }}
                            <template v-if="row.comment">· {{ row.comment }}</template>
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_chineseName')"
                        min-width="110"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">{{ row.description || "-" }}</template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_businessScenario')"
                        min-width="120"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">{{ row.business_scenarios || "-" }}</template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_relatedTable')"
                        min-width="110"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">{{ row.related_table || "-" }}</template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_relatedField')"
                        min-width="100"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">{{ row.related_field || "-" }}</template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_enum')"
                        min-width="120"
                        show-overflow-tooltip
                      >
                        <template #default="{ row }">
                          <template v-if="row.enum && row.enum.length">
                            <el-tag
                              v-for="e in row.enum"
                              :key="e"
                              size="small"
                              effect="plain"
                              class="ig-tag"
                            >
                              {{ e }}
                            </el-tag>
                          </template>
                          <template v-else>-</template>
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_included')"
                        width="56"
                        align="center"
                      >
                        <template #default="{ row }">
                          <el-switch
                            v-model="row.included"
                            size="small"
                            @change="saveColumn(row, true)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_sensitive')"
                        width="56"
                        align="center"
                      >
                        <template #default="{ row }">
                          <el-switch
                            v-model="row.sensitive"
                            size="small"
                            @change="saveColumn(row, true)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="t('ai_workflow.ig_action')"
                        width="96"
                        align="center"
                        fixed="right"
                      >
                        <template #default="{ row }">
                          <el-button
                            icon="EditPen"
                            link
                            type="primary"
                            size="small"
                            @click="openColEdit(row)"
                          >
                            {{ t("ai_workflow.ig_editAttr") }}
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </el-drawer>
            </el-tab-pane>

            <!-- 管道 -->
            <el-tab-pane :label="t('ai_workflow.ig_pipeline')" name="pipe">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openPipe()">
                  {{ t("ai_workflow.ig_newPipe") }}
                </el-button>
                <el-button size="small" @click="openPipeGraph">
                  {{ t("ai_workflow.ig_pipeGraph") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_pipeHint") }}
                </el-tag>
              </div>
              <el-table :data="pipelines" size="small" border height="100%" stripe>
                <template #empty>
                  <el-empty :description="t('ai_workflow.ig_noPipe')" :image-size="60" />
                </template>
                <el-table-column
                  prop="name"
                  :label="t('ai_workflow.ig_pipeline')"
                  min-width="140"
                  show-overflow-tooltip
                />
                <el-table-column
                  :label="t('ai_workflow.ig_srcToTarget')"
                  min-width="180"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">
                    {{ row.source_table }} → {{ row.target_object }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('ai_workflow.ig_action')" width="180" align="center">
                  <template #default="{ row }">
                    <el-button
                      icon="VideoPlay"
                      link
                      type="primary"
                      size="small"
                      @click="runPipe(row)"
                    >
                      {{ t("ai_workflow.ig_run") }}
                    </el-button>
                    <el-button icon="edit" link type="primary" size="small" @click="openPipe(row)">
                      {{ t("ai_workflow.ig_edit") }}
                    </el-button>
                    <el-button
                      icon="DataLine"
                      link
                      type="primary"
                      size="small"
                      @click="viewPipeData(row)"
                    >
                      {{ t("ai_workflow.ig_data") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 指标 -->
            <el-tab-pane :label="t('ai_workflow.ig_metric')" name="metric">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openMetric()">
                  {{ t("ai_workflow.ig_newMetric") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_metricHint") }}
                </el-tag>
                <el-button size="small" :loading="suggestLoading" @click="openSuggest">
                  {{ t("ai_workflow.ig_suggestMetric") }}
                </el-button>
              </div>
              <el-table :data="metrics" size="small" border height="100%" stripe>
                <template #empty>
                  <el-empty :description="t('ai_workflow.ig_noMetric')" :image-size="60" />
                </template>
                <el-table-column
                  prop="name"
                  :label="t('ai_workflow.ig_metric')"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="key"
                  :label="t('ai_workflow.ig_code')"
                  min-width="130"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="sql_template"
                  :label="t('ai_workflow.ig_sqlTemplate')"
                  min-width="240"
                  show-overflow-tooltip
                />
                <el-table-column :label="t('ai_workflow.ig_action')" width="110" align="center">
                  <template #default="{ row }">
                    <el-button
                      icon="edit"
                      link
                      type="primary"
                      size="small"
                      @click="openMetric(row)"
                    >
                      {{ t("ai_workflow.ig_edit") }}
                    </el-button>
                    <el-button
                      icon="delete"
                      link
                      type="danger"
                      size="small"
                      @click="removeMetric(row)"
                    >
                      {{ t("ai_workflow.ig_delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 术语 -->
            <el-tab-pane :label="t('ai_workflow.ig_term')" name="term">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openTerm()">
                  {{ t("ai_workflow.ig_newTerm") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_termHint") }}
                </el-tag>
              </div>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 10px"
                :title="t('ai_workflow.ig_termHintAlert')"
              />
              <el-table :data="terms" size="small" border height="100%" stripe>
                <template #empty>
                  <el-empty :description="t('ai_workflow.ig_noTerm')" :image-size="60" />
                </template>
                <el-table-column
                  prop="term"
                  :label="t('ai_workflow.ig_term')"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="metric_key"
                  :label="t('ai_workflow.ig_metric')"
                  min-width="130"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="field_path"
                  :label="t('ai_workflow.ig_fieldPath')"
                  min-width="220"
                  show-overflow-tooltip
                />
                <el-table-column :label="t('ai_workflow.ig_action')" width="110" align="center">
                  <template #default="{ row }">
                    <el-button icon="edit" link type="primary" size="small" @click="openTerm(row)">
                      {{ t("ai_workflow.ig_edit") }}
                    </el-button>
                    <el-button
                      icon="delete"
                      link
                      type="danger"
                      size="small"
                      @click="removeTerm(row)"
                    >
                      {{ t("ai_workflow.ig_delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 概念 -->
            <el-tab-pane :label="t('ai_workflow.ig_concept')" name="concept">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openConcept()">
                  {{ t("ai_workflow.ig_newConcept") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_conceptHint") }}
                </el-tag>
              </div>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 10px"
                :title="t('ai_workflow.ig_conceptHintAlert')"
              />
              <el-table :data="concepts" size="small" border height="100%" stripe>
                <template #empty>
                  <el-empty :description="t('ai_workflow.ig_noConcept')" :image-size="60" />
                </template>
                <el-table-column
                  prop="name"
                  :label="t('ai_workflow.ig_conceptShort')"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column :label="t('ai_workflow.ig_relatedTables')" min-width="240">
                  <template #default="{ row }">
                    <el-tag
                      v-for="tbl in row.tables || []"
                      :key="tbl"
                      size="small"
                      effect="plain"
                      class="ig-tag"
                    >
                      {{ tbl }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('ai_workflow.ig_action')" width="110" align="center">
                  <template #default="{ row }">
                    <el-button
                      icon="edit"
                      link
                      type="primary"
                      size="small"
                      @click="openConcept(row)"
                    >
                      {{ t("ai_workflow.ig_edit") }}
                    </el-button>
                    <el-button
                      icon="delete"
                      link
                      type="danger"
                      size="small"
                      @click="removeConcept(row)"
                    >
                      {{ t("ai_workflow.ig_delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 示例工程（few-shot） -->
            <el-tab-pane :label="t('ai_workflow.ig_fewshot')" name="fewshot">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openFewshot()">
                  {{ t("ai_workflow.ig_newExample") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_fewshotHint") }}
                </el-tag>
              </div>
              <el-table :data="fewshots" size="small" border height="100%" stripe>
                <template #empty>
                  <el-empty :description="t('ai_workflow.ig_noExample')" :image-size="60" />
                </template>
                <el-table-column
                  prop="question"
                  :label="t('ai_workflow.ig_question')"
                  min-width="200"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="sql"
                  :label="t('ai_workflow.ig_exampleSql')"
                  min-width="260"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="datasource"
                  :label="t('ai_workflow.ig_datasource')"
                  width="110"
                  show-overflow-tooltip
                />
                <el-table-column :label="t('ai_workflow.ig_enabled')" width="70" align="center">
                  <template #default="{ row }">
                    <el-tag
                      size="small"
                      :type="row.enabled === false ? 'info' : 'success'"
                      effect="plain"
                    >
                      {{ row.enabled === false ? t("ai_workflow.ig_no") : t("ai_workflow.ig_yes") }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('ai_workflow.ig_action')" width="110" align="center">
                  <template #default="{ row }">
                    <el-button
                      icon="edit"
                      link
                      type="primary"
                      size="small"
                      @click="openFewshot(row)"
                    >
                      {{ t("ai_workflow.ig_edit") }}
                    </el-button>
                    <el-button
                      icon="delete"
                      link
                      type="danger"
                      size="small"
                      @click="removeFewshot(row)"
                    >
                      {{ t("ai_workflow.ig_delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 血缘 -->
            <el-tab-pane :label="t('ai_workflow.ig_dataGraph')" name="kg">
              <el-alert
                type="info"
                :closable="false"
                class="ig-note"
                :title="t('ai_workflow.ig_kgAlert')"
              />
              <div class="ig-bar">
                <el-button size="small" :icon="Refresh" @click="syncKg">
                  {{ t("ai_workflow.ig_rebuildGraph") }}
                </el-button>
                <el-button size="small" @click="autoLinkKg">
                  {{ t("ai_workflow.ig_autoLink") }}
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  {{ t("ai_workflow.ig_autoLinkHint") }}
                </el-tag>
              </div>
              <el-descriptions :column="3" size="small" border>
                <el-descriptions-item :label="t('ai_workflow.ig_kgTableNode')">
                  {{ kg.nodes ?? "-" }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_kgEdge')">
                  {{ kg.edges ?? "-" }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_kgEntity')">
                  {{ kg.entities ?? "-" }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="ig-kg-filter">
                <span class="ig-kg-filter__label">{{ t("ai_workflow.ig_kgType") }}</span>
                <el-checkbox-group v-model="kgTypeFilter" size="small">
                  <el-checkbox
                    v-for="kt in kgTypeOptions"
                    :key="kt.value"
                    :value="kt.value"
                    :label="kt.value"
                  >
                    {{ kt.label }}
                  </el-checkbox>
                </el-checkbox-group>
                <el-select
                  v-model="kgTableFocus"
                  clearable
                  filterable
                  size="small"
                  :placeholder="t('ai_workflow.ig_kgFocusPlaceholder')"
                  style="width: 210px"
                >
                  <el-option v-for="tb in kgTableOptions" :key="tb" :label="tb" :value="tb" />
                </el-select>
                <span class="ig-kg-filter__hint">
                  {{ t("ai_workflow.ig_kgNodeCount", { count: filteredKgNodes.length }) }}
                </span>
              </div>
              <GraphCanvas
                v-if="filteredKgNodes.length"
                :nodes="filteredKgNodes"
                :edges="filteredKgEdges"
                height="560px"
                layout-name="grid"
                :node-style="nodeStyle"
                class="ig-kg-graph"
              />
              <el-empty v-else :image-size="60" :description="t('ai_workflow.ig_kgEmpty')" />
            </el-tab-pane>

            <!-- 筛选规则工作台 -->
            <el-tab-pane :label="t('ai_workflow.ig_filterRules')" name="rules">
              <FilterRulesWorkbench v-if="curDs" :datasource="curDs" />
              <el-empty :description="t('ai_workflow.ig_selectDsFirst')" />
            </el-tab-pane>

            <!-- 语义建模：大模型自动生成指标/标注（S4）——**两段式：先预览，再勾选落库** -->
            <el-tab-pane :label="t('ai_workflow.ig_aiModeling')" name="modeling">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                :title="t('ai_workflow.ig_modelingAlert')"
                style="margin-bottom: 12px"
              />
              <el-form inline>
                <el-form-item :label="t('ai_workflow.ig_datasource')">
                  <el-tag v-if="curDs">{{ curDs.name }}（{{ modelingDsCode }}）</el-tag>
                  <el-text v-else type="info">{{ t("ai_workflow.ig_selectDsFirst") }}</el-text>
                </el-form-item>
                <el-form-item :label="t('ai_workflow.ig_processObjects')">
                  <el-input-number v-model="modelingMax" :min="1" :max="50" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :disabled="!curDs" @click="openAutoModel('metrics')">
                    {{ t("ai_workflow.ig_genBoundMetric") }}
                  </el-button>
                  <el-button :disabled="!curDs" @click="openAutoModel('annotations')">
                    {{ t("ai_workflow.ig_genAnnotation") }}
                  </el-button>
                </el-form-item>
                <el-form-item>
                  <el-button :loading="semanticLoading" @click="handleExtractObjects">
                    {{ t("ai_workflow.ig_extractObjects") }}
                  </el-button>
                  <el-button :loading="semanticLoading" @click="handleInferRelations">
                    {{ t("ai_workflow.ig_inferRelations") }}
                  </el-button>
                </el-form-item>
              </el-form>
              <el-descriptions v-if="modelingResult" :column="3" border>
                <el-descriptions-item :label="t('ai_workflow.ig_savedThisTime')">
                  {{ modelingResult.saved ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_saveFailed')">
                  {{ modelingResult.reasons?.length ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_scope')">
                  {{
                    modelingResult.scope === "annotations"
                      ? t("ai_workflow.ig_annotationScope")
                      : t("ai_workflow.ig_boundMetricScope")
                  }}
                </el-descriptions-item>
              </el-descriptions>
              <el-table
                v-if="modelingResult?.reasons?.length"
                :data="modelingResult.reasons"
                size="small"
                style="margin-top: 8px"
                border
                stripe
              >
                <el-table-column :label="t('ai_workflow.ig_failReason')" show-overflow-tooltip>
                  <template #default="{ row }">{{ row }}</template>
                </el-table-column>
              </el-table>

              <!-- 预览 → 勾选 → 应用（对话框 append-to-body，放哪都不影响布局） -->
              <AutoModelPreviewDialog
                v-model="autoModelVisible"
                :datasource="modelingDsCode"
                :scope="autoModelScope"
                :max-objects="modelingMax"
                @applied="onAutoModelApplied"
              />
            </el-tab-pane>

            <!-- 治理：驾驶舱/权限/数据质量/数据域/本体对象（原「治理」菜单并入） -->
            <el-tab-pane :label="t('ai_workflow.ig_governance')" name="gov">
              <GovernancePanel />
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- 批量维护：粘贴「表名 中文名」一次填一批 -->
    <el-dialog v-model="batchDlg" :title="t('ai_workflow.ig_batchMaintainTitle')" width="600px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="ig-note"
        :title="t('ai_workflow.ig_batchMaintainHint')"
      />
      <el-input
        v-model="batchText"
        type="textarea"
        :rows="10"
        :placeholder="t('ai_workflow.ig_batchPlaceholder')"
      />
      <div class="ig-bar ig-batch-bar">
        <el-tag size="small" type="info" effect="plain">
          {{ t("ai_workflow.ig_parsedCount", { count: batchRows.length }) }}
        </el-tag>
        <el-tag v-if="batchUnknown.length" size="small" type="warning" effect="plain">
          {{ t("ai_workflow.ig_unknownCount", { count: batchUnknown.length }) }}
        </el-tag>
      </div>
      <el-table :data="batchRows.slice(0, 8)" size="small" border max-height="220" stripe>
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_batchPreviewEmpty')" :image-size="50" />
        </template>
        <el-table-column
          prop="table_name"
          :label="t('ai_workflow.ig_tableName')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="alias"
          :label="t('ai_workflow.ig_chineseName')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="domain"
          :label="t('ai_workflow.ig_businessDomain')"
          width="100"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_workflow.ig_match')" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.known ? 'success' : 'danger'" effect="plain">
              {{ row.known ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="batchRows.length > 8" class="ig-tcmt">
        {{ t("ai_workflow.ig_batchPreviewLimit") }}
      </div>
      <template #footer>
        <el-button @click="batchDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button
          type="primary"
          :disabled="!batchRows.length"
          :loading="batchSaving"
          @click="doBatchSave"
        >
          {{ t("ai_workflow.ig_saveCount", { count: batchRows.length }) }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑管道 -->
    <el-dialog
      v-model="pipeDlg"
      :title="pipeForm.id ? t('ai_workflow.ig_editPipe') : t('ai_workflow.ig_newPipe')"
      width="600px"
    >
      <el-form :model="pipeForm" label-width="100px" size="small">
        <el-form-item :label="t('ai_workflow.ig_pipeName')">
          <el-input
            v-model="pipeForm.name"
            :placeholder="t('ai_workflow.ig_pipeNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_sourceConn')">
          <el-input
            v-model="pipeForm.source_connection"
            :placeholder="t('ai_workflow.ig_sourceConnPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_sourceTable')">
          <el-input
            v-model="pipeForm.source_table"
            :placeholder="t('ai_workflow.ig_sourceTablePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_targetObject')">
          <el-input
            v-model="pipeForm.target_object"
            :placeholder="t('ai_workflow.ig_targetObjectPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_fieldMapping')">
          <el-input
            v-model="pipeForm.mappings_text"
            type="textarea"
            :rows="4"
            :placeholder="t('ai_workflow.ig_mappingPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_enabled')">
          <el-switch v-model="pipeForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pipeDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingPipe" @click="savePipe">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 管道编排图 -->
    <el-dialog v-model="pipeGraphVisible" :title="t('ai_workflow.ig_pipeGraphTitle')" width="900px">
      <GraphCanvas
        v-if="pipeGraphNodes.length"
        :nodes="pipeGraphNodes"
        :edges="pipeGraphEdges"
        height="520px"
        layout-name="breadthfirst"
        :node-style="nodeStyle"
      />
      <el-empty :description="t('ai_workflow.ig_pipeGraphEmpty')" :image-size="60" />
    </el-dialog>

    <!-- AI 推荐指标/术语 -->
    <el-dialog v-model="suggestVisible" :title="t('ai_workflow.ig_suggestTitle')" width="900px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
        :title="t('ai_workflow.ig_suggestHint')"
      />
      <div class="ig-sub">
        {{ t("ai_workflow.ig_suggestMetrics", { count: suggestMetrics.length }) }}
      </div>
      <el-table :data="suggestMetrics" size="small" border max-height="220" stripe>
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_noSuggest')" :image-size="40" />
        </template>
        <el-table-column
          prop="name"
          :label="t('ai_workflow.ig_metricName')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column prop="sql" label="SQL" min-width="260" show-overflow-tooltip />
        <el-table-column :label="t('ai_workflow.ig_action')" width="80" align="center">
          <template #default="{ row }">
            <el-button icon="Check" link type="primary" size="small" @click="adoptMetric(row)">
              {{ t("ai_workflow.ig_adopt") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ig-sub">
        {{ t("ai_workflow.ig_suggestTerms", { count: suggestTerms.length }) }}
      </div>
      <el-table :data="suggestTerms" size="small" border max-height="220" stripe>
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_noSuggest')" :image-size="40" />
        </template>
        <el-table-column
          prop="term"
          :label="t('ai_workflow.ig_term')"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column prop="type" :label="t('ai_workflow.ig_type')" width="100" />
        <el-table-column
          prop="target"
          :label="t('ai_workflow.ig_target')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_workflow.ig_action')" width="80" align="center">
          <template #default="{ row }">
            <el-button icon="Check" link type="primary" size="small" @click="adoptTerm(row)">
              {{ t("ai_workflow.ig_adopt") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 查看管道落库数据 -->
    <el-dialog
      v-model="pipeDataDlg"
      :title="t('ai_workflow.ig_pipeDataTitle', { name: pipeDataName })"
      width="900px"
    >
      <el-table :data="pipeDataRows" size="small" border max-height="420" stripe>
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_pipeDataEmpty')" :image-size="60" />
        </template>
        <el-table-column
          v-for="c in pipeDataCols"
          :key="c"
          :prop="c"
          :label="c"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
    </el-dialog>

    <!-- 新建/编辑指标 -->
    <el-dialog
      v-model="metricDlg"
      :title="metricForm.id ? t('ai_workflow.ig_editMetric') : t('ai_workflow.ig_newMetric')"
      width="600px"
    >
      <el-form :model="metricForm" label-width="100px" size="small">
        <el-form-item :label="t('ai_workflow.ig_displayName')">
          <el-input
            v-model="metricForm.name"
            :placeholder="t('ai_workflow.ig_displayNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_codeKey')">
          <el-input
            v-model="metricForm.key"
            :disabled="!!metricForm.id"
            :placeholder="t('ai_workflow.ig_codeKeyPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_datasource')">
          <el-input
            v-model="metricForm.datasource"
            :placeholder="t('ai_workflow.ig_datasourcePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_sqlTemplate')">
          <el-input
            v-model="metricForm.sql_template"
            type="textarea"
            :rows="4"
            :placeholder="t('ai_workflow.ig_sqlPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_agg')">
          <el-input v-model="metricForm.agg" :placeholder="t('ai_workflow.ig_aggPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_unit')">
          <el-input v-model="metricForm.unit" :placeholder="t('ai_workflow.ig_unitPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_enabled')">
          <el-switch v-model="metricForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metricDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingMetric" @click="saveMetric">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑示例工程 -->
    <el-dialog
      v-model="fewshotDlg"
      :title="fewshotForm.id ? t('ai_workflow.ig_editExample') : t('ai_workflow.ig_newExample')"
      width="600px"
    >
      <el-form :model="fewshotForm" label-width="90px" size="small">
        <el-form-item :label="t('ai_workflow.ig_datasource')">
          <el-select v-model="fewshotForm.datasource" style="width: 100%">
            <el-option :label="t('ai_workflow.ig_systemLibOption')" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_question')" required>
          <el-input
            v-model="fewshotForm.question"
            type="textarea"
            :rows="2"
            :placeholder="t('ai_workflow.ig_questionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_exampleSql')" required>
          <el-input
            v-model="fewshotForm.sql"
            type="textarea"
            :rows="6"
            placeholder="SELECT status, count(*) FROM video_cameras GROUP BY status"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_enabled')">
          <el-switch v-model="fewshotForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fewshotDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingFewshot" @click="saveFewshot">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑术语 -->
    <el-dialog
      v-model="termDlg"
      :title="termForm.id ? t('ai_workflow.ig_editTerm') : t('ai_workflow.ig_newTerm')"
      width="520px"
    >
      <el-form :model="termForm" label-width="100px" size="small">
        <el-form-item :label="t('ai_workflow.ig_term')">
          <el-input
            v-model="termForm.term"
            :disabled="!!termForm.id"
            :placeholder="t('ai_workflow.ig_termPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_datasource')">
          <el-input
            v-model="termForm.datasource"
            :placeholder="t('ai_workflow.ig_datasourcePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_correspondingMetric')">
          <el-input
            v-model="termForm.metric_key"
            :placeholder="t('ai_workflow.ig_metricCodeOptional')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_fieldPath')">
          <el-input
            v-model="termForm.field_path"
            :placeholder="t('ai_workflow.ig_fieldPathOptional')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_type')">
          <el-select v-model="termForm.type">
            <el-option :label="t('ai_workflow.ig_metricAlias')" value="metric" />
            <el-option :label="t('ai_workflow.ig_normalTerm')" value="term" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="termDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingTerm" @click="saveTerm">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑概念 -->
    <el-dialog
      v-model="conceptDlg"
      :title="conceptForm.id ? t('ai_workflow.ig_editConcept') : t('ai_workflow.ig_newConcept')"
      width="600px"
    >
      <el-form :model="conceptForm" label-width="100px" size="small">
        <el-form-item :label="t('ai_workflow.ig_conceptName')">
          <el-input
            v-model="conceptForm.name"
            :disabled="!!conceptForm.id"
            :placeholder="t('ai_workflow.ig_conceptNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_description')">
          <el-input v-model="conceptForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_synonyms')">
          <el-input
            v-model="conceptForm.synonyms"
            :placeholder="t('ai_workflow.ig_synonymsPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_parentConcept')">
          <el-input v-model="conceptForm.parent_name" :placeholder="t('ai_workflow.ig_optional')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_businessDomain')">
          <el-input
            v-model="conceptForm.domain"
            :placeholder="t('ai_workflow.ig_domainPlaceholder2')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_relatedMetric')">
          <el-input
            v-model="conceptForm.metric_key"
            :placeholder="t('ai_workflow.ig_metricCodeOptional')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_relatedTables')">
          <el-input
            v-model="conceptForm.tables_text"
            :placeholder="t('ai_workflow.ig_relatedTablesPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="conceptDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingConcept" @click="saveConcept">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑单字段属性 -->
    <el-dialog
      v-model="colDlg"
      :title="t('ai_workflow.ig_editFieldTitle', { name: colForm.column_name || '' })"
      width="520px"
    >
      <el-form :model="colForm" label-width="90px" size="small">
        <el-form-item :label="t('ai_workflow.ig_fieldName')">
          <span class="ig-tname">{{ colForm.column_name }}</span>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_chineseName')">
          <el-input
            v-model="colForm.description"
            :placeholder="t('ai_workflow.ig_fieldDescPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_businessScenario')">
          <el-input
            v-model="colForm.business_scenarios"
            :placeholder="t('ai_workflow.ig_bizScenarioPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_relatedTable')">
          <el-select-v2
            v-model="colForm.related_table"
            :options="relTableOptions"
            size="small"
            filterable
            clearable
            :placeholder="t('ai_workflow.ig_relatedTablePlaceholder')"
            style="width: 100%"
            @change="colForm.related_field = ''"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_relatedField')">
          <el-select-v2
            v-model="colForm.related_field"
            :options="relFieldOptions(colForm.related_table)"
            size="small"
            filterable
            clearable
            :placeholder="t('ai_workflow.ig_relatedFieldPlaceholder')"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_enum')">
          <el-select
            v-model="colForm.enum"
            multiple
            filterable
            allow-create
            default-first-option
            size="small"
            :placeholder="t('ai_workflow.ig_enumPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="e in colForm.enum" :key="e" :label="e" :value="e" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_includeQuery')">
          <el-switch v-model="colForm.included" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_sensitive')">
          <el-switch v-model="colForm.sensitive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="colDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingCol === colForm.column_name" @click="saveColEdit">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑数据源 -->
    <el-dialog
      v-model="dsDlg"
      :title="dsForm.id ? t('ai_workflow.ig_editDs') : t('ai_workflow.ig_newDs')"
      width="520px"
    >
      <el-form :model="dsForm" label-width="90px" size="small">
        <el-form-item :label="t('ai_workflow.ig_dsCode')">
          <el-input
            v-model="dsForm.code"
            :disabled="!!dsForm.id"
            :placeholder="t('ai_workflow.ig_dsCodePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_dsName')">
          <el-input v-model="dsForm.name" :placeholder="t('ai_workflow.ig_dsNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_dbType')">
          <el-select v-model="dsForm.type">
            <el-option label="PostgreSQL" value="postgres" />
            <el-option label="MySQL" value="mysql" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_host')">
          <el-input v-model="dsForm.host" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_port')">
          <el-input-number v-model="dsForm.port" :min="1" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_database')">
          <el-input v-model="dsForm.database" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_username')">
          <el-input v-model="dsForm.username" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_password')">
          <el-input v-model="dsForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_readOnly')">
          <el-switch v-model="dsForm.read_only" />
        </el-form-item>
        <template v-if="dsForm.filter_rules">
          <el-divider content-position="left" class="ig-form__divider">
            {{ t("ai_workflow.ig_filterRuleSection") }}
          </el-divider>
          <el-form-item :label="t('ai_workflow.ig_enableRule')">
            <el-switch v-model="dsForm.filter_rules.enabled" />
          </el-form-item>
          <el-form-item :label="t('ai_workflow.ig_sysTablePrefix')">
            <el-select
              v-model="dsForm.filter_rules.system_table.prefixes"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              :placeholder="t('ai_workflow.ig_enterAddPrefix')"
              style="width: 100%"
            >
              <el-option
                v-for="p in dsForm.filter_rules.system_table.prefixes"
                :key="p"
                :label="p"
                :value="p"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('ai_workflow.ig_sysTableKeyword')">
            <el-select
              v-model="dsForm.filter_rules.system_table.keywords"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              :placeholder="t('ai_workflow.ig_enterAddKeyword')"
              style="width: 100%"
            >
              <el-option
                v-for="k in dsForm.filter_rules.system_table.keywords"
                :key="k"
                :label="k"
                :value="k"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('ai_workflow.ig_exactTable')">
            <el-select
              v-model="dsForm.filter_rules.system_table.exact"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              :placeholder="t('ai_workflow.ig_enterAddExact')"
              style="width: 100%"
            >
              <el-option
                v-for="e in dsForm.filter_rules.system_table.exact"
                :key="e"
                :label="e"
                :value="e"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('ai_workflow.ig_tableRegex')">
            <el-input
              v-model="dsForm.filter_rules.system_table.regex"
              :placeholder="t('ai_workflow.ig_tableRegexPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('ai_workflow.ig_auditField')">
            <el-select
              v-model="dsForm.filter_rules.audit_fields"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              :placeholder="t('ai_workflow.ig_enterAddAudit')"
              style="width: 100%"
            >
              <el-option
                v-for="a in dsForm.filter_rules.audit_fields"
                :key="a"
                :label="a"
                :value="a"
              />
            </el-select>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dsDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingDs" @click="saveDs">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 资产版本管理 -->
    <AssetVersionsDialog v-model="versionsVisible" :table="versionsTable" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  Plus,
  Refresh,
  Search,
  DataBoard,
  EditPen,
  Delete,
  Coin,
  MagicStick,
} from "@element-plus/icons-vue";
import {
  getQueryDatasources,
  saveQueryDatasource,
  getDatasourceDetail,
  testQueryDatasource,
  deleteQueryDatasources,
  syncQueryDatasourceSchema,
  getQueryDatasourceSchema,
  importDsAsOntology,
  importDsAsOntologyBatch,
  getQueryAssetColumns,
  saveQueryAsset,
  saveQueryAssetColumn,
  batchSaveQueryAssetMeta,
  getQueryAssets,
  suggestQueryAssets,
  addFavorite,
  getQueryFewshots,
  saveQueryFewshot,
  deleteQueryFewshots,
  getPipelineGraph,
  getPipelineList,
  savePipeline,
  runPipeline,
  getPipelineData,
  getQueryMetrics,
  saveQueryMetric,
  deleteQueryMetrics,
  getQueryTerms,
  saveQueryTerm,
  deleteQueryTerms,
  getQueryConcepts,
  saveQueryConcept,
  deleteQueryConcepts,
  getQueryKgStats,
  getQueryKgUnified,
  rebuildQueryKg,
  autoLinkQueryKg,
  extractQueryObjects,
  inferQueryAssetRelations,
  generateQueryAssetDesc,
} from "@/api/module_ai/query";
import { getOntDomains, saveOntObject } from "@/api/module_ai/ontology";
import FilterRulesWorkbench from "./components/FilterRulesWorkbench.vue";
import GovernancePanel from "./components/GovernancePanel.vue";
import AssetVersionsDialog from "./components/AssetVersionsDialog.vue";
import AutoModelPreviewDialog from "./components/AutoModelPreviewDialog.vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";

const tab = ref("table");
const datasources = ref<any[]>([]);
const curDs = ref<any>(null);
const { t } = useI18n();
const dsTables = ref<any[]>([]);
const schemaRows = ref<any[]>([]);
const tableKw = ref("");
const curTable = ref("");
const columns = ref<any[]>([]);
const pipelines = ref<any[]>([]);
const metrics = ref<any[]>([]);
const terms = ref<any[]>([]);
const concepts = ref<any[]>([]);
const fewshots = ref<any[]>([]);
const fewshotDlg = ref(false);
const fewshotForm = ref<any>({});
const savingFewshot = ref(false);
const kg = ref<any>({});
const kgNodes = ref<any[]>([]);
const kgEdges = ref<any[]>([]);
const nodeStyle = {
  sizeMode: "fixed",
  fixedSize: 36,
  colorMode: "type",
  labelSize: 11,
} as const;
// 血缘图过滤：按节点类型 / 按表聚焦（性能优化，避免大图全渲染又密又慢）
const kgTypeFilter = ref<string[]>([]);
const kgTypeOptions = [
  { value: "table", label: t("ai_workflow.ig_kgTypeTable") },
  { value: "field", label: t("ai_workflow.ig_kgTypeField") },
  { value: "metric", label: t("ai_workflow.ig_kgTypeMetric") },
  { value: "term", label: t("ai_workflow.ig_kgTypeTerm") },
  { value: "domain", label: t("ai_workflow.ig_kgTypeDomain") },
  { value: "concept", label: t("ai_workflow.ig_kgTypeConcept") },
];
const kgTableFocus = ref("");
const kgTableOptions = ref<any[]>([]);
const filteredKgNodes = computed(() => {
  let list = kgNodes.value;
  if (kgTypeFilter.value.length) {
    list = list.filter((n) => kgTypeFilter.value.includes(n.etype));
  }
  if (kgTableFocus.value) {
    // 按表定位：保留该表（etype=table 且 name 含所选表名）+ 其 1 跳邻接
    const name = kgTableFocus.value;
    const focus = list.filter(
      (n) => n.etype === "table" && (n.name.includes(name) || name.includes(n.name))
    );
    const ids = new Set(focus.map((n) => n.name));
    const edges = kgEdges.value.filter((e) => ids.has(e.source) || ids.has(e.target));
    edges.forEach((e) => {
      ids.add(e.source);
      ids.add(e.target);
    });
    list = list.filter((n) => ids.has(n.name));
  }
  return list;
});
const filteredKgEdges = computed(() => {
  const nodeNames = new Set(filteredKgNodes.value.map((n) => n.name));
  return kgEdges.value.filter((e) => nodeNames.has(e.source) && nodeNames.has(e.target));
});
const assets = ref<any[]>([]);
const domains = ref<any[]>([]);

const syncing = ref(false);
const importing = ref(false);
const importingBatch = ref(false);
// 纯前端显示过滤开关：只看业务表（隐藏系统表）/ 只看业务字段（隐藏审计字段）
const hideSys = ref(false);
const hideAudit = ref(false);
const hideUnmaintained = ref(false);
// 导入时的目标本体域（单表与批量共用同一选择）
const importDomain = ref("");
const savingTable = ref(false);
const savingCol = ref("");
const savingDs = ref(false);
const dsDlg = ref(false);
const fieldDrawer = ref(false);
const versionsVisible = ref(false);
const versionsTable = ref("");
function openVersions(row: any) {
  versionsTable.value = row.table || row.table_name || "";
  versionsVisible.value = true;
}
async function addFav(row: any) {
  try {
    const r = await addFavorite("table", row.table || row.table_name);
    ElMessage.success(r?.data?.msg || t("ai_workflow.ig_favorited"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_favoriteFail"));
  }
}
const batchDlg = ref(false);
const batchText = ref("");
const batchSaving = ref(false);
const dsForm = ref<any>({ type: "postgres", port: 5432, read_only: true });

// 管道编排
const pipeDlg = ref(false);
const savingPipe = ref(false);
// 管道编排图
const pipeGraphVisible = ref(false);
const pipeGraphNodes = ref<any[]>([]);
const pipeGraphEdges = ref<any[]>([]);
const pipeForm = ref<any>({ enabled: true, mappings_text: "" });
const pipeDataDlg = ref(false);
const pipeDataName = ref("");
const pipeDataCols = ref<string[]>([]);
const pipeDataRows = ref<any[]>([]);
// AI 推荐指标/术语
const suggestVisible = ref(false);
const suggestLoading = ref(false);
const suggestMetrics = ref<any[]>([]);
const suggestTerms = ref<any[]>([]);
// 指标 / 术语 / 概念
const metricDlg = ref(false);
const savingMetric = ref(false);
const metricForm = ref<any>({});
const termDlg = ref(false);
const savingTerm = ref(false);
const termForm = ref<any>({});
const conceptDlg = ref(false);
const savingConcept = ref(false);
const conceptForm = ref<any>({});

const tmeta = ref<any>({
  alias: "",
  domain: "",
  description: "",
  business_scenarios: "",
  included: true,
  object_enabled: false,
  object_key_col: "id",
  object_name_col: "name",
});

// 表行 = schema 表清单（table/comment/is_system/字段数） + 语义元数据（来自 assets）
const tableRows = computed(() => {
  const amap = new Map(assets.value.map((a) => [a.table_name, a]));
  return dsTables.value.map((t) => {
    const a = amap.get(t.table);
    return {
      table: t.table,
      comment: t.comment || "",
      column_count: t.column_count ?? 0,
      is_system: !!t.is_system,
      alias: a?.alias || "",
      domain: a?.domain || "",
      description: a?.description || "",
      business_scenarios: a?.business_scenarios || "",
      // 纳入口径与后端 `_ds_schema_map(included_only=True)` 保持一致：
      // **没建过资产行（同步过 schema 但没治理）默认纳入**，同步完即可问数，
      // 但用 `governed` 在界面上标出「未治理」，避免用户误以为已经治理过。
      included: a?.included ?? true,
      governed: !!a,
      object_enabled: a?.object_enabled ?? false,
    };
  });
});

const filteredTables = computed(() => {
  const kw = tableKw.value.trim().toLowerCase();
  return tableRows.value.filter((t) => {
    // 「只看业务表」= 隐藏系统表（is_system 来自后端 schema 接口）
    if (hideSys.value && t.is_system) return false;
    // 「只看已维护」= 隐藏「未治理」和「显式排除」的表（治理过且在问数范围内才算已维护）
    if (hideUnmaintained.value && (!t.governed || t.included === false)) return false;
    if (!kw) return true;
    return (
      String(t.table).toLowerCase().includes(kw) ||
      String(t.comment).toLowerCase().includes(kw) ||
      String(t.alias || "")
        .toLowerCase()
        .includes(kw)
    );
  });
});

// 关联表下拉选项：当前数据源的所有表（el-select-v2 需 value/label）
const relTableOptions = computed(() =>
  tableRows.value.map((t) => ({
    value: t.table,
    label: t.alias ? `${t.alias}（${t.table}）` : t.table,
  }))
);

// 关联字段下拉选项：某张关联表的所有字段（取自已同步的 schema columns）
function relFieldOptions(table: string) {
  if (!table) return [];
  const row = schemaRows.value.find((x) => x.table === table);
  return (row?.columns || []).map((c: any) => {
    const name = c?.name ?? c?.column_name;
    return {
      value: name,
      label: c?.comment ? `${name}（${c.comment}）` : name,
    };
  });
}

// 字段清单同样做纯前端过滤：隐藏审计字段（is_audit 来自后端 columns 接口）
const filteredColumns = computed(() =>
  hideAudit.value ? columns.value.filter((c) => !c.is_audit) : columns.value
);

// 当前选中表是否为系统表（从 schema 表清单取，用于标题旁的系统标记）
const curTableSys = computed(() => {
  const t = dsTables.value.find((x) => x.table === curTable.value);
  return t ? !!t.is_system : undefined;
});

// 表清单空态文案：区分「未选数据源 / 被过滤清空 / 需同步」
const tableEmptyText = computed(() => {
  if (!curDs.value) return t("ai_workflow.ig_selectDsFirst");
  if (dsTables.value.length && !filteredTables.value.length) {
    return hideSys.value
      ? t("ai_workflow.ig_noBizTableAfterHide")
      : t("ai_workflow.ig_noMatchTable");
  }
  return t("ai_workflow.ig_syncToLoad");
});

async function loadDs() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
}

async function pickDs(row: any) {
  curDs.value = row;
  curTable.value = "";
  columns.value = [];
  dsTables.value = [];
  if (row) await loadDsTables();
}

async function loadDsTables() {
  if (!curDs.value) return;
  try {
    const r = await getQueryDatasourceSchema(curDs.value.id);
    const rows = r.data?.data || [];
    schemaRows.value = rows;
    dsTables.value = rows.map((x: any) => ({
      table: x.table,
      comment: x.comment || "",
      column_count: (x.columns || []).length,
      // Task：schema 接口给每表打 is_system 标，用于「只看业务表」过滤与系统标记
      is_system: !!x.is_system,
    }));
  } catch {
    dsTables.value = [];
  }
}

async function syncSchema() {
  if (!curDs.value) return;
  syncing.value = true;
  try {
    const r = await syncQueryDatasourceSchema(curDs.value.id);
    ElMessage.success(t("ai_workflow.ig_syncedCount", { count: r.data?.data?.tables ?? 0 }));
    await loadDsTables();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_syncFail"));
  } finally {
    syncing.value = false;
  }
}

function fillTmeta(table: string) {
  const a = assets.value.find((x) => x.table_name === table);
  tmeta.value = {
    alias: a?.alias || "",
    domain: a?.domain || "",
    description: a?.description || "",
    business_scenarios: a?.business_scenarios || "",
    included: a?.included ?? true,
    object_enabled: a?.object_enabled ?? false,
    object_key_col: a?.object_key_col || "id",
    object_name_col: a?.object_name_col || "name",
  };
}

async function pickTable(row: any) {
  if (!row) return;
  curTable.value = row.table;
  fillTmeta(row.table);
  try {
    const r = await getQueryAssetColumns(row.table);
    columns.value = (r.data?.data || []).map((c: any) => ({
      ...c,
      // 中文名优先用人工维护值；没有则预填上游注释，省一次手输
      description: c.description || c.comment || "",
      // 枚举统一规范为数组，供 el-select multiple/allow-create 绑定
      enum: Array.isArray(c.enum) ? c.enum : [],
    }));
  } catch {
    columns.value = [];
  }
}

// 点表清单「字段」：加载该表字段并打开字段维护抽屉
async function openFieldDrawer(row: any) {
  await pickTable(row);
  fieldDrawer.value = true;
}

async function saveTable() {
  if (!curTable.value) return;
  savingTable.value = true;
  try {
    await saveQueryAsset({ table_name: curTable.value, ...tmeta.value }, { silent: true });
    // 收敛（Object Type 单一真相源）：勾选「纳入本体对象」时，同步在本体生成 ObjectType（按 code 幂等 upsert）
    if (tmeta.value.object_enabled) {
      try {
        await saveOntObject(
          {
            code: curTable.value,
            name: tmeta.value.alias || curTable.value,
            key_prop: tmeta.value.object_key_col || "id",
            name_prop: tmeta.value.object_name_col || "name",
            icon: tmeta.value.object_icon || "el-icon-Box",
            backing_table: curTable.value,
            datasource_id: curDs.value?.id,
            domain_code: tmeta.value.domain || "",
          },
          { silent: true }
        );
      } catch {
        /* 本体对象创建失败不阻断表信息保存 */
      }
    }
    ElMessage.success(t("ai_workflow.ig_tableSaved"));
    await loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingTable.value = false;
  }
}

async function saveColumn(row: any, quiet = false) {
  savingCol.value = typeof row === "string" ? row : row.column_name;
  try {
    await saveQueryAssetColumn({
      table_name: curTable.value,
      column_name: row.column_name,
      description: row.description || "",
      business_scenarios: row.business_scenarios || "",
      related_table: row.related_table || "",
      related_field: row.related_field || "",
      included: row.included !== false,
      sensitive: !!row.sensitive,
      enum: Array.isArray(row.enum) ? row.enum : [],
    });
    if (!quiet) ElMessage.success(t("ai_workflow.ig_fieldSaved", { name: row.column_name }));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingCol.value = "";
  }
}

const colDlg = ref(false);
const colForm = ref<any>({
  column_name: "",
  description: "",
  business_scenarios: "",
  related_table: "",
  related_field: "",
  enum: [],
  included: true,
  sensitive: false,
});

// 点字段行「编辑属性」：打开单字段属性弹窗，中文名/业务场景/关联表/关联字段/枚举集中编辑
function openColEdit(row: any) {
  colForm.value = {
    column_name: row.column_name,
    description: row.description || "",
    business_scenarios: row.business_scenarios || "",
    related_table: row.related_table || "",
    related_field: row.related_field || "",
    enum: Array.isArray(row.enum) ? [...row.enum] : [],
    included: row.included !== false,
    sensitive: !!row.sensitive,
  };
  colDlg.value = true;
}

async function saveColEdit() {
  savingCol.value = colForm.value.column_name;
  try {
    await saveQueryAssetColumn({ table_name: curTable.value, ...colForm.value });
    ElMessage.success(t("ai_workflow.ig_fieldSaved", { name: colForm.value.column_name }));
    // 同步回字段清单行
    const row = columns.value.find((c) => c.column_name === colForm.value.column_name);
    if (row) Object.assign(row, colForm.value);
    colDlg.value = false;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingCol.value = "";
  }
}

async function doImport() {
  if (!curDs.value || !curTable.value) return;
  importing.value = true;
  try {
    const r = await importDsAsOntology(curDs.value.id, curTable.value, importDomain.value);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](
      d.ok ? t("ai_workflow.ig_importedObject", { object: d.object, count: d.props }) : d.msg
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_importFail"));
  } finally {
    importing.value = false;
  }
}

/** 解析批量粘贴内容：每行「表名 中文名」或「表名,中文名,业务域」。
 *  分隔符兼容逗号 / 制表符 / 多个空格——从 Excel 复制过来是制表符。 */
const batchRows = computed(() => {
  const known = new Set(dsTables.value.map((t) => t.table));
  const out: any[] = [];
  for (const raw of batchText.value.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line
      .split(/[,\t]+|\s{2,}/)
      .map((s) => s.trim())
      .filter(Boolean);
    // 退一步：中文名里可能有单个空格，按"第一个空白"切
    let cells = parts;
    if (cells.length < 2) {
      const m = line.match(/^(\S+)\s+(.+)$/);
      cells = m ? [m[1], m[2]] : [line];
    }
    const table_name = cells[0] || "";
    if (!table_name) continue;
    out.push({
      table_name,
      alias: cells[1] || "",
      domain: cells[2] || "",
      known: known.size === 0 || known.has(table_name),
    });
  }
  return out;
});
const batchUnknown = computed(() => batchRows.value.filter((r) => !r.known));

function openBatch() {
  batchText.value = "";
  batchDlg.value = true;
}

async function doBatchSave() {
  const items = batchRows.value.map((r) => {
    const it: any = { table_name: r.table_name };
    if (r.alias) it.alias = r.alias;
    if (r.domain) it.domain = r.domain;
    return it;
  });
  if (!items.length) return;
  batchSaving.value = true;
  try {
    const res = await batchSaveQueryAssetMeta(items);
    const d = res.data?.data || {};
    ElMessage.success(t("ai_workflow.ig_savedTableCount", { count: d.saved ?? 0 }));
    batchDlg.value = false;
    await loadAssets();
    if (curTable.value) fillTmeta(curTable.value);
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_batchSaveFail"));
  } finally {
    batchSaving.value = false;
  }
}

function openDs(row?: any) {
  if (row) {
    dsForm.value = { ...row, password: "" };
    normalizeRules(dsForm.value);
    // 编辑时拉取详情（含已解析的 filter_rules），密码留空由用户按需重填
    getDatasourceDetail(row.id)
      .then((r) => {
        dsForm.value = { ...dsForm.value, ...(r.data?.data || {}), password: "" };
        normalizeRules(dsForm.value);
      })
      .catch(() => {
        /* 拉取详情失败则保留列表数据 */
      });
  } else {
    dsForm.value = {
      code: "",
      name: "",
      type: "postgres",
      host: "",
      port: 5432,
      database: "",
      username: "",
      password: "",
      read_only: true,
      filter_rules: null,
    };
    normalizeRules(dsForm.value);
  }
  dsDlg.value = true;
}

// 确保 dsForm.filter_rules 结构完整，供编辑弹窗绑定
function normalizeRules(f: any) {
  const fr = f?.filter_rules || {};
  f.filter_rules = {
    enabled: fr.enabled !== false,
    system_table: {
      prefixes: Array.isArray(fr?.system_table?.prefixes) ? fr.system_table.prefixes : [],
      keywords: Array.isArray(fr?.system_table?.keywords) ? fr.system_table.keywords : [],
      exact: Array.isArray(fr?.system_table?.exact) ? fr.system_table.exact : [],
      regex: fr?.system_table?.regex || "",
    },
    audit_fields: Array.isArray(fr?.audit_fields) ? fr.audit_fields : [],
  };
}

async function saveDs() {
  savingDs.value = true;
  try {
    await saveQueryDatasource(dsForm.value);
    ElMessage.success(t("ai_workflow.ig_saveSuccess"));
    dsDlg.value = false;
    await loadDs();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingDs.value = false;
  }
}

async function testDs(row: any) {
  try {
    const r = await testQueryDatasource(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](
      d.message || (d.ok ? t("ai_workflow.ig_connSuccess") : t("ai_workflow.ig_connFail"))
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_testFail"));
  }
}

/** 删除数据源（删除类操作必须二次确认，文案写明影响范围）。 */
async function removeDs(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.ig_delDsConfirm", { name: row.name || row.code }),
      t("ai_workflow.ig_delDsTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.ig_delete"),
        cancelButtonText: t("ai_workflow.ig_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await deleteQueryDatasources([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    // 删除的是当前选中数据源时，清空选中态并回退到空表清单
    if (curDs.value && curDs.value.id === row.id) {
      curDs.value = null;
      curTable.value = "";
      columns.value = [];
      dsTables.value = [];
    }
    await loadDs();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

/** 批量导入：把当前数据源的业务表（非系统表）一次性导为目标本体对象，带到所选本体域。
 *  注意基于 dsTables 而非 filteredTables：搜索关键字（tableKw）只是表清单的显示过滤，
 *  不应影响批量导入的范围——始终导入当前数据源的全部业务表。 */
async function doBatchImport() {
  if (!curDs.value) return;
  const tables = dsTables.value.filter((t) => !t.is_system).map((t) => t.table);
  if (!tables.length) {
    ElMessage.warning(t("ai_workflow.ig_noImportBizTable"));
    return;
  }
  importingBatch.value = true;
  try {
    const r = await importDsAsOntologyBatch(curDs.value.id, tables, false, importDomain.value);
    const d = r.data?.data || {};
    ElMessage[r.data?.msg && !d.ok ? "error" : "success"](
      d.ok
        ? t("ai_workflow.ig_importedCount", { count: d.imported ?? 0 })
        : d.msg || t("ai_workflow.ig_importFail")
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_batchImportFail"));
  } finally {
    importingBatch.value = false;
  }
}

/** 拉取本体域列表，供导入目标域下拉选中（GET /ai/ontology/domains）。 */
async function loadDomains() {
  try {
    const r = await getOntDomains();
    domains.value = r.data?.data || [];
  } catch {
    domains.value = [];
  }
}

/** 解析字段映射：支持「源 目标」多行文本，也支持直接粘贴 JSON 数组。 */
function parseMappings(text: string): any[] {
  const raw = (text || "").trim();
  if (!raw) return [];
  if (raw.startsWith("[")) {
    try {
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch {
      ElMessage.warning(t("ai_workflow.ig_mappingParseFail"));
      return [];
    }
  }
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const m = line.match(/^(\S+)[\s,]+(\S+)$/);
      return m ? { from: m[1], to: m[2] } : { from: line, to: line };
    });
}

async function openPipeGraph() {
  pipeGraphVisible.value = true;
  try {
    const r = await getPipelineGraph();
    const d = r.data?.data || { nodes: [], edges: [] };
    pipeGraphNodes.value = (d.nodes || []).map((n: any) => ({
      id: String(n.id),
      name: n.name,
      etype: n.etype,
      category: n.etype,
    }));
    pipeGraphEdges.value = (d.edges || []).map((e: any) => ({
      source: String(e.source),
      target: String(e.target),
      rtype: e.rtype,
    }));
  } catch {
    pipeGraphNodes.value = [];
    pipeGraphEdges.value = [];
  }
}

function openPipe(row?: any) {
  if (row) {
    const arr = Array.isArray(row.mappings) ? row.mappings : [];
    const text = arr
      .map((m: any) => `${m.from ?? m.source ?? ""} ${m.to ?? m.target ?? ""}`.trim())
      .join("\n");
    pipeForm.value = { ...row, mappings_text: text, enabled: row.enabled !== false };
  } else {
    pipeForm.value = {
      name: "",
      source_connection: "",
      source_table: "",
      target_object: "",
      mappings_text: "",
      enabled: true,
    };
  }
  pipeDlg.value = true;
}

async function savePipe() {
  if (!pipeForm.value.name) {
    ElMessage.warning(t("ai_workflow.ig_pipeNameRequired"));
    return;
  }
  savingPipe.value = true;
  try {
    await savePipeline({
      ...pipeForm.value,
      mappings: parseMappings(pipeForm.value.mappings_text),
    });
    ElMessage.success(t("ai_workflow.ig_pipeSaved"));
    pipeDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingPipe.value = false;
  }
}

async function viewPipeData(row: any) {
  pipeDataName.value = row.name || "";
  pipeDataCols.value = [];
  pipeDataRows.value = [];
  pipeDataDlg.value = true;
  try {
    const r = await getPipelineData(row.id, 50);
    const d = r.data?.data || {};
    if (d.ok === false) {
      ElMessage.warning(d.msg || t("ai_workflow.ig_noPipeData"));
      return;
    }
    const cols: string[] = d.columns || [];
    pipeDataCols.value = cols;
    pipeDataRows.value = (d.rows || []).map((arr: any[]) => {
      const o: Record<string, any> = {};
      cols.forEach((c, i) => (o[c] = arr[i]));
      return o;
    });
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_pipeDataFail"));
  }
}

async function runPipe(row: any) {
  try {
    const r = await runPipeline(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.msg || t("ai_workflow.ig_ran"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_runFail"));
  }
}

// ---- 指标 ----
function openMetric(row?: any) {
  metricForm.value = row
    ? { ...row }
    : {
        datasource: "system",
        name: "",
        key: "",
        sql_template: "",
        agg: "count",
        unit: "",
        enabled: true,
      };
  metricDlg.value = true;
}

// AI 推荐指标/术语
async function openSuggest() {
  suggestVisible.value = true;
  suggestLoading.value = true;
  suggestMetrics.value = [];
  suggestTerms.value = [];
  try {
    const r = await suggestQueryAssets();
    const d = r.data?.data || {};
    suggestMetrics.value = d.metrics || [];
    suggestTerms.value = d.terms || [];
    if (!suggestMetrics.value.length && !suggestTerms.value.length) {
      ElMessage.warning(t("ai_workflow.ig_noSuggestResult"));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_suggestFail"));
  } finally {
    suggestLoading.value = false;
  }
}

/** 采纳推荐指标 → 预填「新建指标」弹窗（编码需用户补全后保存）。 */
function adoptMetric(row: any) {
  suggestVisible.value = false;
  openMetric();
  metricForm.value = {
    datasource: "system",
    name: row.name || "",
    key: "",
    sql_template: row.sql || "",
    agg: row.agg || "count",
    unit: "",
    enabled: true,
  };
}

/** 采纳推荐术语 → 预填「新建术语」弹窗。 */
function adoptTerm(row: any) {
  suggestVisible.value = false;
  openTerm();
  const isDim = row.type === "dimension";
  termForm.value = {
    datasource: "system",
    term: row.term || "",
    type: isDim ? "dimension" : "metric",
    metric_key: isDim ? "" : row.target || "",
    field_path: isDim ? row.target || "" : "",
  };
}

async function saveMetric() {
  const f = metricForm.value;
  if (!f.name || !f.key) {
    ElMessage.warning(t("ai_workflow.ig_metricRequired"));
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(f.key)) {
    ElMessage.warning(t("ai_workflow.ig_codeInvalid"));
    return;
  }
  savingMetric.value = true;
  try {
    await saveQueryMetric({ ...f, params: f.params || [], dimensions: f.dimensions || [] });
    ElMessage.success(t("ai_workflow.ig_metricSaved"));
    metricDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingMetric.value = false;
  }
}

async function removeMetric(row: any) {
  await ElMessageBox.confirm(
    t("ai_workflow.ig_delMetricConfirm", { name: row.name || row.key }),
    t("ai_workflow.ig_delMetricTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  );
  try {
    await deleteQueryMetrics([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

// ---- 示例工程（few-shot）----
function openFewshot(row?: any) {
  fewshotForm.value = row
    ? { ...row }
    : { datasource: "system", question: "", sql: "", enabled: true };
  fewshotDlg.value = true;
}

async function saveFewshot() {
  const f = fewshotForm.value;
  if (!f.question?.trim()) {
    ElMessage.warning(t("ai_workflow.ig_questionRequired"));
    return;
  }
  if (!f.sql?.trim()) {
    ElMessage.warning(t("ai_workflow.ig_sqlRequired"));
    return;
  }
  savingFewshot.value = true;
  try {
    await saveQueryFewshot({ ...f });
    ElMessage.success(t("ai_workflow.ig_exampleSaved"));
    fewshotDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingFewshot.value = false;
  }
}

async function removeFewshot(row: any) {
  await ElMessageBox.confirm(
    t("ai_workflow.ig_delExampleConfirm", { name: (row.question || "").slice(0, 20) }),
    t("ai_workflow.ig_delExampleTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  );
  try {
    await deleteQueryFewshots([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

// ---- 术语 ----
function openTerm(row?: any) {
  termForm.value = row
    ? { ...row }
    : { datasource: "system", term: "", metric_key: "", field_path: "", type: "metric" };
  termDlg.value = true;
}

async function saveTerm() {
  const f = termForm.value;
  if (!f.term) {
    ElMessage.warning(t("ai_workflow.ig_termRequired"));
    return;
  }
  savingTerm.value = true;
  try {
    await saveQueryTerm({ ...f });
    ElMessage.success(t("ai_workflow.ig_termSaved"));
    termDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingTerm.value = false;
  }
}

async function removeTerm(row: any) {
  await ElMessageBox.confirm(
    t("ai_workflow.ig_delTermConfirm", { name: row.term }),
    t("ai_workflow.ig_delTermTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  );
  try {
    await deleteQueryTerms([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

// ---- 概念 ----
function openConcept(row?: any) {
  conceptForm.value = row
    ? { ...row, tables_text: (row.tables || []).join(",") }
    : {
        name: "",
        description: "",
        synonyms: "",
        parent_name: "",
        domain: "",
        metric_key: "",
        tables_text: "",
      };
  conceptDlg.value = true;
}

async function saveConcept() {
  const f = conceptForm.value;
  if (!f.name) {
    ElMessage.warning(t("ai_workflow.ig_conceptRequired"));
    return;
  }
  savingConcept.value = true;
  try {
    await saveQueryConcept({
      ...f,
      tables: (f.tables_text || "")
        .split(",")
        .map((s: string) => s.trim())
        .filter(Boolean),
    });
    ElMessage.success(t("ai_workflow.ig_conceptSaved"));
    conceptDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingConcept.value = false;
  }
}

async function removeConcept(row: any) {
  await ElMessageBox.confirm(
    t("ai_workflow.ig_delConceptConfirm", { name: row.name }),
    t("ai_workflow.ig_delConceptTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  );
  try {
    await deleteQueryConcepts([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

async function syncKg() {
  try {
    await rebuildQueryKg();
    ElMessage.success(t("ai_workflow.ig_graphRebuilt"));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_fail"));
  }
}

async function autoLinkKg() {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.ig_autoLinkConfirm"),
      t("ai_workflow.ig_autoLinkTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.ig_start"),
        cancelButtonText: t("ai_workflow.ig_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const r = await autoLinkQueryKg();
    const d = r.data?.data || {};
    ElMessage.success(
      t("ai_workflow.ig_linkedCount", { count: d.linked ?? d.saved ?? d.count ?? 0 })
    );
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_autoLinkFail"));
  }
}

// AI 生成描述：原来治理巡检的「补全描述」是占位实现（把 alias 写成 "数据表 X" 的假描述），
// 真正调 LLM 的 /assets/generate-desc 端点在前端零入口。这里补上（只补缺的，人工校对后生效）。
const generatingDesc = ref(false);
async function runGenerateDesc() {
  generatingDesc.value = true;
  try {
    const r: any = await generateQueryAssetDesc(false);
    const d = r.data?.data || {};
    ElMessage.success(
      r.data?.msg ||
        t("ai_workflow.ig_descGenerated", { tables: d.tables ?? 0, columns: d.columns ?? 0 })
    );
    await loadAssets();
  } catch (e: any) {
    // 拦截器 reject 的是 axios response，真实 msg 在 data.msg（e.msg 恒为 undefined）
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_workflow.ig_descGenFail"));
  } finally {
    generatingDesc.value = false;
  }
}

async function loadAssets() {
  try {
    const r = await getQueryAssets();
    assets.value = r.data?.data || [];
  } catch {
    assets.value = [];
  }
}

async function loadMisc() {
  const safe = async (fn: () => Promise<any>, set: (v: any) => void) => {
    try {
      const r = await fn();
      set(r.data?.data ?? {});
    } catch {
      set([]);
    }
  };
  await safe(getPipelineList, (v) => (pipelines.value = v));
  await safe(getQueryMetrics, (v) => (metrics.value = v));
  await safe(getQueryTerms, (v) => (terms.value = v));
  await safe(getQueryConcepts, (v) => (concepts.value = v));
  await safe(getQueryFewshots, (v) => (fewshots.value = v));
  await safe(getQueryKgStats, (v) => (kg.value = v));
  await loadUnified();
}

async function loadUnified() {
  try {
    const r = await getQueryKgUnified();
    const d = r.data?.data || { nodes: [], edges: [] };
    const nodes = (d.nodes || []).map((n: any) => ({
      id: n.name,
      name: n.name,
      etype: n.etype,
      category: n.etype,
    }));
    const edges = (d.edges || []).map((e: any) => ({
      source: e.source,
      target: e.target,
      rtype: e.rtype,
    }));
    kgNodes.value = nodes;
    kgEdges.value = edges;
    kgTableOptions.value = nodes
      .filter((n: any) => n.etype === "table")
      .map((n: any) => (n.name as string).replace(/^表:/, ""));
  } catch {
    kgNodes.value = [];
    kgEdges.value = [];
    kgTableOptions.value = [];
  }
}

onMounted(async () => {
  await Promise.all([loadDs(), loadAssets(), loadMisc(), loadDomains()]);
});

// 语义建模（S4）：大模型自动生成指标/标注
// **两段式**：按钮只负责打开预览对话框；大模型调用与落库都在 `AutoModelPreviewDialog` 里完成
// （先预览出候选、用户勾选后精确落库；应用阶段不重跑大模型）。
const modelingMax = ref(12);
const modelingResult = ref<any>(null);
const modelingDsCode = computed(
  () => curDs.value?.code || (curDs.value ? `ds:${curDs.value.id}` : "")
);
const autoModelVisible = ref(false);
const autoModelScope = ref<"metrics" | "annotations">("metrics");

function openAutoModel(scope: "metrics" | "annotations") {
  if (!curDs.value) return;
  autoModelScope.value = scope;
  autoModelVisible.value = true;
}

function onAutoModelApplied(result: any) {
  modelingResult.value = result;
  void loadMisc();
}

// 语义抽取对象 / 推断表间关系（此前有 API 无入口，此处接入「语义建模」）
const semanticLoading = ref(false);

async function handleExtractObjects() {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.ig_extractConfirm"),
      t("ai_workflow.ig_extractTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.ig_start"),
        cancelButtonText: t("ai_workflow.ig_cancel"),
      }
    );
  } catch {
    return;
  }
  semanticLoading.value = true;
  try {
    const r: any = await extractQueryObjects();
    const d = r?.data?.data ?? r?.data ?? {};
    ElMessage.success(t("ai_workflow.ig_extractedCount", { count: d.saved ?? d.count ?? 0 }));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_workflow.ig_extractFail"));
  } finally {
    semanticLoading.value = false;
  }
}

async function handleInferRelations() {
  try {
    await ElMessageBox.confirm(t("ai_workflow.ig_inferConfirm"), t("ai_workflow.ig_inferTitle"), {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_start"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    });
  } catch {
    return;
  }
  semanticLoading.value = true;
  try {
    const r: any = await inferQueryAssetRelations();
    const d = r?.data?.data ?? r?.data ?? {};
    ElMessage.success(t("ai_workflow.ig_inferredCount", { count: d.saved ?? d.count ?? 0 }));
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_workflow.ig_inferFail"));
  } finally {
    semanticLoading.value = false;
  }
}
</script>

<style lang="scss">
.app-container.ai-integration-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
}
</style>

<style scoped lang="scss">
.ig-fill,
.ig-card {
  height: 100%;
}
.ig-card :deep(.el-card__body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.ig-tabs,
.ig-tabs :deep(.el-tabs__content),
.ig-tabs :deep(.el-tab-pane) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.ig-head,
.ig-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ig-head {
  justify-content: space-between;
}
.ig-bar {
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ig-split {
  display: flex;
  flex: 1;
  gap: 12px;
  min-height: 0;
}
.ig-tables {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
/* 字段维护抽屉：内容占满、字段表独立滚动 */
.ig-field-drawer :deep(.el-drawer__body) {
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: hidden;
}
.ig-detail-drawer {
  flex: 1;
  min-height: 0;
}
.ig-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.ig-fields-wrap {
  flex: 1;
  min-height: 0;
}
.ig-tname {
  color: var(--el-text-color-primary);
}
.ig-tcmt {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ig-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ig-sub {
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.ig-form {
  flex-shrink: 0;
}
.ig-form__divider {
  margin: 18px 0 10px;
}
.ig-cell-select {
  width: 100%;
}
.ig-note {
  margin-bottom: 10px;
}
.ig-tag {
  margin: 0 2px;
}
.ig-batch-bar {
  margin-top: 8px;
}
/* 左栏：数据源标题 */
.ig-side-title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
/* 左栏：数据源纵向列表（仿本体左侧导航） */
.ig-ds-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow: auto;
}
.ig-ds-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  border-radius: 4px;
}
.ig-ds-item:hover {
  background: var(--el-fill-color-light);
}
.ig-ds-item.is-active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.ig-ds-item__icon {
  flex-shrink: 0;
  font-size: var(--el-font-size-medium);
}
.ig-ds-item__text {
  flex: 1 1 auto;
  min-width: 0;
}
.ig-ds-item__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
.ig-ds-item.is-active .ig-ds-item__name {
  color: var(--el-color-primary);
}
.ig-ds-item__sub {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 2px;
}
.ig-ds-item__count {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ig-ds-item__ops {
  display: flex;
  visibility: hidden;
  flex-shrink: 0;
  /* 窄左栏（240px）：操作改成竖排图标列，悬浮/选中才显示，避免挤占名称空间 */
  flex-direction: column;
  gap: 0;
  align-items: center;
}
.ig-ds-item:hover .ig-ds-item__ops,
.ig-ds-item.is-active .ig-ds-item__ops {
  visibility: visible;
}
/* 表清单 / 字段清单工具条里的元素 */
.ig-bar__search {
  width: 180px;
}
.ig-bar__gap {
  flex: 1 1 auto;
}
.ig-bar__domain {
  width: 150px;
}
.ig-kg-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
  margin-bottom: 6px;
}
.ig-kg-filter__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ig-kg-filter__hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>

<!-- 布局统一（非 scoped + 唯一类名）：左栏固定 240px（与工作台/个人空间/问数/本体一致） -->
<style lang="scss">
.ai-integration-page > .el-row.ig-fill {
  flex-wrap: nowrap;
  gap: 12px;
  margin: 0 !important;
}

.ai-integration-page > .el-row.ig-fill > .el-col {
  padding: 0 !important;
}

.ai-integration-page > .el-row.ig-fill > .el-col:first-child {
  flex: 0 0 240px;
  max-width: 240px;
}

.ai-integration-page > .el-row.ig-fill > .el-col:last-child {
  flex: 1 1 auto;
  max-width: 100%;
}
</style>
