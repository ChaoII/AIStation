<template>
  <div class="app-container">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="算法管理" name="algorithm">
        <el-table :data="algorithmList" v-loading="algoLoading" stripe border style="width: 100%">
          <template #empty>
            <el-empty :image-size="80" description="暂无算法" />
          </template>
          <el-table-column type="selection" width="50" align="center" />
          <el-table-column label="序号" width="65" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="name" label="算法名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="code" label="编码" width="140" />
          <el-table-column prop="version" label="版本" width="90" align="center" />
          <el-table-column prop="algorithm_type" label="算法类型" width="120" />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status ? 'success' : 'info'" size="small">{{ row.status ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right" align="center">
            <template #default="{ row }">
              <el-button v-hasPerm="['module_video:algorithm:update']" size="small" type="primary" link @click="openAlgoEdit(row)">编辑</el-button>
              <el-button v-hasPerm="['module_video:algorithm:delete']" size="small" type="danger" link @click="handleAlgoDelete(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="算法任务" name="task">
        <div class="page-header" style="padding: 0 0 12px 0; border-bottom: none;">
          <div class="page-header-left" />
          <div class="page-header-right">
            <el-button v-hasPerm="['module_video:algorithm:create']" type="primary" icon="Plus" @click="openTaskCreate">新建任务</el-button>
          </div>
        </div>
        <el-table :data="taskList" v-loading="taskLoading" stripe border style="width: 100%">
          <template #empty>
            <el-empty :image-size="80" description="暂无算法任务" />
          </template>
          <el-table-column type="selection" width="50" align="center" />
          <el-table-column label="序号" width="65" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="camera_id" label="摄像机ID" width="100" align="center" />
          <el-table-column prop="algorithm_id" label="算法ID" width="90" align="center" />
          <el-table-column prop="stream_type" label="码流" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small">{{ row.stream_type === 'MAIN' ? '主码流' : '子码流' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="sensitivity" label="灵敏度" width="80" align="center" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'RUNNING' ? 'success' : row.status === 'ERROR' ? 'danger' : 'info'" size="small">
                {{ taskStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right" align="center">
            <template #default="{ row }">
              <el-button v-hasPerm="['module_video:algorithm:update']" size="small" type="primary" link @click="openTaskEdit(row)">编辑</el-button>
              <el-button v-hasPerm="['module_video:algorithm:delete']" size="small" type="danger" link @click="handleTaskDelete(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="taskDialogVisible" :title="editingTaskId ? '编辑任务' : '新建任务'" width="500px" destroy-on-close>
      <el-form :model="taskForm" label-width="100px" size="default">
        <el-form-item label="摄像机ID" prop="camera_id">
          <el-input-number v-model="taskForm.camera_id" :min="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="算法" prop="algorithm_id">
          <el-select v-model="taskForm.algorithm_id" style="width:100%">
            <el-option v-for="a in algorithmList" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="码流" prop="stream_type">
          <el-radio-group v-model="taskForm.stream_type">
            <el-radio value="MAIN">主码流</el-radio>
            <el-radio value="SUB">子码流</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="灵敏度" prop="sensitivity">
          <el-slider v-model="taskForm.sensitivity" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="taskForm.status" style="width:100%">
            <el-option label="运行中" value="RUNNING" />
            <el-option label="已停止" value="STOPPED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleTaskSave" :loading="taskSubmitLoading">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'

const activeTab = ref('algorithm')

const algoLoading = ref(false)
const algorithmList = ref<any[]>([
  { id: 1, name: '区域入侵检测', code: 'INTRUSION', version: '1.0.0', algorithm_type: '入侵检测', status: true },
  { id: 2, name: '越界检测', code: 'LINE_CROSSING', version: '1.0.0', algorithm_type: '行为分析', status: true },
  { id: 3, name: '人脸识别', code: 'FACE_DETECT', version: '2.0.0', algorithm_type: '生物识别', status: true },
])

const taskLoading = ref(false)
const taskList = ref<any[]>([])
const taskDialogVisible = ref(false)
const taskSubmitLoading = ref(false)
const taskForm = ref<any>({ stream_type: 'SUB', sensitivity: 50, status: 'STOPPED' })
const editingTaskId = ref<number | null>(null)

function taskStatusLabel(status: string) {
  const map: Record<string, string> = { RUNNING: '运行中', STOPPED: '已停止', ERROR: '异常' }
  return map[status] || status
}

function openAlgoEdit(row: any) {
  ElMessage.info('功能开发中')
}

function handleAlgoDelete(id: number) {
  ElMessage.info('功能开发中')
}

function openTaskCreate() {
  editingTaskId.value = null
  taskForm.value = { stream_type: 'SUB', sensitivity: 50, status: 'STOPPED' }
  taskDialogVisible.value = true
}

function openTaskEdit(row: any) {
  editingTaskId.value = row.id
  taskForm.value = { ...row }
  taskDialogVisible.value = true
}

async function handleTaskSave() {
  taskSubmitLoading.value = true
  try {
    await new Promise(r => setTimeout(r, 500))
    if (editingTaskId.value) {
      ElMessage.success('修改成功')
    } else {
      ElMessage.success('创建成功')
    }
    taskDialogVisible.value = false
  } finally {
    taskSubmitLoading.value = false
  }
}

async function handleTaskDelete(id: number) {
  try {
    await ElMessageBox.confirm('确认删除该任务？', '删除确认', { type: 'warning' })
    ElMessage.success('删除成功')
  } catch {}
}

onMounted(() => {})
</script>
