<template>
  <div class="fa-full-height">
    <ElCard shadow="hover" class="fa-table-card">
      <FaTableHeader
        v-model:columns="columnChecks"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <FaTableHeaderLeft
            :remove-ids="selectedIds"
            :perm-create="['module_video:camera:create']"
            :perm-delete="['module_video:camera:delete']"
            :delete-loading="batchDeleting"
            @add="handleOpenDialog('create')"
            @delete="handleBatchDelete"
          />
        </template>
      </FaTableHeader>

      <div class="data-table__content">
        <ElTable
          ref="faTableRef"
          v-loading="loading"
          row-key="id"
          :data="treeList"
          border
          stripe
          default-expand-all
          :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
          @selection-change="onTableSelectionChange"
        >
          <template #empty><ElEmpty :image-size="80" description="暂无数据" /></template>
          <ElTableColumn type="selection" width="55" align="center" />
          <ElTableColumn type="index" fixed label="序号" width="60" align="center" />
          <ElTableColumn label="分组名称" prop="name" min-width="180" show-overflow-tooltip />
          <ElTableColumn label="排序" prop="sort_order" width="80" align="center" />
          <ElTableColumn label="状态" width="80" align="center">
            <template #default="scope">
              <ElTag :type="scope.row.status ? 'success' : 'danger'" size="small">{{ scope.row.status ? "启用" : "停用" }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="备注" prop="description" min-width="160" show-overflow-tooltip />
          <ElTableColumn label="创建时间" prop="created_at" min-width="170" show-overflow-tooltip />
          <ElTableColumn label="操作" fixed="right" align="center" width="140">
            <template #default="scope">
              <ElButton v-hasPerm="['module_video:camera:update']" type="primary" size="small" link @click.stop="handleOpenDialog('update', scope.row.id)">编辑</ElButton>
              <ElButton v-hasPerm="['module_video:camera:delete']" type="danger" size="small" link @click.stop="handleDeleteRow(scope.row.id)">删除</ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </div>
    </ElCard>

    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="550px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" :rules="rules" label-width="100px">
        <ElFormItem label="分组名称" prop="name">
          <ElInput v-model="formData.name" placeholder="请输入分组名称" />
        </ElFormItem>
        <ElFormItem label="上级分组" prop="parent_id">
          <ElTreeSelect v-model="formData.parent_id" :data="treeOptions" :props="{ children: 'children', label: 'label', disabled: 'disabled' }" value-key="value" placeholder="请选择上级分组（不选为顶级）" clearable filterable style="width:100%" />
        </ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="排序" prop="sort_order"><ElInputNumber v-model="formData.sort_order" :min="0" style="width:100%" /></ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="状态" prop="status"><ElSwitch v-model="formData.status" active-text="启用" inactive-text="停用" /></ElFormItem>
          </ElCol>
        </ElRow>
        <ElFormItem label="备注" prop="description">
          <ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选备注信息" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount } from "vue";
import { ElMessage } from "element-plus";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { formatTree } from "@utils";
import { VideoAPI } from "@/api/module_video";

defineOptions({ name: "VideoCameraGroup", inheritAttrs: false });

const { hasAuth } = useAuth();
const treeList = ref<any[]>([]);
const treeOptions = ref<any[]>([]);
const rawList = ref<any[]>([]);
const loading = ref(false);

const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function fetchGroups() {
  loading.value = true;
  try {
    const res = await VideoAPI.listCameraGroup();
    const tree = res.data?.data || [];
    treeList.value = tree;
    rawList.value = flattenTree(tree);
  } finally {
    loading.value = false;
  }
}
function flattenTree(nodes: any[], result: any[] = []): any[] {
  for (const node of nodes) {
    result.push(node);
    if (node.children?.length) flattenTree(node.children, result);
  }
  return result;
}
function refreshData() { return fetchGroups(); }

async function handleDeleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteCameraGroup([id]);
    ElMessage.success("删除成功");
    await refreshData();
  } catch {
    // cancel
  }
}
async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    await VideoAPI.deleteCameraGroup(ids);
    ElMessage.success("删除成功");
    await refreshData();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  parent_id: undefined as number | undefined,
  sort_order: 0,
  status: true,
  description: undefined as string | undefined,
});
const initialFormData = { id: undefined, name: undefined, parent_id: undefined, sort_order: 0, status: true, description: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);
const rules = reactive({ name: [{ required: true, message: "请输入分组名称", trigger: "blur" }] });

function excludeSelfAndChildren(nodes: any[], excludeId: number): any[] {
  return nodes
    .filter(n => n.id !== excludeId)
    .map(n => (n.children?.length ? { ...n, children: excludeSelfAndChildren(n.children, excludeId) } : { ...n }));
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  const res = await VideoAPI.listCameraGroup();
  const treeListData = res.data?.data || [];
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑分组";
    const item = rawList.value.find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id, name: item.name, parent_id: item.parent_id,
        sort_order: item.sort_order, status: item.status, description: item.description,
      });
    }
    treeOptions.value = formatTree(excludeSelfAndChildren(treeListData, id));
  } else {
    dialogVisible.title = "新增分组";
    Object.assign(formData, initialFormData);
    treeOptions.value = formatTree(treeListData);
  }
  dialogVisible.visible = true;
}

function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    try {
      if (id) await VideoAPI.updateCameraGroup(id, { ...formData });
      else await VideoAPI.createCameraGroup({ ...formData });
      ElMessage.success("保存成功");
      dialogVisible.visible = false;
      Object.assign(formData, initialFormData);
      await refreshData();
    } catch {
      // ignore
    } finally {
      submitLoading.value = false;
    }
  });
}

const columnChecks = ref([
  { prop: "selection", label: "选择框", show: true },
  { prop: "name", label: "分组名称", show: true },
  { prop: "sort_order", label: "排序", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "description", label: "备注", show: true },
  { prop: "created_at", label: "创建时间", show: true },
]);

onBeforeMount(fetchGroups);
</script>

<style scoped>
.data-table__content { padding: 0 12px 12px; }
</style>
