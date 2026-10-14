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
              <span class="ont-side__title">本体</span>
              <el-button
                class="ont-side__add"
                size="small"
                type="primary"
                plain
                :icon="Plus"
                :loading="domainSaving"
                @click="openDomainForm()"
              >
                新建本体
              </el-button>
            </div>
          </template>

          <div class="ont-domains">
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
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item command="remove" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div v-if="!domains.length" class="ont-domains__empty">
              <el-empty :image-size="50" description="还没有本体，点「新建本体」创建" />
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
                <span class="ont-crumb">本体 / 图谱</span>
                <el-tag size="small" type="info" effect="plain">
                  {{ currentDomainName }}
                </el-tag>
              </div>
              <div class="ont-main__ops">
                <el-tooltip
                  v-if="wipCount"
                  :content="`有 ${wipCount} 处改动尚未落库，点「保存」后生效`"
                  placement="bottom"
                >
                  <el-badge :value="wipCount" :max="99" type="warning" class="ont-wip-badge">
                    <el-button
                      size="small"
                      type="primary"
                      :icon="Check"
                      :loading="wipSaving"
                      @click="openReview"
                    >
                      保存
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
                  丢弃
                </el-button>
                <el-button size="small" :icon="Promotion" @click="goQuery">去问数验证</el-button>
                <el-button size="small" :icon="DataAnalysis" @click="overviewDrawer = true">
                  概览
                </el-button>
                <el-dropdown trigger="click" @command="onMaint">
                  <el-button size="small" :icon="Tools">
                    维护
                    <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="enrich" :disabled="enrichLoading">
                        业务语义回填（注释→名称/枚举、外键→关系）
                      </el-dropdown-item>
                      <el-dropdown-item command="seed" :disabled="seedLoading">
                        写入示例能力（10 函数 + 7 动作）
                      </el-dropdown-item>
                      <el-dropdown-item command="assign" divided>
                        批量归属本体（已选 {{ selected.length }}）
                      </el-dropdown-item>
                      <el-dropdown-item command="pending">
                        待审批的版本发布（{{ pendingVersions.length }}）
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </template>

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
      title="对象类型详情"
      destroy-on-close
      class="ont-obj-drawer"
    >
      <OntObjectTypeView
        v-if="selObject"
        :key="`objdetail-${selKey}`"
        :code="selKey"
        :page="objPage"
        @update:page="objPage = $event"
        @edit-object="openObjectEdit(selObject)"
        @new-action="openActionEdit()"
        @new-link="openLinkEdit()"
        @go-properties="goObjectProperties"
        @refresh="reloadAll"
      />
    </el-drawer>

    <!-- ================= 概览弹窗 ================= -->
    <EnhancedDialog v-model="overviewDrawer" title="本体概览" width="600px">
      <OntOverviewDrawer />
    </EnhancedDialog>

    <!-- ================= 维护弹窗（按面板切换） ================= -->
    <EnhancedDialog v-model="maintenanceDrawer" :title="maintPanelLabel" width="720px">
      <OntMaintenanceDrawer :panel="maintPanel" />
    </EnhancedDialog>

    <!-- ================= 弹窗 ================= -->
    <!-- 对象类型 -->
    <el-dialog v-model="objDialog" title="对象类型" width="640px" append-to-body>
      <el-form :model="objForm" label-width="130px">
        <el-form-item label="显示名" required>
          <el-input v-model="objForm.name" placeholder="如 摄像机表" />
        </el-form-item>
        <el-form-item label="编码（ID）" required>
          <el-input
            v-model="objForm.code"
            :disabled="!!objForm.id"
            placeholder="如 video_cameras（小写字母/数字/连字符，唯一）"
          />
        </el-form-item>
        <el-form-item label="复数显示名" required>
          <el-input v-model="objForm.plural_name" :placeholder="pluralHint" />
        </el-form-item>
        <el-form-item label="API 名" required>
          <el-input v-model="objForm.api_name" :placeholder="apiHint" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="objForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="可见性">
          <el-select v-model="objForm.visibility" style="width: 100%">
            <el-option
              v-for="v in ONT_VISIBILITY"
              :key="v.value"
              :label="v.label"
              :value="v.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="别名">
          <el-select
            v-model="objForm.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="搜索时会命中这些词，回车新增"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="所属本体">
          <el-select
            v-model="objForm.domain_code"
            clearable
            placeholder="不选 = 未分组"
            style="width: 100%"
          >
            <el-option v-for="d in domains" :key="d.code" :label="d.name" :value="d.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="主键属性" required>
          <el-input v-model="objForm.key_prop" placeholder="id" />
        </el-form-item>
        <el-form-item label="标题属性" required>
          <el-input v-model="objForm.name_prop" placeholder="name" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="objForm.point_of_contact" placeholder="负责人（可选）" />
        </el-form-item>
        <el-form-item label="支撑表">
          <el-input v-model="objForm.backing_table" placeholder="留空则同编码" />
        </el-form-item>
        <el-form-item label="可编辑">
          <el-switch v-model="objForm.edits_enabled" />
          <span class="ont-hint">开启后允许终端用户编辑该类型对象（Writeback）</span>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="objForm.icon" placeholder="Box" />
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

    <!-- 关系类型 -->
    <el-dialog v-model="linkDialog" title="关系类型" width="640px" append-to-body>
      <el-form :model="linkForm" label-width="130px">
        <el-form-item label="源对象类型" required>
          <el-select v-model="linkForm.source_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标对象类型" required>
          <el-select v-model="linkForm.target_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系名"><el-input v-model="linkForm.name" /></el-form-item>
        <el-form-item label="API 名">
          <el-input v-model="linkForm.api_name" placeholder="留空则按关系名自动推导" />
        </el-form-item>
        <el-form-item label="源侧显示名">
          <el-input v-model="linkForm.source_name" placeholder="从源看过去的叫法，如「所属分组」" />
        </el-form-item>
        <el-form-item label="源侧复数名">
          <el-input v-model="linkForm.source_plural_name" />
        </el-form-item>
        <el-form-item label="目标侧显示名">
          <el-input
            v-model="linkForm.target_name"
            placeholder="从目标看回来的叫法，如「包含设备」"
          />
        </el-form-item>
        <el-form-item label="目标侧复数名">
          <el-input v-model="linkForm.target_plural_name" />
        </el-form-item>
        <el-form-item label="连接方式">
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
            多对多必须使用「连接表 Dataset」（官方约束）
          </span>
        </el-form-item>
        <el-form-item label="基数">
          <el-select v-model="linkForm.card" style="width: 100%">
            <el-option
              v-for="c in ONT_CARDINALITY"
              :key="c.value"
              :label="c.label"
              :value="c.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="源字段"><el-input v-model="linkForm.source_field" /></el-form-item>
        <el-form-item label="目标字段"><el-input v-model="linkForm.target_field" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="linkForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="可见性">
          <el-select v-model="linkForm.visibility" style="width: 100%">
            <el-option
              v-for="v in ONT_VISIBILITY"
              :key="v.value"
              :label="v.label"
              :value="v.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="linkForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveLink">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作类型 -->
    <el-dialog v-model="actionDialog" title="动作类型" width="640px" append-to-body>
      <el-form :model="actionForm" label-width="140px">
        <el-form-item label="动作名" required><el-input v-model="actionForm.name" /></el-form-item>
        <el-form-item label="编码" required><el-input v-model="actionForm.code" /></el-form-item>
        <el-form-item label="作用对象类型" required>
          <el-select v-model="actionForm.object_code" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="写回目标">
          <el-input v-model="actionForm.target_table" placeholder="video_cameras" />
        </el-form-item>
        <el-form-item label="方式">
          <el-select v-model="actionForm.method" style="width: 100%">
            <el-option label="update（修改对象）" value="update" />
            <el-option label="insert（暂不支持，会被拒绝）" value="insert" />
            <el-option label="delete（暂不支持，会被拒绝）" value="delete" />
          </el-select>
        </el-form-item>
        <el-form-item label="审批门禁"><el-switch v-model="actionForm.approval" /></el-form-item>
        <el-form-item label="可写字段">
          <el-select
            v-model="actionForm.white_fields"
            multiple
            allow-create
            filterable
            placeholder="字段白名单"
            style="width: 100%"
          >
            <el-option v-for="p in propsForForm" :key="p.code" :label="p.name" :value="p.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="actionForm.status" style="width: 100%">
            <el-option v-for="s in ONT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="actionForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Tool description">
          <el-input
            v-model="actionForm.tool_description"
            type="textarea"
            :rows="2"
            placeholder="给 AI 看的工具描述：这个动作做什么、什么时候该调用。留空则 Agent 退回使用上面的「描述」"
          />
        </el-form-item>
        <el-form-item label="参数（JSON）">
          <el-input
            v-model="actionForm.parametersText"
            type="textarea"
            :rows="3"
            placeholder='[{"key":"name","label":"新名称","type":"string","required":true}]'
          />
          <span class="ont-hint">参数会直接生成 Agent 工具的 JSON Schema</span>
        </el-form-item>
        <el-form-item label="副作用（JSON）">
          <el-input
            v-model="actionForm.sideEffectsText"
            type="textarea"
            :rows="2"
            placeholder='[{"type":"notification","detail":"通知值班人"}]'
          />
          <span class="ont-hint">官方支持通知 / Webhook / 触发调度构建；当前仅声明，无执行器</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveAction">保存</el-button>
      </template>
    </el-dialog>

    <!-- 保存前的改动审核（对齐官方 Review changes） -->
    <el-dialog v-model="reviewDialog" title="审核改动" width="640px" append-to-body>
      <div class="ont-review">
        <div class="ont-review__sum">
          共
          <b>{{ review.count }}</b>
          处改动待保存
          <el-tag v-if="review.errors.length" size="small" type="danger" effect="plain">
            错误 {{ review.errors.length }}
          </el-tag>
          <el-tag v-if="review.warnings.length" size="small" type="warning" effect="plain">
            警告 {{ review.warnings.length }}
          </el-tag>
        </div>

        <el-table :data="review.changes" size="small" border max-height="200">
          <el-table-column prop="label" label="类型" width="100" />
          <el-table-column label="改动" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="actionTagType(row.action)" effect="plain">
                {{ actionLabel(row.action) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="实体" show-overflow-tooltip />
        </el-table>

        <el-alert
          v-if="review.errors.length"
          type="error"
          :closable="false"
          class="ont-review__box"
          title="以下错误会阻止保存"
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
          title="以下警告不会阻止保存"
        >
          <ul class="ont-review__list">
            <li v-for="(w, i) in review.warnings" :key="i">{{ w }}</li>
          </ul>
        </el-alert>

        <div v-if="review.destructive.length" class="ont-review__danger">
          <el-alert type="error" :closable="false" title="存在破坏性改动，需输入实体名称确认">
            <ul class="ont-review__list">
              <li v-for="(d, i) in review.destructive" :key="i">{{ d.name }}：{{ d.reason }}</li>
            </ul>
          </el-alert>
          <el-input
            v-model="confirmName"
            class="ont-review__confirm"
            :placeholder="`请输入实体名称以确认：${review.destructive[0]?.name || ''}`"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="danger" plain :disabled="wipSaving" @click="discardWip">
          丢弃全部改动
        </el-button>
        <el-button
          type="primary"
          :loading="wipSaving"
          :disabled="review.errors.length > 0"
          @click="doSaveWip"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 本体（domain）新建 / 重命名 -->
    <el-dialog
      v-model="domainDialog"
      :title="domainForm.id ? '重命名本体' : '新建本体'"
      width="460px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="domainForm.name" placeholder="本体名称" maxlength="60" />
        </el-form-item>
        <el-form-item v-if="!domainForm.id" label="编码" required>
          <el-input
            v-model="domainForm.code"
            placeholder="唯一编码，如 sales / hr"
            maxlength="40"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="domainDialog = false">取消</el-button>
        <el-button type="primary" :loading="domainSaving" @click="saveDomain">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量归属 -->
    <el-dialog v-model="assignDialog" title="批量归属本体" width="480px" append-to-body>
      <div class="ont-hint">
        已选 {{ selected.length }} 个对象类型：{{
          selected
            .map((o: any) => o.name)
            .slice(0, 6)
            .join("、")
        }}{{ selected.length > 6 ? " 等" : "" }}
      </div>
      <el-form label-width="90px" class="ont-home__mt">
        <el-form-item label="目标本体">
          <el-select
            v-model="assignTarget"
            clearable
            placeholder="不选 = 退回未分组"
            style="width: 100%"
          >
            <el-option v-for="d in domains" :key="d.code" :label="d.name" :value="d.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialog = false">取消</el-button>
        <el-button type="primary" :loading="assignLoading" @click="doAssign">确认归属</el-button>
      </template>
    </el-dialog>

    <!-- 待审批版本 -->
    <el-dialog v-model="pendingDialog" title="待审批的版本发布" width="560px" append-to-body>
      <el-table :data="pendingVersions" size="small" border>
        <template #empty>
          <el-empty description="没有待审批的发布申请" :image-size="50" />
        </template>
        <el-table-column label="对象类型" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
        </el-table-column>
        <el-table-column prop="created_time" label="申请时间" min-width="170" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="doApprove(row)">批准发布</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="pendingDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowDown,
  Box,
  Check,
  DataAnalysis,
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
  getOntProperties,
  getOntVersionPending,
  materializeOntObject,
  removeOntDomain,
  saveOntDomain,
  saveOntWip,
  seedOntologyExamples,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "./composables/useOntologyData";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import OntGraphWorkspace from "./components/OntGraphWorkspace.vue";
import OntOverviewDrawer from "./components/OntOverviewDrawer.vue";
import OntMaintenanceDrawer from "./components/OntMaintenanceDrawer.vue";
import OntObjectTypeView from "./components/OntObjectTypeView.vue";
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
  index: { label: "索引" },
  proposals: { label: "提案" },
  scenarios: { label: "场景" },
  decisions: { label: "决策" },
  explore: { label: "对象探索" },
  groups: { label: "对象类型组" },
  valueTypes: { label: "值类型" },
  shared: { label: "共享属性" },
  interfaces: { label: "接口" },
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
const maintPanelLabel = computed(() => MAINT_PANELS[maintPanel.value]?.label || "维护");

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
    return ElMessage.warning("该对象类型已不存在或不在当前作用域");
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
    ElMessage.warning("未找到对应关系类型");
  }
}
function onGraphEditObject(objectCode: string) {
  const obj = objectByCode(objectCode);
  if (obj) openObjectEdit(obj);
  else ElMessage.warning("该对象类型已不存在");
}
function onGraphDeleteObject(objectCode: string) {
  const obj = objectByCode(objectCode);
  if (obj) removeObj(obj);
  else ElMessage.warning("该对象类型已不存在");
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
      `将删除 ${codes.length} 个对象类型（${names}${codes.length > 6 ? " 等" : ""}）` +
        "及其属性/关系/动作定义（不影响真实数据表）。改动会先进入待保存列表，确认删除？",
      "批量删除对象类型",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
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
  if (!name) return ElMessage.warning("请填写本体名称");
  if (!code && !domainForm.id) return ElMessage.warning("请填写本体编码");
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
    ElMessage.success(r.data?.msg || "已保存");
    domainDialog.value = false;
    await reloadAll();
    if (!domainForm.id && code) {
      currentDomain.value = code;
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    domainSaving.value = false;
  }
}

async function removeDomain(d: any) {
  const cnt = objects.value.filter((o: any) => (o.domain_code || "") === d.code).length;
  try {
    await ElMessageBox.confirm(
      `将删除本体「${d.name}」及其下 ${cnt} 个对象类型（对象类型会变为未分组，本体本身不可恢复），是否继续？`,
      "删除本体",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const r = await removeOntDomain(d.id);
  ElMessage.success(r.data?.msg || "已删除");
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
const pendingDialog = ref(false);
const domainDialog = ref(false);
const domainSaving = ref(false);
const domainForm = reactive({ id: null as number | null, code: "", name: "" });

async function onMaint(cmd: string) {
  if (cmd === "enrich") return doEnrich();
  if (cmd === "seed") return doSeed();
  if (cmd === "assign") {
    if (!selected.value.length) {
      return ElMessage.warning("请先在「对象类型」清单里勾选对象，再执行批量归属");
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
async function doEnrich() {
  enrichLoading.value = true;
  maintMsg.value = "";
  try {
    const r = await enrichOntology();
    maintMsg.value = r.data?.msg || "回填完成";
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "回填失败");
  } finally {
    enrichLoading.value = false;
  }
}
async function doSeed() {
  seedLoading.value = true;
  maintMsg.value = "";
  try {
    const r = await seedOntologyExamples();
    maintMsg.value = r.data?.msg || "示例能力已写入";
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "写入失败");
  } finally {
    seedLoading.value = false;
  }
}
async function doAssign() {
  if (!selected.value.length) return ElMessage.warning("请先勾选对象类型");
  assignLoading.value = true;
  try {
    const r = await assignOntDomain(
      assignTarget.value || "",
      selected.value.map((o: any) => o.code)
    );
    ElMessage.success(r.data?.msg || "已归属");
    assignDialog.value = false;
    selected.value = [];
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "归属失败");
  } finally {
    assignLoading.value = false;
  }
}
async function doApprove(row: any) {
  const r = await approveOntVersion(row.id);
  ElMessage.success(r.data?.msg || "已批准");
  const p = await getOntVersionPending();
  pendingVersions.value = p.data?.data || [];
  await reloadAll();
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
const pluralHint = computed(() => derivePluralName(objForm.name) || "如 摄像机表s");
const apiHint = computed(() => deriveApiName(objForm.code) || "如 VideoCameras");

function openObjectEdit(o?: any) {
  Object.assign(objForm, objBlank(), o ? { ...o } : { domain_code: currentDomain.value || "" });
  objDialog.value = true;
}
async function saveObj() {
  // 官方必填：ID(code) / 显示名 / 复数显示名 / API 名
  if (!objForm.code?.trim() || !objForm.name?.trim()) return ElMessage.warning("请填显示名与编码");
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
    `将删除对象类型「${o.name}」及其属性/关系/动作定义（不影响真实数据表）。改动会先进入待保存列表，确认删除？`,
    "删除对象类型",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await stage("object", "delete", { id: o.id, code: o.code, name: o.name }, "已暂存删除");
}
async function materialize(o: any) {
  const r = await materializeOntObject(o.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](r.data?.msg || d.msg || "已物化");
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
function openLinkEdit(l?: any) {
  Object.assign(linkForm, linkBlank(), l ? { ...l } : {});
  linkDialog.value = true;
}
async function saveLink() {
  if (!linkForm.source_object || !linkForm.target_object)
    return ElMessage.warning("请选择源/目标对象类型");
  // 官方约束：多对多必须由连接表数据集支撑
  if (linkForm.card === "many_to_many" && linkForm.join_method !== "dataset")
    return ElMessage.warning("多对多关系必须使用「连接表 Dataset」连接方式");
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
    throw new Error(`${label}不是合法 JSON`);
  }
  if (!Array.isArray(v)) throw new Error(`${label}必须是 JSON 数组`);
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
    return ElMessage.warning("请填动作名、编码与作用对象类型");
  let parameters: any[] = [];
  let side_effects: any[] = [];
  try {
    parameters = parseJsonList(actionForm.parametersText, "参数");
    side_effects = parseJsonList(actionForm.sideEffectsText, "副作用");
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
  return { create: "新建", update: "修改", delete: "删除", restore: "恢复" }[a] || a;
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
      ElMessage.success(d.msg || "已保存");
      reviewDialog.value = false;
      await reloadAll();
      await refreshWip();
    } else {
      // 后端返回的审核结果覆盖本地，让用户看到真正的原因
      review.value.errors = d.errors || review.value.errors;
      review.value.destructive = d.destructive || review.value.destructive;
      await refreshWip();
      ElMessage.error(d.msg || "保存失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    wipSaving.value = false;
  }
}

async function discardWip() {
  try {
    await ElMessageBox.confirm(
      `将丢弃 ${review.value.count} 处未保存的改动，且不可恢复（库中数据不受影响）。确认丢弃？`,
      "丢弃改动",
      { type: "warning", confirmButtonText: "丢弃", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const r = await discardOntWip();
  ElMessage.success(r.data?.msg || "已丢弃");
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
    ElMessage.success(`已打开视图「${v.name}」`);
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
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
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
  padding: 12px !important;
  overflow: hidden !important;
}

/* 两张白卡的高度链：row → col → card → body */
.ai-ontology-page .ont-row {
  height: 100%;
  min-height: 0;
}
.ai-ontology-page .ont-row > .el-col {
  height: 100%;
  min-height: 0;
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
