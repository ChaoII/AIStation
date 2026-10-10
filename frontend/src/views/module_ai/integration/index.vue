<!-- 数据与集成：把「数据资产」合并进来，做成一条路 —— 选数据源 → 选表 → 就地维护元数据 -->
<template>
  <div class="app-container ai-mod ai-integration-page">
    <el-row :gutter="12" class="ig-fill">
      <!-- 左：数据源 -->
      <el-col :span="7" class="ig-fill">
        <el-card shadow="never" class="ig-card">
          <template #header>
            <div class="ig-head">
              <span>数据源</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openDs()">新建</el-button>
            </div>
          </template>
          <el-table
            :data="datasources"
            size="small"
            border
            height="100%"
            highlight-current-row
            @current-change="pickDs"
          >
            <template #empty>
              <el-empty description="暂无数据源" :image-size="60" />
            </template>
            <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
            <el-table-column prop="type" label="类型" width="66" />
            <el-table-column label="操作" width="92" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click.stop="testDs(row)">
                  测试
                </el-button>
                <el-button link type="primary" size="small" @click.stop="openDs(row)">
                  编辑
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 右：选中数据源的详情 -->
      <el-col :span="17" class="ig-fill">
        <el-card shadow="never" class="ig-card">
          <el-tabs v-model="tab" class="ig-tabs">
            <!-- 表与字段：核心——选表后就地维护 -->
            <el-tab-pane label="表与字段" name="table">
              <div class="ig-split">
                <!-- 表清单 -->
                <div class="ig-tables">
                  <div class="ig-bar">
                    <el-input
                      v-model="tableKw"
                      size="small"
                      placeholder="搜索表名/中文名"
                      :prefix-icon="Search"
                      clearable
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
                  </div>
                  <el-table
                    :data="filteredTables"
                    size="small"
                    border
                    height="100%"
                    highlight-current-row
                    @current-change="pickTable"
                  >
                    <template #empty>
                      <el-empty
                        :description="curDs ? '点「同步」拉取表结构' : '请先选择左侧数据源'"
                        :image-size="50"
                      />
                    </template>
                    <el-table-column label="表" min-width="180" show-overflow-tooltip>
                      <template #default="{ row }">
                        <div class="ig-tname">{{ row.table }}</div>
                        <div v-if="row.comment" class="ig-tcmt">{{ row.comment }}</div>
                      </template>
                    </el-table-column>
                    <el-table-column label="字段" width="64" align="center">
                      <template #default="{ row }">{{ row.column_count ?? "-" }}</template>
                    </el-table-column>
                  </el-table>
                </div>

                <!-- 选中表的元数据 + 字段 -->
                <div class="ig-detail">
                  <template v-if="!curTable">
                    <el-empty description="请从左侧选择一张表" :image-size="60" />
                  </template>
                  <template v-else>
                    <div class="ig-bar">
                      <span class="ig-title">{{ curTable }}</span>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="savingTable"
                        @click="saveTable"
                      >
                        保存表信息
                      </el-button>
                      <el-button
                        size="small"
                        :icon="DataBoard"
                        :loading="importing"
                        @click="doImport"
                      >
                        导入为本体对象
                      </el-button>
                    </div>
                    <el-form :model="tmeta" label-width="86px" size="small" class="ig-form">
                      <el-row :gutter="8">
                        <el-col :span="12">
                          <el-form-item label="中文名">
                            <el-input v-model="tmeta.alias" placeholder="如：燃煤采购结算主表" />
                          </el-form-item>
                        </el-col>
                        <el-col :span="12">
                          <el-form-item label="业务域">
                            <el-input v-model="tmeta.domain" placeholder="如：燃煤/设备/人员" />
                          </el-form-item>
                        </el-col>
                      </el-row>
                      <el-form-item label="业务描述">
                        <el-input
                          v-model="tmeta.description"
                          type="textarea"
                          :rows="2"
                          placeholder="这张表存什么、怎么用——问数会读它来理解表"
                        />
                      </el-form-item>
                      <el-row :gutter="8">
                        <el-col :span="12">
                          <el-form-item label="业务场景">
                            <el-input
                              v-model="tmeta.business_scenarios"
                              placeholder="哪些报表/业务用到"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="12">
                          <el-form-item label="纳入问数">
                            <el-switch v-model="tmeta.included" />
                          </el-form-item>
                        </el-col>
                      </el-row>
                      <el-row :gutter="8">
                        <el-col :span="8">
                          <el-form-item label="业务对象">
                            <el-switch v-model="tmeta.object_enabled" />
                          </el-form-item>
                        </el-col>
                        <el-col :span="8">
                          <el-form-item label="主键列">
                            <el-input
                              v-model="tmeta.object_key_col"
                              :disabled="!tmeta.object_enabled"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="8">
                          <el-form-item label="显示名列">
                            <el-input
                              v-model="tmeta.object_name_col"
                              :disabled="!tmeta.object_enabled"
                            />
                          </el-form-item>
                        </el-col>
                      </el-row>
                    </el-form>

                    <div class="ig-bar">
                      <span class="ig-sub">字段（{{ columns.length }}）</span>
                      <el-tag size="small" type="info" effect="plain">
                        上游注释可作参考，中文名可人工覆盖
                      </el-tag>
                    </div>
                    <el-table :data="columns" size="small" border height="100%">
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
                      <el-table-column label="中文名" min-width="130">
                        <template #default="{ row }">
                          <el-input v-model="row.description" size="small" placeholder="中文名" />
                        </template>
                      </el-table-column>
                      <el-table-column label="关联表" min-width="120">
                        <template #default="{ row }">
                          <el-input
                            v-model="row.related_table"
                            size="small"
                            placeholder="指向哪张表"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column label="关联字段" min-width="110">
                        <template #default="{ row }">
                          <el-input
                            v-model="row.related_field"
                            size="small"
                            placeholder="对应字段"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column label="纳入" width="58" align="center">
                        <template #default="{ row }">
                          <el-switch v-model="row.included" size="small" />
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" width="62" align="center">
                        <template #default="{ row }">
                          <el-button
                            link
                            type="primary"
                            size="small"
                            :loading="savingCol === row.column_name"
                            @click="saveColumn(row)"
                          >
                            保存
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </template>
                </div>
              </div>
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
            <el-tab-pane label="概念" name="concept">
              <div class="ig-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openConcept()">
                  新建概念
                </el-button>
                <el-tag size="small" type="info" effect="plain">本体/概念（语义层）</el-tag>
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
          <el-input v-model="pipeForm.source_connection" placeholder="留空=本系统表；填数据源 ID/编码" />
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
    <el-dialog
      v-model="conceptDlg"
      :title="conceptForm.id ? '编辑概念' : '新建概念'"
      width="560px"
    >
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
      </el-form>
      <template #footer>
        <el-button @click="dsDlg = false">取消</el-button>
        <el-button type="primary" :loading="savingDs" @click="saveDs">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Search, DataBoard, EditPen } from "@element-plus/icons-vue";
import {
  getQueryDatasources,
  saveQueryDatasource,
  testQueryDatasource,
  syncQueryDatasourceSchema,
  getQueryDatasourceSchema,
  importDsAsOntology,
  getQueryAssetColumns,
  saveQueryAsset,
  saveQueryAssetColumn,
  batchSaveQueryAssetMeta,
  getQueryAssets,
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
  rebuildQueryKg,
} from "@/api/module_ai/query";

const tab = ref("table");
const datasources = ref<any[]>([]);
const curDs = ref<any>(null);
const dsTables = ref<any[]>([]);
const tableKw = ref("");
const curTable = ref("");
const columns = ref<any[]>([]);
const pipelines = ref<any[]>([]);
const metrics = ref<any[]>([]);
const terms = ref<any[]>([]);
const concepts = ref<any[]>([]);
const kg = ref<any>({});
const assets = ref<any[]>([]);

const syncing = ref(false);
const importing = ref(false);
const savingTable = ref(false);
const savingCol = ref("");
const savingDs = ref(false);
const dsDlg = ref(false);
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

const filteredTables = computed(() => {
  const kw = tableKw.value.trim().toLowerCase();
  if (!kw) return dsTables.value;
  return dsTables.value.filter(
    (t) =>
      String(t.table).toLowerCase().includes(kw) ||
      String(t.comment || "")
        .toLowerCase()
        .includes(kw)
  );
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
    dsTables.value = rows.map((x: any) => ({
      table: x.table,
      comment: x.comment || "",
      column_count: (x.columns || []).length,
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
    }));
  } catch {
    columns.value = [];
  }
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

async function saveColumn(row: any) {
  savingCol.value = row.column_name;
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
    });
    ElMessage.success(`字段「${row.column_name}」已保存`);
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
    const r = await importDsAsOntology(curDs.value.id, curTable.value);
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
    };
  }
  dsDlg.value = true;
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
}

onMounted(async () => {
  await Promise.all([loadDs(), loadAssets(), loadMisc()]);
});
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
  flex: 0 0 240px;
  flex-direction: column;
  min-height: 0;
}
.ig-detail {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
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
.ig-note {
  margin-bottom: 10px;
}
.ig-tag {
  margin: 0 2px;
}
.ig-batch-bar {
  margin-top: 8px;
}
</style>
