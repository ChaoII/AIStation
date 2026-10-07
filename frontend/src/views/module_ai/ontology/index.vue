<!-- 本体 Ontology：对象类型 / 属性 / Link / Action 强类型元模型（Palantir Ontology） -->
<template>
  <div class="app-container ai-mod ai-ontology-page">
    <el-card shadow="never" class="ont-caps">
      <template #header>
        <div class="ont-head">
          <span class="ont-head__title">能力（Agent 可来自本体的能力）</span>
          <el-button type="primary" size="small" :icon="Plus" @click="openCapEdit()">
            新增能力
          </el-button>
        </div>
      </template>
      <el-tag
        v-for="c in caps"
        :key="c.code"
        size="small"
        effect="plain"
        style="margin: 0 4px 4px 0"
      >
        {{ c.name }} [{{ c.type }}]
      </el-tag>
      <el-empty
        v-if="!caps.length"
        description="暂无能力，点击新增（Agent 装配时可选择这些本体能力）"
        :image-size="40"
      />
    </el-card>
    <el-row :gutter="12">
      <!-- 左：对象类型列表 -->
      <el-col :span="6">
        <el-card shadow="never" class="ont-left">
          <template #header>
            <div class="ont-head">
              <span class="ont-head__title">对象类型（{{ objects.length }}）</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openObjectEdit()">
                新建对象
              </el-button>
            </div>
          </template>
          <div
            v-for="o in objects"
            :key="o.code"
            class="ont-obj"
            :class="{ active: currentCode === o.code }"
            @click="selectObject(o)"
          >
            <el-icon class="ont-obj__icon"><component :is="o.icon || 'Box'" /></el-icon>
            <div class="ont-obj__meta">
              <div class="ont-obj__name">
                {{ o.name }}
                <el-tag
                  v-if="o.dq_score != null"
                  size="small"
                  effect="plain"
                  class="ont-obj__dq"
                  :type="o.dq_score >= 80 ? 'success' : o.dq_score >= 60 ? 'warning' : 'danger'"
                  @click.stop="openDqDetail(o)"
                >
                  DQ {{ o.dq_score }}
                </el-tag>
              </div>
              <div class="ont-obj__code">
                {{ o.code }} · 属性{{ o.property_count }} 关联{{ o.link_count }} 动作{{
                  o.action_count
                }}
              </div>
            </div>
            <el-button link type="danger" size="small" @click.stop="removeObj(o)">删</el-button>
          </div>
          <el-empty v-if="!objects.length" description="暂无对象，点击新建" :image-size="40" />
        </el-card>
      </el-col>

      <!-- 右：对象详情（属性/Link/Action） -->
      <el-col :span="18">
        <el-card shadow="never" class="ont-right">
          <template #header>
            <div v-if="current" class="ont-head">
              <span>
                <el-tag size="small" type="primary" effect="dark">{{ current.name }}</el-tag>
                <span class="ont-desc">{{ current.description }}</span>
              </span>
              <div>
                <el-button size="small" :icon="MagicStick" @click="materialize(current)">
                  物化为表
                </el-button>
                <el-button size="small" :icon="Edit" @click="openObjectEdit(current)">
                  编辑
                </el-button>
              </div>
            </div>
            <span v-else>对象详情</span>
          </template>
          <el-tabs v-if="current" v-model="ontTab">
            <el-tab-pane label="属性" name="property">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openPropEdit()">
                  新增属性
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ props.length }}</el-tag>
              </div>
              <el-table :data="props" size="small" border>
                <el-table-column prop="name" label="属性" min-width="110" show-overflow-tooltip />
                <el-table-column prop="code" label="编码" min-width="100" show-overflow-tooltip />
                <el-table-column prop="prop_type" label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" effect="plain">{{ row.prop_type }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="约束" min-width="140">
                  <template #default="{ row }">
                    <el-tag v-if="row.required" size="small" type="danger" effect="plain">
                      必填
                    </el-tag>
                    <el-tag v-if="row.unique_col" size="small" type="warning" effect="plain">
                      唯一
                    </el-tag>
                    <el-tag v-if="row.sensitive" size="small" type="info" effect="plain">
                      敏感
                    </el-tag>
                    <span
                      v-if="!row.required && !row.unique_col && !row.sensitive"
                      class="ont-none"
                    >
                      —
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="source_col" label="来源列" min-width="90" />
                <el-table-column label="授权角色" min-width="120">
                  <template #default="{ row }">
                    <el-tag
                      v-for="r in row.roles"
                      :key="r"
                      size="small"
                      type="info"
                      effect="plain"
                      style="margin: 0 2px"
                    >
                      {{ r }}
                    </el-tag>
                    <el-tag v-if="!row.roles?.length" size="small" effect="plain">公开</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openPropEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeProp(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="关联 Link" name="link">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openLinkEdit(current)">
                  新增关联
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ links.length }}</el-tag>
              </div>
              <el-table :data="links" size="small" border>
                <el-table-column
                  prop="source_object"
                  label="源对象"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="target_object"
                  label="目标对象"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column prop="name" label="关联名" min-width="110" show-overflow-tooltip />
                <el-table-column prop="card" label="基数" width="90" />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openLinkEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeLink(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="动作 Action" name="action">
              <div class="ont-bar">
                <el-button
                  type="primary"
                  size="small"
                  :icon="Plus"
                  @click="openActionEdit(current)"
                >
                  新增动作
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ actions.length }}</el-tag>
              </div>
              <el-table :data="actions" size="small" border>
                <el-table-column prop="name" label="动作" min-width="110" show-overflow-tooltip />
                <el-table-column prop="code" label="编码" min-width="100" show-overflow-tooltip />
                <el-table-column
                  prop="target_table"
                  label="写回目标"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column prop="method" label="方式" width="80" />
                <el-table-column label="审批" width="80" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.approval ? 'warning' : 'info'" effect="plain">
                      {{ row.approval ? "是" : "否" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openActionEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeAction(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="函数 Function" name="function">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openFuncEdit(current)">
                  新增函数
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ functions.length }}</el-tag>
              </div>
              <el-alert
                type="info"
                :closable="false"
                style="margin-bottom: 8px"
                title="对象上的可复用计算（如 订单毛利率），被问数 / Agent 复用（Palantir Functions）"
              />
              <el-table :data="functions" size="small" border>
                <el-table-column prop="name" label="函数" min-width="120" show-overflow-tooltip />
                <el-table-column prop="code" label="编码" min-width="120" show-overflow-tooltip />
                <el-table-column
                  prop="expr"
                  label="表达式/逻辑"
                  min-width="200"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="description"
                  label="说明"
                  min-width="160"
                  show-overflow-tooltip
                />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openFuncEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeFunc(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="变更记录" name="changelog">
              <div class="ont-bar">
                <el-tag size="small" type="info" effect="plain">共 {{ changelog.length }}</el-tag>
              </div>
              <el-table :data="changelog" size="small" border>
                <template #empty><el-empty description="暂无变更记录" :image-size="60" /></template>
                <el-table-column prop="kind" label="类型" width="90" />
                <el-table-column label="操作" width="80">
                  <template #default="{ row }">
                    <el-tag
                      size="small"
                      :type="row.action === 'delete' ? 'danger' : 'primary'"
                      effect="plain"
                    >
                      {{ row.action }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="detail" label="内容" min-width="200" show-overflow-tooltip />
                <el-table-column
                  prop="created_time"
                  label="时间"
                  min-width="160"
                  show-overflow-tooltip
                />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="版本" name="version">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="publishVer(current)">
                  发布版本
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ versions.length }}</el-tag>
              </div>
              <el-alert
                type="info"
                :closable="false"
                style="margin-bottom: 8px"
                title="将对象当前定义(对象/属性/Link/Action/函数)快照为版本，可随时回滚"
              />
              <el-table :data="versions" size="small" border>
                <template #empty>
                  <el-empty description="暂无版本，点击「发布版本」快照当前定义" :image-size="60" />
                </template>
                <el-table-column prop="version" label="版本" width="80" />
                <el-table-column
                  prop="object_code"
                  label="对象"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="created_time"
                  label="创建时间"
                  min-width="170"
                  show-overflow-tooltip
                />
                <el-table-column label="操作" width="140" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openVersionDiff(row)">
                      对比
                    </el-button>
                    <el-button link type="warning" size="small" @click="rollbackVer(row)">
                      回滚
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
          <div v-else class="ont-empty">
            <el-empty description="请先在左侧选择对象类型" :image-size="90">
              <el-button type="primary" size="small" :icon="Plus" @click="openObjectEdit()">
                新建对象
              </el-button>
            </el-empty>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="ont-head">
              <span class="ont-head__title">对象关系图（对象 → Link → 对象）</span>
              <el-tag size="small" type="info" effect="plain">
                {{ objectGraph.nodes.length }} 对象 / {{ objectGraph.edges.length }} 关联
              </el-tag>
            </div>
          </template>
          <GraphCanvas
            v-if="objectGraph.nodes.length"
            :nodes="objectGraph.nodes"
            :edges="objectGraph.edges"
            height="420px"
            layout-name="cose"
            use-preset
            @node-tap="onGraphNodeTap"
          />
          <el-empty v-else :image-size="60" description="暂无对象，点击新建对象后即可展示对象关系图" />
          <div class="gov-section" style="margin-top: 14px">对象元数据速览</div>
          <el-table :data="objects" size="small" border max-height="300">
            <el-table-column prop="code" label="编码" width="140" show-overflow-tooltip />
            <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
            <el-table-column label="属性" width="70" align="center">
              <template #default="{ row }">{{ row.property_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="关联" width="70" align="center">
              <template #default="{ row }">{{ row.link_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="动作" width="70" align="center">
              <template #default="{ row }">{{ row.action_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="敏感属性" width="90" align="center">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="(row.sensitive_count ?? 0) > 0 ? 'danger' : 'info'"
                  effect="plain"
                >
                  {{ row.sensitive_count ?? 0 }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 版本对比 -->
    <el-dialog v-model="diffDialog" title="版本对比（该版本 vs 当前）" width="560px" append-to-body>
      <template v-if="diffData?.ok">
        <div class="gov-section">
          新增属性（{{ (diffData.added || []).length }}）
        </div>
        <div>
          <el-tag
            v-for="c in diffData.added || []"
            :key="c"
            size="small"
            type="success"
            effect="plain"
            style="margin: 0 3px 4px 0"
          >
            + {{ c }}
          </el-tag>
          <span v-if="!(diffData.added || []).length" class="dq-alert__none">无</span>
        </div>
        <div class="gov-section" style="margin-top: 8px">
          删除属性（{{ (diffData.removed || []).length }}）
        </div>
        <div>
          <el-tag
            v-for="c in diffData.removed || []"
            :key="c"
            size="small"
            type="danger"
            effect="plain"
            style="margin: 0 3px 4px 0"
          >
            - {{ c }}
          </el-tag>
          <span v-if="!(diffData.removed || []).length" class="dq-alert__none">无</span>
        </div>
        <div class="gov-section" style="margin-top: 8px">
          类型/敏感变更（{{ (diffData.changed || []).length }}）
        </div>
        <div>
          <el-tag
            v-for="c in diffData.changed || []"
            :key="c"
            size="small"
            type="warning"
            effect="plain"
            style="margin: 0 3px 4px 0"
          >
            ~ {{ c }}
          </el-tag>
          <span v-if="!(diffData.changed || []).length" class="dq-alert__none">无</span>
        </div>
      </template>
      <el-empty v-else :image-size="50" description="无版本或对比失败" />
      <template #footer>
        <el-button @click="diffDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- DQ 详情 -->
    <el-dialog v-model="dqDialog" title="对象数据质量详情" width="560px" append-to-body>
      <template v-if="dqDetail">
        <el-row :gutter="12">
          <el-col :span="6"><el-statistic title="健康分" :value="dqDetail.score ?? 0" :precision="1" /></el-col>
          <el-col :span="6"><el-statistic title="完整性" :value="dqDetail.completeness ?? 0" :precision="1" /></el-col>
          <el-col :span="6"><el-statistic title="唯一性" :value="dqDetail.uniqueness ?? 0" :precision="1" /></el-col>
          <el-col :span="6"><el-statistic title="新鲜度" :value="dqDetail.freshness ?? 0" :precision="1" /></el-col>
        </el-row>
        <div class="gov-section" style="margin-top: 12px">质量问题</div>
        <div v-if="(dqDetail.issues || []).length">
          <el-tag
            v-for="(it, i) in dqDetail.issues"
            :key="i"
            size="small"
            type="danger"
            effect="plain"
            style="margin: 0 3px 4px 0"
          >
            {{ it }}
          </el-tag>
        </div>
        <el-empty v-else :image-size="40" description="无质量问题" />
      </template>
      <template #footer>
        <el-button @click="dqDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 对象编辑 -->
    <el-dialog v-model="objDialog" title="对象类型" width="560px" append-to-body>
      <el-form :model="objForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="objForm.name" placeholder="如 订单" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input
            v-model="objForm.code"
            :disabled="!!objForm.id"
            placeholder="如 orders（唯一）"
          />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="objForm.icon" placeholder="el-icon-Box" />
        </el-form-item>
        <el-form-item label="主键属性">
          <el-input v-model="objForm.key_prop" placeholder="id" />
        </el-form-item>
        <el-form-item label="名称属性">
          <el-input v-model="objForm.name_prop" placeholder="name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="objForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="objDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveObj">保存</el-button>
      </template>
    </el-dialog>

    <!-- 属性编辑 -->
    <el-dialog v-model="propDialog" title="属性类型" width="560px" append-to-body>
      <el-form :model="propForm" label-width="100px">
        <el-form-item label="名称" required><el-input v-model="propForm.name" /></el-form-item>
        <el-form-item label="编码" required><el-input v-model="propForm.code" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="propForm.prop_type" style="width: 100%">
            <el-option label="字符串 string" value="string" />
            <el-option label="数值 number" value="number" />
            <el-option label="日期 date" value="date" />
            <el-option label="布尔 boolean" value="boolean" />
            <el-option label="枚举 enum" value="enum" />
            <el-option label="对象引用 object_ref" value="object_ref" />
          </el-select>
        </el-form-item>
        <el-form-item label="约束">
          <el-checkbox v-model="propForm.required">必填</el-checkbox>
          <el-checkbox v-model="propForm.unique_col">唯一</el-checkbox>
          <el-checkbox v-model="propForm.sensitive">敏感</el-checkbox>
        </el-form-item>
        <el-form-item label="来源列">
          <el-input v-model="propForm.source_col" placeholder="映射真实表列(可空)" />
        </el-form-item>
        <el-form-item label="可访问角色">
          <el-select
            v-model="propForm.roles"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="空=公开；填 all/public 公开，其它角色受限"
            style="width: 100%"
          >
            <el-option label="公开(public)" value="public" />
            <el-option label="全部(all)" value="all" />
            <el-option label="管理员(admin)" value="admin" />
            <el-option label="分析师(analyst)" value="analyst" />
            <el-option label="只读(reader)" value="reader" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="propForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="propDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveProp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关联编辑 -->
    <el-dialog v-model="linkDialog" title="关联类型" width="560px" append-to-body>
      <el-form :model="linkForm" label-width="100px">
        <el-form-item label="源对象" required>
          <el-select v-model="linkForm.source_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标对象" required>
          <el-select v-model="linkForm.target_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联名"><el-input v-model="linkForm.name" /></el-form-item>
        <el-form-item label="基数">
          <el-select v-model="linkForm.card" style="width: 100%">
            <el-option label="多对一 many_to_one" value="many_to_one" />
            <el-option label="一对多 one_to_many" value="one_to_many" />
            <el-option label="多对多 many_to_many" value="many_to_many" />
          </el-select>
        </el-form-item>
        <el-form-item label="源字段"><el-input v-model="linkForm.source_field" /></el-form-item>
        <el-form-item label="目标字段"><el-input v-model="linkForm.target_field" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveLink">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作编辑 -->
    <el-dialog v-model="actionDialog" title="动作类型" width="560px" append-to-body>
      <el-form :model="actionForm" label-width="100px">
        <el-form-item label="动作名" required><el-input v-model="actionForm.name" /></el-form-item>
        <el-form-item label="编码" required><el-input v-model="actionForm.code" /></el-form-item>
        <el-form-item label="写回目标">
          <el-input v-model="actionForm.target_table" placeholder="ont_orders / video_cameras" />
        </el-form-item>
        <el-form-item label="方式">
          <el-select v-model="actionForm.method" style="width: 100%">
            <el-option label="update" value="update" />
            <el-option label="insert" value="insert" />
            <el-option label="delete" value="delete" />
          </el-select>
        </el-form-item>
        <el-form-item label="审批门禁"><el-switch v-model="actionForm.approval" /></el-form-item>
        <el-form-item label="白名单字段">
          <el-select
            v-model="actionForm.white_fields"
            multiple
            allow-create
            filterable
            placeholder="字段白名单"
            style="width: 100%"
          >
            <el-option v-for="p in props" :key="p.code" :label="p.name" :value="p.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveAction">保存</el-button>
      </template>
    </el-dialog>

    <!-- 函数编辑 -->
    <el-dialog v-model="funcDialog" title="本体计算函数" width="520px" append-to-body>
      <el-form :model="funcForm" label-width="100px">
        <el-form-item label="函数名" required>
          <el-input v-model="funcForm.name" placeholder="如 订单毛利率" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input v-model="funcForm.code" placeholder="gross_margin" />
        </el-form-item>
        <el-form-item label="表达式/逻辑">
          <el-input
            v-model="funcForm.expr"
            type="textarea"
            :rows="3"
            placeholder="如 (amount - cost) / amount"
          />
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="funcForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="funcDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveFunc">保存</el-button>
      </template>
    </el-dialog>

    <!-- 能力编辑 -->
    <el-dialog v-model="capDialog" title="本体能力" width="480px" append-to-body>
      <el-form :model="capForm" label-width="90px">
        <el-form-item label="编码" required>
          <el-input v-model="capForm.code" placeholder="如 retail_query" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="capForm.name" placeholder="如 零售问数" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="capForm.type" style="width: 100%">
            <el-option label="问数 query" value="query" />
            <el-option label="接地 grounding" value="grounding" />
            <el-option label="应用 app" value="app" />
            <el-option label="通用 generic" value="generic" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="capForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="capDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveCap">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Edit, MagicStick } from "@element-plus/icons-vue";
import {
  getOntObjects,
  getOntLinks,
  saveOntObject,
  getOntObjectFull,
  saveOntProperty,
  saveOntLink,
  saveOntAction,
  getOntFunctions,
  saveOntFunction,
  getOntChangelog,
  publishOntVersion,
  getOntVersions,
  getOntVersionDiff,
  rollbackOntVersion,
  getOntCapabilities,
  saveOntCapability,
  removeOnt,
  materializeOntObject,
} from "@/api/module_ai/ontology";
import { computed } from "vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import { getDqOverview } from "@/api/module_ai/query";

const objects = ref<any[]>([]);
const globalLinks = ref<any[]>([]);
const objectGraph = computed(() => {
  const objs = objects.value || [];
  const codeIdx: Record<string, number> = {};
  // 节点 id 与边 source/target 统一用「对象 code 字符串」，避免 cytoscape id 类型不一致导致边创建失败
  const nodes = objs.map((o, i) => {
    codeIdx[o.code] = i + 1;
    return { id: String(o.code), name: o.name || o.code, etype: "object" };
  });
  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = (globalLinks.value || [])
    .filter(
      (l) =>
        l.source_object &&
        l.target_object &&
        nodeIds.has(String(l.source_object)) &&
        nodeIds.has(String(l.target_object))
    )
    .map((l) => ({
      source: String(l.source_object),
      target: String(l.target_object),
      rtype: l.name || "link",
      weight: 1,
    }));
  return { nodes: nodes as any, edges: edges as any };
});
const current = ref<any>(null);
const currentCode = ref("");
const ontTab = ref("property");
const props = ref<any[]>([]);
const links = ref<any[]>([]);
const actions = ref<any[]>([]);
const functions = ref<any[]>([]);
const changelog = ref<any[]>([]);
const versions = ref<any[]>([]);
const caps = ref<any[]>([]);

async function loadObjects() {
  const r = await getOntObjects();
  objects.value = r.data?.data || [];
  // 默认选中第一个对象，右侧即时显示详情（界面饱满）
  if (objects.value.length && !currentCode.value) await selectObject(objects.value[0]);
  const lr = await getOntLinks();
  globalLinks.value = lr.data?.data || [];
  const cr = await getOntCapabilities();
  caps.value = cr.data?.data || [];
}
const dqDialog = ref(false);
const dqDetail = ref<any>(null);
async function onGraphNodeTap(name: string) {
  // 关系图节点名可能是对象 code 或名称，匹配后选中对象详情
  const target =
    objects.value.find((o: any) => String(o.code) === String(name)) ||
    objects.value.find((o: any) => o.name === name);
  if (target) await selectObject(target);
}
async function openDqDetail(o: any) {
  try {
    const r = await getDqOverview();
    const items = r.data?.data?.items || [];
    dqDetail.value = items.find((x: any) => x.table === o.code) || null;
    dqDialog.value = true;
  } catch {
    dqDetail.value = null;
    dqDialog.value = true;
  }
}
// 能力编辑
const capDialog = ref(false);
const capForm = reactive<any>({
  id: null,
  code: "",
  name: "",
  type: "generic",
  description: "",
  enabled: true,
});
function openCapEdit(c?: any) {
  Object.assign(
    capForm,
    c || { id: null, code: "", name: "", type: "generic", description: "", enabled: true }
  );
  capDialog.value = true;
}
async function saveCap() {
  if (!capForm.code?.trim() || !capForm.name?.trim()) return ElMessage.warning("请填能力编码/名称");
  await saveOntCapability({ ...capForm });
  ElMessage.success("已保存");
  capDialog.value = false;
  const cr = await getOntCapabilities();
  caps.value = cr.data?.data || [];
}
async function selectObject(o: any) {
  currentCode.value = o.code;
  current.value = o;
  const r = await getOntObjectFull(o.code);
  const d = r.data?.data || {};
  props.value = d.properties || [];
  links.value = d.links || [];
  actions.value = d.actions || [];
  const fr = await getOntFunctions(o.code);
  functions.value = fr.data?.data || [];
  const cr = await getOntChangelog(o.code);
  changelog.value = cr.data?.data || [];
  const vr = await getOntVersions(o.code);
  versions.value = vr.data?.data || [];
}

// 对象
const objDialog = ref(false);
const objForm = reactive<any>({
  id: null,
  name: "",
  code: "",
  icon: "el-icon-Box",
  key_prop: "id",
  name_prop: "name",
  description: "",
  enabled: true,
});
function openObjectEdit(o?: any) {
  Object.assign(
    objForm,
    o || {
      id: null,
      name: "",
      code: "",
      icon: "el-icon-Box",
      key_prop: "id",
      name_prop: "name",
      description: "",
      enabled: true,
    }
  );
  objDialog.value = true;
}
const savingObj = ref(false);
async function saveObj() {
  if (!objForm.code?.trim() || !objForm.name?.trim()) return ElMessage.warning("请填名称/编码");
  savingObj.value = true;
  try {
    await saveOntObject({ ...objForm });
    ElMessage.success("已保存");
    objDialog.value = false;
    await loadObjects();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingObj.value = false;
  }
}
async function removeObj(o: any) {
  await ElMessageBox.confirm(
    `将删除对象「${o.name}」及其属性/关联/动作定义（不影响真实数据表），是否继续？`,
    "删除确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await removeOnt("object", o.id);
  ElMessage.success("已删除");
  await loadObjects();
}

// 属性
const propDialog = ref(false);
const propForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  code: "",
  prop_type: "string",
  required: false,
  unique_col: false,
  sensitive: false,
  source_col: "",
  description: "",
  roles: [],
});
function openPropEdit(p?: any) {
  Object.assign(
    propForm,
    p || {
      id: null,
      object_code: currentCode.value,
      name: "",
      code: "",
      prop_type: "string",
      required: false,
      unique_col: false,
      sensitive: false,
      source_col: "",
      description: "",
      roles: [],
    }
  );
  propDialog.value = true;
}
async function saveProp() {
  if (!propForm.code?.trim() || !propForm.name?.trim()) return ElMessage.warning("请填写属性");
  await saveOntProperty({ ...propForm });
  ElMessage.success("已保存");
  propDialog.value = false;
  await selectObject(current.value);
}

// 关联
const linkDialog = ref(false);
const linkForm = reactive<any>({
  id: null,
  source_object: "",
  target_object: "",
  name: "",
  card: "many_to_one",
  source_field: "",
  target_field: "",
  description: "",
});
function openLinkEdit(l?: any) {
  Object.assign(
    linkForm,
    l || {
      id: null,
      source_object: currentCode.value,
      target_object: "",
      name: "",
      card: "many_to_one",
      source_field: "",
      target_field: "",
      description: "",
    }
  );
  linkDialog.value = true;
}
async function saveLink() {
  if (!linkForm.source_object || !linkForm.target_object)
    return ElMessage.warning("请选择源/目标对象");
  await saveOntLink({ ...linkForm });
  ElMessage.success("已保存");
  linkDialog.value = false;
  await selectObject(current.value);
}

// 动作
const actionDialog = ref(false);
const actionForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  code: "",
  target_table: "",
  method: "update",
  approval: false,
  white_fields: [],
  description: "",
});
function openActionEdit(a?: any) {
  Object.assign(
    actionForm,
    a || {
      id: null,
      object_code: currentCode.value,
      name: "",
      code: "",
      target_table: "",
      method: "update",
      approval: false,
      white_fields: [],
      description: "",
    }
  );
  actionDialog.value = true;
}
async function saveAction() {
  if (!actionForm.code?.trim() || !actionForm.name?.trim()) return ElMessage.warning("请填写动作");
  await saveOntAction({ ...actionForm });
  ElMessage.success("已保存");
  actionDialog.value = false;
  await selectObject(current.value);
}

function removeProp(p: any) {
  ElMessageBox.confirm(`删除属性「${p.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeOnt("property", p.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}
function removeLink(l: any) {
  ElMessageBox.confirm(
    `删除关联「${l.name || l.source_object + "-" + l.target_object}」?`,
    "确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  ).then(async () => {
    await removeOnt("link", l.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}
function removeAction(a: any) {
  ElMessageBox.confirm(`删除动作「${a.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeOnt("action", a.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}

// 函数
const funcDialog = ref(false);
const funcForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  code: "",
  expr: "",
  description: "",
});
function openFuncEdit(f?: any) {
  Object.assign(
    funcForm,
    f || { id: null, object_code: currentCode.value, name: "", code: "", expr: "", description: "" }
  );
  funcDialog.value = true;
}
async function saveFunc() {
  if (!funcForm.code?.trim() || !funcForm.name?.trim()) return ElMessage.warning("请填函数名/编码");
  savingObj.value = true;
  try {
    await saveOntFunction({ ...funcForm });
    ElMessage.success("已保存");
    funcDialog.value = false;
    await selectObject(current.value);
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingObj.value = false;
  }
}
async function publishVer(o: any) {
  const r = await publishOntVersion(o.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](d.ok ? `已发布版本 v${d.version}` : d.msg);
  await selectObject(o);
}
function rollbackVer(row: any) {
  ElMessageBox.confirm(`将本体的定义回滚到版本 v${row.version}？`, "确认", {
    type: "warning",
    confirmButtonText: "回滚",
    cancelButtonText: "取消",
  }).then(async () => {
    const r = await rollbackOntVersion(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.msg || "已回滚");
    await selectObject(current.value);  });
}
const diffDialog = ref(false);
const diffData = ref<any>(null);
async function openVersionDiff(row: any) {
  try {
    const r = await getOntVersionDiff(row.id);
    diffData.value = r.data?.data || null;
    diffDialog.value = true;
  } catch (e: any) {
    ElMessage.error(e?.message || "对比失败");
  }
}
function removeFunc(f: any) {
  ElMessageBox.confirm(`删除函数「${f.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeOnt("function", f.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}

// 物化
async function materialize(o: any) {
  const r = await materializeOntObject(o.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](d.msg || "已物化");
}

onMounted(async () => {
  await loadObjects();
  // 支持 ?code=xxx 从问数「使用本体」跳转并选中该对象
  try {
    const q = new URLSearchParams(window.location.hash.split("?")[1] || "");
    const code = q.get("code");
    if (code) {
      const target = objects.value.find((o: any) => o.code === code);
      if (target) await selectObject(target);
    }
  } catch {
    /* 忽略 */
  }
});
</script>

<style scoped lang="scss">
.ai-ontology-page {
  padding: 12px;
}
/* 左右白色卡片铺满可视区域（填满，不留下方大片留白） */
.ai-ontology-page .el-col {
  height: 100%;
}
.ai-ontology-page .el-card {
  height: 100%;
}
.ai-ontology-page .ont-left .el-card__body {
  overflow: auto;
}
/* 右侧卡片 body 撑满，空态垂直居中（不缩成很小一条） */
.ai-ontology-page .ont-right .el-card__body {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.ont-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ont-left {
  max-height: calc(100vh - 100px);
  overflow: auto;
}
.ont-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.ont-head__title {
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-head .el-button {
  flex-shrink: 0;
}
.ont-obj {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
}
.ont-obj.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.ont-obj__icon {
  color: var(--el-color-primary);
  font-size: 18px;
}
.ont-obj__meta {
  flex: 1;
  min-width: 0;
}
.ont-obj__name {
  font-size: 14px;
  font-weight: 600;
}
.ont-obj__code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-desc {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-bar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ont-none {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>

<style lang="scss">
/* 覆盖全局 .app-container(flex column;height:100%)：本体页改为块级自然流，避免能力卡撑满把下方对象/关系图区挤出不可见 */
.app-container.ai-ontology-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
.app-container.ai-ontology-page .el-card {
  height: auto !important;
}
.app-container.ai-ontology-page .ont-caps {
  margin-bottom: 12px;
}
</style>
