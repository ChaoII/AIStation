<template>
  <div class="app-container">
    <div class="page-header">
      <div class="page-header-left">
        <span class="page-title">录制计划</span>
      </div>
      <div class="page-header-right">
        <el-button v-hasPerm="['module_video:record:create']" type="primary" icon="Plus" @click="openCreate">新增计划</el-button>
      </div>
    </div>

    <el-table :data="planList" v-loading="loading" stripe border style="width: 100%">
      <template #empty>
        <el-empty :image-size="80" description="暂无录制计划" />
      </template>
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="序号" width="65" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="camera_id" label="摄像机ID" width="100" align="center" />
      <el-table-column prop="plan_type" label="计划类型" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="planTypeTag(row.plan_type)" size="small" effect="plain">{{ planTypeLabel(row.plan_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="pre_record_sec" label="预录(秒)" width="80" align="center" />
      <el-table-column prop="post_record_sec" label="延录(秒)" width="80" align="center" />
      <el-table-column prop="storage_days" label="存储天数" width="90" align="center" />
      <el-table-column prop="stream_type" label="码流" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small">{{ row.stream_type === 'MAIN' ? '主码流' : '子码流' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.status" disabled />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['module_video:record:update']" size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-hasPerm="['module_video:record:delete']" size="small" type="danger" link @click="handleDelete([row.id])">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑计划' : '新增计划'" width="560px" destroy-on-close>
      <el-form :model="formData" label-width="100px" size="default">
        <el-form-item label="摄像机ID" prop="camera_id">
          <el-input-number v-model="formData.camera_id" :min="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="计划类型" prop="plan_type">
          <el-select v-model="formData.plan_type" style="width:100%">
            <el-option label="全天录制" value="CONTINUOUS" />
            <el-option label="定时录制" value="SCHEDULE" />
            <el-option label="事件录制" value="EVENT" />
            <el-option label="告警录制" value="ALARM" />
          </el-select>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="预录(秒)" prop="pre_record_sec">
              <el-input-number v-model="formData.pre_record_sec" :min="0" :max="30" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="延录(秒)" prop="post_record_sec">
              <el-input-number v-model="formData.post_record_sec" :min="0" :max="30" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="存储天数" prop="storage_days">
              <el-input-number v-model="formData.storage_days" :min="1" :max="365" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="录制码流" prop="stream_type">
          <el-radio-group v-model="formData.stream_type">
            <el-radio value="MAIN">主码流</el-radio>
            <el-radio value="SUB">子码流</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="formData.status" />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选备注" />
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
import { Plus } from '@element-plus/icons-vue'
import { getRecordPlanList, createRecordPlan, updateRecordPlan, deleteRecordPlan } from '@/api/module_video/record'
import { ElMessageBox, ElMessage } from 'element-plus'

const loading = ref(false)
const submitLoading = ref(false)
const planList = ref<any[]>([])
const dialogVisible = ref(false)
const formData = ref<any>({ plan_type: 'CONTINUOUS', pre_record_sec: 5, post_record_sec: 5, storage_days: 30, stream_type: 'MAIN', status: true })
const editingId = ref<number | null>(null)

function planTypeLabel(type: string) {
  const map: Record<string, string> = { CONTINUOUS: '全天录制', SCHEDULE: '定时录制', EVENT: '事件录制', ALARM: '告警录制' }
  return map[type] || type
}

function planTypeTag(type: string) {
  const map: Record<string, string> = { CONTINUOUS: 'primary', SCHEDULE: 'success', EVENT: 'warning', ALARM: 'danger' }
  return map[type] || ''
}

async function fetchList() {
  loading.value = true
  try {
    const res = await getRecordPlanList({ page_size: 1000 })
    planList.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  formData.value = { plan_type: 'CONTINUOUS', pre_record_sec: 5, post_record_sec: 5, storage_days: 30, stream_type: 'MAIN', status: true }
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
    if (editingId.value) {
      await updateRecordPlan(editingId.value, formData.value)
      ElMessage.success('修改成功')
    } else {
      await createRecordPlan(formData.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchList()
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(ids: number[]) {
  try {
    await ElMessageBox.confirm('确认删除所选计划？', '删除确认', { type: 'warning' })
    await deleteRecordPlan(ids)
    ElMessage.success('删除成功')
    await fetchList()
  } catch {}
}

onMounted(fetchList)
</script>
