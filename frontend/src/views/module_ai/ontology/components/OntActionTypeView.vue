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
          <div class="ont-act__sub">动作类型 · 作用于 {{ objName(act.object_code) }}</div>
        </div>
      </div>
      <div class="ont-act__ops">
        <el-button size="small" type="success" :icon="VideoPlay" @click="openExec">执行</el-button>
        <el-button size="small" :icon="Edit" @click="emit('edit')">编辑</el-button>
      </div>
    </div>

    <!-- ============ Overview ============ -->
    <template v-if="page === 'overview'">
      <section class="ont-sec">
        <div class="ont-sec__head"><span class="ont-sec__title">元数据</span></div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="动作名">{{ act.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" effect="plain" :type="statusTagType(act.status)">
              {{ labelOf(ONT_STATUS, act.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="编码">
            <span class="ont-mono">{{ act.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="作用对象类型">
            {{ objName(act.object_code) }}
          </el-descriptions-item>
          <el-descriptions-item label="写回目标">
            <span class="ont-mono">{{ act.target_table || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="审批门禁">
            <el-tag size="small" effect="plain" :type="act.approval ? 'warning' : 'info'">
              {{ act.approval ? "需审批" : "无需审批" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            <span :class="{ 'ont-none': !act.description }">{{ act.description || "未填写" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="Tool description（供 AI 调用）" :span="2">
            <span :class="{ 'ont-none': !act.tool_description }">
              {{ act.tool_description || "未填写 —— Agent 将退回使用「描述」" }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </section>

      <!-- Input → Rules 双列图（官方 Overview 的核心卡片） -->
      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">动作总览</span>
          <span class="ont-hint">输入参数 → 规则</span>
        </div>
        <div class="ont-flow">
          <!-- Input 列 -->
          <div class="ont-flow__col">
            <div class="ont-flow__colhead">输入 Input</div>
            <div v-for="f in fields" :key="f.key" class="ont-flow__item">
              <el-icon class="ont-flow__icon">
                <component :is="f.objectRef ? 'Aim' : 'EditPen'" />
              </el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">{{ f.label || f.key }}</div>
                <div class="ont-flow__meta">
                  {{ f.objectRef ? "对象引用参数" : f.desc || f.key }}
                </div>
              </div>
            </div>
            <el-empty v-if="!fields.length" :image-size="40" description="无输入参数" />
          </div>
          <div class="ont-flow__mid">
            <el-icon><Right /></el-icon>
          </div>
          <!-- Rules 列 -->
          <div class="ont-flow__col">
            <div class="ont-flow__colhead">规则 Rules</div>
            <div v-for="(r, i) in rulesSummary" :key="i" class="ont-flow__item">
              <el-icon class="ont-flow__icon"><component :is="ruleIcon" /></el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">
                  {{ r.type ? ruleLabel(r.type) : r.kind }}
                </div>
                <div class="ont-flow__meta">
                  <template v-if="r.type">
                    赋值：{{
                      (r.assignments || [])
                        .map((a: any) => `${a.property}←${SOURCE_LABEL[a.source] || a.source}`)
                        .join("  ") || "无"
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
                <div class="ont-flow__name">副作用 ×{{ realEffects.length }}</div>
                <div class="ont-flow__meta">
                  {{
                    realEffects
                      .map((e: any) => (e.type === "notification" ? "通知" : "Webhook"))
                      .join("、")
                  }}
                </div>
              </div>
            </div>
            <div v-if="act.approval" class="ont-flow__item">
              <el-icon class="ont-flow__icon"><Lock /></el-icon>
              <div class="ont-flow__body">
                <div class="ont-flow__name">审批门禁</div>
                <div class="ont-flow__meta">执行前需通过审批，否则只生成待审单</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="ont-sec">
        <div class="ont-sec__head">
          <span class="ont-sec__title">依赖</span>
          <el-tag size="small" type="info" effect="plain">1</el-tag>
        </div>
        <div class="ont-dep">
          <span class="ont-dep__name">对象类型</span>
          <el-tag size="small" effect="plain">1</el-tag>
          <span class="ont-dep__items">{{ objName(act.object_code) }}</span>
        </div>
        <el-alert
          type="info"
          :closable="false"
          class="ont-note"
          title="智能体、工作流等外部依赖暂未接入。"
        />
      </section>
    </template>

    <!-- ============ Rules ============ -->
    <section v-else-if="page === 'rules'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">规则</span>
        <el-tag size="small" type="info" effect="plain">共 {{ realRules.length }}</el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Edit" @click="openRules">
          编辑规则
        </el-button>
        <el-button size="small" :icon="VideoPlay" @click="openTestRun">试运行</el-button>
      </div>

      <el-alert
        v-if="!realRules.length"
        type="warning"
        :closable="false"
        class="ont-note"
        title="未配置规则：当前走兼容路径（按「写回目标表 + 可写字段白名单」执行 update）。配好规则后，写哪些列由规则决定。"
      />
      <el-table v-else :data="realRules" size="small" border>
        <el-table-column label="规则" width="150">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ ruleLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="赋值" min-width="340">
          <template #default="{ row }">
            <div v-for="a in row.assignments || []" :key="a.property" class="ont-mono">
              {{ a.property }} ← {{ sourceLabel(a) }}
            </div>
            <span v-if="!(row.assignments || []).length" class="ont-none">无赋值</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="ont-sec__head ont-sec__head--mt">
        <span class="ont-sec__title">副作用</span>
        <el-tag size="small" type="info" effect="plain">{{ realEffects.length }}</el-tag>
        <span class="ont-hint">通知写站内信；Webhook 发 HTTP 请求（可设 before/after）</span>
      </div>
      <el-table :data="realEffects" size="small" border>
        <template #empty>
          <el-empty :image-size="50" description="未配置副作用" />
        </template>
        <el-table-column prop="type" label="类型" width="130">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.type === "notification" ? "通知" : "Webhook" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timing" label="时机" width="90">
          <template #default="{ row }">
            {{ row.timing === "before" ? "编辑前" : "编辑后" }}
          </template>
        </el-table-column>
        <el-table-column label="目标" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            {{
              row.type === "notification" ? `收件人 ${(row.recipients || []).join("、")}` : row.url
            }}
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="已实现的规则：修改对象 / 创建对象 / 删除对象（赋值来源：参数、静态值、当前用户、当前时间、对象参数的属性）。官方的链接类规则、函数规则、接口规则尚未实现。"
      />
    </section>

    <!-- ============ Parameters ============ -->
    <section v-else-if="page === 'parameters'" class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">参数</span>
        <el-tag size="small" type="info" effect="plain">{{ fields.length }}</el-tag>
      </div>
      <el-table :data="fields" size="small" border>
        <template #empty><el-empty :image-size="50" description="无参数" /></template>
        <el-table-column prop="key" label="参数 ID" min-width="140" />
        <el-table-column prop="label" label="显示名" min-width="140" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.objectRef ? "对象引用" : "基础类型" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="官方参数支持默认值、下拉过滤、安全策略、覆盖与性能等配置，并会生成工具 JSON Schema。当前版本尚未支持齐。"
      />
    </section>

    <!-- ============ Security & Submission Criteria ============ -->
    <section v-else class="ont-sec">
      <div class="ont-sec__head">
        <span class="ont-sec__title">安全与提交条件</span>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          :icon="Edit"
          @click="openCriteria"
        >
          编辑提交条件
        </el-button>
        <el-button size="small" type="primary" link @click="openEffects">编辑副作用</el-button>
        <el-button size="small" :icon="VideoPlay" @click="openTestRun">试运行</el-button>
      </div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="白名单校验">
          <el-tag size="small" type="success" effect="plain">已启用</el-tag>
          <span class="ont-hint">未配置规则时，写入字段必须在白名单内，否则直接拒绝</span>
        </el-descriptions-item>
        <el-descriptions-item label="可写字段">
          <template v-if="writable.length">
            <el-tag v-for="w in writable" :key="w" size="small" effect="plain" class="ont-tag-gap">
              {{ w }}
            </el-tag>
          </template>
          <span v-else class="ont-none">未配置</span>
        </el-descriptions-item>
        <el-descriptions-item label="审批门禁">
          <el-tag size="small" :type="act.approval ? 'warning' : 'info'" effect="plain">
            {{ act.approval ? "需审批（只生成待审批单，由管理员批准）" : "无需审批" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="提交条件">
          <template v-if="realCriteria.length">
            <el-tag size="small" type="success" effect="plain">
              已配置 {{ realCriteria.length }} 条，全部满足才可提交
            </el-tag>
            <div v-for="(c, i) in realCriteria" :key="i" class="ont-crit-item">
              <span class="ont-mono">{{ critSummary(c) }}</span>
              <span class="ont-none">→ 不满足时提示：{{ c.failure_message || "（未填）" }}</span>
            </div>
          </template>
          <span v-else class="ont-none">未配置（任何满足参数与白名单的请求都可提交）</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="执行顺序：提交条件 → 值类型约束 → 规则/白名单 → 审批门禁 → 规则执行 → 副作用 → 审计。条件模板支持当前用户、当前用户所属组、参数、执行上下文（场景）。"
      />
    </section>

    <!-- 提交条件编辑 -->
    <el-dialog v-model="critDialog" title="编辑提交条件（JSON）" width="720px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"operator":"is_not_empty","failure_message":"名称不能为空","left":{"kind":"parameter","value":"name"}}]'
      />
      <el-input v-model="critText" type="textarea" :rows="12" />
      <div v-if="critErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" title="配置有问题">
          <ul class="ont-review__list">
            <li v-for="(e, i) in critErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="critDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveCriteria">保存</el-button>
      </template>
    </el-dialog>

    <!-- 副作用编辑 -->
    <el-dialog v-model="fxDialog" title="编辑副作用（JSON）" width="720px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"type":"notification","title":"已改名 {{name}}","recipients":[1]},{"type":"webhook","url":"https://example.com/hook","method":"POST","timing":"after","blocking":false}]'
      />
      <el-input v-model="fxText" type="textarea" :rows="10" />
      <div v-if="fxErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" title="配置有问题">
          <ul class="ont-review__list">
            <li v-for="(e, i) in fxErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="fxDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveEffects">保存</el-button>
      </template>
    </el-dialog>

    <!-- 试运行 -->
    <el-dialog v-model="testDialog" title="试运行（不会写入任何数据）" width="720px" append-to-body>
      <el-form label-width="110px" size="small">
        <el-form-item label="对象行 ID">
          <el-input v-model="testForm.object_key" placeholder="目标行主键" style="width: 200px" />
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
        运行
      </el-button>
      <template v-if="testResult">
        <el-divider />
        <el-alert
          :type="testResult.would_submit ? 'success' : 'error'"
          :closable="false"
          :title="testResult.would_submit ? '可以提交' : '会被拦下（或规则有误）'"
        />
        <div class="ont-test__block">
          <div class="ont-sec__title">提交条件</div>
          <div v-if="!testResult.criteria_used" class="ont-none">未配置</div>
          <template v-else>
            <div v-for="(t, i) in testResult.criteria?.trace || []" :key="i">
              <el-tag size="small" :type="t.ok ? 'success' : 'danger'" effect="plain">
                第 {{ i + 1 }} 条：{{ t.ok ? "通过" : "未通过" }}
              </el-tag>
              <div v-for="(n, j) in t.nodes" :key="j" class="ont-mono ont-test__node">
                {{ n.operator }} · 左 {{ JSON.stringify(n.left) }} · 右
                {{ JSON.stringify(n.right) }} → {{ n.ok ? "通过" : "未通过" }}
              </div>
            </div>
            <el-alert
              v-if="(testResult.criteria?.failures || []).length"
              type="error"
              :closable="false"
              class="ont-note"
              :title="'失败信息：' + testResult.criteria.failures.join('；')"
            />
          </template>
        </div>
        <div class="ont-test__block">
          <div class="ont-sec__title">规则会产生的编辑</div>
          <div v-if="!testResult.rules_used" class="ont-none">未配置规则（走白名单兼容路径）</div>
          <div v-for="(e, i) in testResult.rules?.edits || []" :key="i" class="ont-mono">
            {{ ruleLabel(e.rule) }} → {{ JSON.stringify(e.assignments) }}
          </div>
          <div v-for="(w, i) in testResult.rules?.warnings || []" :key="'w' + i" class="ont-none">
            ⚠ {{ w }}
          </div>
        </div>
        <div class="ont-test__block">
          <div class="ont-sec__title">副作用</div>
          <div v-if="!testResult.side_effects_used" class="ont-none">未配置</div>
          <div v-for="(e, i) in testResult.side_effects?.effects || []" :key="i" class="ont-mono">
            {{
              e.type === "notification"
                ? `通知 ${e.recipients?.join("、")}：${e.title}`
                : `${e.method} ${e.url}`
            }}
          </div>
        </div>
        <div v-if="(testResult.value_type_errors || []).length" class="ont-test__block">
          <div class="ont-sec__title">值类型约束</div>
          <div v-for="(v, i) in testResult.value_type_errors" :key="i" class="ont-none">
            {{ v }}
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 规则编辑 -->
    <el-dialog v-model="rulesDialog" title="编辑规则（JSON）" width="720px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title='示例：[{"type":"modify_object","assignments":[{"property":"name","source":"parameter","value":"name"},{"property":"updated_by","source":"current_user"}]}]'
      />
      <el-input v-model="rulesText" type="textarea" :rows="12" />
      <div v-if="rulesErrors.length" class="ont-rules-err">
        <el-alert type="error" :closable="false" title="配置有问题">
          <ul class="ont-review__list">
            <li v-for="(e, i) in rulesErrors" :key="i">{{ e }}</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="rulesDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingCfg" @click="saveRules">保存</el-button>
      </template>
    </el-dialog>

    <!-- 执行对话框 -->
    <el-dialog v-model="execDialog" title="执行本体动作" width="560px" append-to-body>
      <el-alert
        v-if="act.approval"
        type="warning"
        :closable="false"
        class="ont-note"
        title="该动作开启了审批门禁：不勾「已获审批」只会生成待审单，不会写库"
      />
      <el-form :model="execForm" label-width="110px">
        <el-form-item label="动作">
          <el-tag size="small" type="primary" effect="dark">{{ act.name }}</el-tag>
        </el-form-item>
        <el-form-item label="写回目标">
          <span class="ont-mono">{{ act.target_table || "—" }}</span>
        </el-form-item>
        <el-form-item label="对象行 ID" required>
          <el-input v-model="execForm.object_key" placeholder="目标表主键 id" />
        </el-form-item>
        <el-form-item v-for="f in fields" :key="f.key" :label="f.label || f.key">
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
          v-if="act.approval"
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
        class="ont-note"
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
  <el-empty v-else description="未找到该动作类型" />
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Edit, Right, VideoPlay } from "@element-plus/icons-vue";
import { executeOntAction, getOntScenarios, testRunOntAction } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";
import { ONT_STATUS, labelOf, statusTagType } from "../constants";

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
  update: "修改对象",
  insert: "创建对象",
  delete: "删除对象",
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
          ? `按主键定位行并更新白名单内的字段：${writable.value.join("、") || "无"}`
          : m === "insert"
            ? "当前仅支持 update 写回，insert 会被拒绝"
            : "当前仅支持 update 写回，delete 会被拒绝",
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
  modify_object: "修改对象",
  create_object: "创建对象",
  delete_object: "删除对象",
};
const SOURCE_LABEL: Record<string, string> = {
  parameter: "参数",
  static: "静态值",
  current_user: "当前用户",
  current_time: "当前时间",
  object_parameter_property: "对象参数的属性",
};
function ruleLabel(t: string) {
  return RULE_LABEL[t] || t;
}
function sourceLabel(a: any) {
  const s = SOURCE_LABEL[a?.source] || a?.source || "参数";
  const v = a?.source === "static" ? JSON.stringify(a?.value) : a?.value || a?.parameter || "";
  return `${s}(${v})`;
}
function critSummary(c: any) {
  const left =
    c?.left?.kind === "current_user_group"
      ? "当前用户所属组"
      : c?.left?.kind === "current_user"
        ? "当前用户"
        : c?.left?.kind === "execution_context"
          ? "执行上下文"
          : `参数 ${c?.left?.value}`;
  const right =
    c?.right?.kind === "static"
      ? JSON.stringify(c?.right?.value)
      : c?.right?.kind === "parameter"
        ? `参数 ${c?.right?.value}`
        : "";
  const kids = c?.children || c?.conditions;
  if (kids)
    return `(${kids.length} 个子条件) ${c.operator === "or" ? "满足其一" : c.operator === "not" ? "取反" : "全部满足"}`;
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
      ElMessage.error(`${what} 必须是数组`);
      return null;
    }
    return v;
  } catch {
    ElMessage.error(`${what} 不是合法 JSON`);
    return null;
  }
}

/** 前端先做一遍校验（后端保存时还会再校验一次） */
function validateRulesLocal(items: any[]): string[] {
  const errs: string[] = [];
  const types: string[] = [];
  items.forEach((r: any, i: number) => {
    const where = `第 ${i + 1} 条`;
    if (!r || typeof r !== "object") return errs.push(`${where}：不是对象`);
    if (!RULE_LABEL[r.type]) return errs.push(`${where}：类型不支持 ${r.type || "(空)"}`);
    types.push(r.type);
    (r.assignments || []).forEach((a: any, j: number) => {
      if (!a?.property) errs.push(`${where} 赋值 ${j + 1}：缺少 property`);
      const s = a?.source || "parameter";
      if (!SOURCE_LABEL[s]) errs.push(`${where} 赋值 ${j + 1}：来源不支持 ${s}`);
      if (s === "parameter" && a?.value && !paramKeys.value.has(String(a.value)))
        errs.push(`${where} 赋值 ${j + 1}：引用了未定义的参数 ${a.value}`);
    });
  });
  if (types.filter((t) => t === "create_object").length > 1)
    errs.push("同一次提交里不允许创建两次对象（官方限制）");
  return errs;
}
function validateCriteriaLocal(items: any[]): string[] {
  const errs: string[] = [];
  const walk = (nodes: any[], where: string) => {
    nodes.forEach((n: any, i: number) => {
      const w = `${where} ${i + 1}`;
      if (!n || typeof n !== "object") return errs.push(`${w}：不是对象`);
      const kids = n.children || n.conditions;
      if (kids) {
        if (!Array.isArray(kids) || !kids.length) errs.push(`${w}：逻辑组没有子条件`);
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
        errs.push(`${w}：运算符不支持 ${n.operator || "(空)"}`);
      if (!n.left?.kind) errs.push(`${w}：缺少 left.kind`);
      else if (n.left.kind === "parameter") {
        if (!n.left.value) errs.push(`${w}：left 引用了空参数名`);
        else if (!paramKeys.value.has(String(n.left.value)) && paramKeys.value.size)
          errs.push(`${w}：left 引用了未定义的参数 ${n.left.value}`);
      }
      if (
        n.right?.kind === "parameter" &&
        n.right.value &&
        !paramKeys.value.has(String(n.right.value))
      )
        errs.push(`${w}：right 引用了未定义的参数 ${n.right.value}`);
    });
  };
  walk(items, "提交条件第");
  return errs;
}
function validateEffectsLocal(items: any[]): string[] {
  const errs: string[] = [];
  items.forEach((e: any, i: number) => {
    const w = `第 ${i + 1} 条`;
    if (!e || typeof e !== "object") return errs.push(`${w}：不是对象`);
    if (e.type === "notification") {
      if (!(e.recipients || []).length) errs.push(`${w}：通知未指定收件人 recipients`);
    } else if (e.type === "webhook") {
      if (!/^https?:\/\//i.test(String(e.url || "")))
        errs.push(`${w}：Webhook 的 URL 必须是 http/https`);
    } else {
      errs.push(`${w}：类型不支持 ${e.type || "(空)"}（可用 notification、webhook）`);
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
      `${label}已暂存（点右上角「保存」才生效）`
    );
    return ok;
  } finally {
    savingCfg.value = false;
  }
}
async function saveRules() {
  const items = parseArr(rulesText.value, "规则");
  if (items === null) return;
  rulesErrors.value = validateRulesLocal(items);
  if (rulesErrors.value.length) return;
  if (await stageField("rules", items, "规则")) rulesDialog.value = false;
}
async function saveCriteria() {
  const items = parseArr(critText.value, "提交条件");
  if (items === null) return;
  critErrors.value = validateCriteriaLocal(items);
  if (critErrors.value.length) return;
  if (await stageField("submission_criteria", items, "提交条件")) critDialog.value = false;
}
async function saveEffects() {
  const items = parseArr(fxText.value, "副作用");
  if (items === null) return;
  fxErrors.value = validateEffectsLocal(items);
  if (fxErrors.value.length) return;
  if (await stageField("side_effects", items, "副作用")) fxDialog.value = false;
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
    ElMessage.error(e?.msg || "试运行失败");
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
      code: props.code,
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
