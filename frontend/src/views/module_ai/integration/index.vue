<!-- 数据与集成：把「数据资产」合并进来，做成一条路 —— 选数据源 → 选表 → 就地维护元数据 -->
<template>
  <div class="app-container ai-mod ai-integration-page">
    <el-row :gutter="12" class="ig-fill">
      <!-- 左：数据源（纵向列表，仿「本体」左侧导航） -->
      <el-col v-if="tab !== 'gov'" :xs="24" :sm="8" :md="6" :lg="5" class="ig-fill">
        <el-card shadow="never" class="ig-card">
          <template #header>
            <div class="ig-head">
              <span class="ig-side-title">数据源</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openDs()">新建</el-button>
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
                    {{ d.table_count }} 表
                  </span>
                </div>
              </div>
              <div class="ig-ds-item__ops" @click.stop>
                <el-button link type="primary" size="small" @click="testDs(d)">测试</el-button>
                <el-button link type="primary" size="small" @click="openDs(d)">编辑</el-button>
                <el-button
                  v-hasPerm="['module_ai:query:ask']"
                  link
                  type="danger"
                  size="small"
                  @click="removeDs(d)"
                >
                  删除
                </el-button>
              </div>
            </div>
            <el-empty
              v-if="!datasources.length"
              :image-size="60"
              description="暂无数据源，点「新建」创建"
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
            <el-tab-pane label="表与字段" name="table">
              <!-- 表清单：铺满 tab 高度，超出滚动 -->
              <div class="ig-tables">
                <div class="ig-bar">
                  <el-input
                    v-model="tableKw"
                    size="small"
                    placeholder="搜索表名/中文名"
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
                    同步
                  </el-button>
                  <el-button size="small" :icon="EditPen" @click="openBatch">批量维护</el-button>
                  <el-switch v-model="hideSys" active-text="只看业务表" />
                  <el-switch v-model="hideUnmaintained" active-text="只看已维护" />
                  <span class="ig-bar__gap" />
                  <el-select
                    v-model="importDomain"
                    size="small"
                    clearable
                    placeholder="目标本体域"
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
                    size="small"
                    :icon="DataBoard"
                    :disabled="!curDs"
                    :loading="importingBatch"
                    @click="doBatchImport"
                  >
                    批量导入
                  </el-button>
                </div>
                <el-table :data="filteredTables" size="small" border height="100%" row-key="table">
                  <template #empty>
                    <el-empty :description="tableEmptyText" :image-size="50" />
                  </template>
                  <el-table-column label="表名" min-width="200" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div class="ig-tname">{{ row.table }}</div>
                      <div v-if="row.comment" class="ig-tcmt">{{ row.comment }}</div>
                    </template>
                  </el-table-column>
                  <el-table-column label="中文名" min-width="140" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.alias || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="业务域" min-width="120" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.domain || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="业务描述" min-width="180" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.description || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="业务场景" min-width="140" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.business_scenarios || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="字段数" width="70" align="center">
                    <template #default="{ row }">{{ row.column_count ?? "-" }}</template>
                  </el-table-column>
                  <el-table-column label="纳入" width="64" align="center">
                    <template #default="{ row }">
                      <el-tag
                        size="small"
                        :type="row.included === false ? 'info' : 'success'"
                        effect="plain"
                      >
                        {{ row.included === false ? "否" : "是" }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="系统/业务" width="92" align="center">
                    <template #default="{ row }">
                      <el-tag
                        size="small"
                        :type="row.is_system ? 'warning' : 'success'"
                        effect="plain"
                      >
                        {{ row.is_system ? "系统表" : "业务表" }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="224" align="center" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" size="small" @click="openFieldDrawer(row)">
                        字段
                      </el-button>
                      <el-button link type="primary" size="small" @click="openVersions(row)">
                        版本
                      </el-button>
                      <el-button link type="primary" size="small" @click="addFav(row)">
                        收藏
                      </el-button>
                      <el-button link type="primary" size="small" @click="shareTable(row)">
                        分享
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>

              <!-- 选中表：抽屉里做元数据 + 字段维护 -->
              <el-drawer
                v-model="fieldDrawer"
                :title="`字段维护：${curTable || ''}`"
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
                      {{ curTableSys ? "系统表" : "业务表" }}
                    </el-tag>
                    <el-button
                      size="small"
                      type="primary"
                      :loading="savingTable"
                      @click="saveTable"
                    >
                      保存表信息
                    </el-button>
                    <el-select
                      v-model="importDomain"
                      size="small"
                      clearable
                      placeholder="目标本体域"
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
                      size="small"
                      :icon="DataBoard"
                      :loading="importing"
                      @click="doImport"
                    >
                      导入为本体对象
                    </el-button>
                  </div>
                  <el-form :model="tmeta" label-width="100px" size="small" class="ig-form">
                    <el-form-item label="中文名">
                      <el-input v-model="tmeta.alias" placeholder="如：燃煤采购结算主表" />
                    </el-form-item>
                    <el-form-item label="业务域">
                      <el-input v-model="tmeta.domain" placeholder="如：燃煤/设备/人员" />
                    </el-form-item>
                    <el-form-item label="业务描述">
                      <el-input
                        v-model="tmeta.description"
                        type="textarea"
                        :rows="2"
                        placeholder="这张表存什么、怎么用——问数会读它来理解表"
                      />
                    </el-form-item>
                    <el-form-item label="业务场景">
                      <el-input
                        v-model="tmeta.business_scenarios"
                        placeholder="哪些报表/业务用到"
                      />
                    </el-form-item>
                    <el-form-item label="纳入问数">
                      <el-switch v-model="tmeta.included" />
                    </el-form-item>
                    <el-divider content-position="left" class="ig-form__divider">
                      本体对象建模
                    </el-divider>
                    <el-form-item label="业务对象">
                      <el-switch v-model="tmeta.object_enabled" />
                    </el-form-item>
                    <el-form-item label="主键列">
                      <el-input v-model="tmeta.object_key_col" :disabled="!tmeta.object_enabled" />
                    </el-form-item>
                    <el-form-item label="显示名列">
                      <el-input v-model="tmeta.object_name_col" :disabled="!tmeta.object_enabled" />
                    </el-form-item>
                  </el-form>

                  <div class="ig-bar">
                    <span class="ig-sub">字段（{{ filteredColumns.length }}）</span>
                    <el-switch v-model="hideAudit" active-text="只看业务字段" />
                    <el-tag size="small" type="info" effect="plain">
                      上游注释可作参考，中文名/枚举可人工维护
                    </el-tag>
                  </div>
                  <div class="ig-fields-wrap">
                    <el-table :data="filteredColumns" size="small" border height="100%">
                      <template #empty>
                        <el-empty description="该表暂无字段信息，请先同步表结构" :image-size="50" />
                      </template>
                      <el-table-column
                        prop="column_name"
                        label="字段"
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
                      <el-table-column label="中文名" min-width="110" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.description || "-" }}</template>
                      </el-table-column>
                      <el-table-column label="业务场景" min-width="120" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.business_scenarios || "-" }}</template>
                      </el-table-column>
                      <el-table-column label="关联表" min-width="110" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.related_table || "-" }}</template>
                      </el-table-column>
                      <el-table-column label="关联字段" min-width="100" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.related_field || "-" }}</template>
                      </el-table-column>
                      <el-table-column label="枚举" min-width="120" show-overflow-tooltip>
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
                      <el-table-column label="纳入" width="56" align="center">
                        <template #default="{ row }">
                          <el-switch
                            v-model="row.included"
                            size="small"
                            @change="saveColumn(row, true)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column label="敏感" width="56" align="center">
                        <template #default="{ row }">
                          <el-switch
                            v-model="row.sensitive"
                            size="small"
                            @change="saveColumn(row, true)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="96" align="center" fixed="right">
                        <template #default="{ row }">
                          <el-button link type="primary" size="small" @click="openColEdit(row)">
                            编辑属性
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </el-drawer>
            </el-tab-pane>

            <!-- 管道 -->
            <el-tab-pane label="管道" name="pipe">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openPipe()">
                  新建管道
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  源表 → 目标对象，运行后落到管道物化表
                </el-tag>
              </div>
              <el-table :data="pipelines" size="small" border height="100%">
                <template #empty>
                  <el-empty description="暂无管道" :image-size="60" />
                </template>
                <el-table-column prop="name" label="管道" min-width="140" show-overflow-tooltip />
                <el-table-column label="源→目标" min-width="180" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ row.source_table }} → {{ row.target_object }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="180" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="runPipe(row)">
                      运行
                    </el-button>
                    <el-button link type="primary" size="small" @click="openPipe(row)">
                      编辑
                    </el-button>
                    <el-button link type="primary" size="small" @click="viewPipeData(row)">
                      数据
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 指标 -->
            <el-tab-pane label="指标" name="metric">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openMetric()">
                  新建指标
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  语义指标（问数与 Agent 消费）
                </el-tag>
              </div>
              <el-table :data="metrics" size="small" border height="100%">
                <template #empty>
                  <el-empty description="暂无指标" :image-size="60" />
                </template>
                <el-table-column prop="name" label="指标" min-width="150" show-overflow-tooltip />
                <el-table-column prop="key" label="编码" min-width="130" show-overflow-tooltip />
                <el-table-column
                  prop="sql_template"
                  label="SQL 模板"
                  min-width="240"
                  show-overflow-tooltip
                />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openMetric(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeMetric(row)">
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 术语 -->
            <el-tab-pane label="术语" name="term">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openTerm()">
                  新建术语
                </el-button>
                <el-tag size="small" type="info" effect="plain">业务黑话 ↔ 字段映射</el-tag>
              </div>
              <el-table :data="terms" size="small" border height="100%">
                <template #empty>
                  <el-empty description="暂无术语" :image-size="60" />
                </template>
                <el-table-column prop="term" label="术语" min-width="150" show-overflow-tooltip />
                <el-table-column
                  prop="metric_key"
                  label="指标"
                  min-width="130"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="field_path"
                  label="字段路径"
                  min-width="220"
                  show-overflow-tooltip
                />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openTerm(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeTerm(row)">
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 概念 -->
            <el-tab-pane label="业务概念" name="concept">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openConcept()">
                  新建概念
                </el-button>
                <el-tag size="small" type="info" effect="plain">
                  业务概念（语义层，非本体对象）
                </el-tag>
              </div>
              <el-table :data="concepts" size="small" border height="100%">
                <template #empty>
                  <el-empty description="暂无概念" :image-size="60" />
                </template>
                <el-table-column prop="name" label="概念" min-width="150" show-overflow-tooltip />
                <el-table-column label="涉及表" min-width="240">
                  <template #default="{ row }">
                    <el-tag
                      v-for="t in row.tables || []"
                      :key="t"
                      size="small"
                      effect="plain"
                      class="ig-tag"
                    >
                      {{ t }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openConcept(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeConcept(row)">
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 血缘 -->
            <el-tab-pane label="血缘" name="kg">
              <el-alert
                type="info"
                :closable="false"
                class="ig-note"
                title="数据侧血缘：表 / 字段 / 指标 / 术语 / 概念之间的关系。它不等同于「本体类型层图」——后者在 本体 → 关系类型 → 可视化 查看。"
              />
              <div class="ig-bar">
                <el-button size="small" :icon="Refresh" @click="syncKg">重建图谱</el-button>
              </div>
              <el-descriptions :column="3" size="small" border>
                <el-descriptions-item label="表节点">{{ kg.nodes ?? "-" }}</el-descriptions-item>
                <el-descriptions-item label="关系边">{{ kg.edges ?? "-" }}</el-descriptions-item>
                <el-descriptions-item label="实体">{{ kg.entities ?? "-" }}</el-descriptions-item>
              </el-descriptions>
              <div class="ig-kg-filter">
                <span class="ig-kg-filter__label">类型：</span>
                <el-checkbox-group v-model="kgTypeFilter" size="small">
                  <el-checkbox
                    v-for="t in kgTypeOptions"
                    :key="t.value"
                    :value="t.value"
                    :label="t.value"
                  >
                    {{ t.label }}
                  </el-checkbox>
                </el-checkbox-group>
                <el-select
                  v-model="kgTableFocus"
                  clearable
                  filterable
                  size="small"
                  placeholder="按表聚焦（只看该表血缘）"
                  style="width: 210px"
                >
                  <el-option v-for="tb in kgTableOptions" :key="tb" :label="tb" :value="tb" />
                </el-select>
                <span class="ig-kg-filter__hint">当前 {{ filteredKgNodes.length }} 节点</span>
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
              <el-empty
                v-else
                :image-size="60"
                description="暂无图谱，点击「重建图谱」或调整筛选"
              />
            </el-tab-pane>

            <!-- 筛选规则工作台 -->
            <el-tab-pane label="筛选规则" name="rules">
              <FilterRulesWorkbench v-if="curDs" :datasource="curDs" />
              <el-empty v-else description="请先选择左侧数据源" />
            </el-tab-pane>

            <!-- 语义建模：大模型自动生成指标/标注（S4） -->
            <el-tab-pane label="语义建模" name="modeling">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="用大模型对所选数据源自动生成「绑定型指标」与「对象/属性标注」；生成结果可到「指标」标签页查看。"
                style="margin-bottom: 12px"
              />
              <el-form inline>
                <el-form-item label="数据源">
                  <el-tag v-if="curDs">{{ curDs.name }}（{{ modelingDsCode }}）</el-tag>
                  <el-text v-else type="info">请先选择左侧数据源</el-text>
                </el-form-item>
                <el-form-item label="处理对象数">
                  <el-input-number v-model="modelingMax" :min="1" :max="50" />
                </el-form-item>
                <el-form-item>
                  <el-button
                    type="primary"
                    :disabled="!curDs"
                    :loading="modelingLoading"
                    @click="handleModeling('metrics')"
                  >
                    生成绑定型指标
                  </el-button>
                  <el-button
                    :disabled="!curDs"
                    :loading="modelingLoading"
                    @click="handleModeling('annotate')"
                  >
                    生成对象/属性标注
                  </el-button>
                </el-form-item>
              </el-form>
              <el-descriptions v-if="modelingResult" :column="3" border>
                <el-descriptions-item label="解析（候选）">
                  {{ modelingResult.parsed ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="落库">
                  {{ modelingResult.saved ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="拒绝">
                  {{ modelingResult.rejected ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <el-table
                v-if="modelingResult?.reasons?.length"
                :data="modelingResult.reasons"
                size="small"
                style="margin-top: 8px"
              >
                <el-table-column label="拒绝原因" show-overflow-tooltip>
                  <template #default="{ row }">{{ row }}</template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 治理：驾驶舱/权限/数据质量/数据域/本体对象（原「治理」菜单并入） -->
            <el-tab-pane label="治理" name="gov">
              <GovernancePanel />
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- 批量维护：粘贴「表名 中文名」一次填一批 -->
    <el-dialog v-model="batchDlg" title="批量维护表信息" width="680px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="ig-note"
        title="每行一条，用「表名 中文名」或「表名,中文名,业务域」的格式。只填中文名时不会清空已填的描述。"
      />
      <el-input
        v-model="batchText"
        type="textarea"
        :rows="10"
        placeholder="FUEL_CB_COALBALANCE 燃煤采购结算主表&#10;FUEL_CMCS_ASSAY,化验表,燃煤"
      />
      <div class="ig-bar ig-batch-bar">
        <el-tag size="small" type="info" effect="plain">解析出 {{ batchRows.length }} 条</el-tag>
        <el-tag v-if="batchUnknown.length" size="small" type="warning" effect="plain">
          {{ batchUnknown.length }} 条不在当前数据源的表里
        </el-tag>
      </div>
      <el-table :data="batchRows.slice(0, 8)" size="small" border max-height="220">
        <template #empty>
          <el-empty description="粘贴内容后这里会显示预览" :image-size="50" />
        </template>
        <el-table-column prop="table_name" label="表名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="alias" label="中文名" min-width="150" show-overflow-tooltip />
        <el-table-column prop="domain" label="业务域" width="100" show-overflow-tooltip />
        <el-table-column label="匹配" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.known ? 'success' : 'danger'" effect="plain">
              {{ row.known ? "是" : "否" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="batchRows.length > 8" class="ig-tcmt">仅预览前 8 条，保存时会写入全部。</div>
      <template #footer>
        <el-button @click="batchDlg = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!batchRows.length"
          :loading="batchSaving"
          @click="doBatchSave"
        >
          保存 {{ batchRows.length }} 条
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑管道 -->
    <el-dialog v-model="pipeDlg" :title="pipeForm.id ? '编辑管道' : '新建管道'" width="600px">
      <el-form :model="pipeForm" label-width="100px" size="small">
        <el-form-item label="管道名称">
          <el-input v-model="pipeForm.name" placeholder="如：燃煤台账入库" />
        </el-form-item>
        <el-form-item label="源连接">
          <el-input
            v-model="pipeForm.source_connection"
            placeholder="留空=本系统表；填数据源 ID/编码"
          />
        </el-form-item>
        <el-form-item label="源表">
          <el-input v-model="pipeForm.source_table" placeholder="如：FUEL_CB_COALBALANCE" />
        </el-form-item>
        <el-form-item label="目标对象">
          <el-input v-model="pipeForm.target_object" placeholder="本体对象名 / 目标表名" />
        </el-form-item>
        <el-form-item label="字段映射">
          <el-input
            v-model="pipeForm.mappings_text"
            type="textarea"
            :rows="4"
            placeholder='每行「源字段 目标字段」；也可直接粘贴 JSON 数组 [{"from":"a","to":"b"}]'
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="pipeForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pipeDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingPipe" @click="savePipe">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看管道落库数据 -->
    <el-dialog v-model="pipeDataDlg" :title="`管道数据：${pipeDataName}`" width="720px">
      <el-table :data="pipeDataRows" size="small" border max-height="420">
        <template #empty>
          <el-empty description="暂无数据，请先运行管道" :image-size="60" />
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
    <el-dialog v-model="metricDlg" :title="metricForm.id ? '编辑指标' : '新建指标'" width="600px">
      <el-form :model="metricForm" label-width="100px" size="small">
        <el-form-item label="显示名">
          <el-input v-model="metricForm.name" placeholder="如：销售额" />
        </el-form-item>
        <el-form-item label="编码 key">
          <el-input
            v-model="metricForm.key"
            :disabled="!!metricForm.id"
            placeholder="仅字母/数字/下划线，如 sales_amount"
          />
        </el-form-item>
        <el-form-item label="数据源">
          <el-input v-model="metricForm.datasource" placeholder="system 或数据源编码" />
        </el-form-item>
        <el-form-item label="SQL 模板">
          <el-input
            v-model="metricForm.sql_template"
            type="textarea"
            :rows="4"
            placeholder="SELECT ... （可用 :参数）"
          />
        </el-form-item>
        <el-form-item label="聚合">
          <el-input v-model="metricForm.agg" placeholder="count / sum / avg" />
        </el-form-item>
        <el-form-item label="单位">
          <el-input v-model="metricForm.unit" placeholder="如：元 / 台" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="metricForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metricDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingMetric" @click="saveMetric">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑术语 -->
    <el-dialog v-model="termDlg" :title="termForm.id ? '编辑术语' : '新建术语'" width="520px">
      <el-form :model="termForm" label-width="100px" size="small">
        <el-form-item label="术语">
          <el-input
            v-model="termForm.term"
            :disabled="!!termForm.id"
            placeholder="业务黑话，如：产量"
          />
        </el-form-item>
        <el-form-item label="数据源">
          <el-input v-model="termForm.datasource" placeholder="system 或数据源编码" />
        </el-form-item>
        <el-form-item label="对应指标">
          <el-input v-model="termForm.metric_key" placeholder="指标编码（可空）" />
        </el-form-item>
        <el-form-item label="字段路径">
          <el-input v-model="termForm.field_path" placeholder="表.字段（可空）" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="termForm.type">
            <el-option label="指标别名" value="metric" />
            <el-option label="普通术语" value="term" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="termDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingTerm" @click="saveTerm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑概念 -->
    <el-dialog v-model="conceptDlg" :title="conceptForm.id ? '编辑概念' : '新建概念'" width="560px">
      <el-form :model="conceptForm" label-width="100px" size="small">
        <el-form-item label="概念名称">
          <el-input
            v-model="conceptForm.name"
            :disabled="!!conceptForm.id"
            placeholder="如：燃煤批次"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="conceptForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="同义词">
          <el-input v-model="conceptForm.synonyms" placeholder="逗号分隔（可空）" />
        </el-form-item>
        <el-form-item label="父概念">
          <el-input v-model="conceptForm.parent_name" placeholder="可空" />
        </el-form-item>
        <el-form-item label="业务域">
          <el-input v-model="conceptForm.domain" placeholder="如：燃煤" />
        </el-form-item>
        <el-form-item label="关联指标">
          <el-input v-model="conceptForm.metric_key" placeholder="指标编码（可空）" />
        </el-form-item>
        <el-form-item label="涉及表">
          <el-input v-model="conceptForm.tables_text" placeholder="逗号分隔，如：T_A,T_B" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="conceptDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingConcept" @click="saveConcept">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑单字段属性 -->
    <el-dialog v-model="colDlg" :title="`编辑字段属性：${colForm.column_name || ''}`" width="520px">
      <el-form :model="colForm" label-width="90px" size="small">
        <el-form-item label="字段名">
          <span class="ig-tname">{{ colForm.column_name }}</span>
        </el-form-item>
        <el-form-item label="中文名">
          <el-input v-model="colForm.description" placeholder="如 结算数量" />
        </el-form-item>
        <el-form-item label="业务场景">
          <el-input v-model="colForm.business_scenarios" placeholder="哪些报表/业务用到" />
        </el-form-item>
        <el-form-item label="关联表">
          <el-select-v2
            v-model="colForm.related_table"
            :options="relTableOptions"
            size="small"
            filterable
            clearable
            placeholder="选择关联表"
            style="width: 100%"
            @change="colForm.related_field = ''"
          />
        </el-form-item>
        <el-form-item label="关联字段">
          <el-select-v2
            v-model="colForm.related_field"
            :options="relFieldOptions(colForm.related_table)"
            size="small"
            filterable
            clearable
            placeholder="选择对应字段"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="枚举">
          <el-select
            v-model="colForm.enum"
            multiple
            filterable
            allow-create
            default-first-option
            size="small"
            placeholder="输入后回车新增"
            style="width: 100%"
          >
            <el-option v-for="e in colForm.enum" :key="e" :label="e" :value="e" />
          </el-select>
        </el-form-item>
        <el-form-item label="纳入问数">
          <el-switch v-model="colForm.included" />
        </el-form-item>
        <el-form-item label="敏感">
          <el-switch v-model="colForm.sensitive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="colDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingCol === colForm.column_name" @click="saveColEdit">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑数据源 -->
    <el-dialog v-model="dsDlg" :title="dsForm.id ? '编辑数据源' : '新建数据源'" width="520px">
      <el-form :model="dsForm" label-width="90px" size="small">
        <el-form-item label="数据源ID">
          <el-input v-model="dsForm.code" :disabled="!!dsForm.id" placeholder="如 ezdcs_pg" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="dsForm.name" placeholder="如 燃煤业务库" />
        </el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="dsForm.type">
            <el-option label="PostgreSQL" value="postgres" />
            <el-option label="MySQL" value="mysql" />
          </el-select>
        </el-form-item>
        <el-form-item label="主机地址">
          <el-input v-model="dsForm.host" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="dsForm.port" :min="1" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item label="数据库名">
          <el-input v-model="dsForm.database" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="dsForm.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="dsForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="会话只读">
          <el-switch v-model="dsForm.read_only" />
        </el-form-item>
        <template v-if="dsForm.filter_rules">
          <el-divider content-position="left" class="ig-form__divider">
            筛选规则（自动打标系统表/审计字段）
          </el-divider>
          <el-form-item label="启用规则">
            <el-switch v-model="dsForm.filter_rules.enabled" />
          </el-form-item>
          <el-form-item label="系统表前缀">
            <el-select
              v-model="dsForm.filter_rules.system_table.prefixes"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              placeholder="回车新增，如 SYS_ / FUEL_"
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
          <el-form-item label="系统表关键词">
            <el-select
              v-model="dsForm.filter_rules.system_table.keywords"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              placeholder="回车新增，如 _BAK / log"
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
          <el-form-item label="精确表名">
            <el-select
              v-model="dsForm.filter_rules.system_table.exact"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              placeholder="回车新增，如 alembic_version"
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
          <el-form-item label="表名正则">
            <el-input
              v-model="dsForm.filter_rules.system_table.regex"
              placeholder="可空，如 ^TMP_"
            />
          </el-form-item>
          <el-form-item label="审计字段">
            <el-select
              v-model="dsForm.filter_rules.audit_fields"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              placeholder="回车新增，如 created_time / is_deleted"
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
        <el-button @click="dsDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingDs" @click="saveDs">保存</el-button>
      </template>
    </el-dialog>

    <!-- 资产版本管理 -->
    <AssetVersionsDialog v-model="versionsVisible" :table="versionsTable" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Search, DataBoard, EditPen, Coin } from "@element-plus/icons-vue";
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
  addFavorite,
  createShare,
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
  runModelingMetrics,
  runModelingAnnotate,
} from "@/api/module_ai/query";
import { getOntDomains } from "@/api/module_ai/ontology";
import FilterRulesWorkbench from "./components/FilterRulesWorkbench.vue";
import GovernancePanel from "./components/GovernancePanel.vue";
import AssetVersionsDialog from "./components/AssetVersionsDialog.vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";

const tab = ref("table");
const datasources = ref<any[]>([]);
const curDs = ref<any>(null);
const dsTables = ref<any[]>([]);
const schemaRows = ref<any[]>([]);
const tableKw = ref("");
const curTable = ref("");
const columns = ref<any[]>([]);
const pipelines = ref<any[]>([]);
const metrics = ref<any[]>([]);
const terms = ref<any[]>([]);
const concepts = ref<any[]>([]);
const kg = ref<any>({});
const kgNodes = ref<any[]>([]);
const kgEdges = ref<any[]>([]);
const nodeStyle = {
  sizeMode: "fixed",
  fixedSize: 36,
  colorMode: "type",
  labelSize: 11,
};
// 血缘图过滤：按节点类型 / 按表聚焦（性能优化，避免大图全渲染又密又慢）
const kgTypeFilter = ref<string[]>([]);
const kgTypeOptions = [
  { value: "table", label: "表" },
  { value: "field", label: "字段" },
  { value: "metric", label: "指标" },
  { value: "term", label: "术语" },
  { value: "domain", label: "域" },
  { value: "concept", label: "概念" },
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
    ElMessage.success(r?.data?.msg || "已收藏");
  } catch (e: any) {
    ElMessage.error(e?.msg || "收藏失败");
  }
}
async function shareTable(row: any) {
  try {
    const r = await createShare(row.table || row.table_name);
    const d = r?.data?.data || {};
    const link = d.link ? window.location.origin + d.link : "";
    if (link) {
      try {
        await navigator.clipboard.writeText(link);
      } catch {
        /* 剪贴板不可用时仅提示 */
      }
      ElMessage.success("已生成分享链接，并复制到剪贴板");
    } else {
      ElMessage.success("分享成功");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "分享失败");
  }
}
const batchDlg = ref(false);
const batchText = ref("");
const batchSaving = ref(false);
const dsForm = ref<any>({ type: "postgres", port: 5432, read_only: true });

// 管道编排
const pipeDlg = ref(false);
const savingPipe = ref(false);
const pipeForm = ref<any>({ enabled: true, mappings_text: "" });
const pipeDataDlg = ref(false);
const pipeDataName = ref("");
const pipeDataCols = ref<string[]>([]);
const pipeDataRows = ref<any[]>([]);
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
      included: a?.included ?? true,
      object_enabled: a?.object_enabled ?? false,
    };
  });
});

const filteredTables = computed(() => {
  const kw = tableKw.value.trim().toLowerCase();
  return tableRows.value.filter((t) => {
    // 「只看业务表」= 隐藏系统表（is_system 来自后端 schema 接口）
    if (hideSys.value && t.is_system) return false;
    // 「只看已维护」= 隐藏未纳入问数的表
    if (hideUnmaintained.value && t.included === false) return false;
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
  if (!curDs.value) return "请先选择左侧数据源";
  if (dsTables.value.length && !filteredTables.value.length) {
    return hideSys.value ? "已隐藏系统表，当前没有业务表" : "没有匹配的表";
  }
  return "点「同步」拉取表结构";
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
    ElMessage.success(`已同步 ${r.data?.data?.tables ?? 0} 张表`);
    await loadDsTables();
  } catch (e: any) {
    ElMessage.error(e?.msg || "同步失败");
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
    await saveQueryAsset({ table_name: curTable.value, ...tmeta.value });
    ElMessage.success("表信息已保存");
    await loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
    if (!quiet) ElMessage.success(`字段「${row.column_name}」已保存`);
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
    ElMessage.success(`字段「${colForm.value.column_name}」已保存`);
    // 同步回字段清单行
    const row = columns.value.find((c) => c.column_name === colForm.value.column_name);
    if (row) Object.assign(row, colForm.value);
    colDlg.value = false;
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
      d.ok ? `已导入为本体对象「${d.object}」，${d.props} 个属性` : d.msg
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
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
    ElMessage.success(`已保存 ${d.saved ?? 0} 张表`);
    batchDlg.value = false;
    await loadAssets();
    if (curTable.value) fillTmeta(curTable.value);
  } catch (e: any) {
    ElMessage.error(e?.msg || "批量保存失败");
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
    ElMessage.success("保存成功");
    dsDlg.value = false;
    await loadDs();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingDs.value = false;
  }
}

async function testDs(row: any) {
  try {
    const r = await testQueryDatasource(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.message || (d.ok ? "连接成功" : "连接失败"));
  } catch (e: any) {
    ElMessage.error(e?.msg || "测试失败");
  }
}

/** 删除数据源（删除类操作必须二次确认，文案写明影响范围）。 */
async function removeDs(row: any) {
  try {
    await ElMessageBox.confirm(
      `将删除数据源「${row.name || row.code}」及其已同步的表结构，且不可恢复。是否继续？`,
      "删除数据源",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await deleteQueryDatasources([row.id]);
    ElMessage.success("已删除");
    // 删除的是当前选中数据源时，清空选中态并回退到空表清单
    if (curDs.value && curDs.value.id === row.id) {
      curDs.value = null;
      curTable.value = "";
      columns.value = [];
      dsTables.value = [];
    }
    await loadDs();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

/** 批量导入：把当前数据源的业务表（非系统表）一次性导为目标本体对象，带到所选本体域。
 *  注意基于 dsTables 而非 filteredTables：搜索关键字（tableKw）只是表清单的显示过滤，
 *  不应影响批量导入的范围——始终导入当前数据源的全部业务表。 */
async function doBatchImport() {
  if (!curDs.value) return;
  const tables = dsTables.value.filter((t) => !t.is_system).map((t) => t.table);
  if (!tables.length) {
    ElMessage.warning("当前没有可导入的业务表（已隐藏系统表）");
    return;
  }
  importingBatch.value = true;
  try {
    const r = await importDsAsOntologyBatch(curDs.value.id, tables, false, importDomain.value);
    const d = r.data?.data || {};
    ElMessage[r.data?.msg && !d.ok ? "error" : "success"](
      d.ok ? `已导入 ${d.imported ?? 0} 个本体对象` : d.msg || "导入失败"
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || "批量导入失败");
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
  const t = (text || "").trim();
  if (!t) return [];
  if (t.startsWith("[")) {
    try {
      const arr = JSON.parse(t);
      return Array.isArray(arr) ? arr : [];
    } catch {
      ElMessage.warning("映射 JSON 解析失败，已忽略");
      return [];
    }
  }
  return t
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const m = line.match(/^(\S+)[\s,]+(\S+)$/);
      return m ? { from: m[1], to: m[2] } : { from: line, to: line };
    });
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
    ElMessage.warning("请填写管道名称");
    return;
  }
  savingPipe.value = true;
  try {
    await savePipeline({
      ...pipeForm.value,
      mappings: parseMappings(pipeForm.value.mappings_text),
    });
    ElMessage.success("管道已保存");
    pipeDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
      ElMessage.warning(d.msg || "暂无落库结果");
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
    ElMessage.error(e?.msg || "读取管道数据失败");
  }
}

async function runPipe(row: any) {
  try {
    const r = await runPipeline(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.msg || "已运行");
  } catch (e: any) {
    ElMessage.error(e?.msg || "运行失败");
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

async function saveMetric() {
  const f = metricForm.value;
  if (!f.name || !f.key) {
    ElMessage.warning("请填写指标显示名与编码");
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(f.key)) {
    ElMessage.warning("编码仅允许字母/数字/下划线");
    return;
  }
  savingMetric.value = true;
  try {
    await saveQueryMetric({ ...f, params: f.params || [], dimensions: f.dimensions || [] });
    ElMessage.success("指标已保存");
    metricDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingMetric.value = false;
  }
}

async function removeMetric(row: any) {
  await ElMessageBox.confirm(
    `将删除指标「${row.name || row.key}」，问数将不再走该确定性快路径，且不可恢复。`,
    "删除指标",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  try {
    await deleteQueryMetrics([row.id]);
    ElMessage.success("已删除");
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
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
    ElMessage.warning("请填写术语");
    return;
  }
  savingTerm.value = true;
  try {
    await saveQueryTerm({ ...f });
    ElMessage.success("术语已保存");
    termDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingTerm.value = false;
  }
}

async function removeTerm(row: any) {
  await ElMessageBox.confirm(
    `将删除术语「${row.term}」，该业务说法与指标/字段的映射将失效，且不可恢复。`,
    "删除术语",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  try {
    await deleteQueryTerms([row.id]);
    ElMessage.success("已删除");
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
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
    ElMessage.warning("请填写概念名称");
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
    ElMessage.success("概念已保存");
    conceptDlg.value = false;
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingConcept.value = false;
  }
}

async function removeConcept(row: any) {
  await ElMessageBox.confirm(
    `将删除概念「${row.name}」，其在语义层与图谱中的关联将失效，且不可恢复。`,
    "删除概念",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  try {
    await deleteQueryConcepts([row.id]);
    ElMessage.success("已删除");
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

async function syncKg() {
  try {
    await rebuildQueryKg();
    ElMessage.success("图谱已重建");
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.msg || "失败");
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
const modelingMax = ref(12);
const modelingLoading = ref(false);
const modelingResult = ref<any>(null);
const modelingDsCode = computed(
  () => curDs.value?.code || (curDs.value ? `ds:${curDs.value.id}` : "")
);

async function handleModeling(kind: "metrics" | "annotate") {
  if (!curDs.value) return;
  const label = kind === "metrics" ? "绑定型指标" : "对象/属性标注";
  try {
    await ElMessageBox.confirm(
      `将对「${curDs.value.name}」用大模型自动生成${label}（写入本体/指标库），是否继续？`,
      "确认生成",
      { type: "warning", confirmButtonText: "生成", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  modelingLoading.value = true;
  try {
    const fn = kind === "metrics" ? runModelingMetrics : runModelingAnnotate;
    const r: any = await fn({
      datasource: modelingDsCode.value,
      max_objects: modelingMax.value,
    });
    modelingResult.value = r?.data ?? r;
    ElMessage.success("生成完成");
    await loadMisc();
  } catch (e: any) {
    ElMessage.error(e?.message || "生成失败");
  } finally {
    modelingLoading.value = false;
  }
}
</script>

<style scoped lang="scss">
.ai-integration-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
}
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
  /* 悬浮或选中时显示操作，避免挤占名称空间 */
  visibility: hidden;
  flex-shrink: 0;
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
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  margin-bottom: 6px;
}
.ig-kg-filter__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ig-kg-filter__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
</style>
