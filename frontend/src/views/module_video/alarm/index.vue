<template>
  <div class="app-container">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="告警记录" name="record">
        <el-table :data="recordList" v-loading="recordLoading" stripe border style="width: 100%">
          <template #empty>
            <el-empty :image-size="80" description="暂无告警记录" />
          </template>
          <el-table-column type="selection" width="50" align="center" />
          <el-table-column label="序号" width="65" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="alarm_time" label="告警时间" width="170" />
          <el-table-column prop="camera_id" label="摄像机ID" width="90" align="center" />
          <el-table-column prop="alarm_type" label="类型" width="120" />
          <el-table-column prop="severity" label="级别" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="severityTag(row.severity)" size="small" effect="dark">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="240" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'PENDING'"
                v-hasPerm="['module_video:alarm:confirm']"
                size="small"
                type="success"
                plain
                @click="handleConfirm(row.id, 'CONFIRMED')"
              >确认</el-button>
              <el-button
                v-if="row.status === 'PENDING'"
                v-hasPerm="['module_video:alarm:confirm']"
                size="small"
                plain
                @click="handleConfirm(row.id, 'FALSE_ALARM')"
              >误报</el-button>
              <el-button
                v-hasPerm="['module_video:alarm:delete']"
                size="small"
                type="danger"
                link
                @click="handleDeleteRecord([row.id])"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="告警规则" name="rule">
        <div class="page-header" style="padding: 0 0 12px 0; border-bottom: none;">
          <div class="page-header-left" />
          <div class="page-header-right">
            <el-button v-hasPerm="['module_video:alarm_rule:create']" type="primary" icon="Plus" @click="openRuleEdit()">新增规则</el-button>
          </div>
        </div>
        <el-table :data="ruleList" v-loading="ruleLoading" stripe border style="width: 100%">
          <template #empty>
            <el-empty :image-size="80" description="暂无告警规则" />
          </template>
          <el-table-column type="selection" width="50" align="center" />
          <el-table-column label="序号" width="65" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="name" label="规则名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="alarm_type" label="告警类型" width="120" />
          <el-table-column prop="severity" label="级别" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="severityTag(row.severity)" size="small" effect="dark">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="sensitivity" label="灵敏度" width="80" align="center" />
          <el-table-column prop="interval_seconds" label="间隔(秒)" width="90" align="center" />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.status" disabled />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right" align="center">
            <template #default="{ row }">
              <el-button v-hasPerm="['module_video:alarm_rule:update']" size="small" type="primary" link @click="openRuleEdit(row)">编辑</el-button>
              <el-button v-hasPerm="['module_video:alarm_rule:delete']" size="small" type="danger" link @click="handleDeleteRule([row.id])">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="ruleDialogVisible" :title="editingRuleId ? '编辑规则' : '新增规则'" width="560px" destroy-on-close>
      <el-form :model="ruleForm" label-width="100px" size="default">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="ruleForm.name" placeholder="请输入规则名称" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="告警类型" prop="alarm_type">
              <el-select v-model="ruleForm.alarm_type" style="width:100%">
                <el-option label="运动检测" value="MOTION" />
                <el-option label="越界检测" value="LINE_CROSSING" />
                <el-option label="区域入侵" value="INTRUSION" />
                <el-option label="人脸识别" value="FACE_DETECT" />
                <el-option label="移动侦测" value="MOVEMENT" />
                <el-option label="视频遮挡" value="VIDEO_BLOCK" />
                <el-option label="视频丢失" value="VIDEO_LOST" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="级别" prop="severity">
              <el-select v-model="ruleForm.severity" style="width:100%">
                <el-option label="严重" value="CRITICAL" />
                <el-option label="警告" value="WARNING" />
                <el-option label="信息" value="INFO" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="灵敏度" prop="sensitivity">
              <el-slider v-model="ruleForm.sensitivity" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="间隔(秒)" prop="interval_seconds">
              <el-input-number v-model="ruleForm.interval_seconds" :min="1" :max="3600" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="ruleForm.status" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="ruleForm.description" type="textarea" :rows="2" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveRule" :loading="ruleSubmitLoading">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  getAlarmRecordList,
  getAlarmRuleList,
  confirmAlarm,
  deleteAlarmRecord,
  deleteAlarmRule,
  createAlarmRule,
  updateAlarmRule,
} from '@/api/module_video/alarm'
import { ElMessageBox, ElMessage } from 'element-plus'

const activeTab = ref('record')
const recordLoading = ref(false)
const ruleLoading = ref(false)
const ruleSubmitLoading = ref(false)
const recordList = ref<any[]>([])
const ruleList = ref<any[]>([])
const ruleDialogVisible = ref(false)
const ruleForm = ref<any>({ status: true, sensitivity: 50, interval_seconds: 30, severity: 'WARNING' })
const editingRuleId = ref<number | null>(null)

function severityTag(severity: string) {
  const map: Record<string, string> = { CRITICAL: 'danger', WARNING: 'warning', INFO: 'info' }
  return map[(severity || '').toUpperCase()] || 'info'
}

function statusTag(status: string) {
  const map: Record<string, string> = { PENDING: 'danger', CONFIRMED: 'success', IGNORED: 'info', FALSE_ALARM: 'warning' }
  return map[(status || '').toUpperCase()] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { PENDING: '待处理', CONFIRMED: '已确认', IGNORED: '已忽略', FALSE_ALARM: '误报' }
  return map[(status || '').toUpperCase()] || status
}

async function fetchRecords() {
  recordLoading.value = true
  try {
    const res = await getAlarmRecordList({ page_size: 1000 })
    recordList.value = res.data?.items || []
  } finally {
    recordLoading.value = false
  }
}

async function fetchRules() {
  ruleLoading.value = true
  try {
    const res = await getAlarmRuleList({ page_size: 1000 })
    ruleList.value = res.data?.items || []
  } finally {
    ruleLoading.value = false
  }
}

async function handleConfirm(id: number, status: string) {
  try {
    await confirmAlarm(id, status)
    ElMessage.success(status === 'CONFIRMED' ? '已确认告警' : '已标记为误报')
    await fetchRecords()
  } catch {}
}

async function handleDeleteRecord(ids: number[]) {
  try {
    await ElMessageBox.confirm('确认删除所选告警记录？', '删除确认', { type: 'warning' })
    await deleteAlarmRecord(ids)
    ElMessage.success('删除成功')
    await fetchRecords()
  } catch {}
}

function openRuleEdit(row?: any) {
  if (row) {
    editingRuleId.value = row.id
    ruleForm.value = { ...row }
  } else {
    editingRuleId.value = null
    ruleForm.value = { status: true, sensitivity: 50, interval_seconds: 30, severity: 'WARNING' }
  }
  ruleDialogVisible.value = true
}

async function handleSaveRule() {
  ruleSubmitLoading.value = true
  try {
    if (editingRuleId.value) {
      await updateAlarmRule(editingRuleId.value, ruleForm.value)
      ElMessage.success('修改成功')
    } else {
      await createAlarmRule(ruleForm.value)
      ElMessage.success('创建成功')
    }
    ruleDialogVisible.value = false
    await fetchRules()
  } finally {
    ruleSubmitLoading.value = false
  }
}

async function handleDeleteRule(ids: number[]) {
  try {
    await ElMessageBox.confirm('确认删除所选规则？', '删除确认', { type: 'warning' })
    await deleteAlarmRule(ids)
    ElMessage.success('删除成功')
    await fetchRules()
  } catch {}
}

onMounted(() => { fetchRecords(); fetchRules() })
</script>
