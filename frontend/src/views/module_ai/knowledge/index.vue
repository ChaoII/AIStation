<!-- AI 知识库 / 数据源 RAG：知识库（入库/检索/分块） + 数据源（测试/同步），复用 Element Plus -->
<template>
  <div class="app-container ai-knowledge-page">
    <div class="kb-layout">
      <!-- 左：知识库分类树（全部 / 分类 + 计数） -->
      <el-card shadow="never" class="kb-side">
        <template #header>
          <div class="kb-side-head">
            <span>{{ i18nT("ai_ontology.category") }}</span>
            <el-button
              v-hasPerm="'module_ai:knowledge:create'"
              link
              type="primary"
              :icon="Plus"
              @click="openCatCreate(null)"
            />
          </div>
        </template>
        <el-tree
          class="ai-tree"
          :data="catTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="currentCatId ?? undefined"
          highlight-current
          default-expand-all
          :expand-on-click-node="false"
          @node-click="onCatClick"
        >
          <template #default="{ data }">
            <span class="ai-tree-node">
              <el-icon class="ai-tree-node__icon">
                <component :is="data.id === 0 ? Files : Folder" />
              </el-icon>
              <span class="ai-tree-node__label" :title="data.name">{{ data.name }}</span>
              <span class="ai-tree-node__count">{{ data.count ?? 0 }}</span>
            </span>
          </template>
        </el-tree>
      </el-card>

      <el-card shadow="never" class="kb-tabs-card">
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="i18nT('ai_ontology.knowledgeBase')" name="kb">
            <div class="kb-toolbar">
              <el-button
                v-hasPerm="['module_ai:knowledge:create']"
                type="success"
                icon="plus"
                @click="openKbDialog()"
              >
                {{ i18nT("ai_ontology.newKnowledgeBase") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:update']"
                :icon="Upload"
                :disabled="!selectedKb"
                @click="selectedKb && openIngestDialog(selectedKb)"
              >
                {{ i18nT("ai_ontology.textIngest") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:query']"
                :icon="Search"
                :disabled="!selectedKb"
                @click="selectedKb && openSearchDialog(selectedKb)"
              >
                {{ i18nT("ai_ontology.searchTest") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:query']"
                :icon="Files"
                :disabled="!selectedKb"
                @click="selectedKb && openChunks(selectedKb)"
              >
                {{ i18nT("ai_ontology.viewChunks") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:query']"
                :icon="Share"
                :disabled="!selectedKb"
                @click="selectedKb && openGraph(selectedKb)"
              >
                {{ i18nT("ai_ontology.graph2") }}
              </el-button>
              <div class="kb-toolbar__right">
                <el-input
                  v-model="kbKeyword"
                  :placeholder="i18nT('ai_ontology.searchKnowledgeBases')"
                  clearable
                  :prefix-icon="Search"
                  style="width: 200px"
                />
                <el-button
                  circle
                  type="success"
                  :icon="Refresh"
                  :title="i18nT('ai_ontology.refresh')"
                  @click="loadData"
                />
              </div>
            </div>

            <el-table
              v-loading="loading"
              border
              stripe
              :data="filteredBases"
              highlight-current-row
              @current-change="(row: any) => (selectedKb = row)"
            >
              <el-table-column
                prop="name"
                :label="i18nT('ai_ontology.name')"
                min-width="140"
                show-overflow-tooltip
              />
              <el-table-column
                prop="description"
                :label="i18nT('ai_ontology.description')"
                min-width="180"
                show-overflow-tooltip
              >
                <template #default="{ row }">{{ row.description || "—" }}</template>
              </el-table-column>
              <el-table-column
                prop="chunk_count"
                :label="i18nT('ai_ontology.chunks')"
                width="90"
                align="center"
              />
              <el-table-column
                :label="i18nT('ai_ontology.embeddingModel')"
                width="150"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <el-tag v-if="row.model_id" size="small" type="info" effect="plain">
                    {{ modelNameMap[row.model_id] || `#${row.model_id}` }}
                  </el-tag>
                  <span v-else class="kb-opt-hint">
                    {{ i18nT("ai_ontology.deterministicVector") }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column :label="i18nT('ai_ontology.graph2')" width="150" align="center">
                <template #default="{ row }">
                  <el-tag
                    v-if="row.graph_nodes"
                    size="small"
                    type="success"
                    effect="plain"
                    class="kb-graph-cell"
                    :title="i18nT('ai_ontology.clickToViewGraph')"
                    @click.stop="openGraph(row)"
                  >
                    {{
                      i18nT("ai_ontology.graphNodesEdges", {
                        nodes: row.graph_nodes,
                        edges: row.graph_edges,
                      })
                    }}
                  </el-tag>
                  <span v-else class="kb-opt-hint">—</span>
                </template>
              </el-table-column>
              <el-table-column :label="i18nT('ai_ontology.status')" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
                    {{
                      row.enabled ? i18nT("ai_ontology.enabled2") : i18nT("ai_ontology.disabled")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="i18nT('ai_ontology.operations')"
                width="280"
                align="center"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button size="small" link type="info" icon="View" @click="openDetail(row)">
                    {{ i18nT("ai_ontology.details") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_ai:knowledge:create']"
                    size="small"
                    link
                    type="primary"
                    :icon="CopyDocument"
                    @click="copyBase(row)"
                  >
                    {{ i18nT("ai_ontology.copy") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_ai:knowledge:update']"
                    size="small"
                    link
                    type="primary"
                    :icon="Edit"
                    @click="openKbDialog(row)"
                  >
                    {{ i18nT("ai_ontology.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_ai:knowledge:delete']"
                    size="small"
                    link
                    type="danger"
                    :icon="Delete"
                    @click="deleteBases(row)"
                  >
                    {{ i18nT("ai_ontology.delete2") }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="i18nT('ai_ontology.dataSource')" name="ds">
            <div class="kb-toolbar">
              <el-button
                v-hasPerm="['module_ai:knowledge:create']"
                type="success"
                icon="plus"
                @click="openDsDialog()"
              >
                {{ i18nT("ai_ontology.newDataSource") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:query']"
                :icon="Connection"
                :disabled="!selectedDs"
                @click="selectedDs && testDs(selectedDs)"
              >
                {{ i18nT("ai_ontology.test") }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:knowledge:update']"
                type="warning"
                :icon="Refresh"
                :disabled="!selectedDs"
                @click="selectedDs && syncDs(selectedDs)"
              >
                {{ i18nT("ai_ontology.syncIngest") }}
              </el-button>
              <div class="kb-toolbar__right">
                <el-input
                  v-model="dsKeyword"
                  :placeholder="i18nT('ai_ontology.searchDataSources')"
                  clearable
                  :prefix-icon="Search"
                  style="width: 200px"
                />
                <el-button
                  circle
                  type="success"
                  :icon="Refresh"
                  :title="i18nT('ai_ontology.refresh')"
                  @click="loadData"
                />
              </div>
            </div>

            <el-table
              v-loading="loadingDs"
              border
              stripe
              :data="filteredDatasources"
              highlight-current-row
              @current-change="(row: any) => (selectedDs = row)"
            >
              <el-table-column
                prop="name"
                :label="i18nT('ai_ontology.name')"
                min-width="140"
                show-overflow-tooltip
              />
              <el-table-column :label="i18nT('ai_ontology.type')" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain">
                    {{ row.ds_type === "db" ? i18nT("ai_ontology.database") : "API" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="i18nT('ai_ontology.join')"
                min-width="200"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{
                    row.ds_type === "db"
                      ? (row.dialect || "") + " | " + (row.uri || "")
                      : row.uri || ""
                  }}
                </template>
              </el-table-column>
              <el-table-column
                :label="i18nT('ai_ontology.targetKnowledgeBase')"
                min-width="120"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ kbName(row.knowledge_base_id) }}
                </template>
              </el-table-column>
              <el-table-column :label="i18nT('ai_ontology.status')" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
                    {{
                      row.enabled ? i18nT("ai_ontology.enabled2") : i18nT("ai_ontology.disabled")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="i18nT('ai_ontology.operations')"
                width="200"
                align="center"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    v-hasPerm="['module_ai:knowledge:update']"
                    size="small"
                    link
                    type="primary"
                    :icon="Edit"
                    @click="openDsDialog(row)"
                  >
                    {{ i18nT("ai_ontology.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_ai:knowledge:delete']"
                    size="small"
                    link
                    type="danger"
                    :icon="Delete"
                    @click="deleteDatasources(row)"
                  >
                    {{ i18nT("ai_ontology.delete2") }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <!-- 新建知识库分类 -->
    <el-dialog
      v-model="catDialogVisible"
      :title="i18nT('ai_ontology.newCategory')"
      width="420px"
      append-to-body
    >
      <el-form :model="catForm" label-width="80px">
        <el-form-item :label="i18nT('ai_ontology.name')" required>
          <el-input v-model="catForm.name" :placeholder="i18nT('ai_ontology.categoryName')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.parentCategory')">
          <el-select
            v-model="catForm.parent_id"
            clearable
            :placeholder="i18nT('ai_ontology.topLevelCategory')"
            style="width: 100%"
          >
            <el-option v-for="c in flatCatOptions" :key="c.id" :label="c.label" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.owner')">
          <el-input
            v-model="catForm.owner"
            :placeholder="i18nT('ai_ontology.optionalEGZhangSan')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.remark')">
          <el-input
            v-model="catForm.remark"
            type="textarea"
            :rows="2"
            :placeholder="i18nT('ai_ontology.optional')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="catDialogVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="catSaving" @click="saveCat">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 数据源测试结果 -->
    <el-dialog
      v-model="dsTestVisible"
      :title="i18nT('ai_ontology.dataSourceTestResult')"
      width="600px"
      append-to-body
    >
      <el-result
        :icon="dsTestResult.ok ? 'success' : 'error'"
        :title="
          dsTestResult.ok ? i18nT('ai_ontology.connectSuccess') : i18nT('ai_ontology.connectFailed')
        "
        :sub-title="dsTestResult.message || i18nT('ai_ontology.noDetails')"
      />
      <div v-if="dsTestResult.data" class="ds-test-data">
        <div class="ds-test-data__title">{{ i18nT("ai_ontology.returnedDataFirst20Rows") }}</div>
        <pre class="ds-test-data__body">{{ JSON.stringify(dsTestResult.data, null, 2) }}</pre>
      </div>
      <template #footer>
        <el-button type="primary" @click="dsTestVisible = false">
          {{ i18nT("ai_ontology.gotIt") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑知识库 -->
    <el-dialog
      v-model="kbDialogVisible"
      :title="
        editingKb ? i18nT('ai_ontology.editKnowledgeBase') : i18nT('ai_ontology.newKnowledgeBase')
      "
      width="520px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="kbForm" label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.name')" required>
          <el-input v-model="kbForm.name" :placeholder="i18nT('ai_ontology.kbName')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.description')">
          <el-input
            v-model="kbForm.description"
            type="textarea"
            :rows="3"
            :placeholder="i18nT('ai_ontology.description')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.category')">
          <el-select
            v-model="kbForm.category_id"
            clearable
            :placeholder="i18nT('ai_ontology.selectCategoryEmptyUncategorized')"
            style="width: 100%"
          >
            <el-option v-for="c in flatCatOptions" :key="c.id" :label="c.label" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.embeddingModel')">
          <el-select
            v-model="kbForm.model_id"
            clearable
            filterable
            :placeholder="i18nT('ai_ontology.leaveEmptyForDeterministicVector')"
            style="width: 100%"
          >
            <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.enabled')">
          <el-switch v-model="kbForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kbDialogVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingKb" @click="saveKb">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 文本入库 -->
    <el-dialog
      v-model="ingestDialogVisible"
      :title="i18nT('ai_ontology.textIngest')"
      width="600px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="ingestForm" label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.targetKB')">
          <el-input :model-value="ingestTarget?.name" disabled />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.fileName')">
          <el-input
            v-model="ingestForm.file_name"
            :placeholder="i18nT('ai_ontology.sourceFileNameOptional')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.originalContent')" required>
          <el-input
            v-model="ingestForm.content"
            type="textarea"
            :rows="8"
            :placeholder="i18nT('ai_ontology.pasteTextToIngest')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.chunkSize')">
          <el-input-number v-model="ingestForm.chunk_size" :min="100" :max="2000" :step="50" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.overlap')">
          <el-input-number v-model="ingestForm.overlap" :min="0" :max="400" :step="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ingestDialogVisible = false">
          {{ i18nT("ai_ontology.cancel") }}
        </el-button>
        <el-button type="primary" :loading="ingesting" @click="doIngest">
          {{ i18nT("ai_ontology.ingest") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 检索测试 -->
    <el-dialog
      v-model="searchDialogVisible"
      :title="i18nT('ai_ontology.searchTest')"
      width="600px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="searchForm" label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.query')">
          <el-input
            v-model="searchForm.query"
            :placeholder="i18nT('ai_ontology.enterASearchQuestion')"
            @keyup.enter="doSearch"
          />
        </el-form-item>
        <el-form-item label="Top K">
          <el-input-number v-model="searchForm.top_k" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="GraphRAG">
          <el-switch v-model="searchForm.use_graph" />
          <span class="kb-opt-hint">
            {{ i18nT("ai_ontology.expandRelatedEntitiesByKnowledgeGraphWhenEnabled") }}
          </span>
        </el-form-item>
      </el-form>
      <div v-loading="searching">
        <el-empty
          v-if="!searchResults.length"
          :description="i18nT('ai_ontology.enterQueryToSearch')"
          :image-size="60"
        />
        <div v-for="(h, i) in searchResults" :key="i" class="search-hit">
          <div class="search-hit__meta">
            <span class="search-hit__file">{{ h.file_name || i18nT("ai_ontology.unknown") }}</span>
            <span class="search-hit__score">
              {{ i18nT("ai_ontology.similarityScore", { score: h.score }) }}
            </span>
            <el-tag v-if="h.engine" size="small" effect="plain" :type="engineType(h.engine)">
              {{ engineLabel(h.engine) }}
            </el-tag>
            <el-tag v-if="h.graph_entity" size="small" type="warning" effect="plain">
              {{ i18nT("ai_ontology.graphEntityLabel", { entity: h.graph_entity }) }}
            </el-tag>
          </div>
          <div class="search-hit__content">{{ h.content }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 图谱可视化 -->
    <el-dialog
      v-model="graphVisible"
      :title="i18nT('ai_ontology.knowledgeGraphTitle', { name: selectedKb?.name || '' })"
      width="900px"
      height="560px"
      append-to-body
    >
      <div class="graph-dialog">
        <div class="graph-stats">
          <el-tag type="success" effect="plain">
            {{ i18nT("ai_ontology.entityNodeCount", { count: graphStats.nodes }) }}
          </el-tag>
          <el-tag type="warning" effect="plain">
            {{ i18nT("ai_ontology.relationEdgeCount", { count: graphStats.edges }) }}
          </el-tag>
          <span class="kb-opt-hint">
            {{ i18nT("ai_ontology.graphCtxHint") }}
          </span>
        </div>
        <GraphCanvas
          v-if="graphNodes.length"
          class="graph-chart"
          :nodes="graphNodes"
          :edges="graphEdges"
          :use-preset="graphUsePreset"
          @node-tap="onGraphNodeTap"
          @node-dbltap="onGraphNodeDbltap"
          @node-ctx="onGraphNodeCtx"
          @edge-ctx="onGraphEdgeCtx"
          @blank-ctx="onGraphBlankCtx"
        />
        <!-- 图上右键菜单 -->
        <div
          v-if="ctxMenu.visible"
          class="graph-ctx"
          :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
          @click.stop
        >
          <template v-if="ctxMenu.kind === 'node'">
            <div class="graph-ctx__item" @click="ctxEditNode">
              {{ i18nT("ai_ontology.editNodeProperties") }}
            </div>
            <div class="graph-ctx__item" @click="ctxBindNode">
              {{ i18nT("ai_ontology.bindChunk") }}
            </div>
            <div class="graph-ctx__item" @click="ctxAddRel">
              {{ i18nT("ai_ontology.addRelation") }}
            </div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">
              {{ i18nT("ai_ontology.deleteNode") }}
            </div>
          </template>
          <template v-else-if="ctxMenu.kind === 'edge'">
            <div class="graph-ctx__item" @click="ctxEditRel">
              {{ i18nT("ai_ontology.editRelation") }}
            </div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">
              {{ i18nT("ai_ontology.deleteRelation") }}
            </div>
          </template>
          <template v-else>
            <div class="graph-ctx__item" @click="ctxNewNode">
              {{ i18nT("ai_ontology.newNode") }}
            </div>
          </template>
        </div>
      </div>
    </el-dialog>

    <!-- 分块抽屉 -->
    <el-drawer
      v-model="chunksVisible"
      :title="i18nT('ai_ontology.chunksTitle', { name: chunksTarget?.name || '' })"
      size="480px"
    >
      <el-table
        v-loading="loadingChunks"
        :data="chunks"
        size="small"
        max-height="70vh"
        border
        stripe
      >
        <el-table-column
          prop="chunk_index"
          :label="i18nT('ai_ontology.no2')"
          width="60"
          align="center"
        />
        <el-table-column
          prop="file_name"
          :label="i18nT('ai_ontology.source2')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.content')" min-width="200">
          <template #default="{ row }">
            <div class="chunk-content">{{ row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="80" align="center">
          <template #default="{ row }">
            <el-button
              v-hasPerm="['module_ai:knowledge:delete']"
              size="small"
              type="danger"
              :icon="Delete"
              @click="deleteChunk(row)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <!-- 知识库详情抽屉（多 tab） -->
    <el-drawer
      v-model="detailVisible"
      :title="i18nT('ai_ontology.kbManageTitle', { name: detailKb?.name || '' })"
      size="820px"
      append-to-body
    >
      <el-tabs v-model="detailTab" class="detail-tabs">
        <!-- 概览 -->
        <el-tab-pane :label="i18nT('ai_ontology.overview')" name="overview">
          <div class="ov-stats">
            <el-statistic :title="i18nT('ai_ontology.chunk')" :value="detailChunkCount" />
            <el-statistic :title="i18nT('ai_ontology.graphNodes')" :value="detailGraphNodes" />
            <el-statistic :title="i18nT('ai_ontology.graphEdges')" :value="detailGraphEdges" />
            <el-statistic :title="i18nT('ai_ontology.dataSource')" :value="detailDsCount" />
          </div>
          <el-form label-width="80px" size="small" class="ov-form">
            <el-form-item :label="i18nT('ai_ontology.description')">
              <el-input v-model="detailDesc" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item :label="i18nT('ai_ontology.enabled')">
              <el-switch v-model="detailEnabled" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveDetailOverview">
                {{ i18nT("ai_ontology.save") }}
              </el-button>
              <el-button type="warning" :loading="rebuilding" @click="rebuildDetail">
                {{ i18nT("ai_ontology.rebuildIndex") }}
              </el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            :title="i18nT('ai_ontology.rebuildIndexHint')"
          />
        </el-tab-pane>

        <!-- 文本入库 -->
        <el-tab-pane :label="i18nT('ai_ontology.textIngest')" name="ingest">
          <el-form label-width="90px" size="small">
            <el-form-item :label="i18nT('ai_ontology.fileName')">
              <el-input v-model="detailIngest.file_name" />
            </el-form-item>
            <el-form-item :label="i18nT('ai_ontology.content')">
              <el-input
                v-model="detailIngest.content"
                type="textarea"
                :rows="6"
                :placeholder="i18nT('ai_ontology.pasteTextToIngest')"
              />
            </el-form-item>
            <el-form-item :label="i18nT('ai_ontology.splitStrategy')">
              <el-select v-model="detailIngest.strategy" style="width: 200px">
                <el-option :label="i18nT('ai_ontology.fixedOverlap')" value="fixed" />
                <el-option :label="i18nT('ai_ontology.byParagraph')" value="paragraph" />
                <el-option :label="i18nT('ai_ontology.bySentence')" value="sentence" />
              </el-select>
            </el-form-item>
            <el-form-item :label="i18nT('ai_ontology.chunkSizeOverlap')">
              <el-input-number
                v-model="detailIngest.chunk_size"
                :min="100"
                :max="2000"
                :step="50"
              />
              <el-input-number
                v-model="detailIngest.overlap"
                :min="0"
                :max="200"
                :step="10"
                style="margin-left: 8px"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="detailIngesting" @click="doDetailIngest">
                {{ i18nT("ai_ontology.ingest") }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 文档管理（wikiLLM/ima 式） -->
        <el-tab-pane :label="i18nT('ai_ontology.document')" name="documents">
          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            :on-change="onUploadFile"
            accept=".txt,.md,.csv,.json,.docx,.pdf"
            multiple
            class="doc-upload"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              {{ i18nT("ai_ontology.dragFilesHereOr") }}
              <em>{{ i18nT("ai_ontology.clickToUpload") }}</em>
              {{ i18nT("ai_ontology.docFileExtHint") }}
            </div>
          </el-upload>
          <div class="doc-searchbar">
            <el-select v-model="docChunkSize" size="small" style="width: 130px">
              <el-option :label="i18nT('ai_ontology.chunkSizeValue', { size: 200 })" :value="200" />
              <el-option :label="i18nT('ai_ontology.chunkSizeValue', { size: 500 })" :value="500" />
              <el-option
                :label="i18nT('ai_ontology.chunkSizeValue', { size: 1000 })"
                :value="1000"
              />
            </el-select>
            <el-select v-model="docStrategy" size="small" style="width: 130px">
              <el-option :label="i18nT('ai_ontology.fixedOverlap')" value="fixed" />
              <el-option :label="i18nT('ai_ontology.byParagraph')" value="paragraph" />
              <el-option :label="i18nT('ai_ontology.bySentence')" value="sentence" />
              <el-option :label="i18nT('ai_ontology.byTitleTree')" value="heading" />
            </el-select>
            <el-select v-model="docUseOcr" size="small" style="width: 130px">
              <el-option :label="i18nT('ai_ontology.autoParse')" :value="true" />
              <el-option :label="i18nT('ai_ontology.textLayerOnly')" :value="false" />
            </el-select>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="!selectedDocIds.length"
              @click="batchDeleteDocs"
            >
              {{ i18nT("ai_ontology.batchDeleteWithCount", { count: selectedDocIds.length }) }}
            </el-button>
          </div>
          <el-table
            v-loading="loadingDocs"
            border
            stripe
            :data="documents"
            size="small"
            max-height="50vh"
            @selection-change="(sel: any[]) => (selectedDocIds = sel.map((s) => s.id))"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column
              prop="name"
              :label="i18nT('ai_ontology.document')"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column :label="i18nT('ai_ontology.type')" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small" type="info" effect="plain">{{ row.file_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.size2')" width="90" align="center">
              <template #default="{ row }">{{ fmtSize(row.size) }}</template>
            </el-table-column>
            <el-table-column
              prop="chunk_count"
              :label="i18nT('ai_ontology.chunk')"
              width="70"
              align="center"
            />
            <el-table-column :label="i18nT('ai_ontology.progress')" width="150" align="center">
              <template #default="{ row }">
                <template v-if="row.task">
                  <el-progress
                    :percentage="row.task.progress || 0"
                    :status="taskStatusType(row.task.status)"
                    :stroke-width="6"
                  />
                  <el-tooltip v-if="row.task.error" :content="row.task.error" placement="top">
                    <el-tag size="small" type="danger" effect="plain">
                      {{ i18nT("ai_ontology.failureReason") }}
                    </el-tag>
                  </el-tooltip>
                </template>
                <el-tag v-else size="small" type="success" effect="plain">
                  {{
                    row.doc_status === "ready"
                      ? i18nT("ai_ontology.ready")
                      : row.doc_status || i18nT("ai_ontology.ready")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.time')" width="150">
              <template #default="{ row }">{{ row.created_time }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.operations')" width="210" align="center">
              <template #default="{ row }">
                <el-button icon="View" link type="primary" size="small" @click="previewDoc(row)">
                  {{ i18nT("ai_ontology.preview") }}
                </el-button>
                <el-button icon="Refresh" link type="warning" size="small" @click="reparseDoc(row)">
                  {{ i18nT("ai_ontology.rebuild") }}
                </el-button>
                <el-button icon="Download" link size="small" @click="downloadDoc(row)">
                  {{ i18nT("ai_ontology.download") }}
                </el-button>
                <el-button icon="delete" link type="danger" size="small" @click="deleteDoc(row)">
                  {{ i18nT("ai_ontology.delete2") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty
            v-if="!documents.length && !loadingDocs"
            :description="i18nT('ai_ontology.noDocuments')"
            :image-size="60"
          />

          <div class="faq-bar">
            <el-button size="small" type="primary" plain :loading="faqLoading" @click="exportFaq">
              {{ i18nT("ai_ontology.exportFaqCache") }}
            </el-button>
          </div>

          <el-divider />
          <div class="qa-block">
            <div class="qa-block__title">{{ i18nT("ai_ontology.citedSourceQA") }}</div>
            <div class="dt-search">
              <el-input
                v-model="qaQuery"
                :placeholder="i18nT('ai_ontology.qaInputPlaceholder')"
                @keyup.enter="doQaSearch"
              />
              <el-button type="primary" :loading="qaSearching" @click="doQaSearch">
                {{ i18nT("ai_ontology.qA") }}
              </el-button>
            </div>
            <div v-if="qaAnswer" class="qa-answer" @click="onQaClick" v-html="qaAnswerHtml"></div>
            <div v-if="qaRefs.length" class="qa-refs">
              <div class="qa-refs__title">
                {{ i18nT("ai_ontology.referenceSourceClickTheBadgeInTheAnswerToSeeLocation") }}
              </div>
              <div v-for="ref in qaRefs" :key="ref.index" class="qa-ref">
                <el-tag size="small" type="info" effect="plain">[{{ ref.index }}]</el-tag>
                <span class="qa-ref__file">{{ ref.file }}</span>
                <span v-if="ref.page || ref.start_line" class="qa-ref__loc">
                  {{ ref.page ? i18nT("ai_ontology.pageLoc", { page: ref.page }) : ""
                  }}{{ ref.page && ref.start_line ? "，" : ""
                  }}{{
                    ref.start_line ? i18nT("ai_ontology.lineLoc", { line: ref.start_line }) : ""
                  }}
                </span>
                <el-button
                  v-if="ref.rustfs_url"
                  link
                  type="primary"
                  size="small"
                  @click="openRustfs(ref.rustfs_url)"
                >
                  {{ i18nT("ai_ontology.originalDocument") }}
                </el-button>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 分块 -->
        <el-tab-pane :label="i18nT('ai_ontology.chunk')" name="chunks">
          <div class="chunk-toolbar">
            <el-button size="small" :disabled="!detailChunks.length" @click="exportChunksCsv">
              {{ i18nT("ai_ontology.exportCsv") }}
            </el-button>
          </div>
          <el-table
            v-loading="loadingChunks"
            :data="detailChunks"
            size="small"
            max-height="60vh"
            border
            stripe
          >
            <el-table-column prop="chunk_index" label="#" width="60" align="center" />
            <el-table-column :label="i18nT('ai_ontology.type')" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_parent ? 'info' : 'primary'" effect="plain">
                  {{
                    row.is_parent
                      ? i18nT("ai_ontology.parentChunk")
                      : i18nT("ai_ontology.childChunk")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="token_count" label="Token" width="76" align="center" />
            <el-table-column
              prop="file_name"
              :label="i18nT('ai_ontology.source2')"
              width="120"
              show-overflow-tooltip
            />
            <el-table-column :label="i18nT('ai_ontology.content')" min-width="200">
              <template #default="{ row }">
                <div>{{ row.content }}</div>
                <div v-if="(row.annotations || []).length" class="chunk-ann-tags">
                  <el-tag
                    v-for="(a, ai) in row.annotations"
                    :key="ai"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    {{ a.text }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.operations')" width="150" align="center">
              <template #default="{ row }">
                <el-button icon="edit" link type="primary" size="small" @click="openChunkEdit(row)">
                  {{ i18nT("ai_ontology.edit") }}
                </el-button>
                <el-button
                  icon="EditPen"
                  link
                  type="warning"
                  size="small"
                  @click="openAnnotation(row)"
                >
                  {{ i18nT("ai_ontology.annotate") }}
                </el-button>
                <el-button
                  link
                  type="danger"
                  size="small"
                  :icon="Delete"
                  @click="deleteChunkFromDetail(row)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 检索测试 -->
        <el-tab-pane :label="i18nT('ai_ontology.searchTest')" name="search">
          <div class="dt-search">
            <el-select v-model="detailSearchMode" style="width: 130px">
              <el-option :label="i18nT('ai_ontology.hybrid')" value="hybrid" />
              <el-option :label="i18nT('ai_ontology.vector')" value="vector" />
              <el-option :label="i18nT('ai_ontology.chineseFullText')" value="fulltext" />
              <el-option :label="i18nT('ai_ontology.graph2')" value="graph" />
              <el-option :label="i18nT('ai_ontology.substringFullText')" value="grep" />
            </el-select>
            <el-input
              v-model="detailQuery"
              :placeholder="i18nT('ai_ontology.inputToSearch')"
              style="flex: 1"
              @keyup.enter="doDetailSearch"
            />
            <el-button type="primary" :loading="detailSearching" @click="doDetailSearch">
              {{ i18nT("ai_ontology.search2") }}
            </el-button>
            <el-button @click="openGraph(detailKb)">{{ i18nT("ai_ontology.graph2") }}</el-button>
          </div>
          <div v-if="detailSearchMode === 'hybrid'" class="dt-weights">
            <span class="dt-weight-label">{{ i18nT("ai_ontology.hybridWeight") }}</span>
            <el-input-number
              v-model="detailVectorWeight"
              :min="0"
              :max="1"
              :step="0.1"
              size="small"
              controls-position="right"
            />
            <span class="dt-weight-label">{{ i18nT("ai_ontology.vector") }}</span>
            <el-input-number
              v-model="detailFulltextWeight"
              :min="0"
              :max="1"
              :step="0.1"
              size="small"
              controls-position="right"
            />
            <span class="dt-weight-label">{{ i18nT("ai_ontology.fullText") }}</span>
          </div>
          <div class="dt-weights">
            <span class="dt-weight-label">{{ i18nT("ai_ontology.similarityThreshold") }}</span>
            <el-input-number
              v-model="detailMinScore"
              :min="0"
              :max="1"
              :step="0.05"
              size="small"
              controls-position="right"
            />
            <span class="dt-weight-label">{{ i18nT("ai_ontology.fileFilter") }}</span>
            <el-input
              v-model="detailFileFilter"
              size="small"
              :placeholder="i18nT('ai_ontology.fileNameOptional')"
              style="width: 180px"
            />
            <span class="dt-weight-label">Rerank</span>
            <el-switch v-model="detailUseRerank" size="small" />
            <span class="dt-weight-label">{{ i18nT("ai_ontology.queryRewrite") }}</span>
            <el-select v-model="detailRewrite" size="small" style="width: 130px">
              <el-option :label="i18nT('ai_ontology.close')" value="off" />
              <el-option label="multi-query" value="multi_query" />
              <el-option label="HyDE" value="hyde" />
            </el-select>
          </div>
          <el-empty
            v-if="!detailSearchResults.length"
            :description="i18nT('ai_ontology.enterQueryToSearch')"
            :image-size="60"
          />
          <div v-for="(h, i) in detailSearchResults" :key="i" class="search-hit">
            <div class="search-hit__meta">
              <span class="search-hit__file">
                {{ h.file_name || i18nT("ai_ontology.unknown") }}
              </span>
              <span class="search-hit__score">
                {{ i18nT("ai_ontology.scoreValue", { score: h.score }) }}
              </span>
              <span v-if="h.timings" class="search-hit__score">
                {{
                  i18nT("ai_ontology.searchTimings", {
                    total: h.timings.total_ms,
                    embed: h.timings.embed_ms,
                    rerank: rerankLabel(h.timings.rerank),
                  })
                }}
              </span>
              <el-tag size="small" effect="plain" :type="engineType(h.engine)">
                {{ engineLabel(h.engine) }}
              </el-tag>
              <el-tag v-if="h.graph_entity" size="small" type="warning" effect="plain">
                {{ i18nT("ai_ontology.graphEntityLabel", { entity: h.graph_entity }) }}
              </el-tag>
              <el-button
                icon="EditPen"
                link
                type="warning"
                size="small"
                class="search-hit__annotate"
                @click="
                  openAnnotation({ id: h.chunk_id, content: h.content, file_name: h.file_name })
                "
              >
                {{ i18nT("ai_ontology.annotateThisChunk") }}
              </el-button>
              <el-button icon="Aim" link type="primary" size="small" @click="locateInGraph(h)">
                {{ i18nT("ai_ontology.graphLocate") }}
              </el-button>
            </div>
            <div class="search-hit__content" v-html="highlight(h.content, detailQuery)"></div>
          </div>
          <el-divider />
          <div class="dt-suggest">
            <div class="dt-suggest__head">
              <span class="dt-suggest__title">
                {{ i18nT("ai_ontology.searchFailedSuggestRelatedChunksAndAnnotate") }}
              </span>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="suggestLoading"
                :disabled="!detailQuery.trim()"
                @click="loadSuggest"
              >
                {{ i18nT("ai_ontology.suggestRelatedChunks") }}
              </el-button>
            </div>
            <el-alert
              v-if="suggestHint"
              type="success"
              :closable="false"
              show-icon
              :title="suggestHint"
            />
            <div v-for="(s, si) in suggestList" :key="si" class="search-hit">
              <div class="search-hit__meta">
                <span class="search-hit__file">
                  {{ s.file_name || i18nT("ai_ontology.unknown") }}
                </span>
                <span class="search-hit__score">
                  {{ i18nT("ai_ontology.similarValue", { score: s.similarity }) }}
                </span>
                <el-tag v-if="s.hit" size="small" type="success" effect="plain">
                  {{ i18nT("ai_ontology.hit") }}
                </el-tag>
                <el-tag v-else size="small" type="warning" effect="plain">
                  {{ i18nT("ai_ontology.notHitSuggestAnnotating") }}
                </el-tag>
                <el-button
                  icon="EditPen"
                  link
                  type="warning"
                  size="small"
                  @click="
                    openAnnotation({
                      id: s.chunk_id,
                      content: s.content,
                      file_name: s.file_name,
                      _query: detailQuery,
                      _source: 'search',
                    })
                  "
                >
                  {{ i18nT("ai_ontology.annotateThisChunk") }}
                </el-button>
              </div>
              <div class="search-hit__content" v-html="highlight(s.content, detailQuery)"></div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 标注台账 -->
        <el-tab-pane :label="i18nT('ai_ontology.annotationLedger')" name="logs">
          <div class="log-toolbar">
            <el-select
              v-model="logSourceFilter"
              size="small"
              :placeholder="i18nT('ai_ontology.source2')"
              clearable
              style="width: 120px"
            >
              <el-option :label="i18nT('ai_ontology.manual')" value="manual" />
              <el-option :label="i18nT('ai_ontology.search2')" value="search" />
              <el-option :label="i18nT('ai_ontology.auto')" value="auto" />
              <el-option :label="i18nT('ai_ontology.graph2')" value="graph" />
            </el-select>
            <el-select
              v-model="logKindFilter"
              size="small"
              :placeholder="i18nT('ai_ontology.type')"
              clearable
              style="width: 120px"
            >
              <el-option :label="i18nT('ai_ontology.alias')" value="alias" />
              <el-option :label="i18nT('ai_ontology.anchor')" value="anchor" />
              <el-option :label="i18nT('ai_ontology.remark')" value="note" />
            </el-select>
            <el-tag size="small" type="info" effect="plain">
              {{ i18nT("ai_ontology.totalCount", { count: filteredLogs.length }) }}
            </el-tag>
            <el-tag size="small" type="success" effect="plain">
              {{ i18nT("ai_ontology.addedCount", { count: statAdd }) }}
            </el-tag>
            <el-tag size="small" type="danger" effect="plain">
              {{ i18nT("ai_ontology.deletedCount", { count: statRemove }) }}
            </el-tag>
          </div>
          <el-table
            v-loading="loadingLogs"
            :data="filteredLogs"
            size="small"
            max-height="60vh"
            border
            stripe
          >
            <el-table-column :label="i18nT('ai_ontology.time')" width="160">
              <template #default="{ row }">{{ row.created_time }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.chunk')" width="70" align="center">
              <template #default="{ row }">#{{ row.chunk_id }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.action')" width="70" align="center">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.action === 'add' ? 'success' : 'danger'"
                  effect="plain"
                >
                  {{
                    row.action === "add" ? i18nT("ai_ontology.added") : i18nT("ai_ontology.deleted")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.annotate')" min-width="140">
              <template #default="{ row }">{{ row.text }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.type')" width="70" align="center">
              <template #default="{ row }">{{ annotKindLabel(row.kind) }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.source2')" width="90" align="center">
              <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
            </el-table-column>
            <el-table-column
              :label="i18nT('ai_ontology.triggerQuery')"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.query || "—" }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 检索统计 -->
        <el-tab-pane :label="i18nT('ai_ontology.searchStats')" name="stats">
          <el-form inline size="small" class="stats-days">
            <el-form-item :label="i18nT('ai_ontology.recent')">
              <el-input-number v-model="statsDays" :min="7" :max="90" :step="1" size="small" />
            </el-form-item>
            <el-form-item :label="i18nT('ai_ontology.days')">
              <el-button type="primary" size="small" :loading="loadingStats" @click="loadStats">
                {{ i18nT("ai_ontology.refresh") }}
              </el-button>
            </el-form-item>
          </el-form>
          <div v-loading="loadingStats" class="stats-cards">
            <el-statistic :title="i18nT('ai_ontology.searchCount')" :value="searchStats.total" />
            <el-statistic
              :title="i18nT('ai_ontology.hitRate')"
              :value="(searchStats.hit_rate || 0) * 100"
              :precision="0"
              suffix="%"
            />
            <el-statistic :title="i18nT('ai_ontology.averageHits')" :value="searchStats.avg_hits" />
            <el-statistic
              :title="i18nT('ai_ontology.emptyHit')"
              :value="searchStats.zero_hit_count"
            />
          </div>
          <div class="stats-engine">
            <span class="stats-engine__label">{{ i18nT("ai_ontology.engineDistribution") }}</span>
            <el-tag
              v-for="(cnt, eng) in searchStats.engine_dist"
              :key="eng"
              size="small"
              effect="plain"
              class="stats-engine__tag"
            >
              {{ engineLabel(String(eng)) }} × {{ cnt }}
            </el-tag>
            <span v-if="!Object.keys(searchStats.engine_dist || {}).length" class="kb-opt-hint">
              {{ i18nT("ai_ontology.noData") }}
            </span>
          </div>
          <el-table :data="searchStats.trend || []" size="small" max-height="40vh" border stripe>
            <el-table-column prop="date" :label="i18nT('ai_ontology.date')" width="150" />
            <el-table-column
              prop="count"
              :label="i18nT('ai_ontology.searchCount')"
              width="100"
              align="center"
            />
            <el-table-column
              prop="hits"
              :label="i18nT('ai_ontology.totalHits')"
              width="100"
              align="center"
            />
          </el-table>
          <el-empty
            v-if="!(searchStats.trend || []).length"
            :description="i18nT('ai_ontology.noSearchRecords')"
            :image-size="60"
          />
        </el-tab-pane>

        <!-- 评测（数据集 / 配置 / 运行记录） -->
        <el-tab-pane :label="i18nT('ai_ontology.eval')" name="eval">
          <el-form inline size="small" class="stats-days">
            <el-form-item :label="i18nT('ai_ontology.dataset')">
              <el-select
                v-model="evalSetId"
                size="small"
                :placeholder="i18nT('ai_ontology.selectEvalSet')"
                style="width: 220px"
                @change="loadEvalRuns"
              >
                <el-option
                  v-for="s in evalSets"
                  :key="s.id"
                  :label="
                    i18nT('ai_ontology.evalSetKbCount', {
                      name: s.name,
                      count: (s.kb_ids || []).length,
                    })
                  "
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="TopK">
              <el-input-number v-model="evalConfig.top_k" :min="1" :max="20" size="small" />
            </el-form-item>
            <el-form-item label="Rerank">
              <el-switch v-model="evalConfig.use_rerank" size="small" />
            </el-form-item>
            <el-form-item>
              <el-button
                v-hasPerm="'module_ai:knowledge:update'"
                :loading="evalRunning"
                @click="startEval"
              >
                {{ i18nT("ai_ontology.runEval") }}
              </el-button>
            </el-form-item>
            <el-form-item>
              <el-button size="small" @click="loadEvalSets">
                {{ i18nT("ai_ontology.refreshDataset") }}
              </el-button>
            </el-form-item>
          </el-form>
          <el-progress
            v-if="evalTask"
            :percentage="evalTask.progress || 0"
            :status="taskStatusType(evalTask.status)"
            :stroke-width="8"
            class="eval-progress"
          />
          <el-table :data="evalRuns" size="small" max-height="50vh" border stripe>
            <el-table-column prop="id" label="#" width="60" align="center" />
            <el-table-column
              :label="i18nT('ai_ontology.config')"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ evalConfigLabel(row.config) }}
              </template>
            </el-table-column>
            <el-table-column label="Recall@K" width="110" align="center">
              <template #default="{ row }">{{ metricPct(row.metrics?.recall) }}</template>
            </el-table-column>
            <el-table-column label="MRR" width="90" align="center">
              <template #default="{ row }">{{ metricPct(row.metrics?.mrr) }}</template>
            </el-table-column>
            <el-table-column label="NDCG@K" width="100" align="center">
              <template #default="{ row }">{{ metricPct(row.metrics?.ndcg) }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.status')" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'succeeded' ? 'success' : 'info'">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.time')" width="160">
              <template #default="{ row }">{{ row.created_time }}</template>
            </el-table-column>
          </el-table>
          <el-empty
            v-if="!evalRuns.length"
            :description="
              i18nT('ai_ontology.selectADatasetToRunEvalOrCreateEvalSetsAndItemsViaAPI')
            "
            :image-size="60"
          />
        </el-tab-pane>

        <!-- 图谱（内嵌可视化 + 编辑） -->
        <el-tab-pane :label="i18nT('ai_ontology.graph2')" name="graph">
          <div v-loading="graphLoading" class="graph-view">
            <div class="graph-stats">
              <el-tag type="success" effect="plain">
                {{ i18nT("ai_ontology.entityNodeCount", { count: graphStats.nodes }) }}
              </el-tag>
              <el-tag type="warning" effect="plain">
                {{ i18nT("ai_ontology.relationEdgeCount", { count: graphStats.edges }) }}
              </el-tag>
              <el-button size="small" type="primary" plain @click="ctxNewNode">
                {{ i18nT("ai_ontology.newNodeAdd") }}
              </el-button>
              <el-button size="small" type="success" plain @click="openAddRel">
                {{ i18nT("ai_ontology.newRelationAdd") }}
              </el-button>
              <el-button size="small" :loading="graphSavingLayout" @click="saveLayout">
                {{ i18nT("ai_ontology.saveLayout") }}
              </el-button>
              <el-button size="small" @click="relayoutGraph">
                {{ i18nT("ai_ontology.reLayout") }}
              </el-button>
              <el-button size="small" @click="() => reloadGraph()">
                {{ i18nT("ai_ontology.refresh") }}
              </el-button>
              <el-button size="small" @click="openRelationTypeDialog">
                {{ i18nT("ai_ontology.relationTemplate") }}
              </el-button>
              <el-button size="small" @click="exportGraphImage">
                {{ i18nT("ai_ontology.exportImage") }}
              </el-button>
              <el-button size="small" type="primary" plain @click="graphFullscreenVisible = true">
                {{ i18nT("ai_ontology.fullscreen") }}
              </el-button>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="!selectedNames.size"
                @click="batchDeleteNodes"
              >
                {{ i18nT("ai_ontology.batchDeleteNodes", { count: selectedNames.size }) }}
              </el-button>
              <el-button
                v-if="selectedNames.size"
                size="small"
                @click="
                  selectedNames = new Set();
                  reloadGraph();
                "
              >
                {{ i18nT("ai_ontology.clearSelection") }}
              </el-button>
              <el-switch
                v-model="multiSelect"
                size="small"
                :active-text="i18nT('ai_ontology.multiSelectMode')"
                @change="
                  selectedNames = new Set();
                  reloadGraph();
                "
              />
              <el-switch
                v-model="linkMode"
                size="small"
                :active-text="i18nT('ai_ontology.edgeMode')"
                @change="linkSource = null"
              />
              <el-select
                v-model="graphLayout"
                size="small"
                style="width: 110px"
                @change="onGraphLayoutChange"
              >
                <el-option :label="i18nT('ai_ontology.forceDirected')" value="cose" />
                <el-option :label="i18nT('ai_ontology.concentric')" value="concentric" />
                <el-option :label="i18nT('ai_ontology.grid')" value="grid" />
                <el-option :label="i18nT('ai_ontology.ring')" value="circle" />
                <el-option :label="i18nT('ai_ontology.level')" value="breadthfirst" />
              </el-select>
              <el-switch
                v-model="physicsMode"
                size="small"
                :active-text="i18nT('ai_ontology.physicsMode')"
                @change="() => onGraphLayoutChange(graphLayout)"
              />
              <el-button size="small" @click="() => graphCanvasRef?.fit?.()">
                {{ i18nT("ai_ontology.fit") }}
              </el-button>
              <el-button size="small" @click="() => graphCanvasRef?.zoom?.(1.25)">
                {{ i18nT("ai_ontology.zoomIn") }}
              </el-button>
              <el-button size="small" @click="() => graphCanvasRef?.zoom?.(0.8)">
                {{ i18nT("ai_ontology.zoomOut") }}
              </el-button>
              <el-button size="small" @click="() => graphCanvasRef?.center?.()">
                {{ i18nT("ai_ontology.center") }}
              </el-button>
              <el-input
                v-model="graphSearch"
                size="small"
                :placeholder="i18nT('ai_ontology.searchNodes')"
                style="width: 130px"
                clearable
                @keyup.enter="onGraphSearch"
              >
                <template #prefix>
                  <el-icon><component :is="'Search'" /></el-icon>
                </template>
              </el-input>
              <el-switch
                v-model="shortestMode"
                size="small"
                :active-text="i18nT('ai_ontology.shortestPath')"
                @change="graphCanvasRef?.fit?.()"
              />
              <el-button size="small" @click="graphStatsVisible = true">
                {{ i18nT("ai_ontology.stats") }}
              </el-button>
              <el-button size="small" @click="edgeStyleVisible = true">
                {{ i18nT("ai_ontology.edgeStyle") }}
              </el-button>
              <el-button size="small" @click="nodeStyleVisible = true">
                {{ i18nT("ai_ontology.nodeStyle") }}
              </el-button>
              <el-select v-model="graphTheme" size="small" style="width: 90px">
                <el-option
                  v-for="t in THEME_OPTIONS"
                  :key="t.value"
                  :label="t.label"
                  :value="t.value"
                />
              </el-select>
            </div>
            <div class="graph-legend">
              <span v-for="lg in graphLegend" :key="lg.label" class="graph-legend__item">
                <i class="graph-legend__dot" :style="{ background: lg.color }" />
                {{ lg.label }}
              </span>
            </div>
            <div class="kb-opt-hint">
              {{ i18nT("ai_ontology.graphHint") }}
            </div>
            <el-empty
              v-if="!graphNodes.length"
              :description="i18nT('ai_ontology.noNodesRightClickCanvasOrClickNewNode')"
              :image-size="60"
            />
            <GraphCanvas
              v-if="graphNodes.length"
              ref="graphCanvasRef"
              class="graph-chart"
              :nodes="graphNodes"
              :edges="graphEdges"
              :use-preset="graphUsePreset"
              :highlight="graphHighlight"
              :edge-style="edgeStyle"
              :theme="graphTheme"
              :node-style="nodeStyle"
              :layout-name="graphLayout"
              :link-mode="linkMode"
              :physics-mode="physicsMode"
              :shortest-mode="shortestMode"
              @node-tap="onGraphNodeTap"
              @node-dbltap="onGraphNodeDbltap"
              @node-ctx="onGraphNodeCtx"
              @edge-ctx="onGraphEdgeCtx"
              @blank-ctx="onGraphBlankCtx"
              @layout="onGraphLayout"
              @link-draw="onGraphLinkDraw"
              @path-found="onGraphPathFound"
            />
            <!-- 图上右键菜单 -->
            <div
              v-if="ctxMenu.visible"
              class="graph-ctx"
              :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
              @click.stop
            >
              <template v-if="ctxMenu.kind === 'node'">
                <div class="graph-ctx__item" @click="ctxEditNode">
                  {{ i18nT("ai_ontology.editNodeProperties") }}
                </div>
                <div class="graph-ctx__item" @click="ctxBindNode">
                  {{ i18nT("ai_ontology.bindChunk") }}
                </div>
                <div class="graph-ctx__item" @click="ctxAddRel">
                  {{ i18nT("ai_ontology.addRelation") }}
                </div>
                <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">
                  {{ i18nT("ai_ontology.deleteNode") }}
                </div>
              </template>
              <template v-else-if="ctxMenu.kind === 'edge'">
                <div class="graph-ctx__item" @click="ctxEditRel">
                  {{ i18nT("ai_ontology.editRelation") }}
                </div>
                <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">
                  {{ i18nT("ai_ontology.deleteRelation") }}
                </div>
              </template>
              <template v-else>
                <div class="graph-ctx__item" @click="ctxNewNode">
                  {{ i18nT("ai_ontology.newNode") }}
                </div>
              </template>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <!-- 编辑分块 -->
    <el-dialog
      v-model="chunkEditVisible"
      :title="i18nT('ai_ontology.editChunk')"
      width="600px"
      append-to-body
    >
      <el-input
        v-model="chunkEditContent"
        type="textarea"
        :rows="8"
        :placeholder="i18nT('ai_ontology.editChunkContentSavingWillReVectorizeThisChunk')"
      />
      <template #footer>
        <el-button @click="chunkEditVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="chunkEditing" @click="saveChunkEdit">
          {{ i18nT("ai_ontology.saveAndReVectorize") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 图谱实体重命名 -->
    <el-dialog
      v-model="renameEntityVisible"
      :title="i18nT('ai_ontology.nodeProperties')"
      width="520px"
      append-to-body
    >
      <el-form label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.nodeName')" required>
          <el-input v-model="renameForm.name" :placeholder="i18nT('ai_ontology.nodeName2')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.type')">
          <el-input v-model="renameForm.etype" placeholder="keyword" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.weight')">
          <el-input-number v-model="renameForm.weight" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.nodeRemarkDesc')">
          <el-input v-model="renameForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.relatedChunk')">
          <div class="bind-chunks">
            <div v-for="c in entityBoundChunks" :key="c.id" class="bind-item">
              <span class="bind-item__label">#{{ c.chunk_index }}</span>
              <span class="bind-item__text">{{ c.content }}</span>
              <el-button icon="Close" link type="danger" size="small" @click="unbindChunk(c)">
                {{ i18nT("ai_ontology.unbind") }}
              </el-button>
            </div>
            <el-empty
              v-if="!entityBoundChunks.length"
              :description="i18nT('ai_ontology.notBoundToChunks')"
              :image-size="50"
            />
            <el-select
              v-model="entityBindSel"
              multiple
              filterable
              collapse-tags
              :placeholder="i18nT('ai_ontology.selectChunksToBind')"
              size="small"
              style="width: 100%"
            >
              <el-option
                v-for="c in detailChunks"
                :key="c.id"
                :label="`#${c.chunk_index} ${c.content.slice(0, 20)}`"
                :value="c.id"
              />
            </el-select>
            <el-button size="small" type="primary" :loading="bindingChunks" @click="bindChunks">
              {{ i18nT("ai_ontology.bind") }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameEntityVisible = false">
          {{ i18nT("ai_ontology.cancel") }}
        </el-button>
        <el-button type="primary" :loading="renamingEntity" @click="saveRenameEntity">
          {{ i18nT("ai_ontology.saveSyncAge") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 分块标注（换说法召回命中） -->
    <el-dialog
      v-model="annotationVisible"
      :title="i18nT('ai_ontology.chunkAnnotTitle', { index: annotChunk?.chunk_index || '' })"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="i18nT('ai_ontology.chunkAnnotHint')"
      />
      <div class="ann-preview">{{ annotChunk?.content }}</div>
      <div class="ann-list">
        <div v-for="(a, ai) in annotList" :key="ai" class="ann-item">
          <el-tag size="small" type="warning" effect="plain">{{ a.text }}</el-tag>
          <el-tag size="small" type="info" effect="plain">{{ annotKindLabel(a.kind) }}</el-tag>
          <el-button icon="delete" link type="danger" size="small" @click="removeAnnotation(ai)">
            {{ i18nT("ai_ontology.delete2") }}
          </el-button>
        </div>
        <el-empty
          v-if="!annotList.length"
          :description="i18nT('ai_ontology.noAnnotations')"
          :image-size="50"
        />
      </div>
      <div class="ann-add">
        <el-input
          v-model="annotText"
          :placeholder="i18nT('ai_ontology.annotPlaceholder')"
          size="small"
          @keyup.enter="addAnnotation"
        />
        <el-select v-model="annotKind" size="small" style="width: 110px">
          <el-option :label="i18nT('ai_ontology.alias')" value="alias" />
          <el-option :label="i18nT('ai_ontology.anchor')" value="anchor" />
          <el-option :label="i18nT('ai_ontology.remark')" value="note" />
        </el-select>
        <el-button type="primary" size="small" :loading="annotating" @click="addAnnotation">
          {{ i18nT("ai_ontology.add") }}
        </el-button>
      </div>
    </el-dialog>

    <!-- 图谱关系编辑 -->
    <el-dialog
      v-model="relEditVisible"
      :title="i18nT('ai_ontology.editGraphRelation')"
      width="520px"
      append-to-body
    >
      <el-form label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.sourceEntity')">
          <el-select
            v-model="relEditForm.source"
            filterable
            :placeholder="i18nT('ai_ontology.source')"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetEntity')">
          <el-select
            v-model="relEditForm.target"
            filterable
            :placeholder="i18nT('ai_ontology.target')"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.relationType')">
          <el-select
            v-model="relEditForm.rtype"
            filterable
            allow-create
            default-first-option
            :placeholder="i18nT('ai_ontology.selectOrEnterRelationType')"
            style="width: 100%"
          >
            <el-option v-for="r in rtypeOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.weight')">
          <el-input-number v-model="relEditForm.weight" :min="1" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relEditVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingRel" @click="saveRelEdit">
          {{ i18nT("ai_ontology.saveSyncAge") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建节点（图上右键空白） -->
    <el-dialog
      v-model="nodeNewVisible"
      :title="i18nT('ai_ontology.newNode')"
      width="520px"
      append-to-body
    >
      <el-form label-width="80px" size="default">
        <el-form-item :label="i18nT('ai_ontology.nodeName')" required>
          <el-input v-model="nodeNewForm.name" :placeholder="i18nT('ai_ontology.entityName')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.type')">
          <el-input v-model="nodeNewForm.etype" placeholder="keyword" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.weight')">
          <el-input-number v-model="nodeNewForm.weight" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.nodeRemarkDesc')">
          <el-input v-model="nodeNewForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeNewVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="addingNode" @click="saveNewNode">
          {{ i18nT("ai_ontology.create") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建关系（选两个节点 + 关系类型，自动连线） -->
    <el-dialog
      v-model="relAddVisible"
      :title="i18nT('ai_ontology.newRelation')"
      width="520px"
      append-to-body
    >
      <el-form label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.sourceNode')">
          <el-select
            v-model="relAddForm.source"
            filterable
            :placeholder="i18nT('ai_ontology.selectSourceNode')"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetNode')">
          <el-select
            v-model="relAddForm.target"
            filterable
            :placeholder="i18nT('ai_ontology.selectTargetNode')"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.relationType')">
          <el-select
            v-model="relAddForm.rtype"
            filterable
            allow-create
            default-first-option
            :placeholder="i18nT('ai_ontology.selectOrEnterRelationType')"
            style="width: 100%"
          >
            <el-option v-for="r in rtypeOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.weight')">
          <el-input-number v-model="relAddForm.weight" :min="1" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relAddVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="addingRel" @click="saveAddRel">
          {{ i18nT("ai_ontology.add") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 图谱全屏查看 -->
    <el-dialog
      v-model="graphFullscreenVisible"
      :title="i18nT('ai_ontology.knowledgeGraphFullscreen')"
      fullscreen
      append-to-body
    >
      <div v-loading="graphLoading" class="graph-fullscreen">
        <div class="graph-stats">
          <el-tag type="success" effect="plain">
            {{ i18nT("ai_ontology.entityNodeCount", { count: graphStats.nodes }) }}
          </el-tag>
          <el-tag type="warning" effect="plain">
            {{ i18nT("ai_ontology.relationEdgeCount", { count: graphStats.edges }) }}
          </el-tag>
          <el-button size="small" @click="relayoutGraph">
            {{ i18nT("ai_ontology.reLayout") }}
          </el-button>
          <el-button size="small" @click="() => reloadGraph()">
            {{ i18nT("ai_ontology.refresh") }}
          </el-button>
          <el-switch
            v-model="linkMode"
            size="small"
            :active-text="i18nT('ai_ontology.edgeMode')"
            @change="linkSource = null"
          />
        </div>
        <GraphCanvas
          v-if="graphNodes.length"
          ref="graphFullscreenRef"
          class="graph-chart graph-chart--fullscreen"
          :nodes="graphNodes"
          :edges="graphEdges"
          :use-preset="graphUsePreset"
          :highlight="graphHighlight"
          :edge-style="edgeStyle"
          :theme="graphTheme"
          :node-style="nodeStyle"
          :layout-name="graphLayout"
          :link-mode="linkMode"
          :physics-mode="physicsMode"
          :shortest-mode="shortestMode"
          :height="`calc(100vh - 210px)`"
          @node-tap="onGraphNodeTap"
          @node-dbltap="onGraphNodeDbltap"
          @link-draw="onGraphLinkDraw"
          @path-found="onGraphPathFound"
          @node-ctx="onGraphNodeCtx"
          @edge-ctx="onGraphEdgeCtx"
          @blank-ctx="onGraphBlankCtx"
        />
        <div
          v-if="ctxMenu.visible"
          class="graph-ctx"
          :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
          @click.stop
        >
          <template v-if="ctxMenu.kind === 'node'">
            <div class="graph-ctx__item" @click="ctxEditNode">
              {{ i18nT("ai_ontology.editNodeProperties") }}
            </div>
            <div class="graph-ctx__item" @click="ctxBindNode">
              {{ i18nT("ai_ontology.bindChunk") }}
            </div>
            <div class="graph-ctx__item" @click="ctxAddRel">
              {{ i18nT("ai_ontology.addRelation") }}
            </div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">
              {{ i18nT("ai_ontology.deleteNode") }}
            </div>
          </template>
          <template v-else-if="ctxMenu.kind === 'edge'">
            <div class="graph-ctx__item" @click="ctxEditRel">
              {{ i18nT("ai_ontology.editRelation") }}
            </div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">
              {{ i18nT("ai_ontology.deleteRelation") }}
            </div>
          </template>
          <template v-else>
            <div class="graph-ctx__item" @click="ctxNewNode">
              {{ i18nT("ai_ontology.newNode") }}
            </div>
          </template>
        </div>
      </div>
    </el-dialog>

    <!-- 关系类型模板管理 -->
    <el-dialog
      v-model="relationTypeDialogVisible"
      :title="i18nT('ai_ontology.relationTypeTemplate')"
      width="520px"
      append-to-body
    >
      <div class="rt-add">
        <el-input
          v-model="rtNewName"
          :placeholder="i18nT('ai_ontology.relationTypeNameEGDepends')"
          size="small"
          @keyup.enter="addRt"
        />
        <el-button size="small" type="primary" @click="addRt">
          {{ i18nT("ai_ontology.add") }}
        </el-button>
      </div>
      <el-table :data="relationTypes" size="small" max-height="50vh" border stripe>
        <el-table-column prop="name" :label="i18nT('ai_ontology.type')" min-width="140" />
        <el-table-column :label="i18nT('ai_ontology.color')" width="80" align="center">
          <template #default="{ row }">
            <i class="graph-legend__dot" :style="{ background: row.color || '#a0a6ad' }" />
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="80" align="center">
          <template #default="{ row }">
            <el-button icon="delete" link type="danger" size="small" @click="delRt(row)">
              {{ i18nT("ai_ontology.delete2") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="relationTypeDialogVisible = false">
          {{ i18nT("ai_ontology.close") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 节点样式设置 -->
    <el-dialog
      v-model="nodeStyleVisible"
      :title="i18nT('ai_ontology.nodeStyleSettings')"
      width="600px"
      append-to-body
    >
      <el-form label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.nodeSize')">
          <el-radio-group v-model="nodeStyle.sizeMode">
            <el-radio-button label="weight">{{ i18nT("ai_ontology.byWeight") }}</el-radio-button>
            <el-radio-button label="fixed">{{ i18nT("ai_ontology.fixed") }}</el-radio-button>
          </el-radio-group>
          <el-input-number
            v-if="nodeStyle.sizeMode === 'fixed'"
            v-model="nodeStyle.fixedSize"
            :min="10"
            :max="60"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.nodeShape')">
          <el-radio-group v-model="nodeStyle.shapeMode">
            <el-radio-button label="type">{{ i18nT("ai_ontology.byType") }}</el-radio-button>
            <el-radio-button label="uniform">{{ i18nT("ai_ontology.unified") }}</el-radio-button>
          </el-radio-group>
          <el-select
            v-if="nodeStyle.shapeMode === 'uniform'"
            v-model="nodeStyle.uniformShape"
            size="small"
            style="width: 140px; margin-left: 8px"
          >
            <el-option :label="i18nT('ai_ontology.ellipse')" value="ellipse" />
            <el-option :label="i18nT('ai_ontology.circle')" value="circle" />
            <el-option :label="i18nT('ai_ontology.roundedSquare')" value="round-rectangle" />
            <el-option :label="i18nT('ai_ontology.diamond')" value="diamond" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.nodeColor')">
          <el-radio-group v-model="nodeStyle.colorMode">
            <el-radio-button label="type">{{ i18nT("ai_ontology.byType") }}</el-radio-button>
            <el-radio-button label="single">{{ i18nT("ai_ontology.unified") }}</el-radio-button>
          </el-radio-group>
          <el-color-picker
            v-if="nodeStyle.colorMode === 'single'"
            v-model="nodeStyle.singleColor"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.labelSize')">
          <el-input-number v-model="nodeStyle.labelSize" :min="9" :max="20" size="small" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeStyleVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 文档内容预览 -->
    <el-dialog v-model="docPreviewVisible" :title="docPreviewName" width="900px" append-to-body>
      <div v-loading="docPreviewLoading" class="doc-preview">
        <VuePdfEmbed
          v-if="docPreviewKind === 'pdf' && docPreviewPdfUrl"
          :source="docPreviewPdfUrl"
        />
        <div v-else-if="docPreviewKind === 'docx'" class="doc-html" v-html="docPreviewHtml" />
        <div v-else class="doc-text">{{ docPreviewContent || i18nT("ai_ontology.emptyDoc") }}</div>
      </div>
      <template #footer>
        <el-button @click="docPreviewVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 引用来源弹窗 -->
    <el-dialog
      v-model="qaCiteVisible"
      :title="i18nT('ai_ontology.referenceSource')"
      width="600px"
      append-to-body
    >
      <el-descriptions v-if="qaCite" :column="1" size="small" border>
        <el-descriptions-item :label="i18nT('ai_ontology.sourceDocument')">
          {{ qaCite.file }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.location')">
          {{ qaCite.page ? i18nT("ai_ontology.pageLoc", { page: qaCite.page }) : ""
          }}{{ qaCite.page && qaCite.start_line ? "，" : ""
          }}{{
            qaCite.start_line
              ? i18nT("ai_ontology.lineLoc", { line: qaCite.start_line })
              : i18nT("ai_ontology.cantLocateLinePage")
          }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="qa-cite-content">{{ qaCite?.content }}</div>
      <template #footer>
        <el-button v-if="qaCite?.rustfs_url" type="primary" @click="openRustfs(qaCite.rustfs_url)">
          {{ i18nT("ai_ontology.openOriginalDocRustfs") }}
        </el-button>
        <el-button @click="qaCiteVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 连线样式设置 -->
    <el-dialog
      v-model="edgeStyleVisible"
      :title="i18nT('ai_ontology.edgeStyleSettings')"
      width="600px"
      append-to-body
    >
      <el-form label-width="90px" size="default">
        <el-form-item :label="i18nT('ai_ontology.lineStyle')">
          <el-radio-group v-model="edgeStyle.lineStyle">
            <el-radio-button label="solid">{{ i18nT("ai_ontology.solid") }}</el-radio-button>
            <el-radio-button label="dashed">{{ i18nT("ai_ontology.dashed") }}</el-radio-button>
            <el-radio-button label="dotted">{{ i18nT("ai_ontology.dotted") }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.curve')">
          <el-radio-group v-model="edgeStyle.curve">
            <el-radio-button label="bezier">{{ i18nT("ai_ontology.bezier") }}</el-radio-button>
            <el-radio-button label="straight">{{ i18nT("ai_ontology.line") }}</el-radio-button>
            <el-radio-button label="taxi">{{ i18nT("ai_ontology.polyline") }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.arrow')">
          <el-select v-model="edgeStyle.arrow" style="width: 140px">
            <el-option :label="i18nT('ai_ontology.triangle')" value="triangle" />
            <el-option :label="i18nT('ai_ontology.vShape')" value="vee" />
            <el-option :label="i18nT('ai_ontology.dot')" value="circle" />
            <el-option :label="i18nT('ai_ontology.none')" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.lineWidth')">
          <el-radio-group v-model="edgeStyle.widthMode">
            <el-radio-button label="weight">{{ i18nT("ai_ontology.byWeight") }}</el-radio-button>
            <el-radio-button label="fixed">{{ i18nT("ai_ontology.fixed") }}</el-radio-button>
          </el-radio-group>
          <el-input-number
            v-if="edgeStyle.widthMode === 'fixed'"
            v-model="edgeStyle.fixedWidth"
            :min="1"
            :max="8"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.color')">
          <el-radio-group v-model="edgeStyle.colorMode">
            <el-radio-button label="type">
              {{ i18nT("ai_ontology.byRelationType") }}
            </el-radio-button>
            <el-radio-button label="single">{{ i18nT("ai_ontology.unified") }}</el-radio-button>
          </el-radio-group>
          <el-color-picker
            v-if="edgeStyle.colorMode === 'single'"
            v-model="edgeStyle.singleColor"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.relationLabel')">
          <el-select v-model="edgeStyle.label" style="width: 180px">
            <el-option :label="i18nT('ai_ontology.alwaysShow')" value="show" />
            <el-option :label="i18nT('ai_ontology.nonDefaultRelationsOnly')" value="nondefault" />
            <el-option :label="i18nT('ai_ontology.showOnHover')" value="hover" />
            <el-option :label="i18nT('ai_ontology.hide')" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.opacity')">
          <el-slider
            v-model="edgeStyle.opacity"
            :min="0.1"
            :max="1"
            :step="0.05"
            style="width: 260px"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="edgeStyleVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 图谱统计 -->
    <el-dialog
      v-model="graphStatsVisible"
      :title="i18nT('ai_ontology.graphStats')"
      width="600px"
      append-to-body
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="i18nT('ai_ontology.entityNodes')">
          {{ graphStatsDetail.nodes }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.relationEdges')">
          {{ graphStatsDetail.edges }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.averageDegree')">
          {{ graphStatsDetail.avgDegree }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.joinComponent')">—</el-descriptions-item>
      </el-descriptions>
      <div class="stat-block">
        <div class="stat-block__title">{{ i18nT("ai_ontology.entityTypeDistribution") }}</div>
        <el-tag
          v-for="(c, t) in graphStatsDetail.typeCount"
          :key="t"
          size="small"
          effect="plain"
          class="stat-tag"
        >
          {{ typeLabel(String(t)) }} × {{ c }}
        </el-tag>
      </div>
      <div class="stat-block">
        <div class="stat-block__title">{{ i18nT("ai_ontology.relationTypeDistribution") }}</div>
        <el-tag
          v-for="(c, r) in graphStatsDetail.relCount"
          :key="r"
          size="small"
          effect="plain"
          class="stat-tag"
        >
          {{ r }} × {{ c }}
        </el-tag>
      </div>
      <template #footer>
        <el-button @click="graphStatsVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
      </template>
    </el-dialog>

    <!-- 实体关联分块（图谱节点点击直达） -->
    <el-dialog
      v-model="entityChunksVisible"
      :title="i18nT('ai_ontology.entityChunksTitle', { name: entityChunksName })"
      width="600px"
      append-to-body
    >
      <el-table
        v-loading="entityChunksLoading"
        :data="entityChunksList"
        size="small"
        max-height="50vh"
        border
        stripe
      >
        <el-table-column prop="chunk_index" label="#" width="60" align="center" />
        <el-table-column
          prop="file_name"
          :label="i18nT('ai_ontology.source2')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.content')" min-width="200">
          <template #default="{ row }">{{ row.content }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="90" align="center">
          <template #default="{ row }">
            <el-button
              icon="EditPen"
              link
              type="warning"
              size="small"
              @click="
                openAnnotation({ id: row.id, content: row.content, file_name: row.file_name })
              "
            >
              {{ i18nT("ai_ontology.annotate") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!entityChunksList.length"
        :description="i18nT('ai_ontology.thisEntityHasNoBoundChunks')"
        :image-size="50"
      />
    </el-dialog>

    <el-dialog
      v-model="dsDialogVisible"
      :title="editingDs ? i18nT('ai_ontology.editDataSource') : i18nT('ai_ontology.newDataSource')"
      width="600px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="dsForm" label-width="100px" size="default">
        <el-form-item :label="i18nT('ai_ontology.name')" required>
          <el-input v-model="dsForm.name" :placeholder="i18nT('ai_ontology.dataSourceName')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.type')">
          <el-radio-group v-model="dsForm.ds_type">
            <el-radio-button value="db">{{ i18nT("ai_ontology.database") }}</el-radio-button>
            <el-radio-button value="api">API</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="dsForm.ds_type === 'db'" :label="i18nT('ai_ontology.dialect')">
          <el-select v-model="dsForm.dialect" style="width: 100%">
            <el-option label="postgresql" value="postgresql" />
            <el-option label="mysql" value="mysql" />
            <el-option label="sqlite" value="sqlite" />
          </el-select>
        </el-form-item>
        <el-form-item
          :label="
            dsForm.ds_type === 'db' ? i18nT('ai_ontology.connUri') : i18nT('ai_ontology.apiUrl')
          "
        >
          <el-input
            v-model="dsForm.uri"
            :placeholder="
              dsForm.ds_type === 'db'
                ? 'postgresql://user:pass@host/db'
                : 'https://api.example.com/items'
            "
          />
        </el-form-item>
        <el-form-item v-if="dsForm.ds_type === 'api'" label="Method">
          <el-select v-model="dsForm.api_config.method" style="width: 160px">
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="dsForm.ds_type === 'api'" :label="i18nT('ai_ontology.dataPath')">
          <el-input
            v-model="dsForm.api_config.data_path"
            :placeholder="i18nT('ai_ontology.dataPathPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.targetKnowledgeBase')">
          <el-select
            v-model="dsForm.knowledge_base_id"
            clearable
            filterable
            :placeholder="i18nT('ai_ontology.selectSyncTarget')"
            style="width: 100%"
          >
            <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.enabled')">
          <el-switch v-model="dsForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dsDialogVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingDs" @click="saveDs">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { ref, reactive, computed, onMounted, onUnmounted } from "vue";
import GraphCanvas from "./GraphCanvas.vue";
import VuePdfEmbed from "vue-pdf-embed";
import mammoth from "mammoth";

const { t: i18nT } = useI18n();

const graphCanvasRef = ref<any>();
import { ElMessage, ElMessageBox } from "element-plus";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
use([CanvasRenderer, GraphChart, TooltipComponent]);
import {
  Edit,
  Delete,
  Upload,
  Search,
  Files,
  Folder,
  Plus,
  Connection,
  Refresh,
  Share,
  UploadFilled,
  CopyDocument,
} from "@element-plus/icons-vue";
import {
  getAiKnowledgeList,
  getAiKnowledgeCategoryTree,
  createAiKnowledgeCategory,
  createAiKnowledge,
  updateAiKnowledge,
  deleteAiKnowledge,
  ingestAiKnowledge,
  searchAiKnowledge,
  askAiKnowledge,
  rebuildAiKnowledge,
  getAiKnowledgeChunks,
  deleteAiKnowledgeChunk,
  updateAiKnowledgeChunk,
  addAiKnowledgeChunkAnnotation,
  removeAiKnowledgeChunkAnnotation,
  suggestAiKnowledgeAnnotate,
  getAiKnowledgeAnnotationLogs,
  getAiKnowledgeSearchStats,
  getAiKnowledgeEntityChunks,
  bindAiKnowledgeEntityChunks,
  unbindAiKnowledgeEntityChunks,
  updateAiKnowledgeGraphRelation,
  saveAiKnowledgeGraphLayout,
  clearAiKnowledgeGraphLayout,
  getAiRelationTypes,
  createAiRelationType,
  deleteAiRelationType,
  getAiKnowledgeDocuments,
  uploadAiKnowledgeDocument,
  getAiRagTask,
  getAiEvalSets,
  runAiEval,
  getAiEvalRuns,
  deleteAiKnowledgeDocument,
  getAiKnowledgeDocumentContent,
  reparseAiKnowledgeDocument,
  downloadAiKnowledgeDocument,
  getAiKnowledgeFaq,
  getAiKnowledgeGraph,
  copyAiKnowledge,
  createAiKnowledgeGraphEntity,
  updateAiKnowledgeGraphEntity,
  deleteAiKnowledgeGraphEntities,
  createAiKnowledgeGraphRelation,
  deleteAiKnowledgeGraphRelations,
  getAiDatasourceList,
  createAiDatasource,
  updateAiDatasource,
  deleteAiDatasource,
  testAiDatasource,
  syncAiDatasource,
} from "@/api/module_ai/knowledge";
import { getAiModelList } from "@/api/module_ai/model";

defineOptions({ name: "AiKnowledge" });

const activeTab = ref("kb");
const loading = ref(false);
const loadingDs = ref(false);
const bases = ref<any[]>([]);
const datasources = ref<any[]>([]);
const modelOptions = ref<{ id: number; name: string }[]>([]);
const modelNameMap = ref<Record<number, string>>({});
const modelUsageMap = ref<Record<number, string>>({});

// 知识库 / 数据源 关键字过滤（工具栏搜索框，与系统管理一致的搜索体验）
const kbKeyword = ref("");
const dsKeyword = ref("");
const filteredBases = computed(() => {
  const q = kbKeyword.value.trim().toLowerCase();
  const ids = currentCatIds.value;
  return bases.value.filter((b: any) => {
    // 分类过滤：选中分类时含其子分类；「全部」不过滤
    if (ids && !ids.has(b.category_id)) return false;
    if (q) {
      const haystack = [b.name, b.description].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
});
const filteredDatasources = computed(() => {
  const q = dsKeyword.value.trim().toLowerCase();
  if (!q) return datasources.value;
  return datasources.value.filter((d: any) =>
    [d.name, d.uri].filter(Boolean).join(" ").toLowerCase().includes(q)
  );
});

const selectedKb = ref<any>();
const selectedDs = ref<any>();

function kbName(id: number | null) {
  if (id == null) return "—";
  return bases.value.find((b) => b.id === id)?.name || `#${id}`;
}

const loadData = async () => {
  loading.value = true;
  loadingDs.value = true;
  try {
    const [kr, dr, mr] = await Promise.all([
      getAiKnowledgeList(),
      getAiDatasourceList(),
      getAiModelList({}),
    ]);
    const list = kr.data?.data || [];
    // 图谱列：逐个拉取 /graph 统计（可靠）
    await Promise.all(
      list.map(async (b: any) => {
        if (b.graph_nodes == null) {
          try {
            const g = await getAiKnowledgeGraph(b.id);
            b.graph_nodes = (g.data?.data?.nodes || []).length;
            b.graph_edges = (g.data?.data?.edges || []).length;
          } catch {
            b.graph_nodes = 0;
            b.graph_edges = 0;
          }
        }
      })
    );
    bases.value = list;
    datasources.value = dr.data?.data || [];
    // 分类树带各分类的知识库数量（依赖刚加载的 bases）
    await loadCategories();
    const models = mr.data?.data || [];
    // 只列可用作嵌入的模型（usage=embedding 或 capabilities 含 embedding）
    modelOptions.value = models
      .filter((m: any) => m.usage === "embedding" || (m.capabilities || []).includes("embedding"))
      .map((m: any) => ({ id: m.id, name: m.name }));
    modelNameMap.value = Object.fromEntries(models.map((m: any) => [m.id, m.name]));
    modelUsageMap.value = Object.fromEntries(models.map((m: any) => [m.id, m.usage]));
    await loadRelationTypes();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.loadFailed"));
  } finally {
    loading.value = false;
    loadingDs.value = false;
  }
};

// ---------- 知识库分类（左侧分类树） ----------
const catTree = ref<any[]>([]);
const currentCatId = ref<number | null>(null);
const catDialogVisible = ref(false);
const catSaving = ref(false);
const catForm = reactive<any>({ name: "", parent_id: null, owner: "", remark: "" });

/** 分类树：根节点「全部」+ 分类子树（带各分类的知识库数量） */
async function loadCategories() {
  try {
    const res: any = await getAiKnowledgeCategoryTree();
    catTree.value = [
      {
        id: 0,
        name: i18nT("ai_ontology.all"),
        count: bases.value.length,
        children: res.data?.data || [],
      },
    ];
  } catch {
    catTree.value = [
      { id: 0, name: i18nT("ai_ontology.all"), count: bases.value.length, children: [] },
    ];
  }
}

/** 当前选中的分类及其所有子孙 id（父分类应能看到子分类下的知识库） */
const currentCatIds = computed<Set<number> | null>(() => {
  if (currentCatId.value == null) return null;
  const ids = new Set<number>([currentCatId.value]);
  const walk = (list: any[]) => {
    for (const n of list || []) {
      if (ids.has(n.id) && n.children?.length) walk(n.children);
    }
  };
  walk(catTree.value[0]?.children || []);
  return ids;
});

function onCatClick(data: any) {
  currentCatId.value = data.id === 0 ? null : data.id;
}

function openCatCreate(parent?: any) {
  Object.assign(catForm, {
    name: "",
    parent_id: parent?.id ?? null,
    owner: "",
    remark: "",
  });
  catDialogVisible.value = true;
}

/** 分类下拉选项（拍平 + 层级缩进） */
const flatCatOptions = computed(() => {
  const out: { id: number; label: string }[] = [];
  const walk = (list: any[], depth: number) => {
    for (const n of list || []) {
      out.push({ id: n.id, label: `${"　".repeat(depth)}${n.name}` });
      if (n.children?.length) walk(n.children, depth + 1);
    }
  };
  walk(catTree.value[0]?.children || [], 0);
  return out;
});

async function saveCat() {
  if (!catForm.name?.trim()) {
    ElMessage.warning(i18nT("ai_ontology.pleaseEnterCategoryName"));
    return;
  }
  catSaving.value = true;
  try {
    await createAiKnowledgeCategory({
      name: catForm.name.trim(),
      parent_id: catForm.parent_id ?? null,
      owner: catForm.owner || null,
      remark: catForm.remark || "",
    });
    ElMessage.success(i18nT("ai_ontology.categoryCreated"));
    catDialogVisible.value = false;
    await loadCategories();
  } finally {
    catSaving.value = false;
  }
}

// ---------- 知识库 CRUD ----------
const kbDialogVisible = ref(false);
const savingKb = ref(false);
const editingKb = ref<any>();
const kbForm = reactive<any>({});

function openKbDialog(b?: any) {
  editingKb.value = b || undefined;
  Object.assign(
    kbForm,
    b ? { ...b } : { name: "", description: "", model_id: null, category_id: null, enabled: true }
  );
  kbDialogVisible.value = true;
}

async function saveKb() {
  if (!kbForm.name) {
    ElMessage.warning(i18nT("ai_ontology.pleaseEnterKBName"));
    return;
  }
  savingKb.value = true;
  try {
    const payload: any = {
      name: kbForm.name,
      description: kbForm.description || "",
      model_id: kbForm.model_id || null,
      category_id: kbForm.category_id ?? null,
      enabled: kbForm.enabled,
    };
    if (editingKb.value) {
      await updateAiKnowledge(editingKb.value.id, payload);
    } else {
      await createAiKnowledge(payload);
    }
    ElMessage.success(i18nT("ai_ontology.saved2"));
    kbDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.saveFailed"));
  } finally {
    savingKb.value = false;
  }
}

function deleteBases(row: any) {
  ElMessageBox.confirm(
    i18nT("ai_ontology.deleteKbConfirm", { name: row.name, count: row.chunk_count || 0 }),
    i18nT("ai_ontology.deleteConfirm"),
    {
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      await deleteAiKnowledge([row.id]);
      ElMessage.success(i18nT("ai_ontology.deleted2"));
      if (selectedKb.value?.id === row.id) selectedKb.value = undefined;
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
}

async function copyBase(row: any) {
  try {
    const r = await copyAiKnowledge(row.id);
    const d = r.data?.data || {};
    ElMessage.success(i18nT("ai_ontology.kbCopiedMsg", { name: d.name, count: d.chunks }));
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.copyFailed"));
  }
}

// ---------- 入库 ----------
const ingestDialogVisible = ref(false);
const ingesting = ref(false);
const ingestTarget = ref<any>();
const ingestForm = reactive<any>({});

function openIngestDialog(kb: any) {
  ingestTarget.value = kb;
  Object.assign(ingestForm, { file_name: "", content: "", chunk_size: 500, overlap: 50 });
  ingestDialogVisible.value = true;
}

async function doIngest() {
  if (!ingestForm.content.trim()) {
    ElMessage.warning(i18nT("ai_ontology.pleasePasteTextToIngest"));
    return;
  }
  ingesting.value = true;
  try {
    const r = await ingestAiKnowledge(ingestTarget.value.id, { ...ingestForm });
    ElMessage.success(i18nT("ai_ontology.ingestSuccessMsg", { count: r.data?.data?.chunks || 0 }));
    ingestDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.ingestFailed"));
  } finally {
    ingesting.value = false;
  }
}

// ---------- 检索 ----------
const searchDialogVisible = ref(false);
const searching = ref(false);
const searchForm = reactive<any>({ query: "", top_k: 5, use_graph: true });
const searchResults = ref<any[]>([]);

function openSearchDialog(kb: any) {
  selectedKb.value = kb;
  Object.assign(searchForm, { query: "", top_k: 5 });
  searchResults.value = [];
  searchDialogVisible.value = true;
}

async function doSearch() {
  if (!searchForm.query.trim()) {
    ElMessage.warning(i18nT("ai_ontology.pleaseEnterAQuery"));
    return;
  }
  searching.value = true;
  try {
    const r = await searchAiKnowledge(
      selectedKb.value?.id,
      searchForm.query,
      searchForm.top_k,
      searchForm.use_graph
    );
    searchResults.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.searchFailed"));
  } finally {
    searching.value = false;
  }
}

// 检索引擎标签
function engineLabel(e: string): string {
  if (e === "jieba_fulltext") return i18nT("ai_ontology.chineseFullText");
  if (e === "pgvector") return i18nT("ai_ontology.vector");
  if (e === "graphrag") return i18nT("ai_ontology.graph2");
  if (e === "hybrid") return i18nT("ai_ontology.hybrid");
  if (e === "grep") return i18nT("ai_ontology.substringFullText");
  return e;
}
function engineType(e: string): "primary" | "success" | "warning" | "info" | "danger" {
  if (e === "jieba_fulltext") return "success";
  if (e === "pgvector") return "primary";
  if (e === "graphrag") return "warning";
  if (e === "hybrid") return "danger";
  return "info";
}

// ---------- 图谱可视化 ----------
const graphVisible = ref(false);
const graphLoading = ref(false);
const graphStats = ref({ nodes: 0, edges: 0 });
const graphNodes = ref<any[]>([]);
const graphEdges = ref<any[]>([]);
const graphKbId = ref<number>();
const graphUsePreset = ref(false);
const graphLayout = ref("cose");
const physicsMode = ref(false);
const graphSearch = ref("");
const shortestMode = ref(false);
const graphStatsVisible = ref(false);
const edgeStyleVisible = ref(false);
const graphTheme = ref("default");
const nodeStyleVisible = ref(false);
const THEME_OPTIONS = [
  { value: "default", label: i18nT("ai_ontology.default") },
  { value: "ocean", label: i18nT("ai_ontology.ocean") },
  { value: "forest", label: i18nT("ai_ontology.forest") },
  { value: "sunset", label: i18nT("ai_ontology.sunset") },
  { value: "mono", label: i18nT("ai_ontology.mono") },
];
const nodeStyle = reactive({
  sizeMode: "weight" as "weight" | "fixed",
  fixedSize: 22,
  shapeMode: "type" as "type" | "uniform",
  uniformShape: "ellipse" as "ellipse" | "round-rectangle" | "diamond" | "circle",
  colorMode: "type" as "type" | "single",
  singleColor: "#4a86f7",
  labelSize: 12,
});
const edgeStyle = reactive({
  lineStyle: "solid" as "solid" | "dashed" | "dotted",
  curve: "bezier" as "bezier" | "straight" | "taxi",
  arrow: "triangle" as "triangle" | "vee" | "circle" | "none",
  widthMode: "fixed" as "weight" | "fixed",
  fixedWidth: 1.5,
  colorMode: "type" as "type" | "single",
  singleColor: "#a8abb3",
  label: "none" as "show" | "nondefault" | "hover" | "none",
  opacity: 0.55,
});
const graphStatsDetail = computed(() => {
  const typeCount: Record<string, number> = {};
  graphNodes.value.forEach((n: any) => {
    const t = n.etype || "keyword";
    typeCount[t] = (typeCount[t] || 0) + 1;
  });
  const relCount: Record<string, number> = {};
  graphEdges.value.forEach((e: any) => {
    const r = e.rtype || "related";
    relCount[r] = (relCount[r] || 0) + 1;
  });
  const nodes = graphNodes.value.length;
  const edges = graphEdges.value.length;
  return {
    nodes,
    edges,
    typeCount,
    relCount,
    avgDegree: nodes ? Math.round(((edges * 2) / nodes) * 10) / 10 : 0,
  };
});
function onGraphSearch() {
  graphCanvasRef.value?.search?.(graphSearch.value);
}
function onGraphPathFound(a: string, b: string, length: number) {
  if (length < 0) {
    ElMessage.info(i18nT("ai_ontology.noPathMsg", { a, b }));
  } else {
    ElMessage.success(i18nT("ai_ontology.shortestPathMsg", { a, b, length }));
  }
}
function typeLabel(t: string) {
  if (t === "annotation") return i18nT("ai_ontology.graphLegendAnnotLabel");
  if (t === "custom") return i18nT("ai_ontology.custom");
  if (t === "keyword") return i18nT("ai_ontology.keyword");
  return t;
}
// 连线模式：第一次点击记源节点，第二次点击记目标节点建边
const linkMode = ref(false);
const linkSource = ref<string | null>(null);
// 图形 ref（保存布局取节点坐标）
const graphFullscreenRef = ref<any>();
const graphSavingLayout = ref(false);
// 多选批量操作
const multiSelect = ref(false);
const selectedNames = ref<Set<string>>(new Set());
function toggleSelect(name: string) {
  const s = new Set(selectedNames.value);
  if (s.has(name)) s.delete(name);
  else s.add(name);
  selectedNames.value = s;
}
async function exportGraphImage() {
  let url = "";
  try {
    url = graphCanvasRef.value?.png?.() || graphFullscreenRef.value?.png?.() || "";
  } catch {
    url = "";
  }
  if (!url) {
    ElMessage.warning(i18nT("ai_ontology.chartNotReady"));
    return;
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = `${i18nT("ai_ontology.graphFilePrefix")}${graphKbId.value || ""}.png`;
  a.click();
  ElMessage.success(i18nT("ai_ontology.imageExported"));
}
async function batchDeleteNodes() {
  if (!graphKbId.value || !selectedNames.value.size) return;
  const ids = graphNodes.value.filter((n) => selectedNames.value.has(n.name)).map((n) => n.id);
  if (!ids.length) return;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.deleteNodesConfirm", { count: ids.length }),
      i18nT("ai_ontology.batchDelete"),
      {
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    );
  } catch {
    return;
  }
  try {
    await deleteAiKnowledgeGraphEntities(graphKbId.value, ids);
    selectedNames.value = new Set();
    ElMessage.success(i18nT("ai_ontology.batchDeleted"));
    await reloadGraph();
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}
const graphLegend = [
  { color: "#409eff", label: i18nT("ai_ontology.keyword") },
  { color: "#e6a23c", label: i18nT("ai_ontology.graphLegendAnnotLabel") },
  { color: "#67c23a", label: i18nT("ai_ontology.custom") },
  { color: "#909399", label: i18nT("ai_ontology.other") },
];
const relationTypes = ref<any[]>([]);
const rtypeOptions = computed(() => {
  const names = relationTypes.value.map((r: any) => r.name);
  return names.length
    ? names
    : [
        i18nT("ai_ontology.belongsTo"),
        i18nT("ai_ontology.contains"),
        i18nT("ai_ontology.dependencies"),
        i18nT("ai_ontology.related2"),
        i18nT("ai_ontology.reference"),
        i18nT("ai_ontology.locatedAt"),
        i18nT("ai_ontology.usedFor"),
        i18nT("ai_ontology.related"),
      ];
});
async function loadRelationTypes() {
  try {
    const r = await getAiRelationTypes();
    relationTypes.value = r.data?.data || [];
  } catch {
    relationTypes.value = [];
  }
}
// 关系类型模板管理
const relationTypeDialogVisible = ref(false);
const rtNewName = ref("");
function openRelationTypeDialog() {
  rtNewName.value = "";
  relationTypeDialogVisible.value = true;
}
async function addRt() {
  if (!rtNewName.value.trim()) return;
  try {
    await createAiRelationType({ name: rtNewName.value.trim() });
    rtNewName.value = "";
    ElMessage.success(i18nT("ai_ontology.relationTypeAdded"));
    await loadRelationTypes();
    await reloadGraph();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.addFailed"));
  }
}
async function delRt(row: any) {
  try {
    await deleteAiRelationType(row.id);
    ElMessage.success(i18nT("ai_ontology.deleted"));
    await loadRelationTypes();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}
// 图谱全屏
const graphFullscreenVisible = ref(false);
// 检索定位图谱命中节点
const highlightNames = ref<Set<string>>(new Set());
const graphHighlight = computed(() =>
  Array.from(new Set([...highlightNames.value, ...selectedNames.value]))
);
function locateInGraph(h: any) {
  if (!detailKb.value) return;
  const names = new Set<string>();
  const ent = h?.graph_entity;
  if (ent) names.add(ent);
  const q = detailQuery.value.trim();
  if (q) {
    for (const n of graphNodes.value) {
      if (n.name && n.name.includes(q)) names.add(n.name);
    }
  }
  if (!names.size) {
    ElMessage.info(i18nT("ai_ontology.noGraphNodeMatched"));
    return;
  }
  highlightNames.value = names;
  detailTab.value = "graph";
  reloadGraph();
}
async function loadGraph(g: any) {
  graphStats.value = { nodes: (g.nodes || []).length, edges: (g.edges || []).length };
  graphNodes.value = (g.nodes || []).map((n: any) => ({ ...n, id: n.id ?? n.name }));
  graphEdges.value = (g.edges || []).map((e: any, i: number) => ({
    ...e,
    id: e.id ?? `${e.source}_${e.target}_${i}`,
  }));
  graphUsePreset.value =
    graphNodes.value.length > 0 && graphNodes.value.every((n: any) => n.x != null && n.y != null);
  highlightNames.value = new Set();
}

async function openGraph(kb: any) {
  const kbId = kb?.id || selectedKb.value?.id;
  if (!kbId) return;
  selectedKb.value = kb;
  graphKbId.value = kbId;
  graphVisible.value = true;
  graphLoading.value = true;
  linkSource.value = null;
  try {
    const r = await getAiKnowledgeGraph(kbId);
    await loadGraph(r.data?.data || { nodes: [], edges: [] });
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.loadGraphFailed"));
  } finally {
    graphLoading.value = false;
  }
}
async function reloadGraph(hint?: string) {
  if (!graphKbId.value) return;
  try {
    const r = await getAiKnowledgeGraph(graphKbId.value);
    await loadGraph(r.data?.data || { nodes: [], edges: [] });
    if (hint) ElMessage.success(hint);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.refreshGraphFailed"));
  }
}
async function delGraphEntity(n: any) {
  if (!graphKbId.value) return;
  try {
    await deleteAiKnowledgeGraphEntities(graphKbId.value, [n.id]);
    await reloadGraph(i18nT("ai_ontology.entityDeleted"));
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}
// 图谱实体重命名
const renameEntityVisible = ref(false);
const renameForm = reactive<any>({
  id: null,
  name: "",
  etype: "keyword",
  weight: 1,
  description: "",
});
const renamingEntity = ref(false);
// 实体绑定分块
const entityBoundChunks = ref<any[]>([]);
const entityBindSel = ref<number[]>([]);
const bindingChunks = ref(false);
async function loadEntityChunks() {
  if (!graphKbId.value || !renameForm.id) return;
  try {
    const r = await getAiKnowledgeEntityChunks(graphKbId.value, renameForm.id);
    entityBoundChunks.value = r.data?.data || [];
  } catch {
    entityBoundChunks.value = [];
  }
}
async function bindChunks() {
  if (!graphKbId.value || !renameForm.id || !entityBindSel.value.length) return;
  bindingChunks.value = true;
  try {
    await bindAiKnowledgeEntityChunks(graphKbId.value, renameForm.id, entityBindSel.value);
    entityBindSel.value = [];
    ElMessage.success(i18nT("ai_ontology.chunkBound"));
    await loadEntityChunks();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.bindFailed"));
  } finally {
    bindingChunks.value = false;
  }
}
async function unbindChunk(c: any) {
  if (!graphKbId.value || !renameForm.id) return;
  try {
    await unbindAiKnowledgeEntityChunks(graphKbId.value, renameForm.id, [c.id]);
    ElMessage.success(i18nT("ai_ontology.unbound"));
    await loadEntityChunks();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.unbindFailed"));
  }
}
function openRenameEntity(n: any) {
  renameForm.id = n.id;
  renameForm.name = n.name;
  renameForm.etype = n.etype || "keyword";
  renameForm.weight = n.weight || 1;
  renameForm.description = n.description || "";
  renameEntityVisible.value = true;
  loadEntityChunks();
}
// 图谱关系编辑
const relEditVisible = ref(false);
const relEditForm = reactive<any>({
  id: null,
  source: "",
  target: "",
  weight: 1,
  rtype: "related",
});
const savingRel = ref(false);
async function saveRelEdit() {
  if (!graphKbId.value || !relEditForm.id) return;
  if (!relEditForm.source || !relEditForm.target) {
    ElMessage.warning(i18nT("ai_ontology.sourceTargetNotEmpty"));
    return;
  }
  savingRel.value = true;
  try {
    await updateAiKnowledgeGraphRelation(graphKbId.value, relEditForm.id, {
      source: relEditForm.source,
      target: relEditForm.target,
      weight: relEditForm.weight,
      rtype: relEditForm.rtype,
    });
    relEditVisible.value = false;
    await reloadGraph(i18nT("ai_ontology.relationUpdated"));
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.updateFailed"));
  } finally {
    savingRel.value = false;
  }
}
async function saveRenameEntity() {
  if (!graphKbId.value || !renameForm.id) return;
  if (!renameForm.name.trim()) {
    ElMessage.warning(i18nT("ai_ontology.entityNameCannotBeEmpty"));
    return;
  }
  renamingEntity.value = true;
  try {
    await updateAiKnowledgeGraphEntity(graphKbId.value, renameForm.id, {
      name: renameForm.name.trim(),
      etype: renameForm.etype,
      weight: renameForm.weight,
      description: renameForm.description,
    });
    renameEntityVisible.value = false;
    await reloadGraph(i18nT("ai_ontology.entityUpdatedWithRelationCascade"));
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.updateFailed"));
  } finally {
    renamingEntity.value = false;
  }
}
async function delGraphRelation(e: any) {
  if (!graphKbId.value) return;
  try {
    await deleteAiKnowledgeGraphRelations(graphKbId.value, [e.id]);
    await reloadGraph(i18nT("ai_ontology.relationDeleted"));
  } catch (err: any) {
    ElMessage.error(err?.message || i18nT("ai_ontology.deleteRelationFailed"));
  }
}

// ---------- 知识库详情抽屉 ----------
const detailVisible = ref(false);
const detailTab = ref("overview");
const detailKb = ref<any>();
const detailDesc = ref("");
const detailEnabled = ref(true);
const detailChunkCount = ref(0);
const detailGraphNodes = ref(0);
const detailGraphEdges = ref(0);
const detailDsCount = ref(0);
const rebuilding = ref(false);
const detailIngest = reactive<any>({
  file_name: "",
  content: "",
  strategy: "fixed",
  chunk_size: 500,
  overlap: 50,
});
const detailIngesting = ref(false);
const detailChunks = ref<any[]>([]);

function exportChunksCsv() {
  const cols = ["chunk_index", "file_name", "content", "annotations"];
  const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = detailChunks.value.map((c: any) => [
    c.chunk_index,
    c.file_name,
    c.content,
    JSON.stringify(c.annotations || []),
  ]);
  const csv =
    "\ufeff" + cols.join(",") + "\n" + rows.map((r: any) => r.map(esc).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${i18nT("ai_ontology.kbChunksFilePrefix")}${detailKb.value?.name || ""}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success(i18nT("ai_ontology.exportChunksMsg", { count: rows.length }));
}
const detailSearchMode = ref("hybrid");
const detailQuery = ref("");
const detailSearching = ref(false);
const detailSearchResults = ref<any[]>([]);
const detailVectorWeight = ref(0.5);
const detailFulltextWeight = ref(0.5);
const detailMinScore = ref(0);
const detailFileFilter = ref("");
const detailUseRerank = ref(true);
const detailRewrite = ref("off");
function rerankLabel(status?: string) {
  if (status === "applied") return i18nT("ai_ontology.reranked");
  if (status === "skipped") return i18nT("ai_ontology.skipped");
  return i18nT("ai_ontology.disabled");
}

async function loadDetailStats(kbId: number) {
  const [chunksR, graphR] = await Promise.all([
    getAiKnowledgeChunks(kbId).catch(() => ({ data: { data: [] } })),
    getAiKnowledgeGraph(kbId).catch(() => ({ data: { data: { nodes: [], edges: [] } } })),
  ]);
  detailChunks.value = chunksR.data?.data || [];
  detailChunkCount.value = detailChunks.value.length;
  const g = graphR.data?.data || {};
  detailGraphNodes.value = (g.nodes || []).length;
  detailGraphEdges.value = (g.edges || []).length;
  detailDsCount.value = datasources.value.filter((d: any) => d.knowledge_base_id === kbId).length;
}

async function openDetail(row: any) {
  detailKb.value = row;
  detailDesc.value = row.description || "";
  detailEnabled.value = !!row.enabled;
  detailTab.value = "overview";
  detailVisible.value = true;
  await loadDetailStats(row.id);
  // 预加载图谱到共享状态（图谱 tab 内嵌可视化）
  graphKbId.value = row.id;
  graphLoading.value = true;
  try {
    const r = await getAiKnowledgeGraph(row.id);
    await loadGraph(r.data?.data || { nodes: [], edges: [] });
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.loadGraphFailed"));
  } finally {
    graphLoading.value = false;
  }
  // 预加载标注台账
  suggestList.value = [];
  suggestHint.value = "";
  loadLogs();
  loadStats();
  loadDocs();
  loadEvalSets();
  loadEvalRuns();
}

async function saveDetailOverview() {
  if (!detailKb.value) return;
  try {
    await updateAiKnowledge(detailKb.value.id, {
      description: detailDesc.value,
      enabled: detailEnabled.value,
    });
    ElMessage.success(i18nT("ai_ontology.saved"));
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.saveFailed"));
  }
}

async function rebuildDetail() {
  if (!detailKb.value) return;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.rebuildKbConfirm", { name: detailKb.value.name }),
      i18nT("ai_ontology.rebuildIndexConfirm"),
      {
        confirmButtonText: i18nT("ai_ontology.rebuild"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    );
  } catch {
    return;
  }
  rebuilding.value = true;
  try {
    const r = await rebuildAiKnowledge(detailKb.value.id);
    ElMessage.success(i18nT("ai_ontology.rebuildDoneMsg", { count: r.data?.data?.chunks || 0 }));
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.rebuildFailed"));
  } finally {
    rebuilding.value = false;
  }
}

async function doDetailIngest() {
  if (!detailKb.value || !detailIngest.content.trim()) {
    ElMessage.warning(i18nT("ai_ontology.pleasePasteTextToIngest"));
    return;
  }
  detailIngesting.value = true;
  try {
    const r = await ingestAiKnowledge(detailKb.value.id, { ...detailIngest });
    ElMessage.success(i18nT("ai_ontology.ingestSuccessMsg", { count: r.data?.data?.chunks || 0 }));
    detailIngest.content = "";
    await loadDetailStats(detailKb.value.id);
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.ingestFailed"));
  } finally {
    detailIngesting.value = false;
  }
}

async function deleteChunkFromDetail(row: any) {
  if (!detailKb.value) return;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.deleteThisChunkItsVectorAndBindingsAreRemovedAndCannotBeRecovered"),
      i18nT("ai_ontology.deleteChunk"),
      {
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    );
  } catch {
    return;
  }
  await deleteAiKnowledgeChunk(detailKb.value.id, row.id);
  ElMessage.success(i18nT("ai_ontology.chunkDeleted"));
  await loadDetailStats(detailKb.value.id);
}

// 编辑分块
const chunkEditVisible = ref(false);
const chunkEditContent = ref("");
const chunkEditId = ref<number>();
const chunkEditing = ref(false);
function openChunkEdit(row: any) {
  chunkEditId.value = row.id;
  chunkEditContent.value = row.content;
  chunkEditVisible.value = true;
}
async function saveChunkEdit() {
  if (!detailKb.value || !chunkEditId.value) return;
  if (!chunkEditContent.value.trim()) {
    ElMessage.warning(i18nT("ai_ontology.contentCannotBeEmpty"));
    return;
  }
  chunkEditing.value = true;
  try {
    await updateAiKnowledgeChunk(detailKb.value.id, chunkEditId.value, chunkEditContent.value);
    ElMessage.success(i18nT("ai_ontology.savedAndReVectorized"));
    chunkEditVisible.value = false;
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.saveFailed"));
  } finally {
    chunkEditing.value = false;
  }
}

// ---------- 分块标注 ----------
const annotationVisible = ref(false);
const annotChunk = ref<any>();
const annotList = ref<any[]>([]);
const annotText = ref("");
const annotKind = ref("alias");
const annotating = ref(false);
function annotKindLabel(k: string) {
  if (k === "alias") return i18nT("ai_ontology.alias");
  if (k === "anchor") return i18nT("ai_ontology.anchor");
  if (k === "note") return i18nT("ai_ontology.remark");
  return k;
}
function sourceLabel(k: string) {
  if (k === "manual") return i18nT("ai_ontology.manual");
  if (k === "search") return i18nT("ai_ontology.search2");
  if (k === "auto") return i18nT("ai_ontology.auto");
  if (k === "graph") return i18nT("ai_ontology.graph2");
  return k;
}
function openAnnotation(row: any) {
  annotChunk.value = row;
  annotList.value = (row.annotations || []).map((a: any) => ({ ...a }));
  annotText.value = "";
  annotKind.value = "alias";
  annotationVisible.value = true;
}
async function addAnnotation() {
  if (!detailKb.value || !annotChunk.value || !annotText.value.trim()) {
    ElMessage.warning(i18nT("ai_ontology.pleaseEnterAnnotationText"));
    return;
  }
  annotating.value = true;
  try {
    const r = await addAiKnowledgeChunkAnnotation(
      detailKb.value.id,
      annotChunk.value.id,
      annotText.value.trim(),
      annotKind.value,
      annotChunk.value._query,
      annotChunk.value._source || "manual"
    );
    annotList.value = r.data?.data?.annotations || annotList.value;
    annotText.value = "";
    ElMessage.success(i18nT("ai_ontology.annotationAddedAndIndexUpdated"));
    await loadDetailStats(detailKb.value.id);
    await loadLogs();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.addFailed"));
  } finally {
    annotating.value = false;
  }
}
async function removeAnnotation(index: number) {
  if (!detailKb.value || !annotChunk.value) return;
  try {
    const r = await removeAiKnowledgeChunkAnnotation(detailKb.value.id, annotChunk.value.id, index);
    annotList.value = r.data?.data?.annotations || annotList.value;
    ElMessage.success(i18nT("ai_ontology.annotationDeletedAndIndexUpdated"));
    await loadDetailStats(detailKb.value.id);
    await loadLogs();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}

// ---------- 检索失败建议标注 ----------
const suggestList = ref<any[]>([]);
const suggestLoading = ref(false);
const suggestHint = ref("");
async function loadSuggest() {
  if (!detailKb.value || !detailQuery.value.trim()) return;
  suggestLoading.value = true;
  suggestHint.value = "";
  try {
    const r = await suggestAiKnowledgeAnnotate(detailKb.value.id, detailQuery.value, 8);
    suggestList.value = r.data?.data || [];
    const un = suggestList.value.filter((s) => !s.hit);
    suggestHint.value = un.length
      ? i18nT("ai_ontology.suggestRelatedMsg", {
          count: suggestList.value.length,
          unhit: un.length,
        })
      : i18nT("ai_ontology.suggestRelatedHitMsg");
  } catch (e: any) {
    suggestList.value = [];
    ElMessage.error(e?.message || i18nT("ai_ontology.suggestFailed"));
  } finally {
    suggestLoading.value = false;
  }
}

// ---------- 标注台账 ----------
const annotationLogs = ref<any[]>([]);
const loadingLogs = ref(false);
const logSourceFilter = ref("");
const logKindFilter = ref("");
const filteredLogs = computed(() => {
  return annotationLogs.value.filter((l: any) => {
    if (logSourceFilter.value && (l.source || "manual") !== logSourceFilter.value) return false;
    if (logKindFilter.value && (l.kind || "alias") !== logKindFilter.value) return false;
    return true;
  });
});
const statAdd = computed(() => annotationLogs.value.filter((l: any) => l.action === "add").length);
const statRemove = computed(
  () => annotationLogs.value.filter((l: any) => l.action === "remove").length
);
async function loadLogs() {
  if (!detailKb.value) return;
  loadingLogs.value = true;
  try {
    const r = await getAiKnowledgeAnnotationLogs(detailKb.value.id);
    annotationLogs.value = r.data?.data || [];
  } catch {
    annotationLogs.value = [];
  } finally {
    loadingLogs.value = false;
  }
}

// ---------- 文档管理（wikiLLM/ima 式） ----------
const documents = ref<any[]>([]);
const loadingDocs = ref(false);
const uploadingDoc = ref(false);
const docChunkSize = ref(500);
const docOverlap = ref(50);
const docStrategy = ref("fixed");
const docUseOcr = ref(true);
const docTaskTimers = new Map<number, ReturnType<typeof setInterval>>();
function taskStatusType(status?: string): "" | "success" | "exception" | "warning" {
  if (status === "failed") return "exception";
  if (status === "succeeded") return "success";
  if (status === "canceled") return "warning";
  return "";
}
function attachDocTask(docId: number, taskId?: number) {
  if (!taskId) return;
  const row = documents.value.find((d) => d.id === docId);
  if (row) row.task = { id: taskId, progress: 0, status: "pending" };
  const old = docTaskTimers.get(docId);
  if (old) clearInterval(old);
  const timer = setInterval(async () => {
    try {
      const r = await getAiRagTask(taskId);
      const task = r.data?.data;
      const target = documents.value.find((d) => d.id === docId);
      if (task && target) target.task = task;
      if (task && ["succeeded", "failed", "canceled"].includes(task.status)) {
        clearInterval(timer);
        docTaskTimers.delete(docId);
        await loadDocs();
        if (detailKb.value) await loadDetailStats(detailKb.value.id);
      }
    } catch {
      clearInterval(timer);
      docTaskTimers.delete(docId);
    }
  }, 1000);
  docTaskTimers.set(docId, timer);
}
function fmtSize(n: number) {
  if (!n) return "0B";
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}
async function loadDocs() {
  if (!detailKb.value) return;
  loadingDocs.value = true;
  try {
    const r = await getAiKnowledgeDocuments(detailKb.value.id);
    documents.value = r.data?.data || [];
  } catch {
    documents.value = [];
  } finally {
    loadingDocs.value = false;
  }
}
async function onUploadFile(file: any) {
  if (!detailKb.value) return;
  uploadingDoc.value = true;
  try {
    const r = await uploadAiKnowledgeDocument(
      detailKb.value.id,
      file.raw,
      docChunkSize.value,
      docOverlap.value,
      docStrategy.value,
      docUseOcr.value
    );
    const data = r.data?.data || {};
    ElMessage.success(i18nT("ai_ontology.fileUploadedMsg", { name: file.name }));
    await loadDocs();
    attachDocTask(data.id, data.task_id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.uploadFailed"));
  } finally {
    uploadingDoc.value = false;
  }
}
async function deleteDoc(row: any) {
  if (!detailKb.value) return;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.deleteDocConfirm", { name: row.name }),
      i18nT("ai_ontology.deleteDocument"),
      {
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    );
  } catch {
    return;
  }
  try {
    await deleteAiKnowledgeDocument(detailKb.value.id, row.id);
    ElMessage.success(i18nT("ai_ontology.deleted"));
    await loadDocs();
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}
const selectedDocIds = ref<number[]>([]);
async function batchDeleteDocs() {
  if (!detailKb.value || !selectedDocIds.value.length) return;
  try {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.batchDeleteDocsConfirm", { count: selectedDocIds.value.length }),
      i18nT("ai_ontology.batchDeleteDocuments"),
      {
        confirmButtonText: i18nT("ai_ontology.delete2"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    );
  } catch {
    return;
  }
  try {
    for (const id of selectedDocIds.value) {
      await deleteAiKnowledgeDocument(detailKb.value.id, id);
    }
    ElMessage.success(i18nT("ai_ontology.deleteDocsMsg", { count: selectedDocIds.value.length }));
    selectedDocIds.value = [];
    await loadDocs();
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.deleteFailed"));
  }
}
// 预览 / 重建
const docPreviewVisible = ref(false);
const docPreviewName = ref("");
const docPreviewContent = ref("");
const docPreviewLoading = ref(false);
const docPreviewKind = ref("text");
const docPreviewPdfUrl = ref("");
const docPreviewHtml = ref("");
async function previewDoc(row: any) {
  if (!detailKb.value) return;
  docPreviewVisible.value = true;
  docPreviewName.value = row.name;
  docPreviewContent.value = "";
  docPreviewHtml.value = "";
  docPreviewPdfUrl.value = "";
  docPreviewLoading.value = true;
  const ft = (row.file_type || "").toLowerCase();
  try {
    if (ft === "pdf" || ft === "docx") {
      docPreviewKind.value = ft;
      const r: any = await downloadAiKnowledgeDocument(detailKb.value.id, row.id);
      const blob = r.data instanceof Blob ? r.data : new Blob([r.data]);
      const ab = await blob.arrayBuffer();
      if (ft === "pdf") {
        docPreviewPdfUrl.value = URL.createObjectURL(blob);
      } else {
        const res = await mammoth.convertToHtml({ arrayBuffer: ab });
        docPreviewHtml.value = res.value || "";
      }
    } else {
      docPreviewKind.value = "text";
      const r = await getAiKnowledgeDocumentContent(detailKb.value.id, row.id);
      docPreviewContent.value = r.data?.data?.content || "";
    }
  } catch (e: any) {
    docPreviewKind.value = "text";
    docPreviewContent.value = "";
    ElMessage.error(e?.message || i18nT("ai_ontology.previewFailed"));
  } finally {
    docPreviewLoading.value = false;
  }
}
async function reparseDoc(row: any) {
  if (!detailKb.value) return;
  try {
    const r = await reparseAiKnowledgeDocument(detailKb.value.id, row.id);
    const data = r.data?.data || {};
    ElMessage.success(i18nT("ai_ontology.reparseStarted"));
    await loadDocs();
    attachDocTask(row.id, data.task_id);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.rebuildFailed"));
  }
}
async function downloadDoc(row: any) {
  if (!detailKb.value) return;
  // 优先使用 RustFS 预签名链接（原文档存储位置）
  if (row.rustfs_url) {
    window.open(row.rustfs_url, "_blank");
    return;
  }
  try {
    const r: any = await downloadAiKnowledgeDocument(detailKb.value.id, row.id);
    const blob = r.data instanceof Blob ? r.data : new Blob([r.data]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = row.name || "document";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.downloadFailed"));
  }
}
const faqLoading = ref(false);
const faqText = ref("");
async function exportFaq() {
  if (!detailKb.value) return;
  faqLoading.value = true;
  try {
    const r = await getAiKnowledgeFaq(detailKb.value.id, "md");
    const md = r.data?.data?.markdown || "";
    faqText.value = md;
    // 下载 md
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${i18nT("ai_ontology.kbFaqFilePrefix")}${detailKb.value.name || ""}.md`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success(i18nT("ai_ontology.exportFaqMsg", { count: r.data?.data?.count || 0 }));
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.exportFailed"));
  } finally {
    faqLoading.value = false;
  }
}
// 引用溯源问答（跨文档交叉问答 → 带角标引用）
const qaQuery = ref("");
const qaSearching = ref(false);
const qaAnswer = ref("");
const qaRefs = ref<any[]>([]);
const qaCiteVisible = ref(false);
const qaCite = ref<any>(null);
// 把回答中 [n] 渲染成可点击角标
const qaAnswerHtml = computed(() => {
  let s = qaAnswer.value || "";
  s = escapeHtml(s);
  s = s.replace(/\[(\d+)\]/g, '<span class="qa-cite" data-cite="$1">[$1]</span>');
  return s.replace(/\n/g, "<br />");
});
function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
async function doQaSearch() {
  if (!detailKb.value || !qaQuery.value.trim()) return;
  qaSearching.value = true;
  try {
    const r = await askAiKnowledge(detailKb.value.id, qaQuery.value, 6, "hybrid");
    const d = r.data?.data || {};
    qaAnswer.value = d.answer || "";
    qaRefs.value = d.references || [];
    if (!qaRefs.value.length) {
      ElMessage.info(i18nT("ai_ontology.noResultsTryAnotherPhrasingOrAnnotateChunks"));
    }
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.qAFailed"));
  } finally {
    qaSearching.value = false;
  }
}
function showCite(idx: string | number) {
  const i = Number(idx) - 1;
  const ref = qaRefs.value[i];
  if (!ref) return;
  qaCite.value = ref;
  qaCiteVisible.value = true;
}
function onQaClick(ev: Event) {
  const t = ev.target as HTMLElement;
  if (t.classList.contains("qa-cite")) {
    showCite(t.getAttribute("data-cite") || "");
  }
}
function openRustfs(url: string) {
  window.open(url, "_blank");
}

// ---------- 检索统计 ----------
const statsDays = ref(30);
const loadingStats = ref(false);
const searchStats = ref<any>({
  total: 0,
  hit_rate: 0,
  avg_hits: 0,
  zero_hit_count: 0,
  engine_dist: {},
  trend: [],
});
async function loadStats() {
  if (!detailKb.value) return;
  loadingStats.value = true;
  try {
    const r = await getAiKnowledgeSearchStats(detailKb.value.id, statsDays.value);
    searchStats.value = r.data?.data || searchStats.value;
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.loadStatsFailed"));
  } finally {
    loadingStats.value = false;
  }
}

// ---------- 图谱节点点击 → 关联分块 ----------
const entityChunksVisible = ref(false);
const entityChunksName = ref("");
const entityChunksList = ref<any[]>([]);
const entityChunksLoading = ref(false);

// ---------- 图上右键菜单（直接在图里编辑） ----------
const ctxMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  kind: "blank",
  node: null as any,
  edge: null as any,
});
// Cytoscape 事件适配
function onGraphLayoutChange(name: string) {
  graphCanvasRef.value?.setLayout?.(name);
}
function onGraphLinkDraw(source: string, target: string) {
  if (!graphKbId.value || !source || !target || source === target) return;
  try {
    createAiKnowledgeGraphRelation(graphKbId.value, {
      source,
      target,
      rtype: "related",
      weight: 1,
    }).then(() => {
      ElMessage.success(i18nT("ai_ontology.linked"));
      reloadGraph();
    });
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.linkFailed"));
  }
}
function onGraphNodeTap(name: string) {
  closeCtxMenu();
  if (!graphKbId.value) return;
  if (multiSelect.value) {
    toggleSelect(name);
    return;
  }
  if (linkMode.value) {
    if (!linkSource.value) {
      linkSource.value = name;
      ElMessage.info(i18nT("ai_ontology.linkModeNodeHint", { name }));
    } else if (linkSource.value !== name) {
      const src = linkSource.value;
      linkSource.value = null;
      relAddForm.source = src;
      relAddForm.target = name;
      relAddForm.rtype = "related";
      relAddForm.weight = 1;
      relAddVisible.value = true;
    }
    return;
  }
  // 普通单击：仅选中（cytoscape 高亮邻接），不弹窗
}
function onGraphNodeDbltap(name: string) {
  const node = graphNodes.value.find((n) => n.name === name);
  if (!node || !graphKbId.value) return;
  entityChunksName.value = name;
  entityChunksVisible.value = true;
  entityChunksLoading.value = true;
  getAiKnowledgeEntityChunks(graphKbId.value, node.id)
    .then((r: any) => {
      entityChunksList.value = r.data?.data || [];
    })
    .catch(() => {
      entityChunksList.value = [];
    })
    .finally(() => {
      entityChunksLoading.value = false;
    });
}
function onGraphNodeCtx(name: string, x: number, y: number) {
  ctxMenu.kind = "node";
  ctxMenu.node = name;
  ctxMenu.edge = null;
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function onGraphEdgeCtx(source: string, target: string, x: number, y: number) {
  ctxMenu.kind = "edge";
  ctxMenu.node = null;
  ctxMenu.edge = { source, target };
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function onGraphBlankCtx(x: number, y: number) {
  ctxMenu.kind = "blank";
  ctxMenu.node = null;
  ctxMenu.edge = null;
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function closeCtxMenu() {
  ctxMenu.visible = false;
}
function findNodeByName(name: string) {
  return graphNodes.value.find((n) => n.name === name);
}
// 保存 / 重新布局
function onGraphLayout(items: { id: number; x: number; y: number }[]) {
  if (!graphKbId.value || !items.length) return;
  saveAiKnowledgeGraphLayout(graphKbId.value, items)
    .then(() => ElMessage.success(i18nT("ai_ontology.saveLayoutMsg", { count: items.length })))
    .catch(() => ElMessage.error(i18nT("ai_ontology.saveLayoutFailed")));
}
async function saveLayout() {
  if (!graphKbId.value) return;
  graphSavingLayout.value = true;
  try {
    graphCanvasRef.value?.emitPositions?.();
  } finally {
    setTimeout(() => {
      graphSavingLayout.value = false;
    }, 300);
  }
}
async function relayoutGraph() {
  if (!graphKbId.value) return;
  try {
    await clearAiKnowledgeGraphLayout(graphKbId.value);
    await reloadGraph(i18nT("ai_ontology.layoutMemoryClearedReLayoutAutomatically"));
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.reLayoutFailed"));
  }
}
// 右键：新建节点
const nodeNewVisible = ref(false);
const nodeNewForm = reactive<any>({ name: "", etype: "keyword", weight: 1, description: "" });
const addingNode = ref(false);
function ctxNewNode() {
  closeCtxMenu();
  Object.assign(nodeNewForm, { name: "", etype: "keyword", weight: 1, description: "" });
  nodeNewVisible.value = true;
}
async function saveNewNode() {
  if (!graphKbId.value || !nodeNewForm.name.trim()) return;
  addingNode.value = true;
  try {
    await createAiKnowledgeGraphEntity(graphKbId.value, {
      name: nodeNewForm.name.trim(),
      etype: nodeNewForm.etype,
      weight: nodeNewForm.weight,
      description: nodeNewForm.description,
    });
    nodeNewVisible.value = false;
    ElMessage.success(i18nT("ai_ontology.nodeCreated"));
    await reloadGraph();
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.newFailed"));
  } finally {
    addingNode.value = false;
  }
}
// 右键：编辑节点属性
function findEdgeById(s: string, t: string) {
  return graphEdges.value.find((e) => e.source === s && e.target === t);
}
function ctxEditNode() {
  closeCtxMenu();
  const n = findNodeByName(ctxMenu.node);
  if (n) openRenameEntity(n);
}
// 右键：绑定分块（编辑对话框内）
function ctxBindNode() {
  ctxEditNode();
}
// 右键：添加关系
const relAddVisible = ref(false);
const relAddForm = reactive<any>({ source: "", target: "", rtype: "related", weight: 1 });
const addingRel = ref(false);
function openAddRel() {
  if (!graphKbId.value) return;
  relAddForm.source = "";
  relAddForm.target = "";
  relAddForm.rtype = "related";
  relAddForm.weight = 1;
  relAddVisible.value = true;
}
function ctxAddRel() {
  closeCtxMenu();
  const n = findNodeByName(ctxMenu.node);
  if (!n) return;
  relAddForm.source = n.name;
  relAddForm.target = "";
  relAddForm.rtype = "related";
  relAddForm.weight = 1;
  relAddVisible.value = true;
}
async function saveAddRel() {
  if (!graphKbId.value || !relAddForm.source || !relAddForm.target) return;
  addingRel.value = true;
  try {
    await createAiKnowledgeGraphRelation(graphKbId.value, {
      source: relAddForm.source,
      target: relAddForm.target,
      rtype: relAddForm.rtype,
      weight: relAddForm.weight,
    });
    relAddVisible.value = false;
    ElMessage.success(i18nT("ai_ontology.relationAdded"));
    await reloadGraph();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.addFailed"));
  } finally {
    addingRel.value = false;
  }
}
// 右键：删除节点 / 关系
function ctxDelNode() {
  closeCtxMenu();
  const n = findNodeByName(ctxMenu.node);
  if (n) delGraphEntity(n);
}
function ctxEditRel() {
  closeCtxMenu();
  const e = findEdgeById(ctxMenu.edge?.source, ctxMenu.edge?.target);
  if (!e) return;
  relEditForm.id = e.id;
  relEditForm.source = e.source;
  relEditForm.target = e.target;
  relEditForm.weight = e.weight || 1;
  relEditForm.rtype = e.rtype || "related";
  relEditVisible.value = true;
}
function ctxDelRel() {
  closeCtxMenu();
  const e = findEdgeById(ctxMenu.edge?.source, ctxMenu.edge?.target);
  if (e) delGraphRelation(e);
}

async function doDetailSearch() {
  if (!detailKb.value || !detailQuery.value.trim()) return;
  detailSearching.value = true;
  try {
    const r = await searchAiKnowledge(
      detailKb.value.id,
      detailQuery.value,
      10,
      true,
      detailSearchMode.value,
      detailVectorWeight.value,
      detailFulltextWeight.value,
      {
        min_score: detailMinScore.value,
        use_rerank: detailUseRerank.value,
        rewrite: detailRewrite.value,
        filters: detailFileFilter.value.trim()
          ? { file_name: detailFileFilter.value.trim() }
          : null,
      }
    );
    detailSearchResults.value = r.data?.data || [];
    // 检索后自动推测相关分块（若未命中/少命中则提示可标注）
    if (detailSearchResults.value.length < 10) {
      await loadSuggest().catch(() => {});
    }
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.searchFailed"));
  } finally {
    detailSearching.value = false;
  }
}

function highlight(text: string, q: string): string {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const et = esc(text || "");
  const qq = (q || "").trim();
  if (!qq) return et;
  const escq = esc(qq).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return et.replace(new RegExp(`(${escq})`, "gi"), "<mark>$1</mark>");
}

// ---------- 评测 ----------
const evalSets = ref<any[]>([]);
const evalSetId = ref<number | undefined>(undefined);
const evalRuns = ref<any[]>([]);
const evalRunning = ref(false);
const evalTask = ref<any>(null);
const evalConfig = reactive({ top_k: 5, use_rerank: true, mode: "hybrid", min_score: 0 });
let evalTimer: ReturnType<typeof setInterval> | null = null;

function metricPct(v?: number) {
  if (v === undefined || v === null) return "—";
  return `${(Number(v) * 100).toFixed(1)}%`;
}
function evalConfigLabel(cfg: any) {
  if (!cfg) return "—";
  const parts = [`mode=${cfg.mode || "hybrid"}`, `top_k=${cfg.top_k ?? 5}`];
  parts.push(`rerank=${cfg.use_rerank ? "on" : "off"}`);
  if (cfg.min_score) parts.push(`min_score=${cfg.min_score}`);
  return parts.join(" · ");
}
async function loadEvalSets() {
  try {
    const r = await getAiEvalSets();
    evalSets.value = r.data?.data || [];
    if (!evalSetId.value && evalSets.value.length) {
      evalSetId.value = evalSets.value[0].id;
    }
  } catch {
    evalSets.value = [];
  }
}
async function loadEvalRuns() {
  if (!detailKb.value) return;
  try {
    const r = await getAiEvalRuns(detailKb.value.id);
    evalRuns.value = r.data?.data || [];
  } catch {
    evalRuns.value = [];
  }
}
async function startEval() {
  if (!detailKb.value) return;
  if (!evalSetId.value) {
    ElMessage.warning(i18nT("ai_ontology.pleaseCreateAndSelectAnEvalSetFirst"));
    return;
  }
  evalRunning.value = true;
  try {
    const r = await runAiEval(detailKb.value.id, {
      set_id: evalSetId.value,
      config: { ...evalConfig },
    });
    const taskId = r.data?.data?.task_id;
    evalTask.value = { id: taskId, progress: 0, status: "pending" };
    await loadEvalRuns();
    if (evalTimer) clearInterval(evalTimer);
    evalTimer = setInterval(async () => {
      try {
        const t = await getAiRagTask(taskId);
        const task = t.data?.data;
        if (task) evalTask.value = task;
        if (task && ["succeeded", "failed", "canceled"].includes(task.status)) {
          if (evalTimer) clearInterval(evalTimer);
          evalTimer = null;
          await loadEvalRuns();
          if (task.status === "succeeded") ElMessage.success(i18nT("ai_ontology.evalComplete"));
          else ElMessage.error(task.error || i18nT("ai_ontology.evalFailed"));
        }
      } catch {
        if (evalTimer) clearInterval(evalTimer);
        evalTimer = null;
      }
    }, 1500);
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.runEvalFailed"));
  } finally {
    evalRunning.value = false;
  }
}
onUnmounted(() => {
  docTaskTimers.forEach((timer) => clearInterval(timer));
  docTaskTimers.clear();
  if (evalTimer) clearInterval(evalTimer);
  evalTimer = null;
});

// ---------- 分块 ----------
const chunksVisible = ref(false);
const loadingChunks = ref(false);
const chunksTarget = ref<any>();
const chunks = ref<any[]>([]);

async function openChunks(kb: any) {
  chunksTarget.value = kb;
  chunksVisible.value = true;
  loadingChunks.value = true;
  try {
    const r = await getAiKnowledgeChunks(kb.id);
    chunks.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.loadChunkFailed"));
  } finally {
    loadingChunks.value = false;
  }
}

function deleteChunk(row: any) {
  ElMessageBox.confirm(
    i18nT("ai_ontology.deleteThisChunkThisCannotBeUndone"),
    i18nT("ai_ontology.deleteConfirm"),
    {
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      await deleteAiKnowledgeChunk(chunksTarget.value.id, row.id);
      ElMessage.success(i18nT("ai_ontology.deleted2"));
      openChunks(chunksTarget.value);
    })
    .catch(() => {
      /* 取消 */
    });
}

// ---------- 数据源 CRUD ----------
const dsDialogVisible = ref(false);
const savingDs = ref(false);
const editingDs = ref<any>();
const dsForm = reactive<any>({});

function openDsDialog(d?: any) {
  editingDs.value = d || undefined;
  if (d) {
    Object.assign(dsForm, {
      ...d,
      api_config: d.api_config || { method: "GET", data_path: "data" },
    });
  } else {
    Object.assign(dsForm, {
      name: "",
      ds_type: "db",
      dialect: "postgresql",
      uri: "",
      api_config: { method: "GET", data_path: "data" },
      knowledge_base_id: null,
      enabled: true,
    });
  }
  dsDialogVisible.value = true;
}

async function saveDs() {
  if (!dsForm.name) {
    ElMessage.warning(i18nT("ai_ontology.pleaseEnterDataSourceName"));
    return;
  }
  savingDs.value = true;
  try {
    const payload: any = {
      name: dsForm.name,
      ds_type: dsForm.ds_type,
      dialect: dsForm.ds_type === "db" ? dsForm.dialect : null,
      uri: dsForm.uri,
      api_config: dsForm.ds_type === "api" ? dsForm.api_config : null,
      knowledge_base_id: dsForm.knowledge_base_id || null,
      enabled: dsForm.enabled,
    };
    if (editingDs.value) {
      await updateAiDatasource(editingDs.value.id, payload);
    } else {
      await createAiDatasource(payload);
    }
    ElMessage.success(i18nT("ai_ontology.saved2"));
    dsDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.saveFailed"));
  } finally {
    savingDs.value = false;
  }
}

function deleteDatasources(row: any) {
  ElMessageBox.confirm(
    i18nT("ai_ontology.deleteDsConfirm", { name: row.name }),
    i18nT("ai_ontology.deleteConfirm"),
    {
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      await deleteAiDatasource([row.id]);
      ElMessage.success(i18nT("ai_ontology.deleted2"));
      if (selectedDs.value?.id === row.id) selectedDs.value = undefined;
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
}

// ---------- 测试 / 同步 ----------
const dsTestVisible = ref(false);
const dsTestResult = ref<any>({});
async function testDs(row: any) {
  try {
    const r = await testAiDatasource(row.id);
    dsTestResult.value = r.data?.data || {};
  } catch (e: any) {
    dsTestResult.value = { ok: false, message: e?.message || i18nT("ai_ontology.testFailed") };
  }
  dsTestVisible.value = true;
}

function syncDs(row: any) {
  if (row.ds_type === "db") {
    ElMessageBox.prompt(i18nT("ai_ontology.syncPromptLabel"), i18nT("ai_ontology.syncIngest"), {
      confirmButtonText: i18nT("ai_ontology.sync"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
      inputPlaceholder: i18nT("ai_ontology.table"),
    })
      .then(async ({ value }: { value: string }) => {
        if (!value?.trim()) return;
        await doSync(row, { table: value.trim() });
      })
      .catch(() => {
        /* 取消 */
      });
  } else {
    ElMessageBox.confirm(
      i18nT("ai_ontology.syncDsConfirm", { name: row.name }),
      i18nT("ai_ontology.syncConfirm"),
      {
        confirmButtonText: i18nT("ai_ontology.sync"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
        type: "warning",
      }
    )
      .then(async () => {
        await doSync(row, {});
      })
      .catch(() => {
        /* 取消 */
      });
  }
}

async function doSync(row: any, extra: any) {
  try {
    const r = await syncAiDatasource(row.id, { limit: 50, ...extra });
    const d = r.data?.data || {};
    ElMessage.success(
      i18nT("ai_ontology.syncDoneMsg", { rows: d.rows || 0, chunks: d.chunks || 0 })
    );
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || i18nT("ai_ontology.syncFailed"));
  }
}

onMounted(() => {
  loadData();
  // 点击任意处关闭图上右键菜单
  document.addEventListener("click", () => {
    if (ctxMenu.visible) ctxMenu.visible = false;
  });
});
</script>

<style scoped lang="scss">
.ai-knowledge-page {
  height: 100%;
  overflow: auto;
}

.kb-tabs-card {
  .kb-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;
  }

  /* 工具栏右侧：搜索 + 刷新（与系统管理一致） */
  .kb-toolbar__right {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-left: auto;
  }
}

.search-hit {
  padding: 10px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;

  .search-hit__meta {
    display: flex;
    justify-content: space-between;
    margin-bottom: 6px;
  }

  .search-hit__file {
    font-size: 12px;
    color: var(--el-text-color-regular);
  }

  .search-hit__score {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .search-hit__content {
    font-size: var(--el-font-size-base);
    line-height: 1.6;
    color: var(--el-text-color-regular);

    mark {
      padding: 0 2px;
      color: var(--el-color-warning-dark-2);
      background: var(--el-color-warning-light-7);
      border-radius: 2px;
    }
  }
}

.chunk-content {
  max-height: 60px;
  overflow: hidden;
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>

<style lang="scss">
.kb-opt-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.search-hit__score {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.graph-dialog {
  width: 100%;
  height: 480px;
}

.detail-tabs {
  .ov-stats {
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
  }
  .ov-form {
    max-width: 520px;
  }
  .dt-search {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
  .dt-weights {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;

    .dt-weight-label {
      font-size: var(--el-font-size-base);
      color: var(--el-text-color-regular);
    }
  }
  .dt-suggest {
    .dt-suggest__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;

      .dt-suggest__title {
        font-size: var(--el-font-size-base);
        color: var(--el-text-color-regular);
      }
    }
  }
  .log-toolbar {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;
  }
  .stats-cards {
    display: flex;
    gap: 18px;
    margin-bottom: 14px;
  }
  .stats-engine {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 14px;

    .stats-engine__label {
      font-size: var(--el-font-size-base);
      color: var(--el-text-color-regular);
    }
  }
}

.graph-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.graph-edit {
  margin-bottom: 8px;

  .ge-row {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }

  .ge-item {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 2px 0;

    .ge-item__name {
      flex: 1;
      font-size: var(--el-font-size-small);
    }
    .ge-item__w {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }
}
.graph-chart {
  width: 100%;
  height: 100%;
}

.graph-view {
  .graph-chart {
    height: 480px;
  }
}

.graph-fullscreen {
  height: 100%;

  .graph-chart--fullscreen {
    height: calc(100vh - 180px);
  }
}

.graph-legend {
  display: flex;
  gap: 14px;
  margin: 6px 0;

  .graph-legend__item {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);

    .graph-legend__dot {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
  }
}

.stat-block {
  margin-top: 14px;

  .stat-block__title {
    margin-bottom: 8px;
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
  }
}
.stat-tag {
  margin: 0 6px 6px 0;
}
.doc-upload {
  margin-bottom: 12px;
  .el-upload-dragger {
    padding: 26px;
  }
}
.doc-searchbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.doc-preview {
  max-height: 70vh;
  padding: 14px;
  overflow: auto;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.qa-block {
  .qa-block__title {
    margin-bottom: 8px;
    font-size: var(--el-font-size-base);
    font-weight: 600;
    color: var(--el-text-color-regular);
  }
}
.qa-answer {
  padding: 12px 14px;
  margin-top: 12px;
  font-size: var(--el-font-size-base);
  line-height: 1.8;
  color: var(--el-text-color-primary);
  overflow-wrap: anywhere;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.qa-cite {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  margin: 0 2px;
  font-size: 12px;
  font-weight: 600;
  vertical-align: middle;
  color: var(--el-color-primary);
  cursor: pointer;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 4px;
}
.qa-cite:hover {
  background: var(--el-color-primary-light-7);
}
.qa-refs {
  margin-top: 12px;
}
.qa-refs__title {
  margin-bottom: 6px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.qa-ref {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  font-size: var(--el-font-size-base);
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.qa-ref__file {
  color: var(--el-text-color-primary);
}
.qa-ref__loc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.qa-cite-content {
  max-height: 40vh;
  padding: 10px 12px;
  margin-top: 12px;
  overflow: auto;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.faq-bar {
  margin: 12px 0;
}
.chunk-toolbar {
  margin-bottom: 8px;
}
.doc-html {
  img {
    max-width: 100%;
  }
}
.doc-text {
  max-height: 70vh;
  overflow: auto;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.graph-ctx {
  position: fixed;
  z-index: 3000;
  min-width: 140px;
  padding: 4px 0;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);

  .graph-ctx__item {
    padding: 8px 14px;
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    cursor: pointer;

    &:hover {
      color: var(--el-color-primary);
      background: var(--el-fill-color-light);
    }
  }
  .graph-ctx__danger {
    color: var(--el-color-danger);

    &:hover {
      color: var(--el-color-danger);
      background: var(--el-fill-color-light);
    }
  }
}

.chunk-ann-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.search-hit__annotate {
  margin-left: 8px;
}

.ann-preview {
  max-height: 120px;
  padding: 8px 10px;
  margin: 12px 0;
  overflow: auto;
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.ann-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;

  .ann-item {
    display: flex;
    gap: 8px;
    align-items: center;

    .el-tag {
      max-width: 60%;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
}
.ann-add {
  display: flex;
  gap: 8px;
  align-items: center;
}

.bind-chunks {
  width: 100%;

  .bind-item {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 2px 0;

    .bind-item__label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      white-space: nowrap;
    }
    .bind-item__text {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: var(--el-font-size-base);
      white-space: nowrap;
    }
  }
  .el-select {
    margin-bottom: 8px;
  }
}
.ds-test-data {
  margin-top: 8px;
}
.ds-test-data__title {
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ds-test-data__body {
  max-height: 40vh;
  padding: 10px;
  margin: 0;
  overflow: auto;
  font-size: var(--el-font-size-base);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
</style>

<!-- 布局统一（非 scoped + 唯一类名）：白色面板撑满可视区，内容区自己滚（行少时也不露灰底） -->
<style lang="scss">
.app-container.ai-knowledge-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 左分类树 + 右内容（区域隔离，参照个人工作空间） */
.ai-knowledge-page .kb-layout {
  display: flex;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
}

.ai-knowledge-page .kb-side {
  flex: 0 0 240px;
  min-width: 0;
  overflow: auto;
}

.ai-knowledge-page .kb-side > .el-card__header {
  padding: 12px 16px;
}

.ai-knowledge-page .kb-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.ai-knowledge-page .kb-tabs-card {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
}

.ai-knowledge-page .kb-tabs-card > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-knowledge-page .kb-tabs-card .el-tabs {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-knowledge-page .kb-tabs-card .el-tabs__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
</style>
