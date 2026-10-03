<!-- AI 知识库 / 数据源 RAG：知识库（入库/检索/分块） + 数据源（测试/同步），复用 Element Plus -->
<template>
  <div class="app-container ai-knowledge-page">
    <el-card shadow="never" class="kb-tabs-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="知识库" name="kb">
          <div class="kb-toolbar">
            <el-button
              v-hasPerm="['module_ai:knowledge:create']"
              type="primary"
              :icon="Plus"
              @click="openKbDialog()"
            >
              新建知识库
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:update']"
              :icon="Upload"
              :disabled="!selectedKb"
              @click="selectedKb && openIngestDialog(selectedKb)"
            >
              文本入库
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:query']"
              :icon="Search"
              :disabled="!selectedKb"
              @click="selectedKb && openSearchDialog(selectedKb)"
            >
              检索测试
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:query']"
              :icon="Files"
              :disabled="!selectedKb"
              @click="selectedKb && openChunks(selectedKb)"
            >
              分块查看
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:query']"
              :icon="Share"
              :disabled="!selectedKb"
              @click="selectedKb && openGraph(selectedKb)"
            >
              图谱
            </el-button>
          </div>

          <el-table
            v-loading="loading"
            :data="bases"
            highlight-current-row
            @current-change="(row: any) => (selectedKb = row)"
          >
            <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.description || "—" }}</template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="分块数" width="90" align="center" />
            <el-table-column label="嵌入模型" width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag v-if="row.model_id" size="small" type="info" effect="plain">
                  {{ modelNameMap[row.model_id] || `#${row.model_id}` }}
                </el-tag>
                <span v-else class="kb-opt-hint">确定性向量</span>
              </template>
            </el-table-column>
            <el-table-column label="图谱" width="150" align="center">
              <template #default="{ row }">
                <el-tag
                  v-if="row.graph_nodes"
                  size="small"
                  type="success"
                  effect="plain"
                  class="kb-graph-cell"
                  title="点击查看图谱"
                  @click.stop="openGraph(row)"
                >
                  {{ row.graph_nodes }} 节点 / {{ row.graph_edges }} 边
                </el-tag>
                <span v-else class="kb-opt-hint">—</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" align="center" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="openDetail(row)">详情</el-button>
                <el-button
                  v-hasPerm="['module_ai:knowledge:update']"
                  size="small"
                  :icon="Edit"
                  @click="openKbDialog(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:knowledge:delete']"
                  size="small"
                  type="danger"
                  :icon="Delete"
                  @click="deleteBases(row)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="数据源" name="ds">
          <div class="kb-toolbar">
            <el-button
              v-hasPerm="['module_ai:knowledge:create']"
              type="primary"
              :icon="Plus"
              @click="openDsDialog()"
            >
              新增数据源
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:query']"
              :icon="Connection"
              :disabled="!selectedDs"
              @click="selectedDs && testDs(selectedDs)"
            >
              测试
            </el-button>
            <el-button
              v-hasPerm="['module_ai:knowledge:update']"
              type="warning"
              :icon="Refresh"
              :disabled="!selectedDs"
              @click="selectedDs && syncDs(selectedDs)"
            >
              同步入库
            </el-button>
          </div>

          <el-table
            v-loading="loadingDs"
            :data="datasources"
            highlight-current-row
            @current-change="(row: any) => (selectedDs = row)"
          >
            <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column label="类型" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">
                  {{ row.ds_type === "db" ? "数据库" : "API" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="连接" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{
                  row.ds_type === "db"
                    ? (row.dialect || "") + " | " + (row.uri || "")
                    : row.uri || ""
                }}
              </template>
            </el-table-column>
            <el-table-column label="目标知识库" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ kbName(row.knowledge_base_id) }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:knowledge:update']"
                  size="small"
                  :icon="Edit"
                  @click="openDsDialog(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:knowledge:delete']"
                  size="small"
                  type="danger"
                  :icon="Delete"
                  @click="deleteDatasources(row)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建/编辑知识库 -->
    <el-dialog
      v-model="kbDialogVisible"
      :title="editingKb ? '编辑知识库' : '新建知识库'"
      width="520px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="kbForm" label-width="90px" size="default">
        <el-form-item label="名称" required>
          <el-input v-model="kbForm.name" placeholder="知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="kbForm.description" type="textarea" :rows="3" placeholder="描述" />
        </el-form-item>
        <el-form-item label="嵌入模型">
          <el-select
            v-model="kbForm.model_id"
            clearable
            filterable
            placeholder="留空则用确定性向量"
            style="width: 100%"
          >
            <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="kbForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kbDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingKb" @click="saveKb">保存</el-button>
      </template>
    </el-dialog>

    <!-- 文本入库 -->
    <el-dialog
      v-model="ingestDialogVisible"
      title="文本入库"
      width="600px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="ingestForm" label-width="90px" size="default">
        <el-form-item label="目标库">
          <el-input :model-value="ingestTarget?.name" disabled />
        </el-form-item>
        <el-form-item label="文件名">
          <el-input v-model="ingestForm.file_name" placeholder="来源文件名（可选）" />
        </el-form-item>
        <el-form-item label="原文内容" required>
          <el-input
            v-model="ingestForm.content"
            type="textarea"
            :rows="8"
            placeholder="粘贴待入库文本"
          />
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="ingestForm.chunk_size" :min="100" :max="2000" :step="50" />
        </el-form-item>
        <el-form-item label="重叠">
          <el-input-number v-model="ingestForm.overlap" :min="0" :max="400" :step="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ingestDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="ingesting" @click="doIngest">入库</el-button>
      </template>
    </el-dialog>

    <!-- 检索测试 -->
    <el-dialog
      v-model="searchDialogVisible"
      title="检索测试"
      width="620px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="searchForm" label-width="90px" size="default">
        <el-form-item label="查询">
          <el-input v-model="searchForm.query" placeholder="输入检索问题" @keyup.enter="doSearch" />
        </el-form-item>
        <el-form-item label="Top K">
          <el-input-number v-model="searchForm.top_k" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="GraphRAG">
          <el-switch v-model="searchForm.use_graph" />
          <span class="kb-opt-hint">开启后按知识图谱扩展相关实体</span>
        </el-form-item>
      </el-form>
      <div v-loading="searching">
        <el-empty v-if="!searchResults.length" description="输入查询后检索" :image-size="60" />
        <div v-for="(h, i) in searchResults" :key="i" class="search-hit">
          <div class="search-hit__meta">
            <span class="search-hit__file">{{ h.file_name || "未知" }}</span>
            <span class="search-hit__score">相似度 {{ h.score }}</span>
            <el-tag v-if="h.engine" size="small" effect="plain" :type="engineType(h.engine)">
              {{ engineLabel(h.engine) }}
            </el-tag>
            <el-tag v-if="h.graph_entity" size="small" type="warning" effect="plain">
              图谱：{{ h.graph_entity }}
            </el-tag>
          </div>
          <div class="search-hit__content">{{ h.content }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 图谱可视化 -->
    <el-dialog
      v-model="graphVisible"
      :title="`知识图谱 · ${selectedKb?.name || ''}`"
      width="720px"
      height="560px"
      append-to-body
    >
      <div class="graph-dialog">
        <div class="graph-stats">
          <el-tag type="success" effect="plain">{{ graphStats.nodes }} 个实体节点</el-tag>
          <el-tag type="warning" effect="plain">{{ graphStats.edges }} 条关系边</el-tag>
          <span class="kb-opt-hint">拖动节点可微调布局；下方可编辑图谱。</span>
        </div>
        <el-collapse class="graph-edit">
          <el-collapse-item title="编辑实体 / 关系（保存后同步 AGE）" name="edit">
            <div class="ge-row">
              <el-input v-model="newEntityName" placeholder="实体名" size="small" style="flex: 1" />
              <el-input
                v-model="newEntityType"
                placeholder="类型(keyword)"
                size="small"
                style="width: 120px"
              />
              <el-button size="small" type="primary" @click="addGraphEntity">加实体</el-button>
            </div>
            <div v-for="n in graphNodes" :key="n.id" class="ge-item">
              <span class="ge-item__name">{{ n.name }}</span>
              <span v-if="n.weight" class="ge-item__w">w={{ n.weight }}</span>
              <el-button link type="danger" size="small" @click="delGraphEntity(n)">删除</el-button>
            </div>
            <el-divider />
            <div class="ge-row">
              <el-select v-model="newRelSource" placeholder="源" size="small" style="flex: 1">
                <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
              </el-select>
              <el-select v-model="newRelTarget" placeholder="目标" size="small" style="flex: 1">
                <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
              </el-select>
              <el-button size="small" type="primary" @click="addGraphRelation">加关系</el-button>
            </div>
            <div v-for="e in graphEdges" :key="e.id" class="ge-item">
              <span class="ge-item__name">{{ e.source }} → {{ e.target }}</span>
              <span v-if="e.weight" class="ge-item__w">w={{ e.weight }}</span>
              <el-button link type="danger" size="small" @click="delGraphRelation(e)">
                删除
              </el-button>
            </div>
          </el-collapse-item>
        </el-collapse>
        <VChart v-if="graphOption" class="graph-chart" :option="graphOption" autoresize />
      </div>
    </el-dialog>

    <!-- 分块抽屉 -->
    <el-drawer v-model="chunksVisible" :title="`分块 · ${chunksTarget?.name || ''}`" size="480px">
      <el-table v-loading="loadingChunks" :data="chunks" size="small" max-height="70vh">
        <el-table-column prop="chunk_index" label="序号" width="60" align="center" />
        <el-table-column prop="file_name" label="来源" width="120" show-overflow-tooltip />
        <el-table-column label="内容" min-width="200">
          <template #default="{ row }">
            <div class="chunk-content">{{ row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
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
      :title="`知识库管理 · ${detailKb?.name || ''}`"
      size="820px"
      append-to-body
    >
      <el-tabs v-model="detailTab" class="detail-tabs">
        <!-- 概览 -->
        <el-tab-pane label="概览" name="overview">
          <div class="ov-stats">
            <el-statistic title="分块" :value="detailChunkCount" />
            <el-statistic title="图谱节点" :value="detailGraphNodes" />
            <el-statistic title="图谱边" :value="detailGraphEdges" />
            <el-statistic title="数据源" :value="detailDsCount" />
          </div>
          <el-form label-width="80px" size="small" class="ov-form">
            <el-form-item label="描述">
              <el-input v-model="detailDesc" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="detailEnabled" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveDetailOverview">保存</el-button>
              <el-button type="warning" :loading="rebuilding" @click="rebuildDetail">
                重建索引
              </el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="重建索引会重新向量化所有分块并重建图谱（Age 同步）。"
          />
        </el-tab-pane>

        <!-- 文本入库 -->
        <el-tab-pane label="文本入库" name="ingest">
          <el-form label-width="90px" size="small">
            <el-form-item label="文件名">
              <el-input v-model="detailIngest.file_name" />
            </el-form-item>
            <el-form-item label="内容">
              <el-input
                v-model="detailIngest.content"
                type="textarea"
                :rows="6"
                placeholder="粘贴待入库文本"
              />
            </el-form-item>
            <el-form-item label="分段策略">
              <el-select v-model="detailIngest.strategy" style="width: 200px">
                <el-option label="定长+重叠" value="fixed" />
                <el-option label="按段落" value="paragraph" />
                <el-option label="按句子" value="sentence" />
              </el-select>
            </el-form-item>
            <el-form-item label="块大小/重叠">
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
                入库
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 分块 -->
        <el-tab-pane label="分块" name="chunks">
          <el-table v-loading="loadingChunks" :data="detailChunks" size="small" max-height="60vh">
            <el-table-column prop="chunk_index" label="#" width="60" align="center" />
            <el-table-column prop="file_name" label="来源" width="120" show-overflow-tooltip />
            <el-table-column label="内容" min-width="200">
              <template #default="{ row }">{{ row.content }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openChunkEdit(row)">
                  编辑
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
        <el-tab-pane label="检索测试" name="search">
          <div class="dt-search">
            <el-select v-model="detailSearchMode" style="width: 130px">
              <el-option label="混合" value="hybrid" />
              <el-option label="向量" value="vector" />
              <el-option label="中文全文" value="fulltext" />
              <el-option label="图谱" value="graph" />
              <el-option label="子串全文" value="grep" />
            </el-select>
            <el-input
              v-model="detailQuery"
              placeholder="输入检索"
              style="flex: 1"
              @keyup.enter="doDetailSearch"
            />
            <el-button type="primary" :loading="detailSearching" @click="doDetailSearch">
              检索
            </el-button>
            <el-button @click="openGraph(detailKb)">图谱</el-button>
          </div>
          <div v-if="detailSearchMode === 'hybrid'" class="dt-weights">
            <span class="dt-weight-label">混合权重</span>
            <el-input-number
              v-model="detailVectorWeight"
              :min="0"
              :max="1"
              :step="0.1"
              size="small"
              controls-position="right"
            />
            <span class="dt-weight-label">向量</span>
            <el-input-number
              v-model="detailFulltextWeight"
              :min="0"
              :max="1"
              :step="0.1"
              size="small"
              controls-position="right"
            />
            <span class="dt-weight-label">全文</span>
          </div>
          <el-empty
            v-if="!detailSearchResults.length"
            description="输入查询后检索"
            :image-size="60"
          />
          <div v-for="(h, i) in detailSearchResults" :key="i" class="search-hit">
            <div class="search-hit__meta">
              <span class="search-hit__file">{{ h.file_name || "未知" }}</span>
              <span class="search-hit__score">得分 {{ h.score }}</span>
              <el-tag size="small" effect="plain" :type="engineType(h.engine)">
                {{ engineLabel(h.engine) }}
              </el-tag>
              <el-tag v-if="h.graph_entity" size="small" type="warning" effect="plain">
                图谱：{{ h.graph_entity }}
              </el-tag>
            </div>
            <div class="search-hit__content" v-html="highlight(h.content, detailQuery)"></div>
          </div>
        </el-tab-pane>

        <!-- 图谱（内嵌可视化 + 编辑） -->
        <el-tab-pane label="图谱" name="graph">
          <div v-loading="graphLoading" class="graph-view">
            <div class="graph-stats">
              <el-tag type="success" effect="plain">{{ graphStats.nodes }} 个实体节点</el-tag>
              <el-tag type="warning" effect="plain">{{ graphStats.edges }} 条关系边</el-tag>
              <span class="kb-opt-hint">
                拖动节点可微调布局；下方可直接编辑图谱（保存后同步 AGE）。
              </span>
            </div>
            <el-collapse class="graph-edit">
              <el-collapse-item title="编辑实体 / 关系" name="edit">
                <div class="ge-row">
                  <el-input
                    v-model="newEntityName"
                    placeholder="实体名"
                    size="small"
                    style="flex: 1"
                  />
                  <el-input
                    v-model="newEntityType"
                    placeholder="类型(keyword)"
                    size="small"
                    style="width: 120px"
                  />
                  <el-button size="small" type="primary" @click="addGraphEntity">加实体</el-button>
                </div>
                <div v-for="n in graphNodes" :key="n.id" class="ge-item">
                  <span class="ge-item__name">{{ n.name }}</span>
                  <span v-if="n.weight" class="ge-item__w">w={{ n.weight }}</span>
                  <el-button link type="primary" size="small" @click="openRenameEntity(n)">
                    编辑
                  </el-button>
                  <el-button link type="danger" size="small" @click="delGraphEntity(n)">
                    删除
                  </el-button>
                </div>
                <el-divider />
                <div class="ge-row">
                  <el-select v-model="newRelSource" placeholder="源" size="small" style="flex: 1">
                    <el-option
                      v-for="n in graphNodes"
                      :key="n.id"
                      :label="n.name"
                      :value="n.name"
                    />
                  </el-select>
                  <el-select v-model="newRelTarget" placeholder="目标" size="small" style="flex: 1">
                    <el-option
                      v-for="n in graphNodes"
                      :key="n.id"
                      :label="n.name"
                      :value="n.name"
                    />
                  </el-select>
                  <el-button size="small" type="primary" @click="addGraphRelation">
                    加关系
                  </el-button>
                </div>
                <div v-for="e in graphEdges" :key="e.id" class="ge-item">
                  <span class="ge-item__name">{{ e.source }} → {{ e.target }}</span>
                  <span v-if="e.weight" class="ge-item__w">w={{ e.weight }}</span>
                  <el-button link type="danger" size="small" @click="delGraphRelation(e)">
                    删除
                  </el-button>
                </div>
              </el-collapse-item>
            </el-collapse>
            <VChart v-if="graphOption" class="graph-chart" :option="graphOption" autoresize />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <!-- 编辑分块 -->
    <el-dialog v-model="chunkEditVisible" title="编辑分块" width="640px" append-to-body>
      <el-input
        v-model="chunkEditContent"
        type="textarea"
        :rows="8"
        placeholder="编辑分块内容，保存后将重新向量化该分块"
      />
      <template #footer>
        <el-button @click="chunkEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="chunkEditing" @click="saveChunkEdit">
          保存并重向量化
        </el-button>
      </template>
    </el-dialog>

    <!-- 图谱实体重命名 -->
    <el-dialog v-model="renameEntityVisible" title="编辑图谱实体" width="480px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="实体名" required>
          <el-input v-model="renameForm.name" placeholder="实体名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-input v-model="renameForm.etype" placeholder="keyword" />
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="renameForm.weight" :min="1" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameEntityVisible = false">取消</el-button>
        <el-button type="primary" :loading="renamingEntity" @click="saveRenameEntity">
          保存（同步 AGE）
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="dsDialogVisible"
      :title="editingDs ? '编辑数据源' : '新增数据源'"
      width="560px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="dsForm" label-width="100px" size="default">
        <el-form-item label="名称" required>
          <el-input v-model="dsForm.name" placeholder="数据源名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="dsForm.ds_type">
            <el-radio-button value="db">数据库</el-radio-button>
            <el-radio-button value="api">API</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="dsForm.ds_type === 'db'" label="方言">
          <el-select v-model="dsForm.dialect" style="width: 100%">
            <el-option label="postgresql" value="postgresql" />
            <el-option label="mysql" value="mysql" />
            <el-option label="sqlite" value="sqlite" />
          </el-select>
        </el-form-item>
        <el-form-item :label="dsForm.ds_type === 'db' ? '连接URI' : 'API地址'">
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
        <el-form-item v-if="dsForm.ds_type === 'api'" label="数据路径">
          <el-input v-model="dsForm.api_config.data_path" placeholder="如 data 或 data.list" />
        </el-form-item>
        <el-form-item label="目标知识库">
          <el-select
            v-model="dsForm.knowledge_base_id"
            clearable
            filterable
            placeholder="选择同步目标"
            style="width: 100%"
          >
            <el-option v-for="b in bases" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="dsForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dsDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingDs" @click="saveDs">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
use([CanvasRenderer, GraphChart, TooltipComponent]);
import {
  Plus,
  Edit,
  Delete,
  Upload,
  Search,
  Files,
  Connection,
  Refresh,
  Share,
} from "@element-plus/icons-vue";
import {
  getAiKnowledgeList,
  createAiKnowledge,
  updateAiKnowledge,
  deleteAiKnowledge,
  ingestAiKnowledge,
  searchAiKnowledge,
  rebuildAiKnowledge,
  getAiKnowledgeChunks,
  deleteAiKnowledgeChunk,
  updateAiKnowledgeChunk,
  getAiKnowledgeGraph,
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
    const models = mr.data?.data || [];
    // 只列可用作嵌入的模型（usage=embedding 或 capabilities 含 embedding）
    modelOptions.value = models
      .filter((m: any) => m.usage === "embedding" || (m.capabilities || []).includes("embedding"))
      .map((m: any) => ({ id: m.id, name: m.name }));
    modelNameMap.value = Object.fromEntries(models.map((m: any) => [m.id, m.name]));
    modelUsageMap.value = Object.fromEntries(models.map((m: any) => [m.id, m.usage]));
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
    loadingDs.value = false;
  }
};

// ---------- 知识库 CRUD ----------
const kbDialogVisible = ref(false);
const savingKb = ref(false);
const editingKb = ref<any>();
const kbForm = reactive<any>({});

function openKbDialog(b?: any) {
  editingKb.value = b || undefined;
  Object.assign(
    kbForm,
    b ? { ...b } : { name: "", description: "", model_id: null, enabled: true }
  );
  kbDialogVisible.value = true;
}

async function saveKb() {
  if (!kbForm.name) {
    ElMessage.warning("请填写知识库名称");
    return;
  }
  savingKb.value = true;
  try {
    const payload: any = {
      name: kbForm.name,
      description: kbForm.description || "",
      model_id: kbForm.model_id || null,
      enabled: kbForm.enabled,
    };
    if (editingKb.value) {
      await updateAiKnowledge(editingKb.value.id, payload);
    } else {
      await createAiKnowledge(payload);
    }
    ElMessage.success("保存成功");
    kbDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    savingKb.value = false;
  }
}

function deleteBases(row: any) {
  ElMessageBox.confirm(
    `确定删除知识库「${row.name}」吗？将删除其中 ${row.chunk_count || 0} 个分块，且不可恢复。`,
    "删除确认",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  )
    .then(async () => {
      await deleteAiKnowledge([row.id]);
      ElMessage.success("删除成功");
      if (selectedKb.value?.id === row.id) selectedKb.value = undefined;
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
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
    ElMessage.warning("请粘贴待入库文本");
    return;
  }
  ingesting.value = true;
  try {
    const r = await ingestAiKnowledge(ingestTarget.value.id, { ...ingestForm });
    ElMessage.success(`入库成功，写入 ${r.data?.data?.chunks || 0} 个分块`);
    ingestDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "入库失败");
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
    ElMessage.warning("请输入查询");
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
    ElMessage.error(e?.message || "检索失败");
  } finally {
    searching.value = false;
  }
}

// 检索引擎标签
function engineLabel(e: string): string {
  if (e === "jieba_fulltext") return "中文全文";
  if (e === "pgvector") return "向量";
  if (e === "graphrag") return "图谱";
  if (e === "hybrid") return "混合";
  if (e === "grep") return "子串全文";
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
const graphOption = ref<any>(null);
const graphStats = ref({ nodes: 0, edges: 0 });
const graphNodes = ref<any[]>([]);
const graphEdges = ref<any[]>([]);
const graphKbId = ref<number>();
// 编辑表单
const newEntityName = ref("");
const newEntityType = ref("keyword");
const newRelSource = ref("");
const newRelTarget = ref("");
async function loadGraph(g: any) {
  graphStats.value = { nodes: (g.nodes || []).length, edges: (g.edges || []).length };
  graphNodes.value = (g.nodes || []).map((n: any) => ({ ...n, id: n.id ?? n.name }));
  graphEdges.value = (g.edges || []).map((e: any, i: number) => ({
    ...e,
    id: e.id ?? `${e.source}_${e.target}_${i}`,
  }));
  const nodes = graphNodes.value.map((n: any) => ({
    id: String(n.id),
    name: n.name,
    symbolSize: Math.min(20 + (n.weight || 1) * 2, 40),
    itemStyle: { color: "#409eff" },
  }));
  const links = graphEdges.value.map((e: any) => ({
    source: String(e.source),
    target: String(e.target),
    lineStyle: { width: 1 + Math.min((e.weight || 1) / 3, 2), opacity: 0.7 },
  }));
  graphOption.value = {
    tooltip: { show: true },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        data: nodes,
        links,
        force: { repulsion: 120, edgeLength: 80 },
        label: { show: true, position: "right", fontSize: 11 },
      },
    ],
  };
}

async function openGraph(kb: any) {
  const kbId = kb?.id || selectedKb.value?.id;
  if (!kbId) return;
  selectedKb.value = kb;
  graphKbId.value = kbId;
  graphVisible.value = true;
  graphLoading.value = true;
  newEntityName.value = "";
  newEntityType.value = "keyword";
  newRelSource.value = "";
  newRelTarget.value = "";
  try {
    const r = await getAiKnowledgeGraph(kbId);
    await loadGraph(r.data?.data || { nodes: [], edges: [] });
  } catch (e: any) {
    ElMessage.error(e?.message || "加载图谱失败");
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
    ElMessage.error(e?.message || "刷新图谱失败");
  }
}
async function addGraphEntity() {
  const name = newEntityName.value.trim();
  if (!name || !graphKbId.value) return;
  try {
    await createAiKnowledgeGraphEntity(graphKbId.value, {
      name,
      etype: newEntityType.value || "keyword",
    });
    newEntityName.value = "";
    await reloadGraph("已新增实体");
  } catch (e: any) {
    ElMessage.error(e?.message || "新增失败");
  }
}
async function delGraphEntity(n: any) {
  if (!graphKbId.value) return;
  try {
    await deleteAiKnowledgeGraphEntities(graphKbId.value, [n.id]);
    await reloadGraph("已删除实体");
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
}
// 图谱实体重命名
const renameEntityVisible = ref(false);
const renameForm = reactive<any>({ id: null, name: "", etype: "keyword", weight: 1 });
const renamingEntity = ref(false);
function openRenameEntity(n: any) {
  renameForm.id = n.id;
  renameForm.name = n.name;
  renameForm.etype = n.etype || "keyword";
  renameForm.weight = n.weight || 1;
  renameEntityVisible.value = true;
}
async function saveRenameEntity() {
  if (!graphKbId.value || !renameForm.id) return;
  if (!renameForm.name.trim()) {
    ElMessage.warning("实体名不能为空");
    return;
  }
  renamingEntity.value = true;
  try {
    await updateAiKnowledgeGraphEntity(graphKbId.value, renameForm.id, {
      name: renameForm.name.trim(),
      etype: renameForm.etype,
      weight: renameForm.weight,
    });
    renameEntityVisible.value = false;
    await reloadGraph("已更新实体（含关系联动）");
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "更新失败");
  } finally {
    renamingEntity.value = false;
  }
}
async function addGraphRelation() {
  const s = newRelSource.value;
  const t = newRelTarget.value;
  if (!s || !t || !graphKbId.value) return;
  try {
    await createAiKnowledgeGraphRelation(graphKbId.value, { source: s, target: t });
    newRelSource.value = "";
    newRelTarget.value = "";
    await reloadGraph("已新增关系");
  } catch (e: any) {
    ElMessage.error(e?.message || "新增关系失败");
  }
}
async function delGraphRelation(e: any) {
  if (!graphKbId.value) return;
  try {
    await deleteAiKnowledgeGraphRelations(graphKbId.value, [e.id]);
    await reloadGraph("已删除关系");
  } catch (err: any) {
    ElMessage.error(err?.message || "删除关系失败");
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
const detailSearchMode = ref("hybrid");
const detailQuery = ref("");
const detailSearching = ref(false);
const detailSearchResults = ref<any[]>([]);
const detailVectorWeight = ref(0.5);
const detailFulltextWeight = ref(0.5);

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
    ElMessage.error(e?.message || "加载图谱失败");
  } finally {
    graphLoading.value = false;
  }
}

async function saveDetailOverview() {
  if (!detailKb.value) return;
  try {
    await updateAiKnowledge(detailKb.value.id, {
      description: detailDesc.value,
      enabled: detailEnabled.value,
    });
    ElMessage.success("已保存");
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  }
}

async function rebuildDetail() {
  if (!detailKb.value) return;
  rebuilding.value = true;
  try {
    const r = await rebuildAiKnowledge(detailKb.value.id);
    ElMessage.success(`重建完成（${r.data?.data?.chunks || 0} 分块）`);
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || "重建失败");
  } finally {
    rebuilding.value = false;
  }
}

async function doDetailIngest() {
  if (!detailKb.value || !detailIngest.content.trim()) {
    ElMessage.warning("请粘贴待入库文本");
    return;
  }
  detailIngesting.value = true;
  try {
    const r = await ingestAiKnowledge(detailKb.value.id, { ...detailIngest });
    ElMessage.success(`入库成功，写入 ${r.data?.data?.chunks || 0} 个分块`);
    detailIngest.content = "";
    await loadDetailStats(detailKb.value.id);
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "入库失败");
  } finally {
    detailIngesting.value = false;
  }
}

async function deleteChunkFromDetail(row: any) {
  if (!detailKb.value) return;
  await deleteAiKnowledgeChunk(detailKb.value.id, row.id);
  ElMessage.success("已删除分块");
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
    ElMessage.warning("内容不能为空");
    return;
  }
  chunkEditing.value = true;
  try {
    await updateAiKnowledgeChunk(detailKb.value.id, chunkEditId.value, chunkEditContent.value);
    ElMessage.success("已保存并重向量化");
    chunkEditVisible.value = false;
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    chunkEditing.value = false;
  }
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
      detailFulltextWeight.value
    );
    detailSearchResults.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || "检索失败");
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
    ElMessage.error(e?.message || "加载分块失败");
  } finally {
    loadingChunks.value = false;
  }
}

function deleteChunk(row: any) {
  ElMessageBox.confirm("确定删除该分块吗？删除后不可恢复。", "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiKnowledgeChunk(chunksTarget.value.id, row.id);
      ElMessage.success("删除成功");
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
    ElMessage.warning("请填写数据源名称");
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
    ElMessage.success("保存成功");
    dsDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    savingDs.value = false;
  }
}

function deleteDatasources(row: any) {
  ElMessageBox.confirm(`确定删除数据源「${row.name}」吗？删除后不可恢复。`, "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiDatasource([row.id]);
      ElMessage.success("删除成功");
      if (selectedDs.value?.id === row.id) selectedDs.value = undefined;
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
}

// ---------- 测试 / 同步 ----------
async function testDs(row: any) {
  try {
    const r = await testAiDatasource(row.id);
    const d = r.data?.data || {};
    if (d.ok) {
      ElMessage.success(d.message || "连接成功");
    } else {
      ElMessage.warning(d.message || "连接失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "测试失败");
  }
}

function syncDs(row: any) {
  if (row.ds_type === "db") {
    ElMessageBox.prompt("请输入要同步的表名/查询（如 users）", "同步入库", {
      confirmButtonText: "同步",
      cancelButtonText: "取消",
      inputPlaceholder: "表名",
    })
      .then(async ({ value }: { value: string }) => {
        if (!value?.trim()) return;
        await doSync(row, { table: value.trim() });
      })
      .catch(() => {
        /* 取消 */
      });
  } else {
    ElMessageBox.confirm(`确定从「${row.name}」同步数据到目标知识库吗？`, "同步确认", {
      confirmButtonText: "同步",
      cancelButtonText: "取消",
      type: "warning",
    })
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
    ElMessage.success(`同步完成：读取 ${d.rows || 0} 行，写入 ${d.chunks || 0} 个分块`);
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "同步失败");
  }
}

onMounted(loadData);
</script>

<style scoped lang="scss">
.ai-knowledge-page {
  height: 100%;
  overflow: auto;
}

.kb-tabs-card {
  .kb-toolbar {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
}

.search-hit {
  margin-bottom: 10px;
  padding: 10px;
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
    color: var(--el-text-color-regular);
    line-height: 1.6;

    mark {
      background: var(--el-color-warning-light-7);
      color: var(--el-color-warning-dark-2);
      border-radius: 2px;
      padding: 0 2px;
    }
  }
}

.chunk-content {
  max-height: 60px;
  overflow: hidden;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
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
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;

    .dt-weight-label {
      font-size: var(--el-font-size-base);
      color: var(--el-text-color-regular);
    }
  }
}

.graph-stats {
  display: flex;
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
      font-size: 13px;
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
    height: 360px;
  }
}
</style>
