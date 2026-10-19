<!--
  P5 高级类型系统：对象类型组 / 值类型 / 共享属性 / 接口

  四个分区共用一套交互：列表 → 编辑弹窗 → 删除（删除前做引用检查）
-->
<template>
  <div class="ont-adv">
    <!-- ============ 对象类型组 ============ -->
    <template v-if="section === 'groups'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openGroup()">新建组</el-button>
        <el-tag size="small" type="info" effect="plain">共 {{ groups.length }}</el-tag>
        <span class="ont-hint">
          组是**跨对象类型**的多对多分组（不同于「所属本体」的一对一归属），可用于筛选与批量操作
        </span>
      </div>
      <el-table :data="groups" size="small" border max-height="480">
        <template #empty><el-empty :image-size="50" description="暂无分组" /></template>
        <el-table-column prop="name" label="组名" min-width="160" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" min-width="120" show-overflow-tooltip />
        <el-table-column label="成员" min-width="260">
          <template #default="{ row }">
            <template v-if="row.members?.length">
              <el-tag
                v-for="m in row.members.slice(0, 4)"
                :key="m"
                size="small"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ objectLabel(m) }}
              </el-tag>
              <span v-if="row.members.length > 4" class="ont-none">
                +{{ row.members.length - 4 }}
              </span>
            </template>
            <span v-else class="ont-none">无成员</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openGroup(row)">编辑</el-button>
            <el-button link type="danger" size="small" v-hasPerm="'module_ai:ontology:edit'" @click="delGroup(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 值类型 ============ -->
    <template v-else-if="section === 'valueTypes'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openVt()">新建值类型</el-button>
        <el-tag size="small" type="info" effect="plain">共 {{ valueTypes.length }}</el-tag>
        <span class="ont-hint">
          值类型是基础类型之上的**语义包装**（邮箱/URL/UUID/枚举…）＋约束＋版本；属性可引用它
        </span>
      </div>
      <el-table :data="valueTypes" size="small" border max-height="480">
        <template #empty><el-empty :image-size="50" description="暂无值类型" /></template>
        <el-table-column prop="name" label="显示名" min-width="150" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" min-width="130" show-overflow-tooltip />
        <el-table-column prop="base_type" label="基础类型" width="110" />
        <el-table-column label="约束" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'ont-none': !Object.keys(row.constraints || {}).length }">
              {{
                Object.keys(row.constraints || {}).length ? JSON.stringify(row.constraints) : "无"
              }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="引用" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ref_count ? 'warning' : 'info'" effect="plain">
              {{ row.ref_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openVt(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openValidate(row)">试校验</el-button>
            <el-button link type="danger" size="small" v-hasPerm="'module_ai:ontology:edit'" @click="delVt(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 共享属性 ============ -->
    <template v-else-if="section === 'shared'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openSp()">
          新建共享属性
        </el-button>
        <el-tag size="small" type="info" effect="plain">共 {{ shared.length }}</el-tag>
        <span class="ont-hint">
          定义一次、多个对象类型引用；**只共享元数据，不共享数据**。改元数据会同步到引用方
        </span>
      </div>
      <el-table :data="shared" size="small" border max-height="480">
        <template #empty><el-empty :image-size="50" description="暂无共享属性" /></template>
        <el-table-column prop="name" label="显示名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="code" label="属性 ID" min-width="130" show-overflow-tooltip />
        <el-table-column prop="api_name" label="API 名" min-width="130" show-overflow-tooltip />
        <el-table-column prop="prop_type" label="类型" width="100" />
        <el-table-column label="值类型" min-width="120">
          <template #default="{ row }">
            <span :class="{ 'ont-none': !row.value_type_code }">
              {{ row.value_type_code || "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="被引用" min-width="220">
          <template #default="{ row }">
            <el-tag
              v-for="r in (row.refs || []).slice(0, 3)"
              :key="r.where"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ objectLabel(r.where.split(".")[0]) }}
            </el-tag>
            <span v-if="!row.refs?.length" class="ont-none">未被引用</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openSp(row)">编辑</el-button>
            <el-button link type="danger" size="small" v-hasPerm="'module_ai:ontology:edit'" @click="delSp(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 接口 ============ -->
    <template v-else>
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openIf()">新建接口</el-button>
        <el-button size="small" :icon="Search" :loading="checking" @click="runCheck">
          合规检查
        </el-button>
        <el-tag size="small" type="info" effect="plain">共 {{ interfaces.length }}</el-tag>
        <el-tag v-if="issues.length" size="small" type="danger" effect="plain">
          不合规 {{ issues.length }}
        </el-tag>
        <span class="ont-hint">
          接口声明必需属性/关系/动作；让对象类型实现时**约束在实现侧强制**，不满足会被拒绝
        </span>
      </div>
      <el-table :data="interfaces" size="small" border max-height="440">
        <template #empty><el-empty :image-size="50" description="暂无接口" /></template>
        <el-table-column prop="name" label="接口名" min-width="150" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" min-width="120" show-overflow-tooltip />
        <el-table-column label="必需属性" width="100" align="center">
          <template #default="{ row }">{{ row.required_properties?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="必需关系" width="100" align="center">
          <template #default="{ row }">{{ row.required_links?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="必需动作" width="100" align="center">
          <template #default="{ row }">{{ row.required_actions?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="实现者" min-width="240">
          <template #default="{ row }">
            <template v-if="row.implementations?.length">
              <el-tag
                v-for="oc in row.implementations"
                :key="oc"
                size="small"
                type="success"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ objectLabel(oc) }}
              </el-tag>
            </template>
            <span v-else class="ont-none">暂无实现</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openIf(row)">编辑</el-button>
            <el-button link type="danger" size="small" v-hasPerm="'module_ai:ontology:edit'" @click="delIf(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="issues.length" class="ont-sub-title">不合规的实现</div>
      <el-table v-if="issues.length" :data="issues" size="small" border max-height="220">
        <el-table-column prop="interface_name" label="接口" min-width="140" />
        <el-table-column label="对象类型" min-width="150">
          <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
        </el-table-column>
        <el-table-column label="缺失" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">{{ missingText(row.missing) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 编辑弹窗 ============ -->
    <el-dialog v-model="dlg" :title="dlgTitle" width="640px" append-to-body>
      <el-form label-width="130px" size="small">
        <el-form-item label="显示名" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input v-model="form.code" :disabled="!!form.id" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <!-- 组 -->
        <template v-if="section === 'groups'">
          <el-form-item label="成员对象类型">
            <el-select v-model="form.members" multiple filterable style="width: 100%">
              <el-option
                v-for="o in objects"
                :key="o.code"
                :label="`${o.name}（${o.code}）`"
                :value="o.code"
              />
            </el-select>
          </el-form-item>
        </template>

        <!-- 值类型 -->
        <template v-else-if="section === 'valueTypes'">
          <el-form-item label="基础类型">
            <el-select v-model="form.base_type" style="width: 100%">
              <el-option v-for="b in BASE_TYPE_VALUES" :key="b" :label="b" :value="b" />
            </el-select>
          </el-form-item>
          <el-form-item label="约束（JSON）">
            <el-input
              v-model="form.constraintsText"
              type="textarea"
              :rows="4"
              placeholder='{"pattern":"^[\\w.+-]+@[\\w-]+\\.[\\w.]+$","max_length":120}'
            />
            <span class="ont-hint">
              支持 pattern / min / max / min_length / max_length / options
            </span>
          </el-form-item>
          <el-form-item label="权限角色">
            <el-select
              v-model="form.roles"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="留空 = 全部可用"
              style="width: 100%"
            />
          </el-form-item>
        </template>

        <!-- 共享属性 -->
        <template v-else-if="section === 'shared'">
          <el-form-item label="类型">
            <el-select v-model="form.prop_type" style="width: 100%">
              <el-option label="字符串 string" value="string" />
              <el-option label="数值 number" value="number" />
              <el-option label="布尔 boolean" value="boolean" />
              <el-option label="日期 date" value="date" />
              <el-option label="枚举 enum" value="enum" />
              <el-option label="时间戳 timestamp" value="timestamp" />
            </el-select>
          </el-form-item>
          <el-form-item label="基础类型">
            <el-select v-model="form.base_type" style="width: 100%">
              <el-option v-for="b in BASE_TYPE_VALUES" :key="b" :label="b" :value="b" />
            </el-select>
          </el-form-item>
          <el-form-item label="API 名">
            <el-input v-model="form.api_name" placeholder="留空自动推导" />
          </el-form-item>
          <el-form-item label="值类型">
            <el-select v-model="form.value_type_code" clearable style="width: 100%">
              <el-option
                v-for="v in valueTypes"
                :key="v.code"
                :label="`${v.name}（${v.code}）`"
                :value="v.code"
              />
            </el-select>
          </el-form-item>
        </template>

        <!-- 接口 -->
        <template v-else>
          <el-form-item label="必需属性（JSON）">
            <el-input
              v-model="form.reqPropsText"
              type="textarea"
              :rows="3"
              placeholder='[{"code":"name","name":"名称","base_type":"string"}]'
            />
          </el-form-item>
          <el-form-item label="必需关系（JSON）">
            <el-input
              v-model="form.reqLinksText"
              type="textarea"
              :rows="3"
              placeholder='[{"api_name":"video_camera_groups","name":"摄像机分组"}]'
            />
          </el-form-item>
          <el-form-item label="必需动作（JSON）">
            <el-input
              v-model="form.reqActsText"
              type="textarea"
              :rows="3"
              placeholder='[{"code":"cam_rename","name":"修改名称"}]'
            />
          </el-form-item>
          <el-form-item label="实现者">
            <el-select v-model="form.object_codes" multiple filterable style="width: 100%">
              <el-option
                v-for="o in objects"
                :key="o.code"
                :label="`${o.name}（${o.code}）`"
                :value="o.code"
              />
            </el-select>
            <span class="ont-hint">不满足约束的对象类型会被拒绝，并列出缺失项</span>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="saving" v-hasPerm="'module_ai:ontology:edit'" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 值类型：试校验（约束到底生效没有，只有试一次才知道） ============ -->
    <el-dialog v-model="validateVisible" title="按值类型约束校验取值" width="520px" append-to-body>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="值类型">
          {{ validateTarget?.name }}
          <span class="ont-mono">（{{ validateTarget?.code }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="基础类型">
          {{ validateTarget?.base_type }}
        </el-descriptions-item>
        <el-descriptions-item label="约束">
          <span :class="{ 'ont-none': !Object.keys(validateTarget?.constraints || {}).length }">
            {{
              Object.keys(validateTarget?.constraints || {}).length
                ? JSON.stringify(validateTarget.constraints)
                : "无"
            }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="70px" class="ont-note">
        <el-form-item label="取值">
          <el-input v-model="validateInput" placeholder="填一个值，如 abc@example.com" @keyup.enter="doValidate" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="validateResult"
        :type="validateResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
        :title="validateResult.ok ? '校验通过' : '校验不通过'"
      >
        <ul v-if="!validateResult.ok" class="ont-validate__errs">
          <li v-for="(e, i) in validateResult.errors || []" :key="i">{{ e }}</li>
        </ul>
      </el-alert>
      <template #footer>
        <el-button @click="validateVisible = false">关闭</el-button>
        <el-button type="primary" :loading="validating" @click="doValidate">校验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search } from "@element-plus/icons-vue";
import {
  checkOntInterface,
  getOntGroups,
  getOntReferences,
  getOntInterfaces,
  getOntSharedProperties,
  getOntValueTypes,
  removeOntGroup,
  removeOntInterface,
  removeOntSharedProperty,
  removeOntValueType,
  saveOntGroup,
  saveOntInterface,
  saveOntSharedProperty,
  saveOntValueType,
  setOntInterfaceImpls,
  validateOntValue,
} from "@/api/module_ai/ontology";
import { BASE_TYPE_VALUES } from "../constants";

const props = defineProps<{
  section: "groups" | "valueTypes" | "shared" | "interfaces";
  objects: any[];
  objectLabel: (code: string) => string;
}>();

const groups = ref<any[]>([]);
const valueTypes = ref<any[]>([]);
const shared = ref<any[]>([]);
const interfaces = ref<any[]>([]);
const issues = ref<any[]>([]);
const checking = ref(false);

const dlg = ref(false);
const saving = ref(false);
const form = reactive<Record<string, any>>({});
const dlgTitle = computed(
  () =>
    ({
      groups: "对象类型组",
      valueTypes: "值类型",
      shared: "共享属性",
      interfaces: "接口",
    })[props.section] || ""
);

function missingText(m: any) {
  if (!m) return "";
  const parts: string[] = [];
  if (m.properties?.length) parts.push("属性：" + m.properties.join("、"));
  if (m.links?.length) parts.push("关系：" + m.links.join("、"));
  if (m.actions?.length) parts.push("动作：" + m.actions.join("、"));
  return parts.join("；") || m.msg || "";
}

function parseJson(text: string, what: string) {
  try {
    return JSON.parse(text || "[]");
  } catch {
    throw new Error(`${what} 不是合法 JSON`);
  }
}

async function load() {
  if (props.section === "groups") {
    const r = await getOntGroups();
    groups.value = r.data?.data || [];
  } else if (props.section === "valueTypes") {
    const r = await getOntValueTypes();
    valueTypes.value = r.data?.data || [];
  } else if (props.section === "shared") {
    const r = await getOntSharedProperties();
    shared.value = r.data?.data || [];
    const r2 = await getOntValueTypes();
    valueTypes.value = r2.data?.data || [];
  } else {
    const r = await getOntInterfaces();
    interfaces.value = r.data?.data || [];
    issues.value = [];
  }
}
watch(() => props.section, load, { immediate: true });

function reset() {
  Object.keys(form).forEach((k) => delete form[k]);
  Object.assign(form, {
    id: null,
    code: "",
    name: "",
    description: "",
    members: [],
    base_type: "string",
    constraintsText: "{}",
    roles: [],
    prop_type: "string",
    api_name: "",
    value_type_code: "",
    reqPropsText: "[]",
    reqLinksText: "[]",
    reqActsText: "[]",
    object_codes: [],
  });
}

function openGroup(row?: any) {
  reset();
  if (row)
    Object.assign(form, {
      id: row.id,
      code: row.code,
      name: row.name,
      description: row.description,
      members: [...(row.members || [])],
    });
  dlg.value = true;
}
function openVt(row?: any) {
  reset();
  if (row)
    Object.assign(form, {
      id: row.id,
      code: row.code,
      name: row.name,
      description: row.description,
      base_type: row.base_type,
      constraintsText: JSON.stringify(row.constraints || {}, null, 2),
      roles: [...(row.roles || [])],
    });
  dlg.value = true;
}
function openSp(row?: any) {
  reset();
  if (row)
    Object.assign(form, {
      id: row.id,
      code: row.code,
      name: row.name,
      description: row.description,
      prop_type: row.prop_type,
      base_type: row.base_type,
      api_name: row.api_name,
      value_type_code: row.value_type_code,
    });
  dlg.value = true;
}
function openIf(row?: any) {
  reset();
  if (row)
    Object.assign(form, {
      id: row.id,
      code: row.code,
      name: row.name,
      description: row.description,
      reqPropsText: JSON.stringify(row.required_properties || [], null, 2),
      reqLinksText: JSON.stringify(row.required_links || [], null, 2),
      reqActsText: JSON.stringify(row.required_actions || [], null, 2),
      object_codes: [...(row.implementations || [])],
    });
  dlg.value = true;
}

async function save() {
  if (!form.code?.trim() || !form.name?.trim()) return ElMessage.warning("请填显示名与编码");
  saving.value = true;
  try {
    if (props.section === "groups") {
      await saveOntGroup({
        id: form.id,
        code: form.code,
        name: form.name,
        description: form.description,
        members: form.members,
      });
    } else if (props.section === "valueTypes") {
      const constraints = parseJson(form.constraintsText || "{}", "约束");
      await saveOntValueType({
        id: form.id,
        code: form.code,
        name: form.name,
        description: form.description,
        base_type: form.base_type,
        constraints,
        roles: form.roles,
      });
    } else if (props.section === "shared") {
      await saveOntSharedProperty({
        id: form.id,
        code: form.code,
        name: form.name,
        description: form.description,
        prop_type: form.prop_type,
        base_type: form.base_type,
        api_name: form.api_name,
        value_type_code: form.value_type_code,
      });
    } else {
      const r = await saveOntInterface({
        id: form.id,
        code: form.code,
        name: form.name,
        description: form.description,
        required_properties: parseJson(form.reqPropsText || "[]", "必需属性"),
        required_links: parseJson(form.reqLinksText || "[]", "必需关系"),
        required_actions: parseJson(form.reqActsText || "[]", "必需动作"),
      });
      void r;
      const res = await setImpls(form.code, form.object_codes);
      dlg.value = false;
      await load();
      ElMessage.success(res);
      return;
    }
    dlg.value = false;
    await load();
    ElMessage.success("已保存");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

/* ---------- 值类型：试校验 ---------- */
const validateVisible = ref(false);
const validating = ref(false);
const validateTarget = ref<any>(null);
const validateInput = ref("");
const validateResult = ref<any>(null);

function openValidate(row: any) {
  validateTarget.value = row;
  validateInput.value = "";
  validateResult.value = null;
  validateVisible.value = true;
}

async function doValidate() {
  if (!validateTarget.value) return;
  validating.value = true;
  validateResult.value = null;
  try {
    const r = await validateOntValue(validateTarget.value.code, validateInput.value);
    // request() 返回 axios response，业务数据在 data.data
    validateResult.value = r.data?.data || { ok: false, errors: [r.data?.msg || "校验失败"] };
  } catch (e: any) {
    validateResult.value = { ok: false, errors: [e?.msg || "校验请求失败"] };
  } finally {
    validating.value = false;
  }
}

async function setImpls(code: string, codes: string[]): Promise<string> {
  const r = await setOntInterfaceImpls(code, codes);
  const d = r.data?.data || {};
  if (d.rejected?.length) {
    return `${r.data?.msg || "已保存"}；被拒：${d.rejected
      .map((x: any) => `${props.objectLabel(x.object_code)}（${missingText(x.missing)}）`)
      .join("；")}`;
  }
  return r.data?.msg || "已保存";
}

/** 删除前统一做引用检查，把引用方摊开给用户看 */
async function guardDelete(kind: string, code: string, label: string) {
  const r = await getOntReferences(kind, code);
  const d = r.data?.data || {};
  if (d.count) {
    await ElMessageBox.alert(
      `「${label}」仍有 ${d.count} 处引用：${d.refs
        .slice(0, 8)
        .map((x: any) => x.where || x.name)
        .join("、")}`,
      "无法删除",
      { type: "warning", confirmButtonText: "知道了" }
    );
    return false;
  }
  await ElMessageBox.confirm(`将删除「${label}」，确认？`, "删除", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  return true;
}

async function delGroup(row: any) {
  if (!(await guardDelete("group", row.code, row.name))) return;
  await removeOntGroup(row.id);
  ElMessage.success("已删除");
  await load();
}
async function delVt(row: any) {
  if (!(await guardDelete("value_type", row.code, row.name))) return;
  const r = await removeOntValueType(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || "删除失败");
  ElMessage.success("已删除");
  await load();
}
async function delSp(row: any) {
  if (!(await guardDelete("shared_property", row.code, row.name))) return;
  const r = await removeOntSharedProperty(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || "删除失败");
  ElMessage.success("已删除");
  await load();
}
async function delIf(row: any) {
  // 与同文件 delGroup/delVt/delSp 一致：删除必须二次确认（此前是唯一漏掉的删除入口）
  if (!(await guardDelete("interface", row.code, row.name))) return;
  const r = await removeOntInterface(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || "删除失败");
  ElMessage.success("已删除");
  await load();
}

async function runCheck() {
  checking.value = true;
  try {
    const r = await checkOntInterface();
    issues.value = r.data?.data || [];
    ElMessage[issues.value.length ? "warning" : "success"](
      issues.value.length ? `发现 ${issues.value.length} 处不合规` : "全部合规"
    );
  } finally {
    checking.value = false;
  }
}
</script>

<style scoped lang="scss">
.ont-adv {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.ont-validate__errs {
  margin: 0;
  padding-left: 18px;
}
</style>
