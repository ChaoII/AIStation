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
          <span class="kb-opt-hint">
            右键节点可编辑属性/绑定分块/加关系/删除，右键空白新建节点。
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
            <div class="graph-ctx__item" @click="ctxEditNode">编辑节点属性</div>
            <div class="graph-ctx__item" @click="ctxBindNode">绑定分块</div>
            <div class="graph-ctx__item" @click="ctxAddRel">添加关系</div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">删除节点</div>
          </template>
          <template v-else-if="ctxMenu.kind === 'edge'">
            <div class="graph-ctx__item" @click="ctxEditRel">编辑关系</div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">删除关系</div>
          </template>
          <template v-else>
            <div class="graph-ctx__item" @click="ctxNewNode">新建节点</div>
          </template>
        </div>
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

        <!-- 文档管理（wikiLLM/ima 式） -->
        <el-tab-pane label="文档" name="documents">
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
              拖拽文件到此处，或
              <em>点击上传</em>
              （txt/md/docx/pdf）
            </div>
          </el-upload>
          <div class="doc-searchbar">
            <el-select v-model="docChunkSize" size="small" style="width: 130px">
              <el-option label="块大小 200" :value="200" />
              <el-option label="块大小 500" :value="500" />
              <el-option label="块大小 1000" :value="1000" />
            </el-select>
            <el-select v-model="docStrategy" size="small" style="width: 130px">
              <el-option label="定长+重叠" value="fixed" />
              <el-option label="按段落" value="paragraph" />
              <el-option label="按句子" value="sentence" />
            </el-select>
          </div>
          <el-table v-loading="loadingDocs" :data="documents" size="small" max-height="50vh">
            <el-table-column prop="name" label="文档" min-width="180" show-overflow-tooltip />
            <el-table-column label="类型" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small" type="info" effect="plain">{{ row.file_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="90" align="center">
              <template #default="{ row }">{{ fmtSize(row.size) }}</template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="分块" width="70" align="center" />
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ row.created_time }}</template>
            </el-table-column>
            <el-table-column label="操作" width="210" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="previewDoc(row)">
                  预览
                </el-button>
                <el-button link type="warning" size="small" @click="reparseDoc(row)">
                  重建
                </el-button>
                <el-button link size="small" @click="downloadDoc(row)">下载</el-button>
                <el-button link type="danger" size="small" @click="deleteDoc(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty
            v-if="!documents.length && !loadingDocs"
            description="暂无文档"
            :image-size="60"
          />

          <div class="faq-bar">
            <el-button size="small" type="primary" plain :loading="faqLoading" @click="exportFaq">
              导出 FAQ 缓存
            </el-button>
          </div>

          <el-divider />
          <div class="qa-block">
            <div class="qa-block__title">跨文档交叉问答</div>
            <div class="dt-search">
              <el-input
                v-model="qaQuery"
                placeholder="输入问题，检索全部文档"
                @keyup.enter="doQaSearch"
              />
              <el-button type="primary" :loading="qaSearching" @click="doQaSearch">问答</el-button>
            </div>
            <div v-for="(h, i) in qaResults" :key="i" class="search-hit">
              <div class="search-hit__meta">
                <span class="search-hit__file">{{ h.file_name || "未知" }}</span>
                <span class="search-hit__score">得分 {{ h.score }}</span>
                <el-tag size="small" effect="plain" :type="engineType(h.engine)">
                  {{ engineLabel(h.engine) }}
                </el-tag>
              </div>
              <div class="search-hit__content" v-html="highlight(h.content, qaQuery)"></div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 分块 -->
        <el-tab-pane label="分块" name="chunks">
          <el-table v-loading="loadingChunks" :data="detailChunks" size="small" max-height="60vh">
            <el-table-column prop="chunk_index" label="#" width="60" align="center" />
            <el-table-column prop="file_name" label="来源" width="120" show-overflow-tooltip />
            <el-table-column label="内容" min-width="200">
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
            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openChunkEdit(row)">
                  编辑
                </el-button>
                <el-button link type="warning" size="small" @click="openAnnotation(row)">
                  标注
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
              <el-button
                link
                type="warning"
                size="small"
                class="search-hit__annotate"
                @click="
                  openAnnotation({ id: h.chunk_id, content: h.content, file_name: h.file_name })
                "
              >
                + 标注此分块
              </el-button>
              <el-button link type="primary" size="small" @click="locateInGraph(h)">
                图谱定位
              </el-button>
            </div>
            <div class="search-hit__content" v-html="highlight(h.content, detailQuery)"></div>
          </div>
          <el-divider />
          <div class="dt-suggest">
            <div class="dt-suggest__head">
              <span class="dt-suggest__title">检索失败？推测相关分块并标注</span>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="suggestLoading"
                :disabled="!detailQuery.trim()"
                @click="loadSuggest"
              >
                推测相关分块
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
                <span class="search-hit__file">{{ s.file_name || "未知" }}</span>
                <span class="search-hit__score">相似 {{ s.similarity }}</span>
                <el-tag v-if="s.hit" size="small" type="success" effect="plain">已命中</el-tag>
                <el-tag v-else size="small" type="warning" effect="plain">未命中，建议标注</el-tag>
                <el-button
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
                  + 标注此分块
                </el-button>
              </div>
              <div class="search-hit__content" v-html="highlight(s.content, detailQuery)"></div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 标注台账 -->
        <el-tab-pane label="标注台账" name="logs">
          <div class="log-toolbar">
            <el-select
              v-model="logSourceFilter"
              size="small"
              placeholder="来源"
              clearable
              style="width: 120px"
            >
              <el-option label="手动" value="manual" />
              <el-option label="检索" value="search" />
              <el-option label="自动" value="auto" />
              <el-option label="图谱" value="graph" />
            </el-select>
            <el-select
              v-model="logKindFilter"
              size="small"
              placeholder="类型"
              clearable
              style="width: 120px"
            >
              <el-option label="别名" value="alias" />
              <el-option label="锚点" value="anchor" />
              <el-option label="备注" value="note" />
            </el-select>
            <el-tag size="small" type="info" effect="plain">共 {{ filteredLogs.length }} 条</el-tag>
            <el-tag size="small" type="success" effect="plain">添加 {{ statAdd }}</el-tag>
            <el-tag size="small" type="danger" effect="plain">删除 {{ statRemove }}</el-tag>
          </div>
          <el-table v-loading="loadingLogs" :data="filteredLogs" size="small" max-height="60vh">
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ row.created_time }}</template>
            </el-table-column>
            <el-table-column label="分块" width="70" align="center">
              <template #default="{ row }">#{{ row.chunk_id }}</template>
            </el-table-column>
            <el-table-column label="动作" width="70" align="center">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.action === 'add' ? 'success' : 'danger'"
                  effect="plain"
                >
                  {{ row.action === "add" ? "添加" : "删除" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="标注" min-width="140">
              <template #default="{ row }">{{ row.text }}</template>
            </el-table-column>
            <el-table-column label="类型" width="70" align="center">
              <template #default="{ row }">{{ annotKindLabel(row.kind) }}</template>
            </el-table-column>
            <el-table-column label="来源" width="90" align="center">
              <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
            </el-table-column>
            <el-table-column label="触发查询" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.query || "—" }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 检索统计 -->
        <el-tab-pane label="检索统计" name="stats">
          <el-form inline size="small" class="stats-days">
            <el-form-item label="近">
              <el-input-number v-model="statsDays" :min="7" :max="90" :step="1" size="small" />
            </el-form-item>
            <el-form-item label="天">
              <el-button type="primary" size="small" :loading="loadingStats" @click="loadStats">
                刷新
              </el-button>
            </el-form-item>
          </el-form>
          <div v-loading="loadingStats" class="stats-cards">
            <el-statistic title="检索次数" :value="searchStats.total" />
            <el-statistic
              title="命中率"
              :value="(searchStats.hit_rate || 0) * 100"
              :precision="0"
              suffix="%"
            />
            <el-statistic title="平均命中" :value="searchStats.avg_hits" />
            <el-statistic title="空命中" :value="searchStats.zero_hit_count" />
          </div>
          <div class="stats-engine">
            <span class="stats-engine__label">引擎分布：</span>
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
              暂无数据
            </span>
          </div>
          <el-table :data="searchStats.trend || []" size="small" max-height="40vh">
            <el-table-column prop="date" label="日期" width="150" />
            <el-table-column prop="count" label="检索次数" width="100" align="center" />
            <el-table-column prop="hits" label="命中总数" width="100" align="center" />
          </el-table>
          <el-empty
            v-if="!(searchStats.trend || []).length"
            description="暂无检索记录"
            :image-size="60"
          />
        </el-tab-pane>

        <!-- 图谱（内嵌可视化 + 编辑） -->
        <el-tab-pane label="图谱" name="graph">
          <div v-loading="graphLoading" class="graph-view">
            <div class="graph-stats">
              <el-tag type="success" effect="plain">{{ graphStats.nodes }} 个实体节点</el-tag>
              <el-tag type="warning" effect="plain">{{ graphStats.edges }} 条关系边</el-tag>
              <el-button size="small" type="primary" plain @click="ctxNewNode">
                + 新建节点
              </el-button>
              <el-button size="small" type="success" plain @click="openAddRel">
                + 新建关系
              </el-button>
              <el-button size="small" :loading="graphSavingLayout" @click="saveLayout">
                保存布局
              </el-button>
              <el-button size="small" @click="relayoutGraph">重新布局</el-button>
              <el-button size="small" @click="() => reloadGraph()">刷新</el-button>
              <el-button size="small" @click="openRelationTypeDialog">关系模板</el-button>
              <el-button size="small" @click="exportGraphImage">导出图片</el-button>
              <el-button size="small" type="primary" plain @click="graphFullscreenVisible = true">
                全屏
              </el-button>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="!selectedNames.size"
                @click="batchDeleteNodes"
              >
                批量删除{{ selectedNames.size ? ` (${selectedNames.size})` : "" }}
              </el-button>
              <el-button
                v-if="selectedNames.size"
                size="small"
                @click="
                  selectedNames = new Set();
                  reloadGraph();
                "
              >
                清空选择
              </el-button>
              <el-switch
                v-model="multiSelect"
                size="small"
                active-text="多选模式"
                @change="
                  selectedNames = new Set();
                  reloadGraph();
                "
              />
              <el-switch
                v-model="linkMode"
                size="small"
                active-text="连线模式"
                @change="linkSource = null"
              />
              <el-select
                v-model="graphLayout"
                size="small"
                style="width: 110px"
                @change="onGraphLayoutChange"
              >
                <el-option label="力导向" value="cose" />
                <el-option label="同心圆" value="concentric" />
                <el-option label="网格" value="grid" />
                <el-option label="环形" value="circle" />
                <el-option label="层级" value="breadthfirst" />
              </el-select>
              <el-switch
                v-model="physicsMode"
                size="small"
                active-text="物理模式"
                @change="() => onGraphLayoutChange(graphLayout)"
              />
              <el-button size="small" @click="() => graphCanvasRef?.fit?.()">适配</el-button>
              <el-button size="small" @click="() => graphCanvasRef?.zoom?.(1.25)">放大</el-button>
              <el-button size="small" @click="() => graphCanvasRef?.zoom?.(0.8)">缩小</el-button>
              <el-button size="small" @click="() => graphCanvasRef?.center?.()">居中</el-button>
              <el-input
                v-model="graphSearch"
                size="small"
                placeholder="搜索节点"
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
                active-text="最短路径"
                @change="graphCanvasRef?.fit?.()"
              />
              <el-button size="small" @click="graphStatsVisible = true">统计</el-button>
              <el-button size="small" @click="edgeStyleVisible = true">连线样式</el-button>
              <el-button size="small" @click="nodeStyleVisible = true">节点样式</el-button>
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
              右键节点编辑属性/绑定分块/加关系/删除，右键空白新建节点；「新建关系」选两个节点+关系类型自动连线；拖动后可「保存布局」记住位置；多选模式下点击节点可多选批量删除。
            </div>
            <el-empty
              v-if="!graphNodes.length"
              description="暂无节点，右键画布或点「新建节点」创建"
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
                <div class="graph-ctx__item" @click="ctxEditNode">编辑节点属性</div>
                <div class="graph-ctx__item" @click="ctxBindNode">绑定分块</div>
                <div class="graph-ctx__item" @click="ctxAddRel">添加关系</div>
                <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">删除节点</div>
              </template>
              <template v-else-if="ctxMenu.kind === 'edge'">
                <div class="graph-ctx__item" @click="ctxEditRel">编辑关系</div>
                <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">删除关系</div>
              </template>
              <template v-else>
                <div class="graph-ctx__item" @click="ctxNewNode">新建节点</div>
              </template>
            </div>
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
    <el-dialog v-model="renameEntityVisible" title="节点属性" width="520px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="节点名" required>
          <el-input v-model="renameForm.name" placeholder="节点名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-input v-model="renameForm.etype" placeholder="keyword" />
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="renameForm.weight" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item label="备注/描述">
          <el-input v-model="renameForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="关联分块">
          <div class="bind-chunks">
            <div v-for="c in entityBoundChunks" :key="c.id" class="bind-item">
              <span class="bind-item__label">#{{ c.chunk_index }}</span>
              <span class="bind-item__text">{{ c.content }}</span>
              <el-button link type="danger" size="small" @click="unbindChunk(c)">解绑</el-button>
            </div>
            <el-empty
              v-if="!entityBoundChunks.length"
              description="尚未绑定分块"
              :image-size="50"
            />
            <el-select
              v-model="entityBindSel"
              multiple
              filterable
              collapse-tags
              placeholder="选择要绑定的分块"
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
              绑定
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameEntityVisible = false">取消</el-button>
        <el-button type="primary" :loading="renamingEntity" @click="saveRenameEntity">
          保存（同步 AGE）
        </el-button>
      </template>
    </el-dialog>

    <!-- 分块标注（换说法召回命中） -->
    <el-dialog
      v-model="annotationVisible"
      :title="`分块标注 · #${annotChunk?.chunk_index || ''}`"
      width="620px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="给分块加额外标注（别名/锚点/备注），标注会进入向量、中文全文、子串检索索引，用户换种说法提问也能命中该分块。"
      />
      <div class="ann-preview">{{ annotChunk?.content }}</div>
      <div class="ann-list">
        <div v-for="(a, ai) in annotList" :key="ai" class="ann-item">
          <el-tag size="small" type="warning" effect="plain">{{ a.text }}</el-tag>
          <el-tag size="small" type="info" effect="plain">{{ annotKindLabel(a.kind) }}</el-tag>
          <el-button link type="danger" size="small" @click="removeAnnotation(ai)">删除</el-button>
        </div>
        <el-empty v-if="!annotList.length" description="暂无标注" :image-size="50" />
      </div>
      <div class="ann-add">
        <el-input
          v-model="annotText"
          placeholder="输入标注，如「XX 的别名」"
          size="small"
          @keyup.enter="addAnnotation"
        />
        <el-select v-model="annotKind" size="small" style="width: 110px">
          <el-option label="别名" value="alias" />
          <el-option label="锚点" value="anchor" />
          <el-option label="备注" value="note" />
        </el-select>
        <el-button type="primary" size="small" :loading="annotating" @click="addAnnotation">
          添加
        </el-button>
      </div>
    </el-dialog>

    <!-- 图谱关系编辑 -->
    <el-dialog v-model="relEditVisible" title="编辑图谱关系" width="480px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="源实体">
          <el-select v-model="relEditForm.source" filterable placeholder="源" style="width: 100%">
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标实体">
          <el-select v-model="relEditForm.target" filterable placeholder="目标" style="width: 100%">
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select
            v-model="relEditForm.rtype"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入关系类型"
            style="width: 100%"
          >
            <el-option v-for="r in rtypeOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="relEditForm.weight" :min="1" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingRel" @click="saveRelEdit">
          保存（同步 AGE）
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建节点（图上右键空白） -->
    <el-dialog v-model="nodeNewVisible" title="新建节点" width="440px" append-to-body>
      <el-form label-width="80px" size="default">
        <el-form-item label="节点名" required>
          <el-input v-model="nodeNewForm.name" placeholder="实体名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-input v-model="nodeNewForm.etype" placeholder="keyword" />
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="nodeNewForm.weight" :min="1" :max="9999" />
        </el-form-item>
        <el-form-item label="备注/描述">
          <el-input v-model="nodeNewForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeNewVisible = false">取消</el-button>
        <el-button type="primary" :loading="addingNode" @click="saveNewNode">创建</el-button>
      </template>
    </el-dialog>

    <!-- 新建关系（选两个节点 + 关系类型，自动连线） -->
    <el-dialog v-model="relAddVisible" title="新建关系" width="480px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="源节点">
          <el-select
            v-model="relAddForm.source"
            filterable
            placeholder="选择源节点"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标节点">
          <el-select
            v-model="relAddForm.target"
            filterable
            placeholder="选择目标节点"
            style="width: 100%"
          >
            <el-option v-for="n in graphNodes" :key="n.id" :label="n.name" :value="n.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select
            v-model="relAddForm.rtype"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入关系类型"
            style="width: 100%"
          >
            <el-option v-for="r in rtypeOptions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="relAddForm.weight" :min="1" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relAddVisible = false">取消</el-button>
        <el-button type="primary" :loading="addingRel" @click="saveAddRel">添加</el-button>
      </template>
    </el-dialog>

    <!-- 图谱全屏查看 -->
    <el-dialog v-model="graphFullscreenVisible" title="知识图谱 · 全屏" fullscreen append-to-body>
      <div v-loading="graphLoading" class="graph-fullscreen">
        <div class="graph-stats">
          <el-tag type="success" effect="plain">{{ graphStats.nodes }} 个实体节点</el-tag>
          <el-tag type="warning" effect="plain">{{ graphStats.edges }} 条关系边</el-tag>
          <el-button size="small" @click="relayoutGraph">重新布局</el-button>
          <el-button size="small" @click="() => reloadGraph()">刷新</el-button>
          <el-switch
            v-model="linkMode"
            size="small"
            active-text="连线模式"
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
            <div class="graph-ctx__item" @click="ctxEditNode">编辑节点属性</div>
            <div class="graph-ctx__item" @click="ctxBindNode">绑定分块</div>
            <div class="graph-ctx__item" @click="ctxAddRel">添加关系</div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelNode">删除节点</div>
          </template>
          <template v-else-if="ctxMenu.kind === 'edge'">
            <div class="graph-ctx__item" @click="ctxEditRel">编辑关系</div>
            <div class="graph-ctx__item graph-ctx__danger" @click="ctxDelRel">删除关系</div>
          </template>
          <template v-else>
            <div class="graph-ctx__item" @click="ctxNewNode">新建节点</div>
          </template>
        </div>
      </div>
    </el-dialog>

    <!-- 关系类型模板管理 -->
    <el-dialog
      v-model="relationTypeDialogVisible"
      title="关系类型模板"
      width="520px"
      append-to-body
    >
      <div class="rt-add">
        <el-input
          v-model="rtNewName"
          placeholder="关系类型名，如：依赖"
          size="small"
          @keyup.enter="addRt"
        />
        <el-button size="small" type="primary" @click="addRt">添加</el-button>
      </div>
      <el-table :data="relationTypes" size="small" max-height="50vh">
        <el-table-column prop="name" label="类型" min-width="140" />
        <el-table-column label="颜色" width="80" align="center">
          <template #default="{ row }">
            <i class="graph-legend__dot" :style="{ background: row.color || '#a0a6ad' }" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="delRt(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="relationTypeDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 节点样式设置 -->
    <el-dialog v-model="nodeStyleVisible" title="节点样式设置" width="560px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="节点大小">
          <el-radio-group v-model="nodeStyle.sizeMode">
            <el-radio-button label="weight">按权重</el-radio-button>
            <el-radio-button label="fixed">固定</el-radio-button>
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
        <el-form-item label="节点形状">
          <el-radio-group v-model="nodeStyle.shapeMode">
            <el-radio-button label="type">按类型</el-radio-button>
            <el-radio-button label="uniform">统一</el-radio-button>
          </el-radio-group>
          <el-select
            v-if="nodeStyle.shapeMode === 'uniform'"
            v-model="nodeStyle.uniformShape"
            size="small"
            style="width: 140px; margin-left: 8px"
          >
            <el-option label="椭圆" value="ellipse" />
            <el-option label="圆" value="circle" />
            <el-option label="圆角方" value="round-rectangle" />
            <el-option label="菱形" value="diamond" />
          </el-select>
        </el-form-item>
        <el-form-item label="节点颜色">
          <el-radio-group v-model="nodeStyle.colorMode">
            <el-radio-button label="type">按类型</el-radio-button>
            <el-radio-button label="single">统一</el-radio-button>
          </el-radio-group>
          <el-color-picker
            v-if="nodeStyle.colorMode === 'single'"
            v-model="nodeStyle.singleColor"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item label="标签字号">
          <el-input-number v-model="nodeStyle.labelSize" :min="9" :max="20" size="small" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeStyleVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 文档内容预览 -->
    <el-dialog v-model="docPreviewVisible" :title="docPreviewName" width="760px" append-to-body>
      <div v-loading="docPreviewLoading" class="doc-preview">
        <VuePdfEmbed
          v-if="docPreviewKind === 'pdf' && docPreviewPdfUrl"
          :source="docPreviewPdfUrl"
        />
        <div v-else-if="docPreviewKind === 'docx'" class="doc-html" v-html="docPreviewHtml" />
        <div v-else class="doc-text">{{ docPreviewContent || "（空文档）" }}</div>
      </div>
      <template #footer>
        <el-button @click="docPreviewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 连线样式设置 -->
    <el-dialog v-model="edgeStyleVisible" title="连线样式设置" width="560px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="线型">
          <el-radio-group v-model="edgeStyle.lineStyle">
            <el-radio-button label="solid">实线</el-radio-button>
            <el-radio-button label="dashed">虚线</el-radio-button>
            <el-radio-button label="dotted">点线</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="曲线">
          <el-radio-group v-model="edgeStyle.curve">
            <el-radio-button label="bezier">贝塞尔</el-radio-button>
            <el-radio-button label="straight">直线</el-radio-button>
            <el-radio-button label="taxi">折线</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="箭头">
          <el-select v-model="edgeStyle.arrow" style="width: 140px">
            <el-option label="三角" value="triangle" />
            <el-option label="V形" value="vee" />
            <el-option label="圆点" value="circle" />
            <el-option label="无" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item label="线宽">
          <el-radio-group v-model="edgeStyle.widthMode">
            <el-radio-button label="weight">按权重</el-radio-button>
            <el-radio-button label="fixed">固定</el-radio-button>
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
        <el-form-item label="颜色">
          <el-radio-group v-model="edgeStyle.colorMode">
            <el-radio-button label="type">按关系类型</el-radio-button>
            <el-radio-button label="single">统一</el-radio-button>
          </el-radio-group>
          <el-color-picker
            v-if="edgeStyle.colorMode === 'single'"
            v-model="edgeStyle.singleColor"
            size="small"
            style="margin-left: 8px"
          />
        </el-form-item>
        <el-form-item label="关系标签">
          <el-select v-model="edgeStyle.label" style="width: 180px">
            <el-option label="始终显示" value="show" />
            <el-option label="仅非默认关系" value="nondefault" />
            <el-option label="悬停显示" value="hover" />
            <el-option label="不显示" value="none" />
          </el-select>
        </el-form-item>
        <el-form-item label="透明度">
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
        <el-button @click="edgeStyleVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 图谱统计 -->
    <el-dialog v-model="graphStatsVisible" title="图谱统计" width="560px" append-to-body>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="实体节点">{{ graphStatsDetail.nodes }}</el-descriptions-item>
        <el-descriptions-item label="关系边">{{ graphStatsDetail.edges }}</el-descriptions-item>
        <el-descriptions-item label="平均度">{{ graphStatsDetail.avgDegree }}</el-descriptions-item>
        <el-descriptions-item label="连接组件">—</el-descriptions-item>
      </el-descriptions>
      <div class="stat-block">
        <div class="stat-block__title">实体类型分布</div>
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
        <div class="stat-block__title">关系类型分布</div>
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
        <el-button @click="graphStatsVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 实体关联分块（图谱节点点击直达） -->
    <el-dialog
      v-model="entityChunksVisible"
      :title="`实体关联分块 · ${entityChunksName}`"
      width="560px"
      append-to-body
    >
      <el-table
        v-loading="entityChunksLoading"
        :data="entityChunksList"
        size="small"
        max-height="50vh"
      >
        <el-table-column prop="chunk_index" label="#" width="60" align="center" />
        <el-table-column prop="file_name" label="来源" width="120" show-overflow-tooltip />
        <el-table-column label="内容" min-width="200">
          <template #default="{ row }">{{ row.content }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="warning"
              size="small"
              @click="
                openAnnotation({ id: row.id, content: row.content, file_name: row.file_name })
              "
            >
              标注
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!entityChunksList.length" description="该实体尚未绑定分块" :image-size="50" />
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
import { ref, reactive, computed, onMounted } from "vue";
import GraphCanvas from "./GraphCanvas.vue";
import VuePdfEmbed from "vue-pdf-embed";
import mammoth from "mammoth";

const graphCanvasRef = ref<any>();
import { ElMessage, ElMessageBox } from "element-plus";
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
  UploadFilled,
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
  deleteAiKnowledgeDocument,
  getAiKnowledgeDocumentContent,
  reparseAiKnowledgeDocument,
  downloadAiKnowledgeDocument,
  getAiKnowledgeFaq,
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
    await loadRelationTypes();
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
  { value: "default", label: "默认" },
  { value: "ocean", label: "海洋" },
  { value: "forest", label: "森林" },
  { value: "sunset", label: "落日" },
  { value: "mono", label: "单色" },
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
    ElMessage.info(`${a} → ${b} 无连通路径`);
  } else {
    ElMessage.success(`最短路径：${a} → ${b}，${length} 跳`);
  }
}
function typeLabel(t: string) {
  if (t === "annotation") return "标注/关联分块";
  if (t === "custom") return "自定义";
  if (t === "keyword") return "关键词";
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
    ElMessage.warning("图表未就绪");
    return;
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = `知识图谱_${graphKbId.value || ""}.png`;
  a.click();
  ElMessage.success("已导出图片");
}
async function batchDeleteNodes() {
  if (!graphKbId.value || !selectedNames.value.size) return;
  const ids = graphNodes.value.filter((n) => selectedNames.value.has(n.name)).map((n) => n.id);
  if (!ids.length) return;
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 个节点吗？其关联关系与绑定将一并移除，不可恢复。`,
      "批量删除",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await deleteAiKnowledgeGraphEntities(graphKbId.value, ids);
    selectedNames.value = new Set();
    ElMessage.success("已批量删除");
    await reloadGraph();
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
}
const graphLegend = [
  { color: "#409eff", label: "关键词" },
  { color: "#e6a23c", label: "标注/关联分块" },
  { color: "#67c23a", label: "自定义" },
  { color: "#909399", label: "其他" },
];
const relationTypes = ref<any[]>([]);
const rtypeOptions = computed(() => {
  const names = relationTypes.value.map((r: any) => r.name);
  return names.length ? names : ["属于", "包含", "依赖", "相关", "引用", "位于", "用于", "关联"];
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
    ElMessage.success("已添加关系类型");
    await loadRelationTypes();
    await reloadGraph();
  } catch (e: any) {
    ElMessage.error(e?.message || "添加失败");
  }
}
async function delRt(row: any) {
  try {
    await deleteAiRelationType(row.id);
    ElMessage.success("已删除");
    await loadRelationTypes();
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
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
    ElMessage.info("未匹配到图谱节点");
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
    ElMessage.success("已绑定分块");
    await loadEntityChunks();
  } catch (e: any) {
    ElMessage.error(e?.message || "绑定失败");
  } finally {
    bindingChunks.value = false;
  }
}
async function unbindChunk(c: any) {
  if (!graphKbId.value || !renameForm.id) return;
  try {
    await unbindAiKnowledgeEntityChunks(graphKbId.value, renameForm.id, [c.id]);
    ElMessage.success("已解绑");
    await loadEntityChunks();
  } catch (e: any) {
    ElMessage.error(e?.message || "解绑失败");
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
function openRenameRel(e: any) {
  relEditForm.id = e.id;
  relEditForm.source = e.source;
  relEditForm.target = e.target;
  relEditForm.weight = e.weight || 1;
  relEditForm.rtype = e.rtype || "related";
  relEditVisible.value = true;
}
async function saveRelEdit() {
  if (!graphKbId.value || !relEditForm.id) return;
  if (!relEditForm.source || !relEditForm.target) {
    ElMessage.warning("源/目标不能为空");
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
    await reloadGraph("已更新关系");
  } catch (e: any) {
    ElMessage.error(e?.message || "更新失败");
  } finally {
    savingRel.value = false;
  }
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
      description: renameForm.description,
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
  // 预加载标注台账
  suggestList.value = [];
  suggestHint.value = "";
  loadLogs();
  loadStats();
  loadDocs();
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

// ---------- 分块标注 ----------
const annotationVisible = ref(false);
const annotChunk = ref<any>();
const annotList = ref<any[]>([]);
const annotText = ref("");
const annotKind = ref("alias");
const annotating = ref(false);
function annotKindLabel(k: string) {
  if (k === "alias") return "别名";
  if (k === "anchor") return "锚点";
  if (k === "note") return "备注";
  return k;
}
function sourceLabel(k: string) {
  if (k === "manual") return "手动";
  if (k === "search") return "检索";
  if (k === "auto") return "自动";
  if (k === "graph") return "图谱";
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
    ElMessage.warning("请输入标注文本");
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
    ElMessage.success("已添加标注并更新索引");
    await loadDetailStats(detailKb.value.id);
    await loadLogs();
  } catch (e: any) {
    ElMessage.error(e?.message || "添加失败");
  } finally {
    annotating.value = false;
  }
}
async function removeAnnotation(index: number) {
  if (!detailKb.value || !annotChunk.value) return;
  try {
    const r = await removeAiKnowledgeChunkAnnotation(detailKb.value.id, annotChunk.value.id, index);
    annotList.value = r.data?.data?.annotations || annotList.value;
    ElMessage.success("已删除标注并更新索引");
    await loadDetailStats(detailKb.value.id);
    await loadLogs();
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
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
      ? `推测到 ${suggestList.value.length} 个相关分块，其中 ${un.length} 个未被当前检索命中，可对其标注以提升下次召回。`
      : `推测的相关分块均已被命中。`;
  } catch (e: any) {
    suggestList.value = [];
    ElMessage.error(e?.message || "推测失败");
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
    await uploadAiKnowledgeDocument(
      detailKb.value.id,
      file.raw,
      docChunkSize.value,
      docOverlap.value,
      docStrategy.value
    );
    ElMessage.success(`已上传「${file.name}」并索引`);
    await loadDocs();
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || "上传失败");
  } finally {
    uploadingDoc.value = false;
  }
}
async function deleteDoc(row: any) {
  if (!detailKb.value) return;
  try {
    await ElMessageBox.confirm(
      `确定删除文档「${row.name}」吗？其索引分块将一并移除，不可恢复。`,
      "删除文档",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await deleteAiKnowledgeDocument(detailKb.value.id, row.id);
    ElMessage.success("已删除");
    await loadDocs();
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
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
    ElMessage.error(e?.message || "预览失败");
  } finally {
    docPreviewLoading.value = false;
  }
}
async function reparseDoc(row: any) {
  if (!detailKb.value) return;
  try {
    const r = await reparseAiKnowledgeDocument(detailKb.value.id, row.id);
    ElMessage.success(`已重新解析，分块 ${r.data?.data?.chunks || 0}`);
    await loadDocs();
    await loadDetailStats(detailKb.value.id);
  } catch (e: any) {
    ElMessage.error(e?.message || "重建失败");
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
    ElMessage.error(e?.message || "下载失败");
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
    a.download = `知识库FAQ_${detailKb.value.name || ""}.md`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success(`已导出 FAQ（${r.data?.data?.count || 0} 条）`);
  } catch (e: any) {
    ElMessage.error(e?.message || "导出失败");
  } finally {
    faqLoading.value = false;
  }
}
// 跨文档交叉问答
const qaQuery = ref("");
const qaSearching = ref(false);
const qaResults = ref<any[]>([]);
async function doQaSearch() {
  if (!detailKb.value || !qaQuery.value.trim()) return;
  qaSearching.value = true;
  try {
    const r = await searchAiKnowledge(detailKb.value.id, qaQuery.value, 12, true, "hybrid");
    qaResults.value = r.data?.data || [];
    if (!qaResults.value.length) {
      ElMessage.info("未检索到相关内容，可换个问法或给分块加标注");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "问答失败");
  } finally {
    qaSearching.value = false;
  }
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
    ElMessage.error(e?.message || "加载统计失败");
  } finally {
    loadingStats.value = false;
  }
}

// ---------- 图谱节点点击 → 关联分块 ----------
const entityChunksVisible = ref(false);
const entityChunksName = ref("");
const entityChunksList = ref<any[]>([]);
const entityChunksLoading = ref(false);
async function onGraphNodeClick(params: any) {
  closeCtxMenu();
  const name = params?.data?.name || params?.name;
  if (!name || !graphKbId.value) return;
  const node = graphNodes.value.find((n) => n.name === name);
  if (!node) return;
  // 多选模式：点击节点切换选中
  if (multiSelect.value) {
    toggleSelect(name);
    reloadGraph();
    return;
  }
  // 连线模式：第一次点击记起点，第二次点击记终点并弹添加关系
  if (linkMode.value) {
    if (!linkSource.value) {
      linkSource.value = name;
      ElMessage.info(`已选起点「${name}」，再点击目标节点完成连线`);
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
  entityChunksName.value = name;
  entityChunksVisible.value = true;
  entityChunksLoading.value = true;
  try {
    const r = await getAiKnowledgeEntityChunks(graphKbId.value, node.id);
    entityChunksList.value = r.data?.data || [];
  } catch (e: any) {
    entityChunksList.value = [];
    ElMessage.error(e?.message || "加载失败");
  } finally {
    entityChunksLoading.value = false;
  }
}

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
      ElMessage.success("已连线");
      reloadGraph();
    });
  } catch (e: any) {
    ElMessage.error(e?.message || "连线失败");
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
      ElMessage.info(`已选起点「${name}」，再点击目标节点完成连线`);
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
    .then(() => ElMessage.success(`已保存 ${items.length} 个节点位置`))
    .catch(() => ElMessage.error("保存布局失败"));
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
    await reloadGraph("已清除布局记忆，重新自动排版");
  } catch (e: any) {
    ElMessage.error(e?.message || "重新布局失败");
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
    ElMessage.success("已新建节点");
    await reloadGraph();
    await loadDetailStats(graphKbId.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "新建失败");
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
    ElMessage.success("已添加关系");
    await reloadGraph();
  } catch (e: any) {
    ElMessage.error(e?.message || "添加失败");
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
      detailFulltextWeight.value
    );
    detailSearchResults.value = r.data?.data || [];
    // 检索后自动推测相关分块（若未命中/少命中则提示可标注）
    if (detailSearchResults.value.length < 10) {
      await loadSuggest().catch(() => {});
    }
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
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }
  .stats-cards {
    display: flex;
    gap: 18px;
    margin-bottom: 14px;
  }
  .stats-engine {
    display: flex;
    align-items: center;
    gap: 6px;
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
    align-items: center;
    gap: 5px;
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);

    .graph-legend__dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }
  }
}

.stat-block {
  margin-top: 14px;

  .stat-block__title {
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    margin-bottom: 8px;
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
  overflow: auto;
  white-space: pre-wrap;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 14px;
}
.qa-block {
  .qa-block__title {
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    margin-bottom: 8px;
    font-weight: 600;
  }
}
.faq-bar {
  margin: 12px 0;
}
.doc-html {
  img {
    max-width: 100%;
  }
}
.doc-text {
  max-height: 70vh;
  overflow: auto;
  white-space: pre-wrap;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.graph-ctx {
  position: fixed;
  z-index: 3000;
  min-width: 140px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  padding: 4px 0;

  .graph-ctx__item {
    padding: 8px 14px;
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    cursor: pointer;

    &:hover {
      background: var(--el-fill-color-light);
      color: var(--el-color-primary);
    }
  }
  .graph-ctx__danger {
    color: var(--el-color-danger);

    &:hover {
      background: var(--el-fill-color-light);
      color: var(--el-color-danger);
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
  overflow: auto;
  padding: 8px 10px;
  margin: 12px 0;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  line-height: 1.6;
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
      color: var(--el-text-color-secondary);
      font-size: 12px;
      white-space: nowrap;
    }
    .bind-item__text {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--el-font-size-base);
    }
  }
  .el-select {
    margin-bottom: 8px;
  }
}
</style>
