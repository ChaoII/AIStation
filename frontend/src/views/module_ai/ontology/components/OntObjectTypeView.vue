<!--
  对象类型视图（对齐 Palantir Ontology Manager 的 Object type 视图）
  Overview 严格按官方 7 个分区顺序：元数据 / 属性 / 动作类型 / 关系类型图 / 依赖 / 数据源 / 使用量
  子页：Overview、Properties、Security、Datasources、Usage
-->
<template>
  <div v-if="obj" class="ont-obj">
    <!-- 资源头部（对应官方截图顶部：图标 + 名称 + 对象数 + 操作） -->
    <div class="ont-obj__head">
      <div class="ont-obj__title">
        <el-icon class="ont-obj__icon"><component :is="iconName(obj.icon)" /></el-icon>
        <div class="ont-obj__names">
          <div class="ont-obj__name">{{ obj.name }}</div>
          <div class="ont-obj__sub">
            对象类型 · {{ obj.source_rows != null ? `${obj.source_rows} 个对象` : "对象数未统计" }}
          </div>
        </div>
        <el-tag v-if="obj.domain_code" size="small" effect="plain" class="ont-obj__group">
          {{ domainName(obj.domain_code) }}
        </el-tag>
      </div>
      <div class="ont-obj__ops">
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :icon="MagicStick"
          @click="doMaterialize"
        >
          物化为表
        </el-button>
        <el-button size="small" :icon="Edit" @click="emit('edit-object')">编辑</el-button>
      </div>
    </div>

    <!-- ============ 子页导航 ============ -->
    <el-tabs v-model="activeTab" class="ont-obj__tabs">
      <el-tab-pane v-for="t in PRIMARY_TABS" :key="t.value" :name="t.value" :label="t.label" />
      <el-tab-pane name="_more">
        <template #label>
          <el-dropdown trigger="click" @command="onMoreCommand">
            <span class="ont-obj__more-label">
              更多
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="t in MORE_TABS" :key="t.value" :command="t.value">
                  {{ t.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- ============ Overview：官方 7 分区 ============ -->
    <template v-if="page === 'overview'">
      <!-- 1 元数据（官方 14 项：名称/复数名/描述/别名/分组/API名 ⇄ 状态/可见性/索引/可编辑/ID/RID） -->
      <section class="ont-sec">
        <div class="ont-sec__head"><span class="ont-sec__title">元数据</span></div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="显示名">{{ obj.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" effect="plain" :type="statusTagType(obj.status)">
              {{ labelOf(ONT_STATUS, obj.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="复数显示名">
            {{ obj.plural_name || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="可见性">
            <el-tag size="small" effect="plain" :type="visibilityTagType(obj.visibility)">
              {{ labelOf(ONT_VISIBILITY, obj.visibility) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="描述">
            <span :class="{ 'ont-none': !obj.description }">{{ obj.description || "未填写" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="索引状态">
            <el-tag
              size="small"
              effect="plain"
              :type="
                obj.index_status === 'success'
                  ? 'success'
                  : obj.index_status === 'failed'
                    ? 'danger'
                    : 'info'
              "
            >
              {{ labelOf(ONT_INDEX_STATUS, obj.index_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="别名">
            <template v-if="obj.aliases?.length">
              <el-tag
                v-for="a in obj.aliases"
                :key="a"
                size="small"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ a }}
              </el-tag>
            </template>
            <span v-else class="ont-none">无</span>
          </el-descriptions-item>
          <el-descriptions-item label="可编辑（写回）">
            <el-tag size="small" effect="plain" :type="obj.edits_enabled ? 'success' : 'info'">
              {{ obj.edits_enabled ? "Enabled" : "Disabled" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="所属本体">
            {{ obj.domain_code ? domainName(obj.domain_code) : "未分组" }}
          </el-descriptions-item>
          <el-descriptions-item label="编码（ID）">
            <span class="ont-mono">{{ obj.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="API 名">
            <span class="ont-mono">{{ obj.api_name || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="RID">
            <span class="ont-mono ont-ellipsis">{{ obj.rid || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="联系人">
            {{ obj.point_of_contact || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="图标">
            <span class="ont-mono">{{ obj.icon || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="贡献者">
            <template v-if="obj.contributors?.length">
              <el-tag
                v-for="c in obj.contributors"
                :key="c"
                size="small"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ c }}
              </el-tag>
            </template>
            <span v-else class="ont-none">无</span>
          </el-descriptions-item>
          <el-descriptions-item label="启用">
            {{ obj.enabled ? "是" : "否" }}
          </el-descriptions-item>
          <el-descriptions-item label="主键属性（主键）">
            <span class="ont-mono">{{ obj.key_prop || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="标题属性（Title key）">
            <span class="ont-mono">{{ obj.name_prop || "—" }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- 数据源（支撑来源 / 字段映射，只读展示） -->
      <section class="ont-sec">
        <div class="ont-sec__head"><span class="ont-sec__title">数据源</span></div>
        <el-descriptions :column="2" size="small" border title="支撑来源">
          <el-descriptions-item label="支撑表（backing datasource）">
            <span class="ont-mono">{{ obj.backing_table || obj.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="字段映射">
            {{ mappedCount }} / {{ propList.length }} 已映射
          </el-descriptions-item>
          <el-descriptions-item label="数据源 ID">
            <span v-if="obj.datasource_id" class="ont-mono">#{{ obj.datasource_id }}</span>
            <span v-else class="ont-none">未关联（由外部同步导入）</span>
          </el-descriptions-item>
          <el-descriptions-item label="索引状态">
            <el-tag
              size="small"
              effect="plain"
              :type="
                obj.index_status === 'success'
                  ? 'success'
                  : obj.index_status === 'failed'
                    ? 'danger'
                    : 'info'
              "
            >
              {{ labelOf(ONT_INDEX_STATUS, obj.index_status) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">字段映射</span>
        </div>
        <el-table :data="propList" size="small" border max-height="300">
          <el-table-column prop="name" label="属性" min-width="150" show-overflow-tooltip />
          <el-table-column prop="code" label="属性 ID" min-width="130" show-overflow-tooltip />
          <el-table-column label="来源列" min-width="150">
            <template #default="{ row }">
              <span v-if="row.source_col" class="ont-mono">{{ row.source_col }}</span>
              <el-tag v-else size="small" type="info" effect="plain">仅 Action 填充</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="prop_type" label="类型" width="90" />
          <el-table-column prop="base_type" label="Base type" width="110">
            <template #default="{ row }">
              <span class="ont-mono">{{ row.base_type || "—" }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-alert
          type="info"
          :closable="false"
          class="ont-obj__note"
          title="索引状态由支撑表在数据库中的存在性推导（success = 能读到该表结构）。同步时间线需接入数据源同步记录，尚未提供。"
        />
      </section>

      <!-- 依赖（引用方，只读展示） -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">依赖</span>
          <el-tag size="small" type="info" effect="plain">{{ depTotal }}</el-tag>
          <el-button
            class="ont-sec__op"
            size="small"
            type="primary"
            link
            :loading="depLoading"
            @click="loadDependents"
          >
            刷新
          </el-button>
        </div>
        <div v-for="d in dependents" :key="d.kind" class="ont-dep">
          <span class="ont-dep__name">{{ d.kind }}</span>
          <el-tag size="small" effect="plain">{{ d.count }}</el-tag>
          <span class="ont-dep__items">{{ d.items.slice(0, 4).join("、") }}</span>
        </div>
        <div v-if="!dependents.length" class="ont-none">暂无引用方</div>
        <el-alert
          type="info"
          :closable="false"
          class="ont-obj__note"
          title="统计本体内部引用（关系/动作/函数）与外部引用（智能体 capabilities 中引用了本对象的函数/动作编码）。工作流等其它消费方尚未接入。"
        />
      </section>
    </template>

    <!-- ============ 关系类型 子页（类型层图） ============ -->
    <section v-else-if="page === 'relations'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">关系类型</span>
        <el-tag size="small" type="info" effect="plain">{{ rels.length }}</el-tag>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          link
          :icon="Plus"
          @click="emit('new-link')"
        >
          新建关系类型
        </el-button>
      </div>
      <OntTypeLinkGraph
        :code="obj.code"
        @node-tap="(c: string) => emit('open-object', c)"
        @create="emit('new-link')"
      />

      <!-- 关系类型列表：**详情 / 删除**入口。
           此前关系类型只能「新建」——详情组件（OntLinkTypeView）全仓无人引用，
           既看不了元数据/安全/用量，也删不掉。 -->
      <el-table :data="rels" size="small" border max-height="360" style="margin-top: 12px">
        <template #empty><el-empty :image-size="40" description="暂无关系类型" /></template>
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ relDir(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对端对象类型" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ relPeer(row) }}</template>
        </el-table-column>
        <el-table-column prop="card" label="基数" width="90" show-overflow-tooltip />
        <el-table-column prop="join_method" label="连接方式" width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button size="small" link @click="emit('open-link', row.id)">详情</el-button>
            <el-button size="small" type="danger" link @click="removeRel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============ Properties 子页 ============ -->
    <section v-else-if="page === 'properties'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">属性</span>
        <el-tag size="small" type="info" effect="plain">{{ propList.length }}</el-tag>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          :icon="Plus"
          @click="openPropEdit()"
        >
          新建属性
        </el-button>
      </div>
      <el-table :data="propList" size="small" border max-height="460">
        <template #empty><el-empty :image-size="50" description="暂无属性" /></template>
        <el-table-column prop="name" label="显示名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="code" label="属性 ID" min-width="110" show-overflow-tooltip />
        <el-table-column prop="api_name" label="API 名" min-width="120" show-overflow-tooltip />
        <el-table-column label="类型" width="86">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.prop_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Base type" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="ont-mono">{{ row.base_type || labelOf(ONT_BASE_TYPE, "") }}</span>
          </template>
        </el-table-column>
        <el-table-column label="键" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.code === obj.name_prop || row.title_key"
              size="small"
              type="success"
              effect="plain"
            >
              Title
            </el-tag>
            <el-tag v-if="row.code === obj.key_prop" size="small" type="warning" effect="plain">
              Primary
            </el-tag>
            <span
              v-if="row.code !== obj.name_prop && row.code !== obj.key_prop && !row.title_key"
              class="ont-none"
            >
              —
            </span>
          </template>
        </el-table-column>
        <el-table-column label="约束" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.required" size="small" type="danger" effect="plain">必填</el-tag>
            <el-tag v-if="row.unique_col" size="small" type="warning" effect="plain">唯一</el-tag>
            <el-tag v-if="row.sensitive" size="small" type="info" effect="plain">敏感</el-tag>
            <el-tag v-if="row.edit_only" size="small" effect="plain">仅 Action 填充</el-tag>
            <span
              v-if="!row.required && !row.unique_col && !row.sensitive && !row.edit_only"
              class="ont-none"
            >
              —
            </span>
          </template>
        </el-table-column>
        <el-table-column label="可见性" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="visibilityTagType(row.visibility)">
              {{ labelOf(ONT_VISIBILITY, row.visibility) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_col" label="来源列" min-width="100" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
        <el-table-column label="枚举" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.options?.length">{{ row.options.join(" / ") }}</span>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openPropEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeProp(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============ 动作类型 子页 ============ -->
    <section v-else-if="page === 'actions'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">动作类型</span>
        <el-tag size="small" type="info" effect="plain">{{ acts.length }}</el-tag>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          link
          :icon="Plus"
          @click="emit('new-action')"
        >
          新建
        </el-button>
      </div>
      <el-table :data="acts" size="small" border max-height="460">
        <template #empty><el-empty :image-size="40" description="暂无动作类型" /></template>
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" min-width="130" show-overflow-tooltip />
        <el-table-column
          prop="target_table"
          label="写回目标"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column label="审批" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.approval" size="small" type="warning" effect="plain">需审批</el-tag>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="170" align="center">
          <template #default="{ row }">
            <el-button size="small" type="success" link @click="openExec(row)">执行</el-button>
            <el-button size="small" link @click="emit('open-action', row.code)">详情</el-button>
            <el-button size="small" type="danger" link @click="removeAction(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============ Security 子页 ============ -->
    <section v-else-if="page === 'security'" class="ont-sec">
      <!-- P4：真正的对象权限（资源 ACL + 行级策略 + 列级角色 + Check access） -->
      <OntSecurityView :code="props.code" />
    </section>

    <!-- ============ 对象视图（A：Standard/Configured + Full/Panel + tabs→widgets） ============ -->
    <OntObjectViewPanel
      v-else-if="page === 'objectviews'"
      :code="props.code"
      :preset-view="props.viewCode || ''"
      :preset-key="props.viewKey || ''"
    />

    <!-- ============ 函数 ============ -->
    <OntObjectFunctions v-else-if="page === 'functions'" :code="props.code" />

    <!-- ============ 版本历史 ============ -->
    <OntObjectVersions
      v-else-if="page === 'versions'"
      :code="props.code"
      @refresh="emit('refresh')"
    />

    <!-- ============ 清理建议 ============ -->
    <OntObjectCleanup v-else-if="page === 'cleanup'" :code="props.code" />

    <!-- ============ 导入 / 导出 ============ -->
    <OntImportExport v-else-if="page === 'importexport'" :code="props.code" />

    <!-- ============ 指标（绑定到该对象的指标，S4） ============ -->
    <section v-else-if="page === 'metrics'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">指标</span>
      </div>
      <el-table v-loading="metricsLoading" :data="objectMetrics" size="small" border>
        <el-table-column prop="name" label="指标名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="key" label="指标 key" min-width="180" show-overflow-tooltip />
        <el-table-column prop="agg_fn" label="聚合" width="90" />
        <el-table-column label="维度" min-width="140">
          <template #default="{ row }">
            <span v-if="row.bound_dimensions?.length">
              {{ row.bound_dimensions.join("、") }}
            </span>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!metricsLoading && !objectMetrics.length"
        description="该对象暂无绑定指标（可在「数据与集成 / 语义建模」生成）"
      />
    </section>

    <!-- ============ Usage 子页 ============ -->
    <section v-else-if="page === 'usage'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">使用量</span>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          link
          :loading="usageLoading"
          @click="loadUsage(props.code)"
        >
          刷新
        </el-button>
      </div>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="8">
          <el-card shadow="never" class="ont-stat">
            <div class="ont-stat__label">读数（Agent 工具调用）</div>
            <div class="ont-stat__value">{{ usage.reads }}</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-card shadow="never" class="ont-stat">
            <div class="ont-stat__label">写入（动作执行）</div>
            <div class="ont-stat__value">{{ usage.writes }}</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-card shadow="never" class="ont-stat">
            <div class="ont-stat__label">交互（定义改动）</div>
            <div class="ont-stat__value">{{ usage.edits }}</div>
          </el-card>
        </el-col>
      </el-row>
      <el-alert
        type="info"
        :closable="false"
        class="ont-obj__note"
        title="数据来自既有日志表（Agent 调用日志 / 动作执行日志 / 定义变更留痕），未额外埋点。官方的「活跃用户数」需要按用户聚合调用日志，本版未做。"
      />
    </section>

    <!-- 属性编辑 -->
    <el-dialog v-model="propDialog" title="属性类型" width="560px" append-to-body>
      <el-form :model="propForm" label-width="100px">
        <el-form-item label="显示名" required><el-input v-model="propForm.name" /></el-form-item>
        <el-form-item label="属性 ID" required><el-input v-model="propForm.code" /></el-form-item>
        <el-form-item label="API 名">
          <el-input v-model="propForm.api_name" placeholder="留空则按属性 ID 自动推导 PascalCase" />
        </el-form-item>
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
        <el-form-item label="Base type">
          <el-select
            v-model="propForm.base_type"
            clearable
            placeholder="留空则按类型自动推导"
            style="width: 100%"
          >
            <el-option
              v-for="b in ONT_BASE_TYPE"
              :key="b.value"
              :label="b.label"
              :value="b.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="键">
          <el-checkbox v-model="propForm.title_key">标题键（Title key）</el-checkbox>
        </el-form-item>
        <el-form-item label="约束">
          <el-checkbox v-model="propForm.required">必填</el-checkbox>
          <el-checkbox v-model="propForm.unique_col">唯一</el-checkbox>
          <el-checkbox v-model="propForm.sensitive">敏感</el-checkbox>
          <el-checkbox v-model="propForm.edit_only">仅 Action 填充</el-checkbox>
        </el-form-item>
        <el-form-item label="可见性">
          <el-select v-model="propForm.visibility" style="width: 100%">
            <el-option
              v-for="v in ONT_VISIBILITY"
              :key="v.value"
              :label="v.label"
              :value="v.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="来源列">
          <el-input v-model="propForm.source_col" placeholder="映射真实表列（可空）" />
        </el-form-item>
        <el-form-item label="Render hint">
          <el-select v-model="propForm.render_hint" style="width: 100%">
            <el-option
              v-for="r in ONT_RENDER_HINT"
              :key="r.value"
              :label="r.label"
              :value="r.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="类型类别">
          <el-select v-model="propForm.type_class" clearable style="width: 100%">
            <el-option
              v-for="t in ONT_TYPE_CLASS"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>

        <!-- P5：共享属性引用 -->
        <template v-if="propForm.type_class === 'shared'">
          <el-form-item label="共享定义">
            <el-select
              v-model="propForm.shared_code"
              filterable
              clearable
              placeholder="选择共享属性"
              style="width: 100%"
              @change="onSharedPick"
            >
              <el-option
                v-for="s in sharedList"
                :key="s.code"
                :label="`${s.name}（${s.code}）· 被 ${s.ref_count} 处引用`"
                :value="s.code"
              />
            </el-select>
            <span class="ont-hint">
              只引用元数据（类型/约束/值类型），数据仍是本对象类型自己的列；改共享定义会同步过来
            </span>
          </el-form-item>
        </template>

        <!-- P5：派生属性 -->
        <template v-else-if="propForm.type_class === 'derived'">
          <el-form-item label="派生配置">
            <el-input
              v-model="propForm.derivedText"
              type="textarea"
              :rows="5"
              placeholder='{"source_object":"video_alarm_records","link_path":[27],"aggregation":"count","limit":10}'
            />
          </el-form-item>
          <el-form-item label="聚合方式">
            <el-select
              v-model="derivedAgg"
              clearable
              placeholder="选一个快速填入配置"
              style="width: 100%"
            >
              <el-option
                v-for="a in ONT_AGGREGATION"
                :key="a.value"
                :label="a.label"
                :value="a.value"
                @click="applyAgg(a.value)"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="试算">
            <el-input v-model="derivedKey" placeholder="实例主键，如 1" style="width: 140px" />
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              size="small"
              :loading="derivedRunning"
              @click="tryDerived"
            >
              试算
            </el-button>
            <span v-if="derivedResult !== null" class="ont-hint">结果：{{ derivedResult }}</span>
          </el-form-item>
          <el-alert
            type="warning"
            :closable="false"
            class="ont-obj__note"
            title="限制：关系链最多 3 层；collection limit 默认 10、最大 100；派生属性不能依赖另一个派生属性。"
          />
        </template>

        <!-- P5：Struct -->
        <template v-else-if="propForm.type_class === 'struct'">
          <el-form-item label="Struct 字段">
            <el-input
              v-model="propForm.structText"
              type="textarea"
              :rows="4"
              placeholder='[{"key":"x","name":"X","type":"number"},{"key":"y","name":"Y","type":"number"}]'
            />
            <span class="ont-hint">结构体由单个 struct 列支撑；这里描述它的字段组成</span>
          </el-form-item>
        </template>

        <el-form-item label="值类型">
          <el-select v-model="propForm.value_type_code" clearable style="width: 100%">
            <el-option
              v-for="v in valueTypeList"
              :key="v.code"
              :label="`${v.name}（${v.code}）`"
              :value="v.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="可见角色">
          <el-select
            v-model="propForm.roles"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="空 = 公开"
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
        <el-button type="primary" :loading="saving" @click="saveProp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作执行 -->
    <el-dialog v-model="execDialog" title="执行本体动作" width="560px" append-to-body>
      <el-alert
        v-if="execForm.approval"
        type="warning"
        :closable="false"
        class="ont-obj__note"
        title="该动作开启了审批门禁：不勾「已获审批」只会生成待审单，不会写库"
      />
      <el-form :model="execForm" label-width="110px">
        <el-form-item label="动作">
          <el-tag size="small" type="primary" effect="dark">{{ execForm.name }}</el-tag>
        </el-form-item>
        <el-form-item label="写回目标">{{ execForm.target_table }}</el-form-item>
        <el-form-item label="对象行 ID" required>
          <el-input v-model="execForm.object_key" placeholder="目标表主键 id" />
        </el-form-item>
        <el-form-item v-for="f in execForm.fields" :key="f.key" :label="f.label || f.key">
          <el-input v-model="execForm.params[f.key]" :placeholder="f.key" />
        </el-form-item>
        <el-form-item label="场景">
          <el-select
            v-model="scen"
            size="small"
            clearable
            placeholder="主本体（写真实表）"
            style="width: 100%"
            @visible-change="onScenOpen"
          >
            <el-option label="主本体（写真实表）" value="" />
            <el-option v-for="s in scenOptions" :key="s.code" :label="s.name" :value="s.code" />
          </el-select>
          <div class="ont-hint">选中场景则**只暂存差异、不写真实表**，合并场景后才生效</div>
        </el-form-item>
        <el-alert
          v-if="execForm.approval"
          type="warning"
          :closable="false"
          show-icon
          title="该动作需人工审批：提交后只会生成待审批单，由管理员批准后才会真正执行（执行人不能自我批准）。"
        />
      </el-form>
      <el-alert
        v-if="execResult"
        :title="execResult"
        :type="execOk ? 'success' : 'error'"
        :closable="false"
        class="ont-obj__note"
      />
      <template #footer>
        <el-button @click="execDialog = false">关闭</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:execute'"
          type="primary"
          :loading="execLoading"
          @click="runExec"
        >
          执行
        </el-button>
      </template>
    </el-dialog>
  </div>
  <el-empty v-else description="未找到该对象类型" />
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, Edit, MagicStick, Plus } from "@element-plus/icons-vue";
import {
  computeOntDerived,
  executeOntAction,
  getOntDependents,
  getOntObjectFull,
  getOntScenarios,
  getOntSharedProperties,
  getOntUsage,
  getOntValueTypes,
  materializeOntObject,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";
import { getQueryMetrics } from "@/api/module_ai/query";
import OntTypeLinkGraph from "./OntTypeLinkGraph.vue";
import OntObjectFunctions from "./OntObjectFunctions.vue";
import OntObjectVersions from "./OntObjectVersions.vue";
import OntObjectCleanup from "./OntObjectCleanup.vue";
import OntImportExport from "./OntImportExport.vue";
import {
  ONT_AGGREGATION,
  ONT_BASE_TYPE,
  ONT_INDEX_STATUS,
  ONT_RENDER_HINT,
  ONT_STATUS,
  ONT_TYPE_CLASS,
  ONT_VISIBILITY,
  deriveApiName,
  deriveBaseType,
  labelOf,
  statusTagType,
  visibilityTagType,
} from "../constants";

const props = defineProps<{ code: string; page: string; viewCode?: string; viewKey?: string }>();
const emit = defineEmits<{
  (e: "open-object", code: string): void;
  (e: "open-link", id: number): void;
  (e: "open-action", code: string): void;
  (e: "edit-object"): void;
  (e: "new-action"): void;
  (e: "new-link"): void;
  (e: "go-properties"): void;
  (e: "refresh"): void;
  (e: "update:page", page: string): void;
}>();

const TABS = [
  { value: "overview", label: "概览" },
  { value: "relations", label: "关系类型" },
  { value: "properties", label: "属性" },
  { value: "actions", label: "动作类型" },
  { value: "security", label: "安全" },
  { value: "objectviews", label: "对象视图" },
  { value: "usage", label: "使用量" },
  { value: "functions", label: "函数" },
  { value: "versions", label: "版本历史" },
  { value: "cleanup", label: "清理建议", folded: true },
  { value: "importexport", label: "导入导出", folded: true },
  { value: "metrics", label: "指标", folded: true },
];
// 高频 Tab 直接铺在导航栏；低频的折进「更多」下拉（降低 12-Tab 的信息密度）。
const PRIMARY_TABS = TABS.filter((t) => !t.folded);
const MORE_TABS = TABS.filter((t) => t.folded);
const FOLDED_VALUES = new Set(MORE_TABS.map((t) => t.value));
const activeTab = computed({
  get: () => (FOLDED_VALUES.has(props.page) ? "_more" : props.page || "overview"),
  set: (v: string) => emit("update:page", v),
});

function onMoreCommand(value: string) {
  activeTab.value = value;
}

const { domains, objectByCode, linksOf, actionsOf, functionsOf, stage } = useOntologyData();

const obj = computed(() => objectByCode(props.code));
const rels = computed(() => linksOf(props.code));
const acts = computed(() => actionsOf(props.code));
const funs = computed(() => functionsOf(props.code));

/* ---------- 绑定指标（S4） ---------- */
const objectMetrics = ref<any[]>([]);
const metricsLoading = ref(false);

async function loadObjectMetrics() {
  if (!props.code) {
    objectMetrics.value = [];
    return;
  }
  const ds = obj.value?.datasource_id ? `ds:${obj.value.datasource_id}` : "system";
  metricsLoading.value = true;
  try {
    const r: any = await getQueryMetrics(ds);
    const all = r?.data?.data ?? r?.data ?? [];
    objectMetrics.value = (Array.isArray(all) ? all : []).filter(
      (m: any) => m.object_code === props.code
    );
  } catch {
    objectMetrics.value = [];
  } finally {
    metricsLoading.value = false;
  }
}

watch(
  () => [props.page, props.code],
  () => {
    if (props.page === "metrics") loadObjectMetrics();
  }
);

function domainName(code: string) {
  return domains.value.find((d: any) => d.code === code)?.name || code;
}
/** 图标名兼容 "el-icon-Folder" 与 "Folder" 两种写法 */
function iconName(raw?: string) {
  const s = (raw || "Box").trim();
  return s.startsWith("el-icon-") ? s.slice("el-icon-".length) : s;
}

/* ---------- 属性明细 ---------- */
const propList = ref<any[]>([]);
const mappedCount = computed(() => propList.value.filter((p: any) => p.source_col).length);

async function loadDetail() {
  if (!props.code) return;
  const r = await getOntObjectFull(props.code);
  propList.value = r.data?.data?.properties || [];
}
watch(
  () => props.code,
  async () => {
    await loadDetail();
    await loadDependents();
    await loadUsage(props.code);
    await loadP5Options();
  },
  { immediate: true }
);

/* ---------- 用量 ---------- */
const usage = ref<any>({ reads: 0, writes: 0, edits: 0 });
const usageLoading = ref(false);
async function loadUsage(code: string) {
  if (!code) return;
  usageLoading.value = true;
  try {
    const r = await getOntUsage(code);
    usage.value = r.data?.data || { reads: 0, writes: 0, edits: 0 };
  } catch {
    usage.value = { reads: 0, writes: 0, edits: 0 };
  } finally {
    usageLoading.value = false;
  }
}

/* ---------- 依赖（本体内部引用 + 引用本对象的智能体） ---------- */
const depLoading = ref(false);
const depAgents = ref<any[]>([]);
const dependents = computed(() => {
  const list = [
    {
      kind: "智能体",
      items: depAgents.value.map((a: any) => `${a.name}（${a.matched.join("、")}）`),
    },
    {
      kind: "关系类型",
      items: rels.value.map((l: any) => l.name || `${l.source_object}→${l.target_object}`),
    },
    { kind: "动作类型", items: acts.value.map((a: any) => a.name) },
    { kind: "函数", items: funs.value.map((f: any) => f.name) },
  ].filter((d) => d.items.length);
  return list.map((d) => ({ ...d, count: d.items.length }));
});
const depTotal = computed(() => dependents.value.reduce((n: number, d: any) => n + d.count, 0));
async function loadDependents() {
  if (!props.code) return;
  depLoading.value = true;
  try {
    const r = await getOntDependents(props.code);
    depAgents.value = r.data?.data?.agents || [];
  } catch {
    depAgents.value = [];
  } finally {
    depLoading.value = false;
  }
}

/* ---------- 属性 CRUD ---------- */
const propDialog = ref(false);
const saving = ref(false);
const propBlank = () => ({
  id: null,
  object_code: props.code,
  name: "",
  code: "",
  api_name: "",
  prop_type: "string",
  base_type: "",
  title_key: false,
  required: false,
  unique_col: false,
  sensitive: false,
  edit_only: false,
  visibility: "normal",
  render_hint: "",
  type_class: "",
  source_col: "",
  description: "",
  roles: [] as string[],
  // ---- P5 ----
  shared_code: "",
  value_type_code: "",
  derivedText: "{}",
  structText: "[]",
});
const propForm = reactive<any>(propBlank());

/* ---------- P5：共享属性 / 值类型 / 派生 ---------- */
const sharedList = ref<any[]>([]);
const valueTypeList = ref<any[]>([]);
const derivedAgg = ref("");
const derivedKey = ref("");
const derivedResult = ref<any>(null);
const derivedRunning = ref(false);
async function loadP5Options() {
  try {
    const [a, b] = await Promise.all([getOntSharedProperties(), getOntValueTypes()]);
    sharedList.value = a.data?.data || [];
    valueTypeList.value = b.data?.data || [];
  } catch {
    sharedList.value = [];
    valueTypeList.value = [];
  }
}
/** 选了共享定义 → 把它的元数据带过来（只带元数据，不带数据） */
function onSharedPick(code: string) {
  const s = sharedList.value.find((x) => x.code === code);
  if (!s) return;
  propForm.prop_type = s.prop_type;
  propForm.base_type = s.base_type;
  propForm.api_name = s.api_name;
  propForm.value_type_code = s.value_type_code;
}
function applyAgg(v: string) {
  let cfg: any = {};
  try {
    cfg = JSON.parse(propForm.derivedText || "{}");
  } catch {
    cfg = {};
  }
  cfg.aggregation = v;
  cfg.limit = cfg.limit || 10;
  propForm.derivedText = JSON.stringify(cfg, null, 2);
}
async function tryDerived() {
  if (!derivedKey.value) return ElMessage.warning("请填实例主键");
  if (!propForm.code) return ElMessage.warning("请先填属性 ID 并保存该属性，才能试算");
  derivedRunning.value = true;
  try {
    const r = await computeOntDerived({
      object_code: props.code,
      key: derivedKey.value,
      property: propForm.code,
    });
    const d = r.data?.data || {};
    if (!d.ok) {
      derivedResult.value = null;
      return ElMessage.warning(d.msg || "试算失败");
    }
    derivedResult.value = JSON.stringify(d.value);
    ElMessage.success(`匹配 ${d.matched} 条，${d.hops} 层`);
  } catch (e: any) {
    ElMessage.error(e?.msg || "试算失败");
  } finally {
    derivedRunning.value = false;
  }
}
function openPropEdit(p?: any) {
  Object.assign(propForm, propBlank(), p ? { ...p } : {});
  propForm.derivedText =
    p?.derived && Object.keys(p.derived).length ? JSON.stringify(p.derived, null, 2) : "{}";
  propForm.structText = p?.struct_fields?.length ? JSON.stringify(p.struct_fields, null, 2) : "[]";
  derivedResult.value = null;
  propDialog.value = true;
}
async function saveProp() {
  if (!propForm.code?.trim() || !propForm.name?.trim())
    return ElMessage.warning("请填显示名与属性 ID");
  saving.value = true;
  try {
    // API 名与 base type 留空时按官方规则自动推导
    const payload: Record<string, any> = { ...propForm };
    // P5：把两个 JSON 文本框解析成真正的字段
    if (propForm.type_class === "derived") {
      try {
        payload.derived = JSON.parse(propForm.derivedText || "{}");
      } catch {
        saving.value = false;
        return ElMessage.error("派生配置不是合法 JSON");
      }
    } else {
      payload.derived = {};
    }
    if (propForm.type_class === "struct") {
      try {
        payload.struct_fields = JSON.parse(propForm.structText || "[]");
      } catch {
        saving.value = false;
        return ElMessage.error("Struct 字段不是合法 JSON");
      }
    } else {
      payload.struct_fields = [];
    }
    if (propForm.type_class !== "shared") payload.shared_code = "";
    delete payload.derivedText;
    delete payload.structText;
    payload.api_name = propForm.api_name?.trim() || deriveApiName(propForm.code);
    payload.base_type = propForm.base_type || deriveBaseType(propForm.prop_type, propForm.code);
    await stage("property", payload.id ? "update" : "create", payload);
    propDialog.value = false;
    await loadDetail();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "暂存失败");
  } finally {
    saving.value = false;
  }
}
function removeProp(p: any) {
  ElMessageBox.confirm(
    `将删除属性「${p.name}」及其定义（不影响真实数据表的列）。改动会先进入待保存列表，确认删除？`,
    "删除属性",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  ).then(async () => {
    await stage("property", "delete", {
      id: p.id,
      code: p.code,
      object_code: p.object_code,
      name: p.name,
    });
    await loadDetail();
    emit("refresh");
  });
}

/* ---------- 关系类型 / 动作类型：详情入口与删除 ---------- */

/** 关系方向（相对当前对象类型）：出/入/自反 */
function relDir(row: any): string {
  const src = row?.source_object === props.code;
  const tgt = row?.target_object === props.code;
  if (src && tgt) return "自反";
  return src ? "出" : "入";
}

/** 对端对象类型（相对当前对象类型取另一头） */
function relPeer(row: any): string {
  const src = row?.source_object === props.code;
  return String((src ? row?.target_object : row?.source_object) || "");
}

function removeRel(row: any) {
  ElMessageBox.confirm(
    `将删除关系类型「${row?.name || row?.id}」（影响该关系的实例层跳转与图谱连线；改动先进入待保存列表）。确认删除？`,
    "删除关系类型",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  ).then(async () => {
    await stage("link", "delete", {
      id: row?.id,
      name: row?.name,
      source_object: row?.source_object,
      target_object: row?.target_object,
    });
    await loadDetail();
    emit("refresh");
  });
}

function removeAction(row: any) {
  ElMessageBox.confirm(
    `将删除动作类型「${row?.name || row?.code}」（其写回/审批配置一并移除；改动先进入待保存列表）。确认删除？`,
    "删除动作类型",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  ).then(async () => {
    await stage("action", "delete", {
      id: row?.id,
      code: row?.code,
      object_code: row?.object_code || props.code,
      name: row?.name,
    });
    await loadDetail();
    emit("refresh");
  });
}

/* ---------- 物化 ---------- */
async function doMaterialize() {
  const r = await materializeOntObject(props.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](r.data?.msg || d.msg || "已物化");
}

/* ---------- 动作执行 ---------- */
const execDialog = ref(false);
// 场景（P5）：选中则动作只暂存到场景，不写真实表
const scen = ref("");
const scenOptions = ref<{ code: string; name: string }[]>([]);

async function onScenOpen(open: boolean) {
  if (!open || scenOptions.value.length) return;
  try {
    const r = await getOntScenarios({ limit: 300 });
    scenOptions.value = ((r.data?.data || []) as any[])
      .filter((s: any) => s.status === "active")
      .map((s: any) => ({ code: s.code, name: s.name }));
  } catch {
    scenOptions.value = [];
  }
}
const execLoading = ref(false);
const execResult = ref("");
const execOk = ref(false);
const execForm = reactive<any>({
  code: "",
  name: "",
  target_table: "",
  approval: false,
  object_key: "",
  params: {} as Record<string, any>,
  fields: [] as any[],
});
function openExec(a: any) {
  const wf = (a.white_fields || []).map((w: any) => (typeof w === "string" ? w : w.key));
  const sch = (a.input_schema || []) as any[];
  const fields = sch.length
    ? sch.map((f: any) => ({ key: f.key, label: f.label || f.key }))
    : wf.map((k: string) => ({ key: k, label: k }));
  const params: Record<string, any> = {};
  fields.forEach((f: any) => (params[f.key] = ""));
  Object.assign(execForm, {
    code: a.code,
    name: a.name,
    target_table: a.target_table || "",
    approval: !!a.approval,
    object_key: "",
    params,
    fields,
  });
  execResult.value = "";
  execOk.value = false;
  execDialog.value = true;
}
async function runExec() {
  if (!execForm.object_key) return ElMessage.warning("请填对象行 ID");
  const params: Record<string, any> = {};
  Object.keys(execForm.params).forEach((k) => {
    const v = execForm.params[k];
    if (v !== "" && v != null) params[k] = v;
  });
  if (!Object.keys(params).length) return ElMessage.warning("请至少填一个要写入的字段");
  execLoading.value = true;
  try {
    const r = await executeOntAction({
      code: execForm.code,
      object_key: execForm.object_key,
      params,
      scenario: scen.value,
    });
    const d = r.data?.data || {};
    execOk.value = !!d.ok;
    execResult.value = r.data?.msg || d.msg || (d.ok ? "已执行" : "执行失败");
    ElMessage[execOk.value ? "success" : "warning"](execResult.value);
  } catch (e: any) {
    execOk.value = false;
    execResult.value = e?.msg || "执行失败";
    ElMessage.error(execResult.value);
  } finally {
    execLoading.value = false;
  }
}
</script>

<style scoped lang="scss">
.ont-obj__head {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ont-obj__title {
  display: flex;
  align-items: center;
  min-width: 0;
}
.ont-obj__icon {
  margin-right: 8px;
  font-size: var(--el-font-size-extra-large);
  color: var(--el-color-primary);
}
.ont-obj__names {
  min-width: 0;
}
.ont-obj__name {
  font-size: var(--el-font-size-medium);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-obj__sub {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-obj__group {
  margin-left: 10px;
}
.ont-obj__ops {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}
.ont-obj__note {
  margin-top: 8px;
}
.ont-sec {
  padding: 12px;
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.ont-sec__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-sec__head--mt {
  margin-top: 12px;
}
.ont-sec__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-sec__op {
  margin-left: auto;
}
.ont-prop-list__row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ont-prop-list__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  white-space: nowrap;
}
.ont-prop-list__type {
  margin-left: auto;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-act-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ont-act-row__icon {
  color: var(--el-color-primary);
}
.ont-act-row__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  white-space: nowrap;
}
.ont-dep {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: var(--el-font-size-base);
}
.ont-dep__name {
  width: 80px;
  color: var(--el-text-color-regular);
}
.ont-dep__items {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.ont-mono {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-extra-small);
}
.ont-tag-gap {
  margin-right: 4px;
}
.ont-none {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-placeholder);
}
.ont-ellipsis {
  display: inline-block;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
}
/* ---------- 用量 ---------- */
.ont-usage {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ont-usage__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ont-usage__label {
  color: var(--el-text-color-secondary);
}
.ont-usage__value {
  font-weight: 600;
  color: var(--el-color-primary);
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
</style>

<style lang="scss">
/* 对象类型详情：Tab 导航条「吸顶」—— 滚动到任意位置都能一键切换子页（#11 全局 Tab 快速跳转）。
   用非 scoped（.ont-obj__tabs 根由 Element Plus el-tabs 渲染，scoped data-v 不会命中）。
   注意要点：el-tabs 在本页只是「纯导航」，pane 内容为空、真正的分区内容是兄弟模板，
   因此 el-tabs 根仅 ~47px 高；若只给 .el-tabs__header 加 sticky，其父(elt-tabs)太矮无法行程、
   不生效，须给整条 .ont-obj__tabs 加 sticky。 */
.ont-obj__tabs {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--el-bg-color);
}
</style>
