<template>
  <div class="app-container">
    <div class="page-header">
      <div class="page-header-left">
        <span class="page-title">事件联动</span>
      </div>
      <div class="page-header-right">
        <el-button v-hasPerm="['module_video:event:create']" type="primary" icon="Plus" @click="openCreate">新建联动</el-button>
      </div>
    </div>

    <el-table :data="linkageList" v-loading="loading" stripe border style="width: 100%">
      <template #empty>
        <el-empty :image-size="80" description="暂无联动规则" />
      </template>
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="序号" width="65" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="name" label="联动名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="触发事件" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="eventTag(row.trigger_event)" size="small" effect="plain">{{ eventLabel(row.trigger_event) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="动作类型" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="actionTag(row.action_type)" size="small" effect="plain">{{ actionLabel(row.action_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="trigger_camera_ids" label="关联摄像机" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ row.trigger_camera_ids?.length || 0 }}台</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.status" disabled />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['module_video:event:update']" size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-hasPerm="['module_video:event:delete']" size="small" type="danger" link @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑联动' : '新建联动'" width="600px" destroy-on-close>
      <el-form :model="formData" label-width="110px" size="default">
        <el-form-item label="联动名称" prop="name" required>
          <el-input v-model="formData.name" placeholder="例如：入侵检测联动录像" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="触发事件" prop="trigger_event">
              <el-select v-model="formData.trigger_event" style="width:100%">
                <el-option label="告警触发" value="ALARM" />
                <el-option label="移动侦测" value="MOTION" />
                <el-option label="设备离线" value="OFFLINE" />
                <el-option label="设备上线" value="ONLINE" />
                <el-option label="视频丢失" value="VIDEO_LOST" />
                <el-option label="定时触发" value="SCHEDULE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="动作类型" prop="action_type">
              <el-select v-model="formData.action_type" style="width:100%">
                <el-option label="启动录像" value="RECORD" />
                <el-option label="发送告警" value="ALERT" />
                <el-option label="云台控制" value="PTZ" />
                <el-option label="消息推送" value="PUSH" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="关联摄像机" prop="trigger_camera_ids">
          <el-select v-model="formData.trigger_camera_ids" multiple filterable style="width:100%" placeholder="选择摄像机（可选，不选则对所有摄像机生效）">
            <el-option v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="动作参数" prop="action_params">
          <el-input v-model="actionParamsText" type="textarea" :rows="3" placeholder="JSON格式动作参数，例如：{\"storage_days\": 30}" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="formData.status" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
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
import { ref, computed, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { getCameraList } from '@/api/module_video/camera'
import { ElMessageBox, ElMessage } from 'element-plus'

const loading = ref(false)
const submitLoading = ref(false)
const cameras = ref<any[]>([])
const linkageList = ref<any[]>([
  {
    id: 1,
    name: '入侵检测联动录像',
    trigger_event: 'ALARM',
    trigger_camera_ids: [1],
    action_type: 'RECORD',
    action_params: { storage_days: 30 },
    status: true,
    description: '检测到入侵时自动开启录像',
  },
  {
    id: 2,
    name: '设备离线告警推送',
    trigger_event: 'OFFLINE',
    trigger_camera_ids: null,
    action_type: 'PUSH',
    action_params: { notify_type: 'WS_PUSH' },
    status: true,
    description: '设备离线时推送告警消息',
  },
])

const dialogVisible = ref(false)
const formData = ref<any>({ trigger_event: 'ALARM', action_type: 'RECORD', trigger_camera_ids: [], status: true, action_params: {} })
const editingId = ref<number | null>(null)
const actionParamsText = ref('')

function eventLabel(type: string) {
  const map: Record<string, string> = { ALARM: '告警触发', MOTION: '移动侦测', OFFLINE: '设备离线', ONLINE: '设备上线', VIDEO_LOST: '视频丢失', SCHEDULE: '定时触发' }
  return map[type] || type
}

function eventTag(type: string) {
  const map: Record<string, string> = { ALARM: 'danger', MOTION: 'warning', OFFLINE: 'info', ONLINE: 'success', VIDEO_LOST: 'danger', SCHEDULE: 'primary' }
  return map[type] || ''
}

function actionLabel(type: string) {
  const map: Record<string, string> = { RECORD: '启动录像', ALERT: '发送告警', PTZ: '云台控制', PUSH: '消息推送' }
  return map[type] || type
}

function actionTag(type: string) {
  const map: Record<string, string> = { RECORD: 'primary', ALERT: 'danger', PTZ: 'warning', PUSH: 'success' }
  return map[type] || ''
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 1000 })
    cameras.value = res.data?.items || []
  } catch {}
}

function openCreate() {
  editingId.value = null
  formData.value = { trigger_event: 'ALARM', action_type: 'RECORD', trigger_camera_ids: [], status: true, action_params: {} }
  actionParamsText.value = ''
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  formData.value = { ...row }
  actionParamsText.value = row.action_params ? JSON.stringify(row.action_params, null, 2) : ''
  dialogVisible.value = true
}

async function handleSave() {
  submitLoading.value = true
  try {
    if (actionParamsText.value) {
      try {
        formData.value.action_params = JSON.parse(actionParamsText.value)
      } catch {
        ElMessage.warning('动作参数JSON格式错误，已忽略')
        formData.value.action_params = {}
      }
    }
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
    await ElMessageBox.confirm('确认删除该联动规则？', '删除确认', { type: 'warning' })
    ElMessage.success('删除成功')
  } catch {}
}

onMounted(fetchCameras)
</script>
