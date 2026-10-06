<!-- 本体 Ontology：对象类型 / 属性 / Link / Action 强类型元模型（Palantir Ontology） -->
<template>
  <div class="app-container ai-ontology-page">
    <PageHeader
      title="本体"
      subtitle="强类型本体元模型：对象 / 属性 / Link / Action，创建对象不必先有数据库表（本体驱动数据）"
    />
    <el-row :gutter="12">
      <!-- 左：对象类型列表 -->
      <el-col :span="6">
        <el-card shadow="never" class="ont-left">
          <template #header>
            <div class="ont-head">
              <span>对象类型（{{ objects.length }}）</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openObjectEdit()">
                新建对象
              </el-button>
            </div>
          </template>
          <div
            v-for="o in objects"
            :key="o.code"
            class="ont-obj"
            :class="{ active: currentCode === o.code }"
            @click="selectObject(o)"
          >
            <el-icon class="ont-obj__icon"><component :is="o.icon || 'Box'" /></el-icon>
            <div class="ont-obj__meta">
              <div class="ont-obj__name">{{ o.name }}</div>
              <div class="ont-obj__code">
                {{ o.code }} · 属性{{ o.property_count }} 关联{{ o.link_count }} 动作{{
                  o.action_count
                }}
              </div>
            </div>
            <el-button link type="danger" size="small" @click.stop="removeObj(o)">删</el-button>
          </div>
          <el-empty v-if="!objects.length" description="暂无对象，点击新建" :image-size="40" />
        </el-card>
      </el-col>

      <!-- 右：对象详情（属性/Link/Action） -->
      <el-col :span="18">
        <el-card shadow="never">
          <template #header>
            <div v-if="current" class="ont-head">
              <span>
                <el-tag size="small" type="primary" effect="dark">{{ current.name }}</el-tag>
                <span class="ont-desc">{{ current.description }}</span>
              </span>
              <div>
                <el-button size="small" :icon="MagicStick" @click="materialize(current)">
                  物化为表
                </el-button>
                <el-button size="small" :icon="Edit" @click="openObjectEdit(current)">
                  编辑
                </el-button>
              </div>
            </div>
            <span v-else>请选择左侧对象类型</span>
          </template>
          <el-tabs v-if="current" v-model="ontTab">
            <el-tab-pane label="属性" name="property">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openPropEdit()">
                  新增属性
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ props.length }}</el-tag>
              </div>
              <el-table :data="props" size="small" border>
                <el-table-column prop="name" label="属性" min-width="110" show-overflow-tooltip />
                <el-table-column prop="code" label="编码" min-width="100" show-overflow-tooltip />
                <el-table-column prop="prop_type" label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" effect="plain">{{ row.prop_type }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="约束" min-width="140">
                  <template #default="{ row }">
                    <el-tag v-if="row.required" size="small" type="danger" effect="plain">
                      必填
                    </el-tag>
                    <el-tag v-if="row.unique_col" size="small" type="warning" effect="plain">
                      唯一
                    </el-tag>
                    <el-tag v-if="row.sensitive" size="small" type="info" effect="plain">
                      敏感
                    </el-tag>
                    <span
                      v-if="!row.required && !row.unique_col && !row.sensitive"
                      class="ont-none"
                    >
                      —
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="source_col" label="来源列" min-width="90" />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openPropEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeProp(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="关联 Link" name="link">
              <div class="ont-bar">
                <el-button type="primary" size="small" :icon="Plus" @click="openLinkEdit(current)">
                  新增关联
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ links.length }}</el-tag>
              </div>
              <el-table :data="links" size="small" border>
                <el-table-column
                  prop="source_object"
                  label="源对象"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="target_object"
                  label="目标对象"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column prop="name" label="关联名" min-width="110" show-overflow-tooltip />
                <el-table-column prop="card" label="基数" width="90" />
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openLinkEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeLink(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="动作 Action" name="action">
              <div class="ont-bar">
                <el-button
                  type="primary"
                  size="small"
                  :icon="Plus"
                  @click="openActionEdit(current)"
                >
                  新增动作
                </el-button>
                <el-tag size="small" type="info" effect="plain">共 {{ actions.length }}</el-tag>
              </div>
              <el-table :data="actions" size="small" border>
                <el-table-column prop="name" label="动作" min-width="110" show-overflow-tooltip />
                <el-table-column prop="code" label="编码" min-width="100" show-overflow-tooltip />
                <el-table-column
                  prop="target_table"
                  label="写回目标"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column prop="method" label="方式" width="80" />
                <el-table-column label="审批" width="80" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.approval ? 'warning' : 'info'" effect="plain">
                      {{ row.approval ? "是" : "否" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="110" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" size="small" @click="openActionEdit(row)">
                      编辑
                    </el-button>
                    <el-button link type="danger" size="small" @click="removeAction(row)">
                      删
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- 对象编辑 -->
    <el-dialog v-model="objDialog" title="对象类型" width="560px" append-to-body>
      <el-form :model="objForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="objForm.name" placeholder="如 订单" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input
            v-model="objForm.code"
            :disabled="!!objForm.id"
            placeholder="如 orders（唯一）"
          />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="objForm.icon" placeholder="el-icon-Box" />
        </el-form-item>
        <el-form-item label="主键属性">
          <el-input v-model="objForm.key_prop" placeholder="id" />
        </el-form-item>
        <el-form-item label="名称属性">
          <el-input v-model="objForm.name_prop" placeholder="name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="objForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="objDialog = false">取消</el-button>
        <el-button type="primary" @click="saveObj">保存</el-button>
      </template>
    </el-dialog>

    <!-- 属性编辑 -->
    <el-dialog v-model="propDialog" title="属性类型" width="560px" append-to-body>
      <el-form :model="propForm" label-width="100px">
        <el-form-item label="名称" required><el-input v-model="propForm.name" /></el-form-item>
        <el-form-item label="编码" required><el-input v-model="propForm.code" /></el-form-item>
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
        <el-form-item label="约束">
          <el-checkbox v-model="propForm.required">必填</el-checkbox>
          <el-checkbox v-model="propForm.unique_col">唯一</el-checkbox>
          <el-checkbox v-model="propForm.sensitive">敏感</el-checkbox>
        </el-form-item>
        <el-form-item label="来源列">
          <el-input v-model="propForm.source_col" placeholder="映射真实表列(可空)" />
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="propForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="propDialog = false">取消</el-button>
        <el-button type="primary" @click="saveProp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关联编辑 -->
    <el-dialog v-model="linkDialog" title="关联类型" width="560px" append-to-body>
      <el-form :model="linkForm" label-width="100px">
        <el-form-item label="源对象" required>
          <el-select v-model="linkForm.source_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标对象" required>
          <el-select v-model="linkForm.target_object" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联名"><el-input v-model="linkForm.name" /></el-form-item>
        <el-form-item label="基数">
          <el-select v-model="linkForm.card" style="width: 100%">
            <el-option label="多对一 many_to_one" value="many_to_one" />
            <el-option label="一对多 one_to_many" value="one_to_many" />
            <el-option label="多对多 many_to_many" value="many_to_many" />
          </el-select>
        </el-form-item>
        <el-form-item label="源字段"><el-input v-model="linkForm.source_field" /></el-form-item>
        <el-form-item label="目标字段"><el-input v-model="linkForm.target_field" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialog = false">取消</el-button>
        <el-button type="primary" @click="saveLink">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作编辑 -->
    <el-dialog v-model="actionDialog" title="动作类型" width="560px" append-to-body>
      <el-form :model="actionForm" label-width="100px">
        <el-form-item label="动作名" required><el-input v-model="actionForm.name" /></el-form-item>
        <el-form-item label="编码" required><el-input v-model="actionForm.code" /></el-form-item>
        <el-form-item label="写回目标">
          <el-input v-model="actionForm.target_table" placeholder="ont_orders / video_cameras" />
        </el-form-item>
        <el-form-item label="方式">
          <el-select v-model="actionForm.method" style="width: 100%">
            <el-option label="update" value="update" />
            <el-option label="insert" value="insert" />
            <el-option label="delete" value="delete" />
          </el-select>
        </el-form-item>
        <el-form-item label="审批门禁"><el-switch v-model="actionForm.approval" /></el-form-item>
        <el-form-item label="白名单字段">
          <el-select
            v-model="actionForm.white_fields"
            multiple
            allow-create
            filterable
            placeholder="字段白名单"
            style="width: 100%"
          >
            <el-option v-for="p in props" :key="p.code" :label="p.name" :value="p.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAction">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Edit, MagicStick } from "@element-plus/icons-vue";
import {
  getOntObjects,
  saveOntObject,
  getOntObjectFull,
  saveOntProperty,
  saveOntLink,
  saveOntAction,
  removeOnt,
  materializeOntObject,
} from "@/api/module_ai/ontology";

const objects = ref<any[]>([]);
const current = ref<any>(null);
const currentCode = ref("");
const ontTab = ref("property");
const props = ref<any[]>([]);
const links = ref<any[]>([]);
const actions = ref<any[]>([]);

async function loadObjects() {
  const r = await getOntObjects();
  objects.value = r.data?.data || [];
}
async function selectObject(o: any) {
  currentCode.value = o.code;
  current.value = o;
  const r = await getOntObjectFull(o.code);
  const d = r.data?.data || {};
  props.value = d.properties || [];
  links.value = d.links || [];
  actions.value = d.actions || [];
}

// 对象
const objDialog = ref(false);
const objForm = reactive<any>({
  id: null,
  name: "",
  code: "",
  icon: "el-icon-Box",
  key_prop: "id",
  name_prop: "name",
  description: "",
  enabled: true,
});
function openObjectEdit(o?: any) {
  Object.assign(
    objForm,
    o || {
      id: null,
      name: "",
      code: "",
      icon: "el-icon-Box",
      key_prop: "id",
      name_prop: "name",
      description: "",
      enabled: true,
    }
  );
  objDialog.value = true;
}
async function saveObj() {
  if (!objForm.code?.trim() || !objForm.name?.trim()) return ElMessage.warning("请填名称/编码");
  await saveOntObject({ ...objForm });
  ElMessage.success("已保存");
  objDialog.value = false;
  await loadObjects();
}
async function removeObj(o: any) {
  await ElMessageBox.confirm(
    `将删除对象「${o.name}」及其属性/关联/动作定义（不影响真实数据表），是否继续？`,
    "删除确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await removeOnt("object", o.id);
  ElMessage.success("已删除");
  await loadObjects();
}

// 属性
const propDialog = ref(false);
const propForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  code: "",
  prop_type: "string",
  required: false,
  unique_col: false,
  sensitive: false,
  source_col: "",
  description: "",
});
function openPropEdit(p?: any) {
  Object.assign(
    propForm,
    p || {
      id: null,
      object_code: currentCode.value,
      name: "",
      code: "",
      prop_type: "string",
      required: false,
      unique_col: false,
      sensitive: false,
      source_col: "",
      description: "",
    }
  );
  propDialog.value = true;
}
async function saveProp() {
  if (!propForm.code?.trim() || !propForm.name?.trim()) return ElMessage.warning("请填写属性");
  await saveOntProperty({ ...propForm });
  ElMessage.success("已保存");
  propDialog.value = false;
  await selectObject(current.value);
}

// 关联
const linkDialog = ref(false);
const linkForm = reactive<any>({
  id: null,
  source_object: "",
  target_object: "",
  name: "",
  card: "many_to_one",
  source_field: "",
  target_field: "",
  description: "",
});
function openLinkEdit(l?: any) {
  Object.assign(
    linkForm,
    l || {
      id: null,
      source_object: currentCode.value,
      target_object: "",
      name: "",
      card: "many_to_one",
      source_field: "",
      target_field: "",
      description: "",
    }
  );
  linkDialog.value = true;
}
async function saveLink() {
  if (!linkForm.source_object || !linkForm.target_object)
    return ElMessage.warning("请选择源/目标对象");
  await saveOntLink({ ...linkForm });
  ElMessage.success("已保存");
  linkDialog.value = false;
  await selectObject(current.value);
}

// 动作
const actionDialog = ref(false);
const actionForm = reactive<any>({
  id: null,
  object_code: "",
  name: "",
  code: "",
  target_table: "",
  method: "update",
  approval: false,
  white_fields: [],
  description: "",
});
function openActionEdit(a?: any) {
  Object.assign(
    actionForm,
    a || {
      id: null,
      object_code: currentCode.value,
      name: "",
      code: "",
      target_table: "",
      method: "update",
      approval: false,
      white_fields: [],
      description: "",
    }
  );
  actionDialog.value = true;
}
async function saveAction() {
  if (!actionForm.code?.trim() || !actionForm.name?.trim()) return ElMessage.warning("请填写动作");
  await saveOntAction({ ...actionForm });
  ElMessage.success("已保存");
  actionDialog.value = false;
  await selectObject(current.value);
}

function removeProp(p: any) {
  ElMessageBox.confirm(`删除属性「${p.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeOnt("property", p.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}
function removeLink(l: any) {
  ElMessageBox.confirm(
    `删除关联「${l.name || l.source_object + "-" + l.target_object}」?`,
    "确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  ).then(async () => {
    await removeOnt("link", l.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}
function removeAction(a: any) {
  ElMessageBox.confirm(`删除动作「${a.name}」?`, "确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  }).then(async () => {
    await removeOnt("action", a.id);
    ElMessage.success("已删除");
    await selectObject(current.value);
  });
}

// 物化
async function materialize(o: any) {
  const r = await materializeOntObject(o.code);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](d.msg || "已物化");
}

onMounted(loadObjects);
</script>

<style scoped lang="scss">
.ai-ontology-page {
  padding: 12px;
}
.ont-left {
  max-height: calc(100vh - 100px);
  overflow: auto;
}
.ont-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ont-obj {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
}
.ont-obj.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.ont-obj__icon {
  color: var(--el-color-primary);
  font-size: 18px;
}
.ont-obj__meta {
  flex: 1;
  min-width: 0;
}
.ont-obj__name {
  font-size: 14px;
  font-weight: 600;
}
.ont-obj__code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-desc {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ont-bar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ont-none {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
