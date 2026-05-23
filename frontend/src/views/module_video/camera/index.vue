<template>
  <div class="app-container">
    <div class="page-header">
      <div class="page-header-left">
        <span class="page-title">摄像机管理</span>
      </div>
      <div class="page-header-right">
        <el-button v-hasPerm="['module_video:camera:create']" type="primary" icon="Plus" @click="openCreate">新增摄像机</el-button>
      </div>
    </div>

    <el-table :data="cameraList" v-loading="loading" stripe border style="width: 100%" size="default">
      <template #empty>
        <el-empty :image-size="80" description="暂无摄像机" />
      </template>
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="序号" width="65" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="device_type" label="类型" width="120">
        <template #default="{ row }">
          <el-tag :type="deviceTypeTag(row.device_type)" size="small" effect="plain">{{ deviceTypeLabel(row.device_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ONLINE' ? 'success' : row.status === 'ERROR' ? 'danger' : 'info'" size="small">
            <template #default>
              <span :style="{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: row.status === 'ONLINE' ? '#67c23a' : row.status === 'ERROR' ? '#f56c6c' : '#909399', marginRight: '4px', verticalAlign: 'middle' }"></span>
              {{ row.status === 'ONLINE' ? '在线' : row.status === 'ERROR' ? '异常' : '离线' }}
            </template>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="location" label="位置" min-width="120" show-overflow-tooltip />
      <el-table-column prop="brand" label="品牌" width="100" show-overflow-tooltip />
      <el-table-column prop="stream_id" label="流状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.stream_id" type="success" size="small">推流中</el-tag>
          <el-tag v-else type="info" size="small">未推流</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="推流操作" width="150" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.stream_id"
            v-hasPerm="['module_video:camera:stream']"
            size="small"
            type="primary"
            plain
            @click="handleStartStream(row)"
          >
            启动
          </el-button>
          <el-button
            v-else
            v-hasPerm="['module_video:camera:stream']"
            size="small"
            type="warning"
            plain
            @click="handleStopStream(row)"
          >
            停止
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-hasPerm="['module_video:camera:update']" size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-hasPerm="['module_video:camera:delete']" size="small" type="danger" link @click="handleDelete([row.id])">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="680px" destroy-on-close>
      <el-form ref="formRef" :model="formData" label-width="100px" size="default">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="名称" prop="name" required>
              <el-input v-model="formData.name" placeholder="请输入摄像机名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备类型" prop="device_type">
              <el-select v-model="formData.device_type" style="width:100%">
                <el-option label="IP Camera" value="IP_CAMERA" />
                <el-option label="GB28181" value="GB28181" />
                <el-option label="ONVIF" value="ONVIF" />
                <el-option label="NVR" value="NVR" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="主码流RTSP" prop="rtsp_url_main">
          <el-input v-model="formData.rtsp_url_main" placeholder="rtsp://..." />
        </el-form-item>
        <el-form-item label="子码流RTSP" prop="rtsp_url_sub">
          <el-input v-model="formData.rtsp_url_sub" placeholder="rtsp://..." />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="formData.username" placeholder="登录用户名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input v-model="formData.password" type="password" show-password placeholder="登录密码" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="安装位置" prop="location">
              <el-input v-model="formData.location" placeholder="例如：一楼大厅" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序" prop="sort_order">
              <el-input-number v-model="formData.sort_order" :min="0" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="品牌" prop="brand">
              <el-input v-model="formData.brand" placeholder="例如：海康威视" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="型号" prop="model_name">
              <el-input v-model="formData.model_name" placeholder="例如：DS-2CD3T86" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选备注信息" />
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
import { getCameraList, createCamera, updateCamera, deleteCamera, startStream, stopStream } from '@/api/module_video/camera'
import { ElMessageBox, ElMessage } from 'element-plus'

const loading = ref(false)
const submitLoading = ref(false)
const cameraList = ref<any[]>([])
const dialogVisible = ref(false)
const dialogTitle = ref('新增摄像机')
const formRef = ref()
const formData = ref<any>({ device_type: 'IP_CAMERA', stream_type: 'MAIN', onvif_port: 80, sort_order: 0 })
const editingId = ref<number | null>(null)

function deviceTypeLabel(type: string) {
  const map: Record<string, string> = { IP_CAMERA: 'IP摄像机', GB28181: 'GB28181', ONVIF: 'ONVIF', NVR: 'NVR' }
  return map[type] || type
}

function deviceTypeTag(type: string) {
  const map: Record<string, string> = { IP_CAMERA: '', GB28181: 'success', ONVIF: 'warning', NVR: 'info' }
  return map[type] || ''
}

async function fetchList() {
  loading.value = true
  try {
    const res = await getCameraList({ page_size: 1000 })
    cameraList.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dialogTitle.value = '新增摄像机'
  formData.value = { device_type: 'IP_CAMERA', stream_type: 'MAIN', onvif_port: 80, sort_order: 0 }
  editingId.value = null
  dialogVisible.value = true
}

function openEdit(row: any) {
  dialogTitle.value = '编辑摄像机'
  formData.value = { ...row }
  editingId.value = row.id
  dialogVisible.value = true
}

async function handleSave() {
  submitLoading.value = true
  try {
    if (editingId.value) {
      await updateCamera(editingId.value, formData.value)
      ElMessage.success('修改成功')
    } else {
      await createCamera(formData.value)
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
    await ElMessageBox.confirm('确认删除所选摄像机？此操作不可恢复。', '删除确认', { type: 'warning' })
    await deleteCamera(ids)
    ElMessage.success('删除成功')
    await fetchList()
  } catch {}
}

async function handleStartStream(row: any) {
  try {
    await startStream(row.id)
    ElMessage.success('推流启动成功')
    await fetchList()
  } catch (e: any) {
    ElMessage.error(e?.message || '推流启动失败')
  }
}

async function handleStopStream(row: any) {
  try {
    await stopStream(row.id)
    ElMessage.success('推流已停止')
    await fetchList()
  } catch (e: any) {
    ElMessage.error(e?.message || '停止推流失败')
  }
}

onMounted(fetchList)
</script>
