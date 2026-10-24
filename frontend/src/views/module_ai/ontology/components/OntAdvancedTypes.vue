<!--
  P5 高级类型系统：对象类型组 / 值类型 / 共享属性 / 接口

  四个分区共用一套交互：列表 → 编辑弹窗 → 删除（删除前做引用检查）
-->
<template>
  <div class="ont-adv">
    <!-- ============ 对象类型组 ============ -->
    <template v-if="section === 'groups'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openGroup()">
          {{ i18nT("ai_ontology.newGroup") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ i18nT("ai_ontology.totalCountShort", { count: groups.length }) }}
        </el-tag>
        <span class="ont-hint">
          {{ i18nT("ai_ontology.groupHint") }}
        </span>
      </div>
      <el-table :data="groups" size="small" border max-height="480" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noGroups')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.groupName')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.code')"
          min-width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.members')" min-width="260">
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
            <span v-else class="ont-none">{{ i18nT("ai_ontology.noMembers") }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          :label="i18nT('ai_ontology.note')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.operations')" width="130" align="center">
          <template #default="{ row }">
            <el-button icon="edit" link type="primary" size="small" @click="openGroup(row)">
              {{ i18nT("ai_ontology.edit") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="danger"
              size="small"
              @click="delGroup(row)"
            >
              {{ i18nT("ai_ontology.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 值类型 ============ -->
    <template v-else-if="section === 'valueTypes'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openVt()">
          {{ i18nT("ai_ontology.newValueType") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ i18nT("ai_ontology.totalCountShort", { count: valueTypes.length }) }}
        </el-tag>
        <span class="ont-hint">
          {{ i18nT("ai_ontology.valueTypeHint") }}
        </span>
      </div>
      <el-table :data="valueTypes" size="small" border max-height="480" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noValueTypes')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.displayName')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.code')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column prop="base_type" :label="i18nT('ai_ontology.baseType')" width="110" />
        <el-table-column
          :label="i18nT('ai_ontology.constraints')"
          min-width="200"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span :class="{ 'ont-none': !Object.keys(row.constraints || {}).length }">
              {{
                Object.keys(row.constraints || {}).length
                  ? JSON.stringify(row.constraints)
                  : i18nT("ai_ontology.none")
              }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="version" :label="i18nT('ai_ontology.version')" width="80">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.reference')" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ref_count ? 'warning' : 'info'" effect="plain">
              {{ row.ref_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="180" align="center">
          <template #default="{ row }">
            <el-button icon="edit" link type="primary" size="small" @click="openVt(row)">
              {{ i18nT("ai_ontology.edit") }}
            </el-button>
            <el-button icon="Checked" link type="primary" size="small" @click="openValidate(row)">
              {{ i18nT("ai_ontology.draftValidate") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="danger"
              size="small"
              @click="delVt(row)"
            >
              {{ i18nT("ai_ontology.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 共享属性 ============ -->
    <template v-else-if="section === 'shared'">
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openSp()">
          {{ i18nT("ai_ontology.newSharedProperty") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ i18nT("ai_ontology.totalCountShort", { count: shared.length }) }}
        </el-tag>
        <span class="ont-hint">
          {{ i18nT("ai_ontology.sharedHint") }}
        </span>
      </div>
      <el-table :data="shared" size="small" border max-height="480" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noSharedProperties')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.displayName')"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.attributeId')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column
          prop="api_name"
          :label="i18nT('ai_ontology.apiName')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column prop="prop_type" :label="i18nT('ai_ontology.type')" width="100" />
        <el-table-column :label="i18nT('ai_ontology.valueType')" min-width="120">
          <template #default="{ row }">
            <span :class="{ 'ont-none': !row.value_type_code }">
              {{ row.value_type_code || "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.referenced')" min-width="220">
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
            <span v-if="!row.refs?.length" class="ont-none">
              {{ i18nT("ai_ontology.notReferenced") }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="130" align="center">
          <template #default="{ row }">
            <el-button icon="edit" link type="primary" size="small" @click="openSp(row)">
              {{ i18nT("ai_ontology.edit") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="danger"
              size="small"
              @click="delSp(row)"
            >
              {{ i18nT("ai_ontology.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 接口 ============ -->
    <template v-else>
      <div class="ont-bar">
        <el-button type="primary" size="small" :icon="Plus" @click="openIf()">
          {{ i18nT("ai_ontology.newInterface") }}
        </el-button>
        <el-button size="small" :icon="Search" :loading="checking" @click="runCheck">
          {{ i18nT("ai_ontology.complianceCheck") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ i18nT("ai_ontology.totalCountShort", { count: interfaces.length }) }}
        </el-tag>
        <el-tag v-if="issues.length" size="small" type="danger" effect="plain">
          {{ i18nT("ai_ontology.nonCompliantCount", { count: issues.length }) }}
        </el-tag>
        <span class="ont-hint">
          {{ i18nT("ai_ontology.interfaceHint") }}
        </span>
      </div>
      <el-table :data="interfaces" size="small" border max-height="440" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noInterfaces')" />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.interfaceName')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.code')"
          min-width="120"
          show-overflow-tooltip
        />
        <el-table-column
          :label="i18nT('ai_ontology.requiredProperties')"
          width="100"
          align="center"
        >
          <template #default="{ row }">{{ row.required_properties?.length || 0 }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.requiredRelations')" width="100" align="center">
          <template #default="{ row }">{{ row.required_links?.length || 0 }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.requiredActions')" width="100" align="center">
          <template #default="{ row }">{{ row.required_actions?.length || 0 }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.implementor')" min-width="240">
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
            <span v-else class="ont-none">{{ i18nT("ai_ontology.noImplementor") }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="130" align="center">
          <template #default="{ row }">
            <el-button icon="edit" link type="primary" size="small" @click="openIf(row)">
              {{ i18nT("ai_ontology.edit") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="danger"
              size="small"
              @click="delIf(row)"
            >
              {{ i18nT("ai_ontology.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="issues.length" class="ont-sub-title">
        {{ i18nT("ai_ontology.nonCompliantImplementations") }}
      </div>
      <el-table v-if="issues.length" :data="issues" size="small" border max-height="220" stripe>
        <el-table-column
          prop="interface_name"
          :label="i18nT('ai_ontology.interface')"
          min-width="140"
        />
        <el-table-column :label="i18nT('ai_ontology.objectType')" min-width="150">
          <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
        </el-table-column>
        <el-table-column
          :label="i18nT('ai_ontology.missing')"
          min-width="300"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ missingText(row.missing) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ============ 编辑弹窗 ============ -->
    <el-dialog v-model="dlg" :title="dlgTitle" width="600px" append-to-body>
      <el-form label-width="130px" size="small">
        <el-form-item :label="i18nT('ai_ontology.displayName')" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.code')" required>
          <el-input v-model="form.code" :disabled="!!form.id" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.note')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <!-- 组 -->
        <template v-if="section === 'groups'">
          <el-form-item :label="i18nT('ai_ontology.memberObjectTypes')">
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
          <el-form-item :label="i18nT('ai_ontology.baseType')">
            <el-select v-model="form.base_type" style="width: 100%">
              <el-option v-for="b in BASE_TYPE_VALUES" :key="b" :label="b" :value="b" />
            </el-select>
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.constraintsJson')">
            <el-input
              v-model="form.constraintsText"
              type="textarea"
              :rows="4"
              placeholder='{"pattern":"^[\\w.+-]+@[\\w-]+\\.[\\w.]+$","max_length":120}'
            />
            <span class="ont-hint">
              {{ i18nT("ai_ontology.constraintsSupportHint") }}
            </span>
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.permissionRoles')">
            <el-select
              v-model="form.roles"
              multiple
              filterable
              allow-create
              default-first-option
              :placeholder="i18nT('ai_ontology.leaveEmptyAllAvailable')"
              style="width: 100%"
            />
          </el-form-item>
        </template>

        <!-- 共享属性 -->
        <template v-else-if="section === 'shared'">
          <el-form-item :label="i18nT('ai_ontology.type')">
            <el-select v-model="form.prop_type" style="width: 100%">
              <el-option :label="i18nT('ai_ontology.typeString')" value="string" />
              <el-option :label="i18nT('ai_ontology.typeNumber')" value="number" />
              <el-option :label="i18nT('ai_ontology.typeBoolean')" value="boolean" />
              <el-option :label="i18nT('ai_ontology.typeDate')" value="date" />
              <el-option :label="i18nT('ai_ontology.typeEnum')" value="enum" />
              <el-option :label="i18nT('ai_ontology.typeTimestamp')" value="timestamp" />
            </el-select>
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.baseType')">
            <el-select v-model="form.base_type" style="width: 100%">
              <el-option v-for="b in BASE_TYPE_VALUES" :key="b" :label="b" :value="b" />
            </el-select>
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.apiName')">
            <el-input
              v-model="form.api_name"
              :placeholder="i18nT('ai_ontology.leaveEmptyToAutoDerive')"
            />
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.valueType')">
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
          <el-form-item :label="i18nT('ai_ontology.requiredPropertiesJson')">
            <el-input
              v-model="form.reqPropsText"
              type="textarea"
              :rows="3"
              :placeholder="i18nT('ai_ontology.requiredPropsPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.requiredRelationsJson')">
            <el-input
              v-model="form.reqLinksText"
              type="textarea"
              :rows="3"
              :placeholder="i18nT('ai_ontology.requiredLinksPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.requiredActionsJson')">
            <el-input
              v-model="form.reqActsText"
              type="textarea"
              :rows="3"
              :placeholder="i18nT('ai_ontology.requiredActionsPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="i18nT('ai_ontology.implementor')">
            <el-select v-model="form.object_codes" multiple filterable style="width: 100%">
              <el-option
                v-for="o in objects"
                :key="o.code"
                :label="`${o.name}（${o.code}）`"
                :value="o.code"
              />
            </el-select>
            <span class="ont-hint">
              {{
                i18nT(
                  "ai_ontology.objectTypesThatDonTSatisfyConstraintsAreRejectedAndListMissingItems"
                )
              }}
            </span>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="saving"
          @click="save"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 值类型：试校验（约束到底生效没有，只有试一次才知道） ============ -->
    <el-dialog
      v-model="validateVisible"
      :title="i18nT('ai_ontology.validateValueAgainstValueTypeConstraints')"
      width="520px"
      append-to-body
    >
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item :label="i18nT('ai_ontology.valueType')">
          {{ validateTarget?.name }}
          <span class="ont-mono">（{{ validateTarget?.code }}）</span>
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.baseType')">
          {{ validateTarget?.base_type }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.constraints')">
          <span :class="{ 'ont-none': !Object.keys(validateTarget?.constraints || {}).length }">
            {{
              Object.keys(validateTarget?.constraints || {}).length
                ? JSON.stringify(validateTarget.constraints)
                : i18nT("ai_ontology.none")
            }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="70px" class="ont-note">
        <el-form-item :label="i18nT('ai_ontology.value2')">
          <el-input
            v-model="validateInput"
            :placeholder="i18nT('ai_ontology.validateValuePlaceholder')"
            @keyup.enter="doValidate"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="validateResult"
        :type="validateResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
        :title="
          validateResult.ok
            ? i18nT('ai_ontology.validatePass')
            : i18nT('ai_ontology.validateNotPass')
        "
      >
        <ul v-if="!validateResult.ok" class="ont-validate__errs">
          <li v-for="(e, i) in validateResult.errors || []" :key="i">{{ e }}</li>
        </ul>
      </el-alert>
      <template #footer>
        <el-button @click="validateVisible = false">{{ i18nT("ai_ontology.close") }}</el-button>
        <el-button type="primary" :loading="validating" @click="doValidate">
          {{ i18nT("ai_ontology.validate") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
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

const { t: i18nT } = useI18n();

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
      groups: i18nT("ai_ontology.objectTypeGroup"),
      valueTypes: i18nT("ai_ontology.valueType"),
      shared: i18nT("ai_ontology.sharedProperty"),
      interfaces: i18nT("ai_ontology.interface"),
    })[props.section] || ""
);

function missingText(m: any) {
  if (!m) return "";
  const parts: string[] = [];
  if (m.properties?.length) parts.push(i18nT("ai_ontology.property2") + m.properties.join("、"));
  if (m.links?.length) parts.push(i18nT("ai_ontology.relation2") + m.links.join("、"));
  if (m.actions?.length) parts.push(i18nT("ai_ontology.action2") + m.actions.join("、"));
  return parts.join("；") || m.msg || "";
}

function parseJson(text: string, what: string) {
  try {
    return JSON.parse(text || "[]");
  } catch {
    throw new Error(i18nT("ai_ontology.notValidJson", { label: what }));
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
  if (!form.code?.trim() || !form.name?.trim())
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterDisplayNameAndCode"));
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
      const constraints = parseJson(form.constraintsText || "{}", i18nT("ai_ontology.constraints"));
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
        required_properties: parseJson(
          form.reqPropsText || "[]",
          i18nT("ai_ontology.requiredProperties")
        ),
        required_links: parseJson(
          form.reqLinksText || "[]",
          i18nT("ai_ontology.requiredRelations")
        ),
        required_actions: parseJson(form.reqActsText || "[]", i18nT("ai_ontology.requiredActions")),
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
    ElMessage.success(i18nT("ai_ontology.saved"));
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || i18nT("ai_ontology.saveFailed"));
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
    validateResult.value = r.data?.data || {
      ok: false,
      errors: [r.data?.msg || i18nT("ai_ontology.validateFailed")],
    };
  } catch (e: any) {
    validateResult.value = {
      ok: false,
      errors: [e?.msg || i18nT("ai_ontology.validateRequestFailed")],
    };
  } finally {
    validating.value = false;
  }
}

async function setImpls(code: string, codes: string[]): Promise<string> {
  const r = await setOntInterfaceImpls(code, codes);
  const d = r.data?.data || {};
  if (d.rejected?.length) {
    const detail = d.rejected
      .map((x: any) => `${props.objectLabel(x.object_code)}（${missingText(x.missing)}）`)
      .join("；");
    return i18nT("ai_ontology.rejectedDetail", {
      base: r.data?.msg || i18nT("ai_ontology.saved"),
      detail,
    });
  }
  return r.data?.msg || i18nT("ai_ontology.saved");
}

/** 删除前统一做引用检查，把引用方摊开给用户看 */
async function guardDelete(kind: string, code: string, label: string) {
  const r = await getOntReferences(kind, code);
  const d = r.data?.data || {};
  if (d.count) {
    const refs = d.refs
      .slice(0, 8)
      .map((x: any) => x.where || x.name)
      .join("、");
    await ElMessageBox.alert(
      i18nT("ai_ontology.stillReferencedCount", { label, count: d.count, refs }),
      i18nT("ai_ontology.cannotDelete"),
      { type: "warning", confirmButtonText: i18nT("ai_ontology.gotIt") }
    );
    return false;
  }
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deleteConfirmLabel", { label }),
    i18nT("ai_ontology.delete2"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  return true;
}

async function delGroup(row: any) {
  if (!(await guardDelete("group", row.code, row.name))) return;
  await removeOntGroup(row.id);
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await load();
}
async function delVt(row: any) {
  if (!(await guardDelete("value_type", row.code, row.name))) return;
  const r = await removeOntValueType(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || i18nT("ai_ontology.deleteFailed"));
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await load();
}
async function delSp(row: any) {
  if (!(await guardDelete("shared_property", row.code, row.name))) return;
  const r = await removeOntSharedProperty(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || i18nT("ai_ontology.deleteFailed"));
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await load();
}
async function delIf(row: any) {
  // 与同文件 delGroup/delVt/delSp 一致：删除必须二次确认（此前是唯一漏掉的删除入口）
  if (!(await guardDelete("interface", row.code, row.name))) return;
  const r = await removeOntInterface(row.id);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(r.data?.msg || i18nT("ai_ontology.deleteFailed"));
  ElMessage.success(i18nT("ai_ontology.deleted"));
  await load();
}

async function runCheck() {
  checking.value = true;
  try {
    const r = await checkOntInterface();
    issues.value = r.data?.data || [];
    ElMessage[issues.value.length ? "warning" : "success"](
      issues.value.length
        ? i18nT("ai_ontology.foundNonCompliant", { count: issues.value.length })
        : i18nT("ai_ontology.allCompliant")
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
