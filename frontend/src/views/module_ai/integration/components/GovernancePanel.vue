<!-- 治理面板（Governance / Oversight）：驾驶舱 + ABAC + DQ + 数据域 + 本体对象。
     作为「数据与集成」的一个内嵌区块，承载原「治理」菜单的 5 个子模块。 -->
<template>
  <div class="gp-wrap">
    <el-tabs v-model="tab" @tab-change="onTab">
      <!-- 驾驶舱 -->
      <el-tab-pane label="驾驶舱" name="overview">
        <el-card shadow="never" style="margin-bottom: 12px">
          <template #header>治理驾驶舱（Governance Overview）</template>
          <el-row :gutter="12">
            <el-col :span="3">
              <el-statistic title="业务对象" :value="g.overview?.objects ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="数据源" :value="g.overview?.datasources ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="数据管道" :value="g.overview?.pipelines ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="ABAC 策略" :value="g.overview?.access_rules ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="数据域" :value="g.overview?.domains ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="智能体" :value="g.overview?.agents ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic title="动作审计" :value="g.overview?.action_logs ?? 0" />
            </el-col>
            <el-col :span="3">
              <el-statistic
                title="平均健康分"
                :value="g.overview?.dq?.avg_score ?? 0"
                :precision="1"
              />
            </el-col>
          </el-row>
        </el-card>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>
                <div class="gp-head">
                  <span>数据质量（DQ）</span>
                  <el-tag v-if="(g.overview?.dq_alerts ?? 0) > 0" size="small" type="danger">
                    预警 {{ g.overview.dq_alerts }}
                  </el-tag>
                </div>
              </template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item label="平均健康分">
                  {{ g.overview?.dq?.avg_score ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="健康/预警/共">
                  {{ g.overview?.dq?.healthy ?? 0 }} / {{ g.overview?.dq?.risk ?? 0 }} /
                  {{ g.overview?.dq?.total ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="gp-section">质量预警</div>
              <div v-for="a in g.overview?.alert_list || []" :key="a.table" class="gp-alert">
                <el-tag size="small" type="danger">{{ a.alias }}</el-tag>
                <span class="gp-score">健康分 {{ a.score }}</span>
                <div class="gp-down">
                  <el-tag
                    v-for="o in a.downstream.objects"
                    :key="o"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    对象 {{ o }}
                  </el-tag>
                  <el-tag
                    v-for="m in a.downstream.metrics"
                    :key="m"
                    size="small"
                    type="primary"
                    effect="plain"
                  >
                    指标 {{ m }}
                  </el-tag>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>资产与语义资产</template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item label="指标">
                  {{ g.overview?.metrics ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="术语">
                  {{ g.overview?.terms ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="本体概念">
                  {{ g.overview?.concepts ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="对象应用">
                  {{ g.overview?.workshop_apps ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="动作定义">
                  {{ g.overview?.actions ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="动作审计">
                  {{ g.overview?.action_logs ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="gp-section">最近管道运行</div>
              <el-table :data="g.overview?.pipeline_runs || []" size="small" max-height="200">
                <el-table-column prop="name" label="管道" min-width="120" />
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.status === 'success' ? 'success' : 'info'">
                      {{ row.status }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="at" label="运行时间" min-width="140" show-overflow-tooltip />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ABAC 权限 -->
      <el-tab-pane label="权限" name="access">
        <div class="gp-bar">
          <el-button type="primary" size="small" :icon="Plus" @click="openAccess()">
            新建策略
          </el-button>
          <el-button size="small" @click="openMatrix">权限矩阵</el-button>
          <el-button size="small" @click="openSandbox">权限沙箱</el-button>
          <el-tag size="small" type="info" effect="plain">
            共 {{ accessRules.length }} 条 ABAC 策略
          </el-tag>
        </div>
        <el-alert
          type="info"
          :closable="false"
          style="margin-bottom: 10px"
          title="ABAC：超管默认可见全部；命中「敏感放行」可查看敏感对象字段，否则 resolve/问数自动剔除敏感字段。"
        />
        <el-table :data="accessRules" size="small" border>
          <template #empty>
            <el-empty description="暂无 ABAC 策略，点击「新建策略」配置访问管控" :image-size="60" />
          </template>
          <el-table-column prop="name" label="策略" min-width="130" show-overflow-tooltip />
          <el-table-column prop="attribute" label="属性" width="80" />
          <el-table-column prop="value" label="属性值" width="120" show-overflow-tooltip />
          <el-table-column label="允许对象" min-width="150">
            <template #default="{ row }">
              <el-tag
                v-for="t in row.allowed_tables"
                :key="t"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ t }}
              </el-tag>
              <el-tag v-if="!row.allowed_tables?.length" size="small" type="info" effect="plain">
                全部
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="敏感放行" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
                {{ row.sensitive_ok ? "是" : "否" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editAccess(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="delAccess(row)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据质量 -->
      <el-tab-pane label="数据质量" name="dq">
        <div class="gp-bar">
          <el-button
            type="primary"
            size="small"
            :icon="Refresh"
            :loading="dqScanning"
            @click="scanAll"
          >
            扫描全部对象
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            平均分 {{ dqData.avg_score ?? "-" }} · 健康 {{ dqData.healthy ?? 0 }} · 风险
            {{ dqData.risk ?? 0 }}
          </el-tag>
        </div>
        <div v-if="dqAlerts.length" class="gp-alert gp-alert--warn">
          <el-alert
            type="warning"
            :closable="false"
            :title="`质量预警：${dqAlerts.length} 个对象健康分低于 60`"
            show-icon
          />
        </div>
        <el-table :data="dqData.items || []" size="small" border>
          <template #empty>
            <el-empty description="暂无数据质量结果，点击「扫描全部对象」" :image-size="60" />
          </template>
          <el-table-column prop="alias" label="对象" min-width="110" show-overflow-tooltip />
          <el-table-column prop="table" label="表" min-width="140" show-overflow-tooltip />
          <el-table-column label="健康分" width="170">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score || 0)"
                :color="
                  (row.score || 0) >= 80
                    ? '#67c23a'
                    : (row.score || 0) >= 60
                      ? '#e6a23c'
                      : '#f56c6c'
                "
                :stroke-width="10"
              />
            </template>
          </el-table-column>
          <el-table-column prop="total" label="行数" width="80" />
          <el-table-column label="问题" min-width="180">
            <template #default="{ row }">
              <el-tag
                v-for="(i, k) in row.issues || []"
                :key="k"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                {{ i }}
              </el-tag>
              <span v-if="!(row.issues || []).length" class="gp-empty">无</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据域 -->
      <el-tab-pane label="数据域" name="domain">
        <div class="gp-bar">
          <el-button type="primary" size="small" :icon="Plus" @click="openDomain()">
            新建数据域
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            共 {{ domainView.domains?.length || 0 }} 个域 · 未归属
            {{ domainView.unassigned?.length || 0 }}
          </el-tag>
        </div>
        <el-row :gutter="12">
          <el-col v-for="d in domainView.domains || []" :key="d.id" :span="12">
            <el-card shadow="never" style="margin-bottom: 12px">
              <template #header>
                <div class="gp-head">
                  <span>
                    <el-tag size="small" type="primary" effect="dark">{{ d.name }}</el-tag>
                    <el-tag size="small" type="info" effect="plain" style="margin-left: 6px">
                      {{ d.code }}
                    </el-tag>
                  </span>
                  <el-button link type="primary" size="small" @click="editDomain(d)">
                    编辑
                  </el-button>
                  <el-button link type="danger" size="small" @click="delDomain(d)">删</el-button>
                </div>
              </template>
              <div class="gp-section">对象（{{ d.objects.length }}）</div>
              <el-tag
                v-for="o in d.objects"
                :key="o.table"
                size="small"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                {{ o.alias }}
              </el-tag>
              <div class="gp-section">成员用户ID</div>
              <el-tag
                v-for="m in d.members"
                :key="m"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                #{{ m }}
              </el-tag>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 本体对象 -->
      <el-tab-pane label="本体对象" name="ontgov">
        <div class="gp-bar">
          <el-tag size="small" type="info" effect="plain">
            本体对象 · 来源管道 / 下游 / 数据质量分 | 平均 {{ ontGov.avg_score ?? "-" }}
          </el-tag>
        </div>
        <el-table :data="ontGov.items || []" size="small" border>
          <template #empty>
            <el-empty description="暂无本体对象，请先在「本体」页定义对象并物化" :image-size="60" />
          </template>
          <el-table-column prop="name" label="本体对象" min-width="110" show-overflow-tooltip />
          <el-table-column prop="table" label="表" min-width="110" show-overflow-tooltip />
          <el-table-column prop="rows" label="行数" width="80" />
          <el-table-column label="质量分" width="170">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score || 0)"
                :color="
                  (row.score || 0) >= 80
                    ? '#67c23a'
                    : (row.score || 0) >= 60
                      ? '#e6a23c'
                      : '#f56c6c'
                "
                :stroke-width="10"
              />
            </template>
          </el-table-column>
          <el-table-column label="来源管道" min-width="120">
            <template #default="{ row }">
              <el-tag
                v-for="p in row.source_pipelines"
                :key="p"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ p }}
              </el-tag>
              <span v-if="!row.source_pipelines.length" class="gp-empty">—</span>
            </template>
          </el-table-column>
          <el-table-column label="下游指标/概念" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="m in row.downstream_metrics"
                :key="m"
                size="small"
                type="primary"
                effect="plain"
                style="margin: 0 2px"
              >
                指标 {{ m }}
              </el-tag>
              <el-tag
                v-for="c in row.downstream_concepts"
                :key="c"
                size="small"
                type="success"
                effect="plain"
                style="margin: 0 2px"
              >
                概念 {{ c }}
              </el-tag>
              <span
                v-if="!row.downstream_metrics.length && !row.downstream_concepts.length"
                class="gp-empty"
              >
                —
              </span>
            </template>
          </el-table-column>
          <el-table-column label="问题" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="(i, k) in row.issues"
                :key="k"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ i }}
              </el-tag>
              <span v-if="!row.issues.length" class="gp-empty">无</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 动作审批：写回动作的待审批/定义/审计 -->
      <el-tab-pane label="动作审批" name="action">
        <div class="gp-bar">
          <el-tag size="small" type="info" effect="plain">
            待审批动作 {{ pendingActions.length }} · 动作定义 {{ actionList.length }}
          </el-tag>
        </div>
        <div class="gp-section">待审批（写回需人工批准，批准后生效）</div>
        <el-table :data="pendingActions" size="small" border style="margin-bottom: 16px">
          <template #empty>
            <el-empty description="暂无待审批动作" :image-size="50" />
          </template>
          <el-table-column prop="action" label="动作" width="120" show-overflow-tooltip />
          <el-table-column prop="table" label="对象表" min-width="130" show-overflow-tooltip />
          <el-table-column prop="key" label="记录" width="80" />
          <el-table-column label="参数" min-width="160">
            <template #default="{ row }">
              <div class="gp-params">{{ JSON.stringify(row.params || {}) }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="80" />
          <el-table-column prop="time" label="时间" min-width="150" show-overflow-tooltip />
          <el-table-column label="操作" width="130" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="apAction(row, true)">
                批准
              </el-button>
              <el-button link type="danger" size="small" @click="apAction(row, false)">
                驳回
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="gp-section">动作定义（对象可写列 / 校验 / 是否需审批）</div>
        <el-table :data="actionList" size="small" border>
          <template #empty>
            <el-empty description="暂无动作定义" :image-size="50" />
          </template>
          <el-table-column prop="name" label="动作" width="120" show-overflow-tooltip />
          <el-table-column
            prop="object_table"
            label="对象表"
            min-width="130"
            show-overflow-tooltip
          />
          <el-table-column label="可写列" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="c in row.writable_cols"
                :key="c"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ c }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="validation" label="校验" min-width="120" show-overflow-tooltip />
          <el-table-column label="需审批" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.approve ? 'warning' : 'info'" effect="plain">
                {{ row.approve ? "是" : "否" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
                {{ row.enabled ? "是" : "否" }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="gp-section">审计日志（最近 50 条）</div>
        <el-table :data="actionLogs" size="small" border max-height="260">
          <template #empty>
            <el-empty description="暂无审计日志" :image-size="50" />
          </template>
          <el-table-column prop="action" label="动作" width="120" show-overflow-tooltip />
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'approved' ? 'success' : 'info'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="80" />
          <el-table-column prop="time" label="时间" min-width="150" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 权限策略编辑 -->
    <el-dialog v-model="accessDialog" title="ABAC 权限策略" width="520px" append-to-body>
      <el-form :model="accessForm" label-width="100px">
        <el-form-item label="策略名称" required>
          <el-input v-model="accessForm.name" placeholder="如 生产部可看敏感" />
        </el-form-item>
        <el-form-item label="属性">
          <el-select v-model="accessForm.attribute" style="width: 100%">
            <el-option label="角色 role" value="role" />
            <el-option label="部门 dept" value="dept" />
            <el-option label="数据域 domain" value="domain" />
          </el-select>
        </el-form-item>
        <el-form-item label="属性值" required>
          <el-input v-model="accessForm.value" placeholder="production / 生产部" />
        </el-form-item>
        <el-form-item label="允许对象">
          <el-select
            v-model="accessForm.allowed_tables"
            multiple
            clearable
            filterable
            placeholder="空=全部"
            style="width: 100%"
          >
            <el-option
              v-for="o in govObjects"
              :key="o.table"
              :label="(o.alias || o.table) + ' (' + o.table + ')'"
              :value="o.table"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="敏感放行">
          <el-switch v-model="accessForm.sensitive_ok" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accessDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAccessForm()">保存</el-button>
      </template>
    </el-dialog>

    <!-- 权限矩阵（按角色） -->
    <el-dialog v-model="matrixDialog" title="数据域权限矩阵（按角色）" width="720px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
        title="每个系统角色「合并后」可查询的对象清单；未命中策略即不受限（默认全部）。"
      />
      <el-table v-loading="matrixLoading" :data="matrixRows" size="small" border max-height="420">
        <template #empty>
          <el-empty description="暂无角色" :image-size="60" />
        </template>
        <el-table-column prop="name" label="角色" width="150" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" width="150" show-overflow-tooltip />
        <el-table-column label="是否受限" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.restricted ? 'warning' : 'info'" effect="plain">
              {{ row.restricted ? "受限" : "不限" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="可查对象" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="!row.restricted" size="small" type="info" effect="plain">全部</el-tag>
            <template v-else>
              <el-tag
                v-for="t in row.tables.slice(0, 6)"
                :key="t"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ t }}
              </el-tag>
              <el-text v-if="row.tables.length > 6" size="small" type="info">
                +{{ row.tables.length - 6 }}
              </el-text>
              <el-text v-if="!row.tables.length" size="small" type="info">无</el-text>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="敏感放行" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
              {{ row.sensitive_ok ? "是" : "否" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 权限沙箱（按用户/角色预览可查表） -->
    <el-dialog v-model="sandboxDialog" title="权限沙箱" width="720px" append-to-body>
      <el-form label-width="80px" inline>
        <el-form-item label="按用户">
          <el-input-number
            v-model="sandboxUserId"
            :min="0"
            :controls="false"
            style="width: 110px"
          />
          <el-button
            size="small"
            type="primary"
            :loading="sandboxLoading"
            style="margin-left: 8px"
            @click="runSandboxUser"
          >
            预览
          </el-button>
        </el-form-item>
        <el-form-item label="按角色">
          <el-select
            v-model="sandboxRole"
            size="small"
            clearable
            placeholder="选择角色"
            style="width: 160px"
          >
            <el-option v-for="r in matrixRows" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
          <el-button
            size="small"
            type="primary"
            :loading="sandboxLoading"
            style="margin-left: 8px"
            @click="runSandboxRole"
          >
            预览
          </el-button>
        </el-form-item>
      </el-form>
      <el-descriptions v-if="sandboxResult" :column="2" size="small" border>
        <el-descriptions-item label="主体">{{ sandboxResult.label }}</el-descriptions-item>
        <el-descriptions-item label="是否受限">
          <el-tag size="small" :type="sandboxResult.restricted ? 'warning' : 'info'" effect="plain">
            {{ sandboxResult.restricted ? "受限" : "不限" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="可查对象数">{{ sandboxResult.count }}</el-descriptions-item>
        <el-descriptions-item label="敏感放行">
          <el-tag
            size="small"
            :type="sandboxResult.sensitive_ok ? 'success' : 'info'"
            effect="plain"
          >
            {{ sandboxResult.sensitive_ok ? "是" : "否" }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="sandboxResult" style="margin-top: 10px">
        <el-tag
          v-for="t in sandboxResult.tables"
          :key="t"
          size="small"
          effect="plain"
          style="margin: 2px"
        >
          {{ t }}
        </el-tag>
        <el-text v-if="!sandboxResult.tables.length" size="small" type="info">无可查对象</el-text>
      </div>
      <el-empty v-else description="选择用户或角色后点「预览」" :image-size="60" />
    </el-dialog>

    <!-- 数据域编辑 -->
    <el-dialog v-model="domainDialog" title="数据域" width="520px" append-to-body>
      <el-form :model="domainForm" label-width="100px">
        <el-form-item label="域名称" required>
          <el-input v-model="domainForm.name" placeholder="如 生产域" />
        </el-form-item>
        <el-form-item label="域编码">
          <el-input v-model="domainForm.code" placeholder="prod" />
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="domainForm.description" /></el-form-item>
        <el-form-item label="对象">
          <el-select
            v-model="domainForm.tables"
            multiple
            filterable
            clearable
            placeholder="本域对象"
            style="width: 100%"
          >
            <el-option
              v-for="o in govObjects"
              :key="o.table"
              :label="(o.alias || o.table) + ' (' + o.table + ')'"
              :value="o.table"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="成员用户">
          <el-select
            v-model="domainForm.members"
            multiple
            filterable
            clearable
            allow-create
            placeholder="成员用户ID"
            style="width: 100%"
          >
            <el-option v-for="i in 5" :key="i" :label="`用户 #${i}`" :value="i" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="domainDialog = false">取消</el-button>
        <el-button type="primary" @click="saveDomainForm()">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";

import {
  getGovernanceOverview,
  getOntologyGovernance,
  getAccessRules,
  getAccessMatrix,
  accessPreview,
  accessPreviewRole,
  getDqOverview,
  getDqAlert,
  scanAllDq,
  getDomainObjects,
  saveAccessRule,
  saveDomain,
  removeAccessRule,
  removeDomain,
  getQueryObjects,
  getActionList,
  getPendingActions,
  getActionLogs,
  approveAction,
  rejectAction,
} from "@/api/module_ai/query";

defineOptions({ name: "GovernancePanel" });

const tab = ref("overview");
const g = ref<any>({ overview: {} });
const accessRules = ref<any[]>([]);
// 权限矩阵 / 沙箱
const matrixDialog = ref(false);
const matrixRows = ref<any[]>([]);
const matrixLoading = ref(false);
const sandboxDialog = ref(false);
const sandboxUserId = ref(1);
const sandboxRole = ref("");
const sandboxLoading = ref(false);
const sandboxResult = ref<any>(null);

async function openMatrix() {
  matrixDialog.value = true;
  matrixLoading.value = true;
  try {
    const r = await getAccessMatrix();
    matrixRows.value = r.data?.data?.roles || [];
  } catch {
    matrixRows.value = [];
  } finally {
    matrixLoading.value = false;
  }
}

function openSandbox() {
  sandboxDialog.value = true;
  sandboxResult.value = null;
}

async function runSandboxUser() {
  sandboxLoading.value = true;
  try {
    const r = await accessPreview(sandboxUserId.value);
    const d = r.data?.data || {};
    sandboxResult.value = {
      label: `用户 #${d.user_id}（${d.superuser ? "超管" : (d.roles || []).join("/") || "无角色"}）`,
      restricted: !!d.domain_restricted,
      count: d.count || 0,
      sensitive_ok: !!d.superuser,
      tables: d.allowed_tables || [],
    };
  } catch (e: any) {
    ElMessage.error(e?.msg || "预览失败");
  } finally {
    sandboxLoading.value = false;
  }
}

async function runSandboxRole() {
  if (!sandboxRole.value) {
    ElMessage.warning("请选择角色");
    return;
  }
  sandboxLoading.value = true;
  try {
    const r = await accessPreviewRole(sandboxRole.value);
    const d = r.data?.data || {};
    sandboxResult.value = {
      label: `角色 ${d.role}`,
      restricted: !!d.restricted,
      count: d.count || 0,
      sensitive_ok: !!d.sensitive_ok,
      tables: d.allowed_tables || [],
    };
  } catch (e: any) {
    ElMessage.error(e?.msg || "预览失败");
  } finally {
    sandboxLoading.value = false;
  }
}
const dqData = ref<any>({ avg_score: 0, healthy: 0, risk: 0, items: [] });
const dqAlerts = ref<any[]>([]);
const dqScanning = ref(false);
const domainView = ref<any>({ domains: [], unassigned: [], total_objects: 0 });
const ontGov = ref<any>({ avg_score: 0, items: [] });
const govObjects = ref<any[]>([]);
// 动作审批
const pendingActions = ref<any[]>([]);
const actionList = ref<any[]>([]);
const actionLogs = ref<any[]>([]);

async function loadOverview() {
  const r = await getGovernanceOverview();
  g.value = { overview: r.data?.data || {} };
}
async function loadOntGov() {
  const r = await getOntologyGovernance();
  ontGov.value = r.data?.data || { avg_score: 0, items: [] };
}
async function loadAccess() {
  const r = await getAccessRules();
  accessRules.value = r.data?.data || [];
}
async function loadDq() {
  const r = await getDqOverview();
  dqData.value = r.data?.data || { avg_score: 0, healthy: 0, risk: 0, items: [] };
}
async function loadDqAlert() {
  const r = await getDqAlert();
  dqAlerts.value = r.data?.data?.alerts || [];
}
async function loadDomain() {
  const r = await getDomainObjects();
  domainView.value = r.data?.data || { domains: [], unassigned: [], total_objects: 0 };
}
async function loadObjects() {
  const r = await getQueryObjects();
  govObjects.value = r.data?.data || [];
}

function onTab(name: any) {
  if (name === "overview") loadOverview();
  else if (name === "access") loadAccess();
  else if (name === "dq") {
    loadDq();
    loadDqAlert();
  } else if (name === "domain") loadDomain();
  else if (name === "ontgov") loadOntGov();
  else if (name === "action") loadAction();
}

// 动作审批：待审批/定义/日志
async function loadAction() {
  try {
    const [pa, al, lg] = await Promise.all([
      getPendingActions(50),
      getActionList(),
      getActionLogs(50),
    ]);
    pendingActions.value = pa.data?.data || [];
    actionList.value = al.data?.data || [];
    actionLogs.value = lg.data?.data || [];
  } catch {
    pendingActions.value = [];
    actionList.value = [];
    actionLogs.value = [];
  }
}

async function apAction(row: any, approve: boolean) {
  try {
    await (approve ? approveAction : rejectAction)({ approval_id: row.id });
    ElMessage.success(approve ? "已批准" : "已驳回");
    await loadAction();
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}
async function scanAll() {
  dqScanning.value = true;
  try {
    await scanAllDq();
    ElMessage.success("已全量扫描");
    await loadDq();
    await loadDqAlert();
  } catch (e: any) {
    ElMessage.error(e?.msg || "扫描失败");
  } finally {
    dqScanning.value = false;
  }
}
function openAccess() {
  Object.assign(accessForm, {
    id: null,
    name: "",
    attribute: "role",
    value: "",
    allowed_tables: [],
    sensitive_ok: false,
    enabled: true,
  });
  accessDialog.value = true;
}
function openDomain() {
  Object.assign(domainForm, {
    id: null,
    name: "",
    code: "",
    description: "",
    tables: [],
    members: [],
    enabled: true,
  });
  domainDialog.value = true;
}
const accessDialog = ref(false);
const accessForm = reactive<any>({
  id: null,
  name: "",
  attribute: "role",
  value: "",
  allowed_tables: [],
  sensitive_ok: false,
  enabled: true,
});
async function saveAccessForm() {
  if (!accessForm.name?.trim() || !accessForm.value?.trim())
    return ElMessage.warning("请填策略名/属性值");
  await saveAccessRule({ ...accessForm });
  ElMessage.success("已保存");
  accessDialog.value = false;
  loadAccess();
  loadOverview();
}
const domainDialog = ref(false);
const domainForm = reactive<any>({
  id: null,
  name: "",
  code: "",
  description: "",
  tables: [],
  members: [],
  enabled: true,
});
async function saveDomainForm() {
  if (!domainForm.name?.trim()) return ElMessage.warning("请填域名称");
  await saveDomain({ ...domainForm });
  ElMessage.success("已保存");
  domainDialog.value = false;
  loadDomain();
  loadOverview();
}
function editAccess(row: any) {
  Object.assign(accessForm, { ...row });
  accessDialog.value = true;
}
function editDomain(row: any) {
  Object.assign(domainForm, { ...row });
  domainDialog.value = true;
}
function delAccess(row: any) {
  ElMessageBox.confirm(`删除权限策略「${row.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeAccessRule(row.id);
    ElMessage.success("已删除");
    loadAccess();
  });
}
function delDomain(row: any) {
  ElMessageBox.confirm(`删除数据域「${row.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeDomain(row.id);
    ElMessage.success("已删除");
    loadDomain();
  });
}

onMounted(() => {
  loadOverview();
  loadObjects();
});
</script>

<style lang="scss" scoped>
.gp-wrap {
  padding: 12px;
}
.gp-section {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
}
.gp-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.gp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gp-bar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gp-alert {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}
.gp-alert--warn {
  padding: 4px;
}
.gp-score {
  margin-left: 8px;
  font-size: var(--el-font-size-small);
  color: var(--el-color-warning);
}
.gp-down {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gp-params {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-family: monospace;
  word-break: break-all;
}
</style>
