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
        <span class="ont-sec__title">本体资源权限</span>
        <template v-if="overview">
          <el-tag v-if="overview.acl?.inherited" size="small" type="info" effect="plain">
            未配置（公开）
          </el-tag>
          <template v-else>
            <el-button class="ont-sec__op" size="small" type="primary" v-hasPerm="'module_ai:ontology:manage'" @click="saveAcl">
              保存
            </el-button>
            <el-button size="small" v-hasPerm="'module_ai:ontology:manage'" @click="resetAcl">恢复默认</el-button>
          </template>
        </template>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="控制谁能看到/编辑/管理这个对象类型的定义。看得到类型不等于看得到数据——数据由下面的行级与列级策略决定。"
      />
      <el-form label-width="110px" class="ont-secview__form">
        <el-form-item label="可查看角色">
          <el-select
            v-model="acl.view_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            placeholder="留空 = 所有人可见"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="可编辑角色">
          <el-select
            v-model="acl.edit_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            placeholder="留空 = 所有人可编辑"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="可管理角色">
          <el-select
            v-model="acl.manage_roles"
            multiple
            filterable
            clearable
            style="width: 100%"
            placeholder="留空 = 所有人可管理（含改权限策略本身）"
          >
            <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ② 行级策略（对象安全策略） -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">行级安全策略</span>
        <el-tag size="small" effect="plain">{{ rowPolicies.length }} 条</el-tag>
        <el-button
          class="ont-sec__op"
          size="small"
          type="primary"
          :icon="Plus"
          @click="openPolicy()"
        >
          新建策略
        </el-button>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        class="ont-note"
        title="只在读时生效：过滤用户能读到哪些对象实例，不影响底层数据，也不会传播到下游导出。未配置任何启用的允许策略时全部可见。"
      />
      <el-table :data="rowPolicies" size="small" border>
        <template #empty>
          <el-empty :image-size="50" description="未配置行级策略（全部可见）" />
        </template>
        <el-table-column prop="name" label="策略名" min-width="150" show-overflow-tooltip />
        <el-table-column label="表达式" min-width="260">
          <template #default="{ row }">
            <code class="ont-secview__expr">{{ row.expression }}</code>
          </template>
        </el-table-column>
        <el-table-column label="效果" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.effect === 'allow' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ row.effect === "allow" ? "允许" : "拒绝" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="引用属性" min-width="150" show-overflow-tooltip>
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
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openPolicy(row)">编辑</el-button>
            <el-button link type="danger" size="small" v-hasPerm="'module_ai:ontology:manage'" @click="doRemovePolicy(row)">删除</el-button>
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
        <span class="ont-sec__title">列级安全（属性可见角色）</span>
        <el-tag size="small" effect="plain">
          {{ overview?.column_restricted?.length || 0 }} / {{ overview?.column_total || 0 }} 受限
        </el-tag>
      </div>
      <el-table :data="propList" size="small" border max-height="420">
        <template #empty><el-empty :image-size="50" description="暂无属性" /></template>
        <el-table-column prop="name" label="属性" min-width="150" show-overflow-tooltip />
        <el-table-column prop="code" label="属性 ID" min-width="130" show-overflow-tooltip />
        <el-table-column label="策略属性" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="policyProps.includes(row.code)"
              size="small"
              type="warning"
              effect="plain"
            >
              是
            </el-tag>
            <span v-else class="ont-none">否</span>
          </template>
        </el-table-column>
        <el-table-column label="可见角色" min-width="260">
          <template #default="{ row }">
            <el-select
              v-model="row.roles"
              multiple
              filterable
              clearable
              size="small"
              placeholder="留空 = 所有人可见"
              style="width: 100%"
              @change="saveColumn(row)"
            >
              <el-option v-for="r in roleOptions" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="敏感" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive" size="small" type="danger" effect="plain">是</el-tag>
            <span v-else class="ont-none">否</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="ont-hint">
        被行级策略引用的「策略属性」改动会影响可见性，因此额外受管理角色约束。
      </div>
    </el-card>

    <!-- ④ Check access -->
    <el-card shadow="never" class="ont-secview__card">
      <div class="ont-sec__head">
        <span class="ont-sec__title">检查访问权限</span>
        <span class="ont-hint">选一个人，看他能不能看到某个对象、以及为什么</span>
      </div>
      <div class="ont-secview__check">
        <el-select v-model="checkUser" filterable placeholder="选择用户" style="width: 200px">
          <el-option
            v-for="u in userOptions"
            :key="u.id"
            :label="`${u.name}（${u.username}）`"
            :value="u.id"
          />
        </el-select>
        <el-input
          v-model="checkKey"
          placeholder="对象主键（可留空，只看类型与列）"
          style="width: 240px"
        />
        <el-button type="primary" size="small" :loading="checking" @click="runCheck">
          检查
        </el-button>
      </div>
      <template v-if="checkResult">
        <el-alert
          :type="checkResult.allowed ? 'success' : 'error'"
          :closable="false"
          class="ont-note"
          :title="checkResult.allowed ? '允许访问' : '拒绝访问'"
        />
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item v-for="(s, i) in checkResult.steps" :key="i" :label="s.step">
            <el-tag size="small" :type="s.ok ? 'success' : 'danger'" effect="plain">
              {{ s.ok ? "通过" : "拒绝" }}
            </el-tag>
            <span class="ont-secview__reason">{{ s.detail }}</span>
            <div v-if="s.hidden?.length" class="ont-hint">
              不可读属性：{{ s.hidden.map((h: any) => h.code).join("、") }}
            </div>
          </el-descriptions-item>
          <el-descriptions-item v-if="checkResult.visible_columns" label="可见列数">
            {{ checkResult.visible_columns.length }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-card>

    <!-- 策略编辑 -->
    <el-dialog v-model="policyDialog" title="行级安全策略" width="760px" append-to-body>
      <el-form label-width="110px">
        <el-form-item label="策略名">
          <el-input v-model="policyForm.name" placeholder="如 只看本部门设备" />
        </el-form-item>
        <el-form-item label="效果">
          <el-radio-group v-model="policyForm.effect">
            <el-radio-button value="allow">允许</el-radio-button>
            <el-radio-button value="deny">拒绝</el-radio-button>
          </el-radio-group>
          <span class="ont-hint">拒绝优先于允许；有允许策略时必须命中至少一条</span>
        </el-form-item>
        <el-form-item label="表达式">
          <CodeEditor v-model="policyForm.expression" language="python" height="120px" border />
          <div class="ont-hint">
            可用对象属性（直接写列名）与
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
            。支持 and / or / not / in 与比较。
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="policyForm.enabled" />
        </el-form-item>
        <el-form-item label="">
          <el-button size="small" :loading="policyChecking" v-hasPerm="'module_ai:ontology:manage'" @click="doCheckPolicy">
            校验表达式
          </el-button>
          <span v-if="policyCheckMsg" class="ont-secview__reason">{{ policyCheckMsg }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="policyDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" v-hasPerm="'module_ai:ontology:manage'" @click="savePolicy">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
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
    ElMessage.error(e?.msg || "加载安全配置失败");
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
    ElMessage.success("资源权限已保存");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function resetAcl() {
  await ElMessageBox.confirm(
    "将清除该对象类型的资源权限配置，恢复为「所有人可见/可编辑」。行级与列级策略不受影响。确认恢复？",
    "恢复默认",
    { type: "warning", confirmButtonText: "恢复", cancelButtonText: "取消" }
  );
  await clearOntResourceAcl("object", props.code);
  ElMessage.success("已恢复默认");
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
    ElMessage.error(e?.msg || "暂存失败");
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
    if (d.ok) ElMessage.success("表达式可用");
    else ElMessage.warning(d.msg || "表达式有问题");
  } catch (e: any) {
    policyCheckMsg.value = e?.msg || "校验失败";
    ElMessage.error(policyCheckMsg.value);
  } finally {
    policyChecking.value = false;
  }
}

async function savePolicy() {
  if (!policyForm.expression?.trim()) return ElMessage.warning("请填写策略表达式");
  saving.value = true;
  try {
    const r = await saveOntRowPolicy({ ...policyForm });
    ElMessage.success(r.data?.msg || "已保存");
    policyDialog.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function doRemovePolicy(row: any) {
  await ElMessageBox.confirm(
    `将删除行级策略「${row.name || row.expression}」。删除后该策略不再参与过滤` +
      "（若这是唯一的允许策略，所有人将恢复可见全部对象）。确认删除？",
    "删除策略",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await removeOntRowPolicy(row.id);
  ElMessage.success("已删除");
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
    ElMessage.error(e?.msg || "检查失败");
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
