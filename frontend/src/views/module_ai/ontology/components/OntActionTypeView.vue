<!--
  动作类型视图（对齐 Palantir Ontology Manager 的 Action type 视图）
  子页：Overview（元数据 + Input → Rules 双列图）/ Rules / Parameters / Security & Submission Criteria
  一个动作类型 = 一组可一次性施加的变更（规则）+ 触发时的副作用。
-->
<template>
  <div v-if="act" class="ont-act">
    <div class="ont-act__head">
      <div class="ont-act__title">
        <el-icon class="ont-act__ico">
          <component :is="act.approval ? 'Lock' : 'EditPen'" />
        </el-icon>
        <div>
          <div class="ont-act__name">{{ act.name }}</div>
          <div class="ont-act__sub">
            {{ i18nT("ai_ontology.actionTypeActingOn", { name: objName(act.object_code) }) }}
          </div>
        </div>
      </div>
      <div class="ont-act__ops">
        <el-button size="small" type="success" :icon="VideoPlay" @click="openExec">
          {{ i18nT("ai_ontology.execute") }}
        </el-button>
        <el-button size="small" :icon="Edit" @click="emit('edit')">
          {{ i18nT("ai_ontology.edit") }}
        </el-button>
      </div>
    </div>

    <!-- ============ Overview ============ -->
    <template v-if="page === 'overview'">
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.metadata") }}</span>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="i18nT('ai_ontology.actionName')">
            {{ act.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.status')">
            <el-tag size="small" effect="plain" :type="statusTagType(act.status)">
              {{ labelOf(ONT_STATUS, act.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.code')">
            <span class="ont-mono">{{ act.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.targetObjectType')">
            {{ objName(act.object_code) }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.writebackTarget')">
            <span class="ont-mono">{{ act.target_table || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.approvalGate')">
            <el-tag size="small" effect="plain" :type="act.approval ? 'warning' : 'info'">
              {{
                act.approval
                  ? i18nT("ai_ontology.needsApproval")
                  : i18nT("ai_ontology.noApprovalNeeded")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.description')" :span="2">
            <span :class="{ 'ont-none': !act.description }">
              {{ act.description || i18nT("ai_ontology.notFilled") }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.toolDescriptionForAI')" :span="2">
            <span :class="{ 'ont-none': !act.tool_description }">
              {{ act.tool_description || i18nT("ai_ontology.notFilledAgentFallback") }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- Input → Rules 双列图（官方 Overview 的核心卡片） -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.actionOverview") }}</span>
          <span class="ont-hint">{{ i18nT("ai_ontology.inputToRules") }}</span>
        </div>
        <div class="ont-flow">
          <!-- Input 列 -->
          <div class="ont-flow__col">
            <div class="ont-flow__colhead">{{ i18nT("ai_ontology.inputCol") }}</div>
            <div v-for="f in fields" :key="f.key" class="ont-flow__item">
              <el-icon class="ont-flow__icon">
                <component :is="f.objectRef ? 'Aim' : 'EditPen'" />
              </el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">{{ f.label || f.key }}</div>
                <div class="ont-flow__meta">
                  {{ f.objectRef ? i18nT("ai_ontology.objectRefParameter") : f.desc || f.key }}
                </div>
              </div>
            </div>
            <el-empty
              v-if="!fields.length"
              :image-size="40"
              :description="i18nT('ai_ontology.noInputParameters')"
            />
          </div>
          <div class="ont-flow__mid">
            <el-icon><Right /></el-icon>
          </div>
          <!-- Rules 列 -->
          <div class="ont-flow__col">
            <div class="ont-flow__colhead">{{ i18nT("ai_ontology.rulesCol") }}</div>
            <div v-for="(r, i) in rulesSummary" :key="i" class="ont-flow__item">
              <el-icon class="ont-flow__icon"><component :is="ruleIcon" /></el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">
                  {{ r.type ? ruleLabel(r.type) : r.kind }}
                </div>
                <div class="ont-flow__meta">
                  <template v-if="r.type">
                    {{
                      i18nT("ai_ontology.assignmentValue", {
                        value:
                          (r.assignments || [])
                            .map((a: any) => `${a.property}←${SOURCE_LABEL[a.source] || a.source}`)
                            .join("  ") || i18nT("ai_ontology.none"),
                      })
                    }}
                  </template>
                  <template v-else>
                    {{ r.detail }}
                  </template>
                </div>
              </div>
            </div>
            <div v-if="realEffects.length" class="ont-flow__item">
              <el-icon class="ont-flow__icon"><Bell /></el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">
                  {{ i18nT("ai_ontology.sideEffectsWithCount", { count: realEffects.length }) }}
                </div>
                <div class="ont-flow__meta">
                  {{
                    realEffects
                      .map((e: any) =>
                        e.type === "notification" ? i18nT("ai_ontology.notification") : "Webhook"
                      )
                      .join("、")
                  }}
                </div>
              </div>
            </div>
            <div v-if="act.approval" class="ont-flow__item">
              <el-icon class="ont-flow__icon"><Lock /></el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">{{ i18nT("ai_ontology.approvalGate") }}</div>
                <div class="ont-flow__meta">
                  {{
                    i18nT(
                      "ai_ontology.requiresApprovalBeforeExecutionOtherwiseOnlyAPendingFormIsGenerated"
                    )
                  }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.dependencies") }}</span>
          <el-tag size="small" type="info" effect="plain">1</el-tag>
        </div>
        <div class="ont-dep">
          <span class="ont-dep__name">{{ i18nT("ai_ontology.objectType") }}</span>
          <el-tag size="small" effect="plain">1</el-tag>
          <span class="ont-dep__items">{{ objName(act.object_code) }}</span>
        </div>
        <el-alert
          type="info"
          :closable="false"
          class="ont-note"
          :title="i18nT('ai_ontology.externalDependenciesLikeAgentsAndWorkflowsAreNotConnectedYet')"
        />
      </section>
    </template>

    <!-- ============ Rules ============ -->
    <section v-else-if="page === 'rules'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.rule") }}</span>
        <el-tag size="small" type="info" effect="plain">
          {{ i18nT("ai_ontology.totalRulesCount", { count: realRules.length }) }}
        </el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Edit" @click="openRules">
          {{ i18nT("ai_ontology.editRules") }}
        </el-button>
        <el-button size="small" :icon="VideoPlay" @click="openTestRun">
          {{ i18nT("ai_ontology.dryRun") }}
        </el-button>
      </div>

      <el-alert
        v-if="!realRules.length"
        type="warning"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.noRulesConfiguredCompat')"
      />
      <el-table v-else :data="realRules" size="small" border stripe>
        <el-table-column :label="i18nT('ai_ontology.rule')" width="150">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ ruleLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.assignment')" min-width="340">
          <template #default="{ row }">
            <div v-for="a in row.assignments || []" :key="a.property" class="ont-mono">
              {{ a.property }} ← {{ sourceLabel(a) }}
            </div>
            <span v-if="!(row.assignments || []).length" class="ont-none">
              {{ i18nT("ai_ontology.noAssignment") }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="ont-sec__head ont-sec__head--mt">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.sideEffects") }}</span>
        <el-tag size="small" type="info" effect="plain">{{ realEffects.length }}</el-tag>
        <span class="ont-hint">{{ i18nT("ai_ontology.sideEffectsHint") }}</span>
      </div>
      <el-table :data="realEffects" size="small" border stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noSideEffectsConfigured')" />
        </template>
        <el-table-column prop="type" :label="i18nT('ai_ontology.type')" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.type === "notification" ? i18nT("ai_ontology.notification") : "Webhook" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timing" :label="i18nT('ai_ontology.when')" width="90">
          <template #default="{ row }">
            {{
              row.timing === "before"
                ? i18nT("ai_ontology.beforeEdit")
                : i18nT("ai_ontology.afterEdit")
            }}
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.target')" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            {{
              row.type === "notification"
                ? i18nT("ai_ontology.recipientsValue", { value: (row.recipients || []).join("、") })
                : row.url
            }}
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.implementedRulesHint')"
      />
    </section>

    <!-- ============ Parameters ============ -->
    <section v-else-if="page === 'parameters'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.parameter") }}</span>
        <el-tag size="small" type="info" effect="plain">{{ fields.length }}</el-tag>
      </div>
      <el-table :data="fields" size="small" border stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noParameters')" />
        </template>
        <el-table-column prop="key" :label="i18nT('ai_ontology.parameterId')" min-width="140" />
        <el-table-column prop="label" :label="i18nT('ai_ontology.displayName')" min-width="140" />
        <el-table-column :label="i18nT('ai_ontology.type')" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{
                row.objectRef ? i18nT("ai_ontology.objectReference") : i18nT("ai_ontology.baseType")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="desc"
          :label="i18nT('ai_ontology.note')"
          min-width="200"
          show-overflow-tooltip
        />
      </el-table>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.officialParamsHint')"
      />
    </section>

    <!-- ============ Security & Submission Criteria ============ -->
    <section v-else class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.securityAndSubmitConditions") }}</span>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          :icon="Edit"
          @click="openCriteria"
        >
          {{ i18nT("ai_ontology.editSubmitConditions") }}
        </el-button>
        <el-button size="small" type="primary" link @click="openEffects">
          {{ i18nT("ai_ontology.editSideEffects") }}
        </el-button>
        <el-button size="small" :icon="VideoPlay" @click="openTestRun">
          {{ i18nT("ai_ontology.dryRun") }}
        </el-button>
      </div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item :label="i18nT('ai_ontology.whitelistValidation')">
          <el-tag size="small" type="success" effect="plain">
            {{ i18nT("ai_ontology.enabled2") }}
          </el-tag>
          <span class="ont-hint">
            {{ i18nT("ai_ontology.withoutRulesWrittenFieldsMustBeInTheWhitelistOrRejected") }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.writableFields')">
          <template v-if="writable.length">
            <el-tag v-for="w in writable" :key="w" size="small" effect="plain" class="ont-tag-gap">
              {{ w }}
            </el-tag>
          </template>
          <span v-else class="ont-none">{{ i18nT("ai_ontology.notConfigured") }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.approvalGate')">
          <el-tag size="small" :type="act.approval ? 'warning' : 'info'" effect="plain">
            {{
              act.approval
                ? i18nT("ai_ontology.needsApprovalPendingOnly")
                : i18nT("ai_ontology.noApprovalNeeded")
            }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.submitCondition')">
          <template v-if="realCriteria.length">
            <el-tag size="small" type="success" effect="plain">
              {{ i18nT("ai_ontology.criteriaCountAllMatch", { count: realCriteria.length }) }}
            </el-tag>
            <div v-for="(c, i) in realCriteria" :key="i" class="ont-crit-item">
              <span class="ont-mono">{{ critSummary(c) }}</span>
              <span class="ont-none">
                {{
                  i18nT("ai_ontology.notSatisfiedHint", {
                    msg: c.failure_message || i18nT("ai_ontology.notFilledParen"),
                  })
                }}
              </span>
            </div>
          </template>
          <span v-else class="ont-none">
            {{ i18nT("ai_ontology.notConfiguredAnyRequestSatisfyingParamsAndWhitelistCanSubmit") }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.execOrderHint')"
      />
    </section>

    <!-- 提交条件编辑 -->
    <el-dialog
      v-model="critDialog"
      :title="i18nT('ai_ontology.editCriteriaJson')"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"operator":"is_not_empty","failure_message":"名称不能为空","left":{"kind":"parameter","value":"name"}}]'
      />
      <el-input v-model="critText" type="textarea" :rows="12" />
      <div v-if="critErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" :title="i18nT('ai_ontology.configIssue')">
          <ul class="ont-review__list">
            <li v-for="(e, i) in critErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="critDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveCriteria">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 副作用编辑 -->
    <el-dialog
      v-model="fxDialog"
      :title="i18nT('ai_ontology.editSideEffectsJson')"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"type":"notification","title":"已改名 {{name}}","recipients":[1]},{"type":"webhook","url":"https://example.com/hook","method":"POST","timing":"after","blocking":false}]'
      />
      <el-input v-model="fxText" type="textarea" :rows="10" />
      <div v-if="fxErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" :title="i18nT('ai_ontology.configIssue')">
          <ul class="ont-review__list">
            <li v-for="(e, i) in fxErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="fxDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveEffects">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 试运行 -->
    <el-dialog
      v-model="testDialog"
      :title="i18nT('ai_ontology.dryRunWritesNoData')"
      width="900px"
      append-to-body
    >
      <el-form label-width="110px" size="small">
        <el-form-item :label="i18nT('ai_ontology.objectRowId')">
          <el-input
            v-model="testForm.object_key"
            :placeholder="i18nT('ai_ontology.targetRowPK')"
            style="width: 200px"
          />
        </el-form-item>
        <el-form-item v-for="f in fields" :key="f.key" :label="f.label || f.key">
          <el-input v-model="testForm.params[f.key]" :placeholder="f.key" />
        </el-form-item>
      </el-form>
      <el-button
        v-hasPerm="'module_ai:ontology:execute'"
        type="primary"
        size="small"
        :loading="testing"
        @click="runTest"
      >
        {{ i18nT("ai_ontology.run") }}
      </el-button>
      <template v-if="testResult">
        <el-divider />
        <el-alert
          :type="testResult.would_submit ? 'success' : 'error'"
          :closable="false"
          :title="
            testResult.would_submit
              ? i18nT('ai_ontology.canSubmit')
              : i18nT('ai_ontology.willBeBlocked')
          "
        />
        <div class="ont-test__block">
          <div class="ont-sec__title">{{ i18nT("ai_ontology.submitCondition") }}</div>
          <div v-if="!testResult.criteria_used" class="ont-none">
            {{ i18nT("ai_ontology.notConfigured") }}
          </div>
          <template v-else>
            <div v-for="(t, i) in testResult.criteria?.trace || []" :key="i">
              <el-tag size="small" :type="t.ok ? 'success' : 'danger'" effect="plain">
                {{
                  i18nT("ai_ontology.conditionIndexResult", {
                    index: i + 1,
                    result: t.ok ? i18nT("ai_ontology.pass") : i18nT("ai_ontology.notPass"),
                  })
                }}
              </el-tag>
              <div v-for="(n, j) in t.nodes" :key="j" class="ont-mono ont-test__node">
                {{
                  i18nT("ai_ontology.nodeTraceResult", {
                    op: n.operator,
                    left: JSON.stringify(n.left),
                    right: JSON.stringify(n.right),
                    result: n.ok ? i18nT("ai_ontology.pass") : i18nT("ai_ontology.notPass"),
                  })
                }}
              </div>
            </div>
            <el-alert
              v-if="(testResult.criteria?.failures || []).length"
              type="error"
              :closable="false"
              class="ont-note"
              :title="
                i18nT('ai_ontology.failInfo', { msg: testResult.criteria.failures.join('；') })
              "
            />
          </template>
        </div>
        <div class="ont-test__block">
          <div class="ont-sec__title">{{ i18nT("ai_ontology.editsTheRuleProduces") }}</div>
          <div v-if="!testResult.rules_used" class="ont-none">
            {{ i18nT("ai_ontology.noRulesConfiguredUsingWhitelistFallback") }}
          </div>
          <div v-for="(e, i) in testResult.rules?.edits || []" :key="i" class="ont-mono">
            {{ ruleLabel(e.rule) }} → {{ JSON.stringify(e.assignments) }}
          </div>
          <div v-for="(w, i) in testResult.rules?.warnings || []" :key="'w' + i" class="ont-none">
            ⚠ {{ w }}
          </div>
        </div>
        <div class="ont-test__block">
          <div class="ont-sec__title">{{ i18nT("ai_ontology.sideEffects") }}</div>
          <div v-if="!testResult.side_effects_used" class="ont-none">
            {{ i18nT("ai_ontology.notConfigured") }}
          </div>
          <div v-for="(e, i) in testResult.side_effects?.effects || []" :key="i" class="ont-mono">
            {{
              e.type === "notification"
                ? i18nT("ai_ontology.notifyRecipientsTitle", {
                    recipients: e.recipients?.join("、"),
                    title: e.title,
                  })
                : `${e.method} ${e.url}`
            }}
          </div>
        </div>
        <div v-if="(testResult.value_type_errors || []).length" class="ont-test__block">
          <div class="ont-sec__title">{{ i18nT("ai_ontology.valueTypeConstraints") }}</div>
          <div v-for="(v, i) in testResult.value_type_errors" :key="i" class="ont-none">
            {{ v }}
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 规则编辑 -->
    <el-dialog
      v-model="rulesDialog"
      :title="i18nT('ai_ontology.editRulesJson')"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"type":"modify_object","assignments":[{"property":"name","source":"parameter","value":"name"},{"property":"updated_by","source":"current_user"}]}]'
      />
      <el-input v-model="rulesText" type="textarea" :rows="12" />
      <div v-if="rulesErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" :title="i18nT('ai_ontology.configIssue')">
          <ul class="ont-review__list">
            <li v-for="(e, i) in rulesErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="rulesDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveRules">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 执行对话框 -->
    <el-dialog
      v-model="execDialog"
      :title="i18nT('ai_ontology.executeOntologyAction')"
      width="600px"
      append-to-body
    >
      <el-alert
        v-if="act.approval"
        type="warning"
        :closable="false"
        class="ont-note"
        :title="
          i18nT('ai_ontology.thisActionHasAnApprovalGateWithoutApprovedItOnlyCreatesAPendingForm')
        "
      />
      <el-form :model="execForm" label-width="110px">
        <el-form-item :label="i18nT('ai_ontology.action')">
          <el-tag size="small" type="primary" effect="dark">{{ act.name }}</el-tag>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.writebackTarget')">
          <span class="ont-mono">{{ act.target_table || "—" }}</span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.objectRowId')" required>
          <el-input
            v-model="execForm.object_key"
            :placeholder="i18nT('ai_ontology.targetTablePrimaryKey')"
          />
        </el-form-item>
        <el-form-item v-for="f in fields" :key="f.key" :label="f.label || f.key">
          <el-input v-model="execForm.params[f.key]" :placeholder="f.key" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.scenario')">
          <el-select
            v-model="scen"
            size="small"
            clearable
            :placeholder="i18nT('ai_ontology.primaryOntologyWritesRealTable')"
            style="width: 100%"
            @visible-change="onScenOpen"
          >
            <el-option :label="i18nT('ai_ontology.primaryOntologyWritesRealTable')" value="" />
            <el-option v-for="s in scenOptions" :key="s.code" :label="s.name" :value="s.code" />
          </el-select>
          <div class="ont-hint">{{ i18nT("ai_ontology.scenarioStagedOnly") }}</div>
        </el-form-item>
        <el-alert
          v-if="act.approval"
          type="warning"
          :closable="false"
          show-icon
          :title="
            i18nT(
              'ai_ontology.thisActionNeedsManualApprovalAdminsApproveBeforeExecutionExecutorCannotSelfApprove'
            )
          "
        />
      </el-form>
      <el-alert
        v-if="execResult"
        :title="execResult"
        :type="execOk ? 'success' : 'error'"
        :closable="false"
        class="ont-note"
      />
      <template #footer>
        <el-button @click="execDialog = false">{{ i18nT("ai_ontology.close") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:execute'"
          type="primary"
          :loading="execLoading"
          @click="runExec"
        >
          {{ i18nT("ai_ontology.execute") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
  <el-empty v-else :description="i18nT('ai_ontology.actionTypeNotFound')" />
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Right, VideoPlay } from "@element-plus/icons-vue";
import { executeOntAction, getOntScenarios, testRunOntAction } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";
import { ONT_STATUS, labelOf, statusTagType } from "../constants";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string; page: string }>();
const emit = defineEmits<{ (e: "edit"): void }>();

const { actions, objectLabel, stage } = useOntologyData();

const act = computed(() => actions.value.find((a: any) => a.code === props.code) || null);
function objName(code: string) {
  return objectLabel(code);
}

/** 输入参数：优先用 input_schema，回退到 white_fields */
const fields = computed(() => {
  const a = act.value;
  if (!a) return [];
  const sch = (a.input_schema || []) as any[];
  if (sch.length) {
    return sch.map((f: any) => ({
      key: f.key,
      label: f.label || f.key,
      objectRef: f.type === "object_ref" || f.object_ref === true,
      desc: f.description || "",
    }));
  }
  return (a.white_fields || []).map((w: any) => ({
    key: typeof w === "string" ? w : w.key,
    label: typeof w === "string" ? w : w.label || w.key,
    objectRef: false,
    desc: "",
  }));
});

const writable = computed(() =>
  (act.value?.white_fields || []).map((w: any) => (typeof w === "string" ? w : w.key))
);

const METHOD_RULE: Record<string, string> = {
  update: i18nT("ai_ontology.modifyObject"),
  insert: i18nT("ai_ontology.createObject"),
  delete: i18nT("ai_ontology.deleteObject"),
};
const ruleIcon = computed(() => {
  const m = act.value?.method || "update";
  return m === "insert" ? "CirclePlus" : m === "delete" ? "Delete" : "Edit";
});
const rules = computed(() => {
  const a = act.value;
  if (!a) return [];
  const m = a.method || "update";
  return [
    {
      kind: METHOD_RULE[m] || m,
      target: a.target_table || objName(a.object_code),
      detail:
        m === "update"
          ? i18nT("ai_ontology.updateWhitelistFields", {
              fields: writable.value.join("、") || i18nT("ai_ontology.none"),
            })
          : m === "insert"
            ? i18nT("ai_ontology.onlyUpdateSupportedInsertBlocked")
            : i18nT("ai_ontology.onlyUpdateSupportedDeleteBlocked"),
    },
  ];
});

/* ---------------- P0：规则 / 提交条件 / 副作用的真实编辑与试运行 ---------------- */
const realRules = computed<any[]>(() => act.value?.rules || []);
const realEffects = computed<any[]>(() => act.value?.side_effects || []);
const realCriteria = computed<any[]>(() => act.value?.submission_criteria || []);
/** Overview 的 Input → Rules 卡片用：有真规则显示真规则，否则显示兼容路径 */
const rulesSummary = computed(() => (realRules.value.length ? realRules.value : rules.value));

const RULE_LABEL: Record<string, string> = {
  modify_object: i18nT("ai_ontology.modifyObject"),
  create_object: i18nT("ai_ontology.createObject"),
  delete_object: i18nT("ai_ontology.deleteObject"),
};
const SOURCE_LABEL: Record<string, string> = {
  parameter: i18nT("ai_ontology.parameter"),
  static: i18nT("ai_ontology.staticValue"),
  current_user: i18nT("ai_ontology.currentUser"),
  current_time: i18nT("ai_ontology.currentTime"),
  object_parameter_property: i18nT("ai_ontology.propertyOfObjectParameter"),
};
function ruleLabel(t: string) {
  return RULE_LABEL[t] || t;
}
function sourceLabel(a: any) {
  const s = SOURCE_LABEL[a?.source] || a?.source || i18nT("ai_ontology.parameter");
  const v = a?.source === "static" ? JSON.stringify(a?.value) : a?.value || a?.parameter || "";
  return `${s}(${v})`;
}
function critSummary(c: any) {
  const left =
    c?.left?.kind === "current_user_group"
      ? i18nT("ai_ontology.currentUserSGroup")
      : c?.left?.kind === "current_user"
        ? i18nT("ai_ontology.currentUser")
        : c?.left?.kind === "execution_context"
          ? i18nT("ai_ontology.executionContext")
          : i18nT("ai_ontology.paramValue", { value: c?.left?.value });
  const right =
    c?.right?.kind === "static"
      ? JSON.stringify(c?.right?.value)
      : c?.right?.kind === "parameter"
        ? i18nT("ai_ontology.paramValue", { value: c?.right?.value })
        : "";
  const kids = c?.children || c?.conditions;
  if (kids)
    return i18nT("ai_ontology.subConditionsCount", {
      count: kids.length,
      operator:
        c.operator === "or"
          ? i18nT("ai_ontology.anySatisfied")
          : c.operator === "not"
            ? i18nT("ai_ontology.negated")
            : i18nT("ai_ontology.allSatisfied"),
    });
  return `${left} ${c?.operator} ${right}`;
}

const savingCfg = ref(false);
const rulesDialog = ref(false);
const rulesText = ref("");
const rulesErrors = ref<string[]>([]);
const critDialog = ref(false);
const critText = ref("");
const critErrors = ref<string[]>([]);
const fxDialog = ref(false);
const fxText = ref("");
const fxErrors = ref<string[]>([]);

/** 参数键集合（规则/条件里引用的参数必须在其中） */
const paramKeys = computed(() => new Set(fields.value.map((f: any) => String(f.key))));

function parseArr(text: string, what: string): any[] | null {
  try {
    const v = JSON.parse(text || "[]");
    if (!Array.isArray(v)) {
      ElMessage.error(i18nT("ai_ontology.mustBeArrayShort", { label: what }));
      return null;
    }
    return v;
  } catch {
    ElMessage.error(i18nT("ai_ontology.notValidJson", { label: what }));
    return null;
  }
}

/** 前端先做一遍校验（后端保存时还会再校验一次） */
function validateRulesLocal(items: any[]): string[] {
  const errs: string[] = [];
  const types: string[] = [];
  items.forEach((r: any, i: number) => {
    const where = i18nT("ai_ontology.itemIndex", { index: i + 1 });
    if (!r || typeof r !== "object") return errs.push(i18nT("ai_ontology.notObject", { where }));
    if (!RULE_LABEL[r.type])
      return errs.push(
        i18nT("ai_ontology.typeNotSupported", {
          where,
          type: r.type || i18nT("ai_ontology.emptyParen"),
        })
      );
    types.push(r.type);
    (r.assignments || []).forEach((a: any, j: number) => {
      if (!a?.property)
        errs.push(i18nT("ai_ontology.assignmentMissingProperty", { where, n: j + 1 }));
      const s = a?.source || "parameter";
      if (!SOURCE_LABEL[s])
        errs.push(
          i18nT("ai_ontology.assignmentSourceNotSupported", { where, n: j + 1, source: s })
        );
      if (s === "parameter" && a?.value && !paramKeys.value.has(String(a.value)))
        errs.push(
          i18nT("ai_ontology.assignmentUndefinedParam", { where, n: j + 1, param: a.value })
        );
    });
  });
  if (types.filter((t) => t === "create_object").length > 1)
    errs.push(i18nT("ai_ontology.cannotCreateAnObjectTwiceInOneSubmissionOfficialLimit"));
  return errs;
}
function validateCriteriaLocal(items: any[]): string[] {
  const errs: string[] = [];
  const walk = (nodes: any[], where: string) => {
    nodes.forEach((n: any, i: number) => {
      const w = `${where} ${i + 1}`;
      if (!n || typeof n !== "object")
        return errs.push(i18nT("ai_ontology.notObject", { where: w }));
      const kids = n.children || n.conditions;
      if (kids) {
        if (!Array.isArray(kids) || !kids.length)
          errs.push(i18nT("ai_ontology.logicalGroupNoChildren", { where: w }));
        else walk(kids, `${w} >`);
        return;
      }
      const OPS = [
        "is",
        "is_not",
        "matches",
        "lt",
        "lte",
        "gt",
        "gte",
        "is_empty",
        "is_not_empty",
        "includes",
        "includes_any",
        "is_included_in",
        "each_is",
        "each_is_not",
      ];
      if (!OPS.includes(String(n.operator)))
        errs.push(
          i18nT("ai_ontology.operatorNotSupported", {
            where: w,
            op: n.operator || i18nT("ai_ontology.emptyParen"),
          })
        );
      if (!n.left?.kind) errs.push(i18nT("ai_ontology.missingLeftKind", { where: w }));
      else if (n.left.kind === "parameter") {
        if (!n.left.value) errs.push(i18nT("ai_ontology.leftEmptyParam", { where: w }));
        else if (!paramKeys.value.has(String(n.left.value)) && paramKeys.value.size)
          errs.push(i18nT("ai_ontology.leftUndefinedParam", { where: w, param: n.left.value }));
      }
      if (
        n.right?.kind === "parameter" &&
        n.right.value &&
        !paramKeys.value.has(String(n.right.value))
      )
        errs.push(i18nT("ai_ontology.rightUndefinedParam", { where: w, param: n.right.value }));
    });
  };
  walk(items, i18nT("ai_ontology.submitCondition2"));
  return errs;
}
function validateEffectsLocal(items: any[]): string[] {
  const errs: string[] = [];
  items.forEach((e: any, i: number) => {
    const w = i18nT("ai_ontology.itemIndex", { index: i + 1 });
    if (!e || typeof e !== "object") return errs.push(i18nT("ai_ontology.notObject", { where: w }));
    if (e.type === "notification") {
      if (!(e.recipients || []).length)
        errs.push(i18nT("ai_ontology.notifyNoRecipients", { where: w }));
    } else if (e.type === "webhook") {
      if (!/^https?:\/\//i.test(String(e.url || "")))
        errs.push(i18nT("ai_ontology.webhookUrlInvalid", { where: w }));
    } else {
      errs.push(
        i18nT("ai_ontology.effectTypeNotSupported", {
          where: w,
          type: e.type || i18nT("ai_ontology.emptyParen"),
        })
      );
    }
  });
  return errs;
}

function openRules() {
  rulesText.value = JSON.stringify(realRules.value, null, 2);
  rulesErrors.value = [];
  rulesDialog.value = true;
}
function openCriteria() {
  critText.value = JSON.stringify(realCriteria.value, null, 2);
  critErrors.value = [];
  critDialog.value = true;
}
function openEffects() {
  fxText.value = JSON.stringify(realEffects.value, null, 2);
  fxErrors.value = [];
  fxDialog.value = true;
}

/** 统一：把某个字段的新值作为一条动作改动暂存（走工作副本，点保存才落库） */
async function stageField(field: string, value: any, label: string) {
  if (!act.value) return false;
  savingCfg.value = true;
  try {
    const ok = await stage(
      "action",
      "update",
      { ...act.value, [field]: value },
      `${i18nT("ai_ontology.stagedSaveHint", { label })}`
    );
    return ok;
  } finally {
    savingCfg.value = false;
  }
}
async function saveRules() {
  const items = parseArr(rulesText.value, i18nT("ai_ontology.rule"));
  if (items === null) return;
  rulesErrors.value = validateRulesLocal(items);
  if (rulesErrors.value.length) return;
  if (await stageField("rules", items, i18nT("ai_ontology.rule"))) rulesDialog.value = false;
}
async function saveCriteria() {
  const items = parseArr(critText.value, i18nT("ai_ontology.submitCondition"));
  if (items === null) return;
  critErrors.value = validateCriteriaLocal(items);
  if (critErrors.value.length) return;
  if (await stageField("submission_criteria", items, i18nT("ai_ontology.submitCondition")))
    critDialog.value = false;
}
async function saveEffects() {
  const items = parseArr(fxText.value, i18nT("ai_ontology.sideEffects"));
  if (items === null) return;
  fxErrors.value = validateEffectsLocal(items);
  if (fxErrors.value.length) return;
  if (await stageField("side_effects", items, i18nT("ai_ontology.sideEffects")))
    fxDialog.value = false;
}

/* ---------------- 试运行 ---------------- */
const testDialog = ref(false);
const testing = ref(false);
const testResult = ref<any>(null);
const testForm = reactive<{ object_key: string; params: Record<string, any> }>({
  object_key: "",
  params: {},
});
function openTestRun() {
  const p: Record<string, any> = {};
  fields.value.forEach((f: any) => (p[f.key] = ""));
  testForm.params = p;
  testForm.object_key = "";
  testResult.value = null;
  testDialog.value = true;
}
async function runTest() {
  if (!act.value) return;
  testing.value = true;
  try {
    const params: Record<string, any> = {};
    Object.keys(testForm.params).forEach((k) => {
      if (testForm.params[k] !== "") params[k] = testForm.params[k];
    });
    const r = await testRunOntAction({
      code: act.value.code,
      object_key: testForm.object_key,
      params,
    });
    testResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.dryRunFailed"));
  } finally {
    testing.value = false;
  }
}

/* ---------- 执行 ---------- */
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
  object_key: "",
  params: {} as Record<string, any>,
});

function openExec() {
  const params: Record<string, any> = {};
  fields.value.forEach((f: any) => (params[f.key] = ""));
  Object.assign(execForm, { object_key: "", params });
  execResult.value = "";
  execOk.value = false;
  execDialog.value = true;
}
async function runExec() {
  if (!execForm.object_key) return ElMessage.warning(i18nT("ai_ontology.pleaseFillObjectRowId"));
  const params: Record<string, any> = {};
  Object.keys(execForm.params).forEach((k) => {
    const v = execForm.params[k];
    if (v !== "" && v != null) params[k] = v;
  });
  if (!Object.keys(params).length)
    return ElMessage.warning(i18nT("ai_ontology.pleaseFillAtLeastOneFieldToWrite"));
  execLoading.value = true;
  try {
    const r = await executeOntAction({
      code: props.code,
      object_key: execForm.object_key,
      params,
      scenario: scen.value,
    });
    const d = r.data?.data || {};
    execOk.value = !!d.ok;
    execResult.value =
      r.data?.msg ||
      d.msg ||
      (d.ok ? i18nT("ai_ontology.executed") : i18nT("ai_ontology.executeFailed"));
    ElMessage[execOk.value ? "success" : "warning"](execResult.value);
  } catch (e: any) {
    execOk.value = false;
    execResult.value = e?.msg || i18nT("ai_ontology.executeFailed");
    ElMessage.error(execResult.value);
  } finally {
    execLoading.value = false;
  }
}
</script>

<style scoped lang="scss">
.ont-act__head {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ont-act__title {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.ont-act__ico {
  font-size: var(--el-font-size-extra-large);
  color: var(--el-color-primary);
}
.ont-act__name {
  font-size: var(--el-font-size-medium);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-act__sub {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-act__ops {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
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
.ont-sec__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-note {
  margin-top: 8px;
}
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-flow {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.ont-flow__col {
  flex: 1 1 0;
  min-width: 0;
  padding: 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.ont-flow__colhead {
  padding: 4px 8px;
  margin-bottom: 8px;
  font-size: var(--el-font-size-extra-small);
  font-weight: 600;
  color: var(--el-color-white);
  background: var(--el-text-color-secondary);
  border-radius: 3px;
}
.ont-flow__mid {
  padding-top: 60px;
  font-size: var(--el-font-size-large);
  color: var(--el-text-color-secondary);
}
.ont-flow__item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px;
  margin-bottom: 6px;
  background: var(--el-bg-color);
  border-radius: 4px;
}
.ont-flow__icon {
  margin-top: 2px;
  color: var(--el-color-primary);
}
.ont-flow__body {
  min-width: 0;
}
.ont-flow__name {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}
.ont-flow__meta {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-dep {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: var(--el-font-size-base);
}
.ont-dep__name {
  width: 80px;
  color: var(--el-text-color-regular);
}
.ont-dep__items {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
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
.ont-rules-err {
  margin-top: 8px;
}
.ont-crit-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 6px;
}
.ont-test__block {
  margin-top: 10px;
}
.ont-test__node {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}
</style>
