<template>
  <div class="app-container">
    <div class="page-header">
      <div class="page-header-left">
        <span class="page-title">布局管理</span>
      </div>
      <div class="page-header-right">
        <el-button v-hasPerm="['module_video:layout:create']" type="primary" icon="Plus" @click="openCreate">新建布局</el-button>
      </div>
    </div>

    <el-table :data="layouts" v-loading="loading" stripe border style="width: 100%">
      <template #empty>
        <el-empty :image-size="80" description="暂无布局" />
      </template>
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="序号" width="65" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="name" label="布局名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="grid_type" label="画面数" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small">{{ row.grid_type }}路</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认布局" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          <span v-else class="text-secondary">-</span>
        </template>
      </el-table-column>
      <el-table-column label="预览" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" icon="View" circle @click="handlePreview(row.grid_type)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['module_video:layout:update']" size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-hasPerm="['module_video:layout:delete']" size="small" type="danger" link @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑布局' : '新建布局'" width="500px" destroy-on-close>
      <el-form :model="formData" label-width="100px" size="default">
        <el-form-item label="布局名称" prop="name" required>
          <el-input v-model="formData.name" placeholder="例如：4路默认" />
        </el-form-item>
        <el-form-item label="画面数" prop="grid_type">
          <el-select v-model="formData.grid_type" style="width:100%">
            <el-option label="1路" value="1" />
            <el-option label="4路" value="4" />
            <el-option label="6路" value="6" />
            <el-option label="8路" value="8" />
            <el-option label="9路" value="9" />
            <el-option label="16路" value="16" />
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="submitLoading">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, View } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'

const loading = ref(false)
const submitLoading = ref(false)
const layouts = ref<any[]>([
  { id: 1, name: '4路默认布局', grid_type: '4', is_default: true, description: '适用于小型监控场景' },
  { id: 2, name: '9路密集布局', grid_type: '9', is_default: false, description: '适用于密集监控场景' },
  { id: 3, name: '1路全屏', grid_type: '1', is_default: false, description: '单路全屏预览' },
])
const dialogVisible = ref(false)
const formData = ref<any>({ grid_type: '4', is_default: false })
const editingId = ref<number | null>(null)

function openCreate() {
  editingId.value = null
  formData.value = { grid_type: '4', is_default: false, name: '', description: '' }
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  formData.value = { ...row }
  dialogVisible.value = true
}

async function handleSave() {
  submitLoading.value = true
  try {
    await new Promise(r => setTimeout(r, 300))
    if (editingId.value) {
      ElMessage.success('修改成功')
    } else {
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确认删除该布局？', '删除确认', { type: 'warning' })
    ElMessage.success('删除成功')
  } catch {}
}

function handlePreview(gridType: string) {
  ElMessage.info(`预览 ${gridType} 路布局（功能开发中）`)
}

onMounted(() => {})
</script>

<style scoped>
.text-secondary {
  color: var(--el-text-color-secondary);
}
</style>
