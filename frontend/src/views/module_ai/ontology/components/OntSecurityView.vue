<!--
  安全（P4）——对象权限

  对齐官方 object-permissioning 的两层模型：
  · 本体资源（模式层）：对象/关系/动作/函数的 view / edit / manage
  · 对象与关系（数据层）：单元格级安全 = 行级（对象安全策略）+ 列级（属性角色）
  并把官方的「Security 标签页」与「Check access 面板」做出来。
-->
<template>
  <div class="ont-secview">
    <!-- ① 资源权限（模式层） -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.ontologyResourcePermissions") }}</span>
        <template v-if="overview">
          <el-tag v-if="overview.acl?.inherited" size="small" type="info" effect="plain">
            {{ i18nT("ai_ontology.notConfiguredPublic") }}
          </el-tag>
          <template v-else>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              class="ont-sec__op"
              size="small"
              type="primary"
              @click="saveAcl"
            >
              {{ i18nT("ai_ontology.save") }}
            </el-button>
            <el-button v-hasPerm="'module_ai:ontology:manage'" size="small" @click="resetAcl">
              {{ i18nT("ai_ontology.restoreDefault") }}
            </el-button>
          </template>
        </template>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.resourceAclAlert')"
      />
      <el-form label-width="110px" class="ont-secview__form">
        <el-form-item :label="i18nT('ai_ontology.viewableRoles')">
          <el-select
            v-model="acl.view_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            :placeholder="i18nT('ai_ontology.leaveEmptyEveryoneCanView')"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.editableRoles')">
          <el-select
            v-model="acl.edit_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            :placeholder="i18nT('ai_ontology.leaveEmptyEveryoneCanEdit')"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.manageRoles')">
          <el-select
            v-model="acl.manage_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            :placeholder="i18nT('ai_ontology.leaveEmptyEveryoneCanManage')"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ② 行级策略（对象安全策略） -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.rowLevelSecurityPolicy") }}</span>
        <el-tag size="small" effect="plain">
          {{ i18nT("ai_ontology.countItems", { count: rowPolicies.length }) }}
        </el-tag>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          :icon="Plus"
          @click="openPolicy()"
        >
          {{ i18nT("ai_ontology.newPolicy") }}
        </el-button>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.rowPolicyAlert')"
      />
      <el-table :data="rowPolicies" size="small" border stripe>
        <template #empty>
          <el-empty
            :image-size="50"
            :description="i18nT('ai_ontology.noRowLevelPolicyAllVisible')"
          />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.policyName')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.expression')" min-width="260">
          <template #default="{ row }">
            <code class="ont-secview__expr">{{ row.expression }}</code>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.effect')" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.effect === 'allow' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ row.effect === "allow" ? i18nT("ai_ontology.allow") : i18nT("ai_ontology.deny") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="i18nT('ai_ontology.referencedProperty')"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <el-tag
              v-for="v in row.variables"
              :key="v"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ v }}
            </el-tag>
            <span v-if="!row.variables?.length" class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.enabled')" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? i18nT("ai_ontology.enabled") : i18nT("ai_ontology.disabled") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="120" align="center">
          <template #default="{ row }">
            <el-button icon="edit" link type="primary" size="small" @click="openPolicy(row)">
              {{ i18nT("ai_ontology.edit") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              icon="delete"
              link
              type="danger"
              size="small"
              @click="doRemovePolicy(row)"
            >
              {{ i18nT("ai_ontology.delete2") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="overview?.hardening_hint"
        type="warning"
        :closable="false"
        class="ont-note"
        :title="overview.hardening_hint"
      />
    </el-card>

    <!-- ③ 列级安全（属性角色） -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">
          {{ i18nT("ai_ontology.columnLevelSecurityPropertyVisibilityRoles") }}
        </span>
        <el-tag size="small" effect="plain">
          {{
            i18nT("ai_ontology.restrictedCount", {
              restricted: overview?.column_restricted?.length || 0,
              total: overview?.column_total || 0,
            })
          }}
        </el-tag>
      </div>
      <el-table :data="propList" size="small" border max-height="420" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noProperties')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.property')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.attributeId')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.policyProperties')" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="policyProps.includes(row.code)"
              size="small"
              type="warning"
              effect="plain"
            >
              {{ i18nT("ai_ontology.yes") }}
            </el-tag>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.no") }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.visibleRoles')" min-width="260">
          <template #default="{ row }">
            <el-select
              v-model="row.roles"
              multiple
              filterable
              clearable
              size="small"
              :placeholder="i18nT('ai_ontology.leaveEmptyEveryoneCanView')"
              style="width: 100%"
              @change="saveColumn(row)"
            >
              <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.sensitive')" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive" size="small" type="danger" effect="plain">
              {{ i18nT("ai_ontology.yes") }}
            </el-tag>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.no") }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="ont-hint">
        {{
          i18nT(
            "ai_ontology.policyPropertyChangesReferencedByRowPoliciesAffectVisibilityAndNeedManageRoles"
          )
        }}
      </div>
    </el-card>

    <!-- ④ Check access -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.checkAccessPermissions") }}</span>
        <span class="ont-hint">
          {{ i18nT("ai_ontology.pickAPersonToSeeIfTheyCanSeeAnObjectAndWhy") }}
        </span>
      </div>
      <div class="ont-secview__check">
        <el-select
          v-model="checkUser"
          filterable
          :placeholder="i18nT('ai_ontology.selectUser')"
          style="width: 200px"
        >
          <el-option
            v-for="u in userOptions"
            :key="u.id"
            :label="
              i18nT('ai_ontology.userNameWithUsername', { name: u.name, username: u.username })
            "
            :value="u.id"
          />
        </el-select>
        <el-input
          v-model="checkKey"
          :placeholder="i18nT('ai_ontology.objectPKOptionalOnlyTypeAndColumn')"
          style="width: 240px"
        />
        <el-button type="primary" size="small" :loading="checking" @click="runCheck">
          {{ i18nT("ai_ontology.check") }}
        </el-button>
      </div>
      <template v-if="checkResult">
        <el-alert
          :type="checkResult.allowed ? 'success' : 'error'"
          :closable="false"
          class="ont-note"
          :title="
            checkResult.allowed ? i18nT('ai_ontology.allowAccess') : i18nT('ai_ontology.denyAccess')
          "
        />
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item v-for="(s, i) in checkResult.steps" :key="i" :label="s.step">
            <el-tag size="small" :type="s.ok ? 'success' : 'danger'" effect="plain">
              {{ s.ok ? i18nT("ai_ontology.pass") : i18nT("ai_ontology.deny") }}
            </el-tag>
            <span class="ont-secview__reason">{{ s.detail }}</span>
            <div v-if="s.hidden?.length" class="ont-hint">
              {{
                i18nT("ai_ontology.unreadableProps", {
                  list: s.hidden.map((h: any) => h.code).join("、"),
                })
              }}
            </div>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="checkResult.visible_columns"
            :label="i18nT('ai_ontology.visibleColumns')"
          >
            {{ checkResult.visible_columns.length }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-card>

    <!-- 策略编辑 -->
    <el-dialog
      v-model="policyDialog"
      :title="i18nT('ai_ontology.rowLevelSecurityPolicy')"
      width="900px"
      append-to-body
    >
      <el-form label-width="110px">
        <el-form-item :label="i18nT('ai_ontology.policyName')">
          <el-input
            v-model="policyForm.name"
            :placeholder="i18nT('ai_ontology.eGOnlyDevicesInThisDept')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.effect')">
          <el-radio-group v-model="policyForm.effect">
            <el-radio-button value="allow">{{ i18nT("ai_ontology.allow") }}</el-radio-button>
            <el-radio-button value="deny">{{ i18nT("ai_ontology.reject2") }}</el-radio-button>
          </el-radio-group>
          <span class="ont-hint">
            {{
              i18nT("ai_ontology.denyTakesPrecedenceOverAllowWithAllowPoliciesAtLeastOneMustMatch")
            }}
          </span>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.expression')">
          <CodeEditor v-model="policyForm.expression" language="python" height="120px" border />
          <div class="ont-hint">
            {{ i18nT("ai_ontology.availableObjectPropertiesWriteColumnNamesAnd") }}
            <code>user</code>
            ：
            <code>user.id</code>
            /
            <code>user.name</code>
            /
            <code>user.dept</code>
            /
            <code>user.attribute('x')</code>
            /
            <code>user.role('ADMIN')</code>
            {{ i18nT("ai_ontology.exprSupportHint") }}
          </div>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.enabled')">
          <el-switch v-model="policyForm.enabled" />
        </el-form-item>
        <el-form-item label="">
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            size="small"
            :loading="policyChecking"
            @click="doCheckPolicy"
          >
            {{ i18nT("ai_ontology.validateExpression") }}
          </el-button>
          <span v-if="policyCheckMsg" class="ont-secview__reason">{{ policyCheckMsg }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="policyDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="saving"
          @click="savePolicy"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import CodeEditor from "@/components/CodeEditor/index.vue";
import {
  checkOntPolicy,
  clearOntResourceAcl,
  explainOntAccess,
  getOntRowPolicies,
  getOntSecurityOverview,
  getOntSecuritySubjects,
  removeOntRowPolicy,
  saveOntResourceAcl,
  saveOntRowPolicy,
} from "@/api/module_ai/ontology";
import { stageOntChange, getOntProperties } from "@/api/module_ai/ontology";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string }>();

const overview = ref<any>(null);
const rowPolicies = ref<any[]>([]);
const propList = ref<any[]>([]);
const roleOptions = ref<any[]>([]);
const userOptions = ref<any[]>([]);
const acl = reactive<{ view_roles: string[]; edit_roles: string[]; manage_roles: string[] }>({
  view_roles: [],
  edit_roles: [],
  manage_roles: [],
});
const saving = ref(false);

const policyProps = computed<string[]>(() => overview.value?.policy_properties || []);

async function load() {
  if (!props.code) return;
  try {
    const [ov, pol, pr, sub] = await Promise.all([
      getOntSecurityOverview(props.code),
      getOntRowPolicies(props.code),
      getOntProperties(props.code),
      getOntSecuritySubjects(),
    ]);
    overview.value = ov.data?.data || null;
    rowPolicies.value = pol.data?.data || [];
    propList.value = (pr.data?.data || []).map((p: any) => ({ ...p, roles: p.roles || [] }));
    const d = sub.data?.data || {};
    roleOptions.value = d.roles || [];
    userOptions.value = d.users || [];
    const a = overview.value?.acl || {};
    acl.view_roles = a.view_roles || [];
    acl.edit_roles = a.edit_roles || [];
    acl.manage_roles = a.manage_roles || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadSecurityConfigFailed"));
  }
}

async function saveAcl() {
  saving.value = true;
  try {
    await saveOntResourceAcl({
      resource_kind: "object",
      resource_code: props.code,
      view_roles: acl.view_roles,
      edit_roles: acl.edit_roles,
      manage_roles: acl.manage_roles,
    });
    ElMessage.success(i18nT("ai_ontology.resourcePermissionsSaved"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    saving.value = false;
  }
}

async function resetAcl() {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.resetAclConfirm"),
    i18nT("ai_ontology.restoreDefault"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.restore"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await clearOntResourceAcl("object", props.code);
  ElMessage.success(i18nT("ai_ontology.defaultRestored"));
  await load();
}

/** 列级：改属性的可见角色（走工作副本暂存） */
async function saveColumn(row: any) {
  try {
    await stageOntChange({
      kind: "property",
      action: "update",
      data: {
        id: row.id,
        object_code: props.code,
        code: row.code,
        name: row.name,
        prop_type: row.prop_type,
        roles: row.roles,
      },
    });
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.stagingFailed"));
  }
}

/* ---------------- 行级策略 ---------------- */
const policyDialog = ref(false);
const policyChecking = ref(false);
const policyCheckMsg = ref("");
const policyForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  description: "",
  expression: "",
  effect: "allow",
  enabled: true,
  priority: 0,
});

function openPolicy(row?: any) {
  Object.assign(policyForm, {
    id: row?.id ?? null,
    object_code: props.code,
    name: row?.name || "",
    description: row?.description || "",
    expression: row?.expression || "",
    effect: row?.effect || "allow",
    enabled: row?.enabled ?? true,
    priority: row?.priority ?? 0,
  });
  policyCheckMsg.value = "";
  policyDialog.value = true;
}

async function doCheckPolicy() {
  policyChecking.value = true;
  policyCheckMsg.value = "";
  try {
    const r = await checkOntPolicy({
      expression: policyForm.expression,
      object_code: props.code,
    });
    const d = r.data?.data || {};
    policyCheckMsg.value = d.msg || "";
    if (d.ok) ElMessage.success(i18nT("ai_ontology.expressionAvailable"));
    else ElMessage.warning(d.msg || i18nT("ai_ontology.expressionIssue"));
  } catch (e: any) {
    policyCheckMsg.value = e?.msg || i18nT("ai_ontology.validateFailed");
    ElMessage.error(policyCheckMsg.value);
  } finally {
    policyChecking.value = false;
  }
}

async function savePolicy() {
  if (!policyForm.expression?.trim())
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterPolicyExpression"));
  saving.value = true;
  try {
    const r = await saveOntRowPolicy({ ...policyForm });
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.saved"));
    policyDialog.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    saving.value = false;
  }
}

async function doRemovePolicy(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deletePolicyConfirm", { name: row.name || row.expression }),
    i18nT("ai_ontology.deletePolicy"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await removeOntRowPolicy(row.id);
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await load();
}

/* ---------------- Check access ---------------- */
const checkUser = ref<number | undefined>(undefined);
const checkKey = ref("");
const checking = ref(false);
const checkResult = ref<any>(null);

async function runCheck() {
  checking.value = true;
  checkResult.value = null;
  try {
    const r = await explainOntAccess({
      object_code: props.code,
      object_key: checkKey.value || undefined,
      user_id: checkUser.value,
    });
    checkResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.checkFailed"));
  } finally {
    checking.value = false;
  }
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-secview__card {
  margin-bottom: 12px;
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
.ont-sec__op {
  margin-left: auto;
}

.ont-secview__form {
  max-width: 620px;
}

.ont-secview__expr {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-extra-small);
  color: var(--el-color-primary);
}

.ont-secview__check {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.ont-secview__reason {
  margin-left: 8px;
  color: var(--el-text-color-regular);
}

/* 标题与右侧说明之间留间距（否则会挤在一起） */
.ont-secview .ont-sec__head .ont-hint {
  margin-left: 8px;
}
</style>
