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
                <el-button size="small" :icon="Promotion" @click="goQuery">
                  去问数验证
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
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- ================= 对象详情抽屉（点图谱节点打开） ================= -->
    <el-drawer
      v-model="objectDrawer"
      :title="selObject?.name || '对象类型详情'"
      size="620px"
      class="ont-obj-drawer"
    >
      <template #header>
        <div class="ont-obj-drawer__title">{{ selObject?.name || "对象类型详情" }}</div>
      </template>
      <OntObjectTypeView
        v-if="selObject"
        :key="`objdetail-${selKey}`"
        :code="selKey"
        page="overview"
        @edit-object="openObjectEdit(selObject)"
        @new-action="openActionEdit()"
        @new-link="openLinkEdit()"
        @go-properties="goObjectProperties"
        @refresh="reloadAll"
      />
    </el-drawer>

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

    <!-- 函数 -->
    <el-dialog v-model="funcDialog" title="本体计算函数" width="720px" append-to-body>
      <el-form :model="funcForm" label-width="140px">
        <el-form-item label="函数名" required>
          <el-input v-model="funcForm.name" placeholder="如 摄像机在线率（%）" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input v-model="funcForm.code" placeholder="cam_online_rate" />
        </el-form-item>
        <el-form-item label="所属对象类型" required>
          <el-select v-model="funcForm.object_code" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="函数形态" required>
          <el-radio-group v-model="funcForm.kind">
            <el-radio-button v-for="k in FN_KINDS" :key="k.value" :value="k.value">
              {{ k.label }}
            </el-radio-button>
          </el-radio-group>
          <div class="ont-hint">{{ fnKindHint }}</div>
        </el-form-item>

        <el-form-item v-if="funcForm.kind === 'expression'" label="表达式">
          <el-input
            v-model="funcForm.expr"
            type="textarea"
            :rows="2"
            placeholder="如 round(percent(online_count, total_count), 1)"
          />
          <div class="ont-hint">
            支持 + - * / 与比较、三元表达式，以及 {{ fnBuiltins.length }} 个内置函数。
            <el-button type="primary" link @click="showBuiltins = !showBuiltins">
              {{ showBuiltins ? "收起" : "查看内置函数" }}
            </el-button>
          </div>
          <div v-if="showBuiltins" class="ont-builtins">
            <el-tag
              v-for="b in fnBuiltins"
              :key="b"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ b }}
            </el-tag>
          </div>
        </el-form-item>

        <el-form-item label="入参（JSON）">
          <el-input
            v-model="funcForm.parametersText"
            type="textarea"
            :rows="5"
            :placeholder="fnParamsPlaceholder"
          />
          <div class="ont-hint">
            声明后生成 Agent 工具入参。
            <code>source</code>
            可为 parameter（调用方传入）、 object_property（取对象属性，需填
            <code>object_property</code>
            ）、static、 current_user、current_time。
          </div>
        </el-form-item>

        <el-form-item label="出参（JSON）">
          <el-input
            v-model="funcForm.outputsText"
            type="textarea"
            :rows="2"
            placeholder='[{"key":"rate","name":"在线率(%)","type":"number"}]'
          />
          <div class="ont-hint">声明返回值结构，会写进 Agent 工具说明</div>
        </el-form-item>

        <el-form-item v-if="funcForm.kind !== 'expression'" label="形态配置（JSON）">
          <el-input
            v-model="funcForm.configText"
            type="textarea"
            :rows="7"
            :placeholder="fnConfigPlaceholder"
          />
          <div class="ont-hint">{{ fnConfigHint }}</div>
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="funcForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Tool description">
          <el-input
            v-model="funcForm.tool_description"
            type="textarea"
            :rows="2"
            placeholder="给 AI 看的工具描述：这个函数算什么、什么时候该调用。留空则回退到「描述」"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="funcDialog = false">取消</el-button>
        <el-button :loading="fnChecking" @click="checkFunc">校验定义</el-button>
        <el-button type="primary" :loading="savingObj" @click="saveFunc">保存</el-button>
      </template>
    </el-dialog>

    <!-- 函数运行 / 试运行 -->
    <el-dialog
      v-model="fnRunDialog"
      title="运行函数（不会写入任何数据）"
      width="620px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="`函数：${fnRunTarget?.name || ''}（${fnKindLabel(fnRunTarget?.kind)}）`"
      />
      <el-form label-width="130px">
        <el-form-item v-if="fnRunNeedsObjectKey" label="对象行 ID">
          <el-input v-model="fnRunForm.object_key" placeholder="聚合/对象上下文的实例主键" />
        </el-form-item>
        <el-form-item v-for="p in fnRunInputs" :key="p.key" :label="p.name || p.key">
          <el-input v-model="fnRunForm.args[p.key]" :placeholder="p.description || p.key" />
          <div v-if="p.required" class="ont-hint">必填</div>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="fnRunInputs.some((p: any) => p.inferred)"
        type="info"
        :closable="false"
        class="ont-note"
        title="该函数未声明入参，下面按表达式里的变量推断。建议到「编辑」里正式声明入参，这样 AI 调用时也能正确传值。"
      />
      <el-button type="primary" :loading="fnRunning" @click="runFunc">运行</el-button>
      <template v-if="fnRunResult">
        <el-divider />
        <el-alert
          :type="fnRunResult.ok ? 'success' : 'error'"
          :closable="false"
          :title="fnRunResult.ok ? '执行成功' : fnRunResult.msg || '执行失败'"
        />
        <template v-if="fnRunResult.ok">
          <div class="ont-test__block">
            <div class="ont-sec__title">返回值</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.value, null, 2) }}</pre>
          </div>
          <div class="ont-test__block">
            <div class="ont-sec__title">实际入参</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.inputs, null, 2) }}</pre>
          </div>
        </template>
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
          <el-input v-model="domainForm.code" placeholder="唯一编码，如 sales / hr" maxlength="40" />
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
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowDown,
  Box,
  Check,
  MoreFilled,
  Plus,
  Promotion,
  RefreshLeft,
  Search,
  Tools,
} from "@element-plus/icons-vue";
import {
  approveOntVersion,
  assignOntDomain,
  checkOntFunction,
  discardOntWip,
  enrichOntology,
  exportOntology,
  getOntCleanup,
  getOntDomains,
  getOntFunctionBuiltins,
  getOntProperties,
  getOntUsage,
  getOntVersionPending,
  importOntology,
  materializeOntObject,
  removeOntDomain,
  runOntFunction,
  saveOntDomain,
  saveOntWip,
  seedOntologyExamples,
  stageOntRestore,
} from "@/api/module_ai/ontology";
import {
  applyIndustryTemplate,
  getIndustryTemplates,
  getQueryDatasources,
  getQueryDatasourceSchema,
  importDsAsOntologyBatch,
} from "@/api/module_ai/query";
import { useOntologyData } from "./composables/useOntologyData";
import OntGraphWorkspace from "./components/OntGraphWorkspace.vue";
import OntInstanceExplorer from "./components/OntInstanceExplorer.vue";
import OntAdvancedTypes from "./components/OntAdvancedTypes.vue";
import OntObjectTypeView from "./components/OntObjectTypeView.vue";
import OntLinkTypeView from "./components/OntLinkTypeView.vue";
import OntActionTypeView from "./components/OntActionTypeView.vue";
import OntDecisionView from "./components/OntDecisionView.vue";
import {
  clearOntDemo,
  getOntObjectView,
  getOntDemoReport,
  getOntDemoStatus,
  loadOntDemo,
} from "@/api/module_ai/ontology";
import OntIndexView from "./components/OntIndexView.vue";
import OntProposalView from "./components/OntProposalView.vue";
import OntScenarioView from "./components/OntScenarioView.vue";
import {
  ONT_CARDINALITY,
  ONT_JOIN_METHOD,
  ONT_STATUS,
  ONT_VISIBILITY,
  deriveApiName,
  derivePluralName,
  labelOf,
  statusTagType,
  visibilityTagType,
} from "./constants";

const router = useRouter();

/** 双向闭环：本体 → 问数（用刚定义/改动的语义去验证一次真实问数）。 */
function goQuery() {
  router.push("/ai/query");
}

const {
  domains,
  objects,
  actions,
  pendingVersions,
  currentDomain,
  currentDomainName,
  scopedObjects,
  scopedLinks,
  scopedActions,
  scopedFunctions,
  scopedProperties,
  scopedVersions,
  wip,
  refreshWip,
  stage,
  changelog,
  healthIssues,
  reloadAll,
  objectLabel,
  objectByCode,
} = useOntologyData();

/* ---------------- 导航状态 ---------------- */
type Mode = "home" | "object" | "link" | "action";
const mode = ref<Mode>("home");
const page = ref("overview");
// 深链里带过来的对象主键（?objectview=<code>&objectkey=<key>）
const objectViewKey = ref("");
// 深链指定的视图编码（?objectview=<code>）
const objectViewCode = ref("");
const selKey = ref(""); // 对象类型 / 动作类型的 code
const selId = ref<number | null>(null); // 关系类型的 id
const objectDrawer = ref(false); // 图谱点节点 → 对象详情抽屉

/** 本体选择器：'__all__' 代表全部本体 */

const scopedChangelog = computed(() =>
  currentDomain.value === undefined
    ? changelog.value
    : changelog.value.filter((c: any) =>
        scopedObjects.value.some((o: any) => o.code === c.object_code)
      )
);

const selObject = computed(() => objectByCode(selKey.value));
const selLink = computed(() => scopedLinks.value.find((l: any) => l.id === selId.value) || null);
const selAction = computed(() =>
  actions.value.find((a: any) => a.code === selKey.value) || null
);

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
  objectDrawer.value = true;
}
function goObjectProperties() {
  // 概览已含属性分区，无需切换子页；保留该方法以兼容 go-properties 事件
  ElMessage.info("属性定义见上方「属性」分区");
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

/* ---------------- 概览统计 ---------------- */
const homeStats = computed(() => [
  { label: "对象类型", value: scopedObjects.value.length, target: "objects" },
  { label: "属性", value: scopedProperties.value, target: "properties" },
  { label: "关系类型", value: scopedLinks.value.length, target: "links" },
  { label: "动作类型", value: scopedActions.value.length, target: "actions" },
  { label: "函数", value: scopedFunctions.value.length, target: "functions" },
  { label: "健康问题", value: healthIssues.value.length, target: "health" },
]);

/* ---------------- 全局属性清单 ---------------- */
const propAll = ref<any[]>([]);
const propSearch = ref("");
const propPage = ref(1);
const propPageSize = ref(20);
const filteredProps = computed(() => {
  const base =
    currentDomain.value === undefined
      ? propAll.value
      : propAll.value.filter((p: any) =>
          scopedObjects.value.some((o: any) => o.code === p.object_code)
        );
  const q = (propSearch.value || "").trim().toLowerCase();
  if (!q) return base;
  return base.filter(
    (p: any) =>
      (p.name || "").toLowerCase().includes(q) ||
      (p.code || "").toLowerCase().includes(q) ||
      (objectLabel(p.object_code) || "").toLowerCase().includes(q)
  );
});
const pagedProps = computed(() =>
  filteredProps.value.slice(
    (propPage.value - 1) * propPageSize.value,
    propPage.value * propPageSize.value
  )
);
async function loadAllProps() {
  if (propAll.value.length) return;
  try {
    const r = await getOntProperties();
    propAll.value = r.data?.data || [];
  } catch {
    propAll.value = [];
  }
}
watch(page, (p) => {
  if (p === "properties" || p === "search") loadAllProps();
});

/* ---------------- 对象类型清单 ---------------- */
const objSearch = ref("");
const objStatus = ref("");
const objVisibility = ref("");
const objPage = ref(1);
const objPageSize = ref(20);
const selected = ref<any[]>([]);
const filteredObjects = computed(() => {
  const q = (objSearch.value || "").trim().toLowerCase();
  return scopedObjects.value.filter((o: any) => {
    if (objStatus.value && o.status !== objStatus.value) return false;
    if (objVisibility.value && o.visibility !== objVisibility.value) return false;
    if (!q) return true;
    return (
      (o.name || "").toLowerCase().includes(q) ||
      (o.code || "").toLowerCase().includes(q) ||
      (o.api_name || "").toLowerCase().includes(q) ||
      (o.description || "").toLowerCase().includes(q)
    );
  });
});
const pagedObjects = computed(() =>
  filteredObjects.value.slice(
    (objPage.value - 1) * objPageSize.value,
    objPage.value * objPageSize.value
  )
);
function onObjectRowClick(_row: any, column: any) {
  // 勾选列不触发跳转（点击「打开」按钮才进详情）
  if (column?.type === "selection") return;
}

/* ---------------- 跨资源搜索 ---------------- */
const kw = ref("");
const searchResults = computed(() => {
  const q = (kw.value || "").trim().toLowerCase();
  if (!q) return [];
  const out: any[] = [];
  const hit = (s: string) => (s || "").toLowerCase().includes(q);
  scopedObjects.value.forEach((o: any) => {
    if (hit(o.name) || hit(o.code) || hit(o.description))
      out.push({
        kind: "对象类型",
        name: o.name,
        code: o.code,
        hint: o.description,
        mode: "object",
        key: o.code,
      });
  });
  filteredProps.value.forEach((p: any) => {
    if (hit(p.name) || hit(p.code)) {
      out.push({
        kind: "属性",
        name: p.name,
        code: p.code,
        hint: objectLabel(p.object_code),
        mode: "object",
        key: p.object_code,
      });
    }
  });
  scopedLinks.value.forEach((l: any) => {
    const label = `${objectLabel(l.source_object)} → ${objectLabel(l.target_object)}`;
    if (hit(l.name) || hit(label))
      out.push({
        kind: "关系类型",
        name: l.name || label,
        code: label,
        hint: l.card,
        mode: "link",
        key: l.id,
      });
  });
  scopedActions.value.forEach((a: any) => {
    if (hit(a.name) || hit(a.code))
      out.push({
        kind: "动作类型",
        name: a.name,
        code: a.code,
        hint: objectLabel(a.object_code),
        mode: "action",
        key: a.code,
      });
  });
  scopedFunctions.value.forEach((f: any) => {
    if (hit(f.name) || hit(f.code) || hit(f.expr))
      out.push({
        kind: "函数",
        name: f.name,
        code: f.code,
        hint: f.expr,
        mode: "object",
        key: f.object_code,
      });
  });
  return out.slice(0, 200);
});
const searchCount = computed(() => (kw.value.trim() ? searchResults.value.length : 0));

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
}
async function doEnrich() {
  enrichLoading.value = true;
  maintMsg.value = "";
  try {
    const r = await enrichOntology();
    maintMsg.value = r.data?.msg || "回填完成";
    await reloadAll();
    refreshProps();
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
function refreshProps() {
  propAll.value = [];
  if (page.value === "properties") loadAllProps();
}

/* ---------------- 导入 / 模板 ---------------- */
const datasources = ref<any[]>([]);
const impDs = ref<number | null>(null);
const impTableCount = ref(0);
const impIncludeTechnical = ref(false);
const impLoading = ref(false);
const industryTemplates = ref<any[]>([]);
const tplLoading = ref("");

async function loadImportPanel() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
    if (!impDs.value && datasources.value.length) {
      const best = [...datasources.value].sort(
        (a: any, b: any) => (b.table_count || 0) - (a.table_count || 0)
      )[0];
      impDs.value = best.id;
      await onImportDsChange(impDs.value);
    }
  } catch {
    datasources.value = [];
  }
  try {
    const t = await getIndustryTemplates();
    industryTemplates.value = t.data?.data || [];
  } catch {
    industryTemplates.value = [];
  }
}
async function onImportDsChange(id: number | null) {
  if (!id) {
    impTableCount.value = 0;
    return;
  }
  try {
    const r = await getQueryDatasourceSchema(id);
    impTableCount.value = (r.data?.data || []).length;
  } catch {
    impTableCount.value = 0;
  }
}
async function doBatchImport() {
  if (!impDs.value) return;
  impLoading.value = true;
  try {
    const r = await importDsAsOntologyBatch(impDs.value, null, impIncludeTechnical.value);
    const d = r.data?.data || {};
    ElMessage.success(r.data?.msg || `已导入 ${d.imported ?? 0} 个对象`);
    await reloadAll();
    refreshProps();
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
  } finally {
    impLoading.value = false;
  }
}
async function applyTemplate(t: any) {
  tplLoading.value = t.id;
  try {
    const r = await applyIndustryTemplate(t.id);
    ElMessage.success(r.data?.msg || `已应用模板「${t.name}」`);
    await reloadAll();
    refreshProps();
  } catch (e: any) {
    ElMessage.error(e?.msg || "应用失败");
  } finally {
    tplLoading.value = "";
  }
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
  const ok = await stage(
    "object",
    "delete",
    { id: o.id, code: o.code, name: o.name },
    "已暂存删除"
  );
  if (ok) {
    refreshProps();
  }
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
function joinLabel(jm?: string) {
  return labelOf(ONT_JOIN_METHOD, jm || "foreign_key");
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
  // 可写字段候选取自作用对象类型的属性
  if (actionForm.object_code) {
    const cached = propAll.value.filter((p: any) => p.object_code === actionForm.object_code);
    if (cached.length) {
      propsForForm.value = cached;
    } else {
      const r = await getOntProperties(actionForm.object_code);
      propsForForm.value = r.data?.data || [];
    }
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

/* ---------------- 清理建议 ---------------- */
const advTab = ref("groups");
const cleanupList = ref<any[]>([]);
const cleanupLoading = ref(false);
async function loadCleanup() {
  cleanupLoading.value = true;
  try {
    const r = await getOntCleanup();
    cleanupList.value = r.data?.data || [];
  } catch {
    cleanupList.value = [];
  } finally {
    cleanupLoading.value = false;
  }
}
async function deprecateByCleanup(row: any) {
  const obj = objects.value.find((o: any) => o.code === row.object_code);
  if (!obj) return ElMessage.error("对象类型不存在");
  await ElMessageBox.confirm(
    `将把「${row.object_name}」标记为 deprecated（弃用）。改动会先进入待保存列表，确认？`,
    "标记弃用",
    { type: "warning", confirmButtonText: "标记弃用", cancelButtonText: "取消" }
  );
  await stage("object", "update", { ...obj, status: "deprecated" }, "已暂存弃用标记");
}

/* ---------------- 导入 / 导出 ---------------- */
const transferLoading = ref(false);
const importText = ref("");
async function doExport() {
  transferLoading.value = true;
  try {
    const r = await exportOntology(currentDomain.value || undefined);
    const data = r.data?.data || {};
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ontology-${data.domain_code || "all"}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    const c = data.counts || {};
    ElMessage.success(
      `已导出 ${c.objects || 0} 对象 / ${c.properties || 0} 属性 / ${c.links || 0} 关系 / ${c.actions || 0} 动作`
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || "导出失败");
  } finally {
    transferLoading.value = false;
  }
}
async function doImport(mode: "stage" | "apply") {
  let payload: any;
  try {
    payload = JSON.parse(importText.value || "{}");
  } catch {
    return ElMessage.error("JSON 解析失败，请检查粘贴内容");
  }
  if (!payload.objects) return ElMessage.error("不是合法的本体定义（缺少 objects）");
  if (mode === "apply") {
    try {
      await ElMessageBox.confirm(
        "将把导入内容**直接写入**本体（不经过待保存列表），可能覆盖现有同名定义。确认直接导入？",
        "直接导入",
        { type: "warning", confirmButtonText: "直接导入", cancelButtonText: "取消" }
      );
    } catch {
      return;
    }
  }
  transferLoading.value = true;
  try {
    const r = await importOntology(payload, mode);
    ElMessage.success(r.data?.msg || "已导入");
    await reloadAll();
    await refreshWip();
    if (mode === "stage") importText.value = "";
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
  } finally {
    transferLoading.value = false;
  }
}
async function onImportFile(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0];
  if (!f) return;
  importText.value = await f.text();
  (ev.target as HTMLInputElement).value = "";
}

/* ---------------- 用量 ---------------- */
const usage = ref<any>({ reads: 0, writes: 0, edits: 0 });
const usageLoading = ref(false);
async function loadUsage(objectCode = "") {
  usageLoading.value = true;
  try {
    const r = await getOntUsage(objectCode);
    usage.value = r.data?.data || { reads: 0, writes: 0, edits: 0 };
  } catch {
    usage.value = { reads: 0, writes: 0, edits: 0 };
  } finally {
    usageLoading.value = false;
  }
}

/* ---------------- 历史：恢复 ---------------- */
async function restoreVersion(v: any) {
  await ElMessageBox.confirm(
    `将把「${objectLabel(v.object_code)}」的定义恢复到版本 v${v.version}（覆盖当前属性/关系/动作/函数定义）。` +
      "改动会先进入待保存列表，点「保存」后才生效。确认恢复？",
    "恢复历史版本",
    { type: "warning", confirmButtonText: "恢复", cancelButtonText: "取消" }
  );
  const r = await stageOntRestore(v.id);
  await reloadAll();
  await refreshWip();
  ElMessage.success(r.data?.msg || "已暂存恢复");
}

/* ---------------- 函数 CRUD ---------------- */
const funcDialog = ref(false);
// P2：函数形态
const FN_KINDS = [
  { value: "expression", label: "表达式" },
  { value: "aggregate", label: "关联聚合" },
  { value: "http", label: "外部服务" },
  { value: "model", label: "模型调用" },
];
function fnKindLabel(k: string) {
  return FN_KINDS.find((x) => x.value === k)?.label || k || "表达式";
}
const fnKindHint = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return "沿关系链在关联对象上聚合（count/sum/avg/min/max/first/last/collect_list/collect_set），需要对象主键作上下文";
    case "http":
      return "调用外部 REST API，按 result_path 从响应里取值";
    case "model":
      return "调用平台已登记的模型（AI 管理 → 模型配置），把响应文本作为返回值";
    default:
      return "受控表达式：算术、比较、三元表达式 + 内置函数；无字段访问、无任意代码执行";
  }
});
const fnParamsPlaceholder = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return '[{"key":"object_key","name":"对象ID","type":"string","required":true}]';
    case "http":
      return '[{"key":"text","name":"文本","type":"string","required":true}]';
    case "model":
      return '[{"key":"text","name":"文本","type":"string","required":true}]';
    default:
      return '[{"key":"online_count","name":"在线路数","type":"number","required":true,"description":"当前在线摄像机数量"}]';
  }
});
const fnConfigPlaceholder = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return JSON.stringify(
        {
          from_object: "video_cameras",
          source_object: "video_alarm_records",
          link_path: [27],
          aggregation: "count",
          property: "",
          limit: 10,
        },
        null,
        2
      );
    case "http":
      return JSON.stringify(
        {
          url: "https://example.com/api/score",
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body_template: '{"text":"{{text}}"}',
          result_path: "data.score",
          timeout: 10,
        },
        null,
        2
      );
    default:
      return JSON.stringify(
        { model_id: 1, system: "你是简洁的助手", prompt: "概括：{{text}}", temperature: 0.2 },
        null,
        2
      );
  }
});
const fnConfigHint = computed(() =>
  funcForm.kind === "aggregate"
    ? "link_path 是关系 ID 数组（最多 3 层）；property 在 count 时可留空"
    : funcForm.kind === "http"
      ? "URL 必须是 http/https；body_template 支持 {{参数名}} 占位"
      : "model_id 留空则用默认模型；prompt 支持 {{参数名}} 占位"
);
const fnBuiltins = ref<string[]>([]);
const showBuiltins = ref(false);
const fnChecking = ref(false);

const funcBlank = () => ({
  id: null,
  object_code: selKey.value || "",
  name: "",
  code: "",
  kind: "expression",
  expr: "",
  description: "",
  tool_description: "",
  parametersText: "",
  outputsText: "",
  configText: "",
});
const funcForm = reactive<any>(funcBlank());
function openFuncEdit(f?: any) {
  Object.assign(funcForm, funcBlank(), f ? { ...f } : {});
  funcForm.kind = f?.kind || "expression";
  funcForm.parametersText = f?.parameters?.length ? JSON.stringify(f.parameters, null, 2) : "";
  funcForm.outputsText = f?.outputs?.length ? JSON.stringify(f.outputs, null, 2) : "";
  funcForm.configText =
    f?.config && Object.keys(f.config).length ? JSON.stringify(f.config, null, 2) : "";
  funcDialog.value = true;
}

/** 解析弹窗里的三段 JSON，出错时返回 null */
function funcPayload(): Record<string, any> | null {
  let parameters: any[] = [];
  let outputs: any[] = [];
  let config: Record<string, any> = {};
  try {
    parameters = parseJsonList(funcForm.parametersText, "入参");
    outputs = parseJsonList(funcForm.outputsText, "出参");
    const raw = (funcForm.configText || "").trim();
    if (raw) {
      const v = JSON.parse(raw);
      if (typeof v !== "object" || Array.isArray(v)) throw new Error("形态配置必须是 JSON 对象");
      config = v;
    }
  } catch (e: any) {
    ElMessage.error(e.message || "JSON 解析失败");
    return null;
  }
  const payload: Record<string, any> = {};
  Object.keys(funcForm).forEach((k) => {
    if (!["parametersText", "outputsText", "configText"].includes(k)) payload[k] = funcForm[k];
  });
  payload.parameters = parameters;
  payload.outputs = outputs;
  payload.config = config;
  return payload;
}

/** 只做前端粗校验：表达式变量必须在入参里、且不能是内置函数名 */
function funcLocalErrors(payload: Record<string, any>): string[] {
  const errs: string[] = [];
  if (payload.kind !== "expression") return errs;
  const declared: string[] = (payload.parameters || []).map((p: any) => p.key).filter(Boolean);
  const ids: string[] = Array.from(
    new Set<string>(((funcForm.expr as string) || "").match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
  );
  const missing = ids.filter((v) => !declared.includes(v) && !fnBuiltins.value.includes(v));
  if (missing.length) errs.push(`表达式里的变量 ${missing.join("、")} 未在入参中声明`);
  return errs;
}

async function checkFunc() {
  const payload = funcPayload();
  if (!payload) return;
  const local = funcLocalErrors(payload);
  fnChecking.value = true;
  try {
    const r = await checkOntFunction(payload);
    const errs = [...local, ...((r.data?.data?.errors as string[]) || [])];
    if (!errs.length) ElMessage.success("定义正确");
    else
      ElMessageBox.alert(errs.map((e: string) => `· ${e}`).join("<br/>"), "发现以下问题", {
        dangerouslyUseHTMLString: true,
      });
  } finally {
    fnChecking.value = false;
  }
}

async function saveFunc() {
  if (!funcForm.code?.trim() || !funcForm.name?.trim() || !funcForm.object_code)
    return ElMessage.warning("请填函数名、编码与所属对象类型");
  const payload = funcPayload();
  if (!payload) return;
  const errs = funcLocalErrors(payload);
  if (errs.length) return ElMessage.error(errs.join("；"));
  savingObj.value = true;
  try {
    const ok = await stage("function", payload.id ? "update" : "create", payload);
    if (ok) funcDialog.value = false;
  } finally {
    savingObj.value = false;
  }
}
async function removeFunc(f: any) {
  await ElMessageBox.confirm(
    `将删除函数「${f.name}」，引用它的智能体能力会失效。改动会先进入待保存列表，确认删除？`,
    "删除函数",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await stage("function", "delete", { id: f.id, code: f.code, name: f.name }, "已暂存删除");
  await reloadAll();
}

/* ---------------- 函数运行 ---------------- */
const fnRunDialog = ref(false);
const fnRunning = ref(false);
const fnRunTarget = ref<any>(null);
const fnRunResult = ref<any>(null);
const fnRunForm = reactive<{ object_key: string; args: Record<string, any> }>({
  object_key: "",
  args: {},
});
const fnRunInputs = computed(() => {
  const f = fnRunTarget.value;
  if (!f) return [];
  const declared: any[] = (f.parameters || []).filter((p: any) => p.source !== "object_property");
  if (declared.length) return declared;
  // 老函数没声明入参：按表达式变量推断（与 Agent 工具生成入参的回退一致）。
  // 否则运行弹窗一个输入框都没有，函数根本没法跑。
  if ((f.kind || "expression") !== "expression") return [];
  const ids = Array.from(
    new Set<string>(((f.expr as string) || "").match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
  ).filter((v) => !fnBuiltins.value.includes(v));
  return ids.map((v) => ({ key: v, name: v, type: "number", required: true, inferred: true }));
});
const fnRunNeedsObjectKey = computed(() => {
  const f = fnRunTarget.value;
  if (!f) return false;
  if ((f.kind || "expression") !== "expression") return true;
  return (f.parameters || []).some((p: any) => p.source === "object_property");
});
function openFnRun(f: any) {
  fnRunTarget.value = f;
  fnRunResult.value = null;
  fnRunForm.object_key = "";
  const args: Record<string, any> = {};
  // 用 fnRunInputs（含「按表达式变量推断」的回退），否则老函数填不了参数
  fnRunInputs.value.forEach((p: any) => (args[p.key] = ""));
  fnRunForm.args = args;
  fnRunDialog.value = true;
}
async function runFunc() {
  if (!fnRunTarget.value) return;
  fnRunning.value = true;
  try {
    const args: Record<string, any> = {};
    Object.keys(fnRunForm.args).forEach((k) => {
      if (fnRunForm.args[k] !== "") args[k] = fnRunForm.args[k];
    });
    const r = await runOntFunction({
      code: fnRunTarget.value.code,
      args,
      object_key: fnRunForm.object_key,
    });
    fnRunResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || "运行失败");
  } finally {
    fnRunning.value = false;
  }
}

/* ---------------- 初始化 ---------------- */
/* ---------------- 演示数据 ---------------- */
const demoStatus = ref<any>(null);
const demoReport = ref<any>(null);
const demoBusy = ref(false);

async function refreshDemo() {
  try {
    const s = await getOntDemoStatus();
    demoStatus.value = s.data?.data || null;
    if (demoStatus.value?.loaded) {
      const r = await getOntDemoReport();
      demoReport.value = r.data?.data?.pages || null;
    } else {
      demoReport.value = null;
    }
  } catch {
    demoStatus.value = null;
  }
}

async function doLoadDemo(force: boolean) {
  if (force) {
    await ElMessageBox.confirm(
      "将先清除已载入的演示数据，再重新载入一份新的。你自己建的东西不受影响。确认？",
      "先清除再载入",
      { type: "warning", confirmButtonText: "继续", cancelButtonText: "取消" }
    );
  }
  demoBusy.value = true;
  try {
    const r = await loadOntDemo(force);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || "已载入");
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "载入失败");
  } finally {
    demoBusy.value = false;
  }
}

async function doClearDemo() {
  await ElMessageBox.confirm(
    `将删除已载入的 ${demoStatus.value?.total ?? 0} 项演示数据` +
      "（含演示用的对象视图、索引、提案、场景、决策、行级策略与资源权限）。" +
      "**只删登记过的演示项，你自己建的东西不动。** 确认清除？",
    "清除演示数据",
    { type: "warning", confirmButtonText: "清除", cancelButtonText: "取消" }
  );
  demoBusy.value = true;
  try {
    const r = await clearOntDemo();
    ElMessage.success(r.data?.msg || "已清除");
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "清除失败");
  } finally {
    demoBusy.value = false;
  }
}
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
  refreshDemo();
  // 内置函数清单（前端校验表达式时要排除它们）
  try {
    const b = await getOntFunctionBuiltins();
    fnBuiltins.value = b.data?.data || [];
  } catch {
    fnBuiltins.value = [];
  }
  await refreshWip();
  loadImportPanel();
  loadCleanup();
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
  font-size: 20px;
  color: var(--el-color-primary);
}
.ont-side__restext {
  min-width: 0;
}
.ont-side__resname {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}
.ont-side__ressub {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
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
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* 左栏：本体列表 */
.ont-side__title {
  font-size: 14px;
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
  font-size: 16px;
  flex-shrink: 0;
}
.ont-dom-item__name {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
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
  font-size: 14px;
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
  font-size: 14px;
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
  font-size: 22px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.ont-statcard__label {
  font-size: 12px;
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
  font-size: 14px;
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
  font-size: 14px;
  font-weight: 600;
}
.ont-tag-gap {
  margin: 0 4px 4px 0;
}
.ont-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-note {
  margin-bottom: 8px;
}
.ont-none {
  font-size: 12px;
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
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-stat__value {
  margin-top: 4px;
  font-size: 24px;
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
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>
