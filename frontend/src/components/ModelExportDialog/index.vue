<template>
  <el-dialog v-model="visible" title="导出模型" width="600px" :close-on-click-modal="false">
    <template v-if="!exporting && !result">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="基本" name="basic">
          <el-form label-width="120px" size="small">
            <el-form-item label="导出格式">
              <el-select v-model="form.format" style="width:100%">
                <el-option v-for="fmt in formats" :key="fmt.value" :label="fmt.label" :value="fmt.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="输入尺寸">
              <el-input-number v-model="form.imgsz" :min="32" :step="32" style="width:100%" />
            </el-form-item>
            <el-form-item label="批量大小">
              <el-input-number v-model="form.batch" :min="1" :max="32" style="width:100%" />
            </el-form-item>
            <el-form-item label="导出设备">
              <el-select v-model="form.device" style="width:100%">
                <el-option label="CPU" value="cpu" />
                <el-option label="GPU 0" value="0" />
                <el-option label="GPU 1" value="1" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="优化" name="optimize">
          <el-form label-width="140px" size="small">
            <el-form-item v-if="hasParam('quantize')" label="量化精度">
              <el-select v-model="form.quantize" placeholder="无（FP32）" clearable style="width:100%">
                <el-option label="FP32（无量化）" value="" />
                <el-option label="FP16（半精度）" value="16" />
                <el-option label="INT8（整数量化）" value="8" />
                <el-option label="W8A16（权重INT8+激活FP16）" value="w8a16" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="hasParam('dynamic')" label="动态输入尺寸">
              <el-switch v-model="form.dynamic" />
              <span style="margin-left:8px;font-size:12px;color:#909399">允许输入不同尺寸的图片</span>
            </el-form-item>
            <el-form-item v-if="hasParam('simplify')" label="ONNX 图简化">
              <el-switch v-model="form.simplify" />
            </el-form-item>
            <el-form-item v-if="hasParam('opset')" label="ONNX Opset 版本">
              <el-select v-model="form.opset" placeholder="自动" clearable style="width:100%">
                <el-option label="自动（推荐）" value="" />
                <el-option label="15" value="15" />
                <el-option label="16" value="16" />
                <el-option label="17" value="17" />
                <el-option label="18" value="18" />
                <el-option label="19" value="19" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="hasParam('workspace')" label="TensorRT 工作空间">
              <el-input-number v-model="wsVal" :min="1" :max="32" style="width:100%" /> GiB
            </el-form-item>
            <el-form-item v-if="hasParam('optimize')" label="移动端优化">
              <el-switch v-model="form.optimize" />
              <span style="margin-left:8px;font-size:12px;color:#909399">TorchScript 移动端优化</span>
            </el-form-item>
            <el-form-item v-if="hasParam('keras')" label="Keras 格式">
              <el-switch v-model="form.keras" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="后处理" name="postproc">
          <el-form label-width="140px" size="small">
            <el-form-item v-if="hasParam('nms')" label="内置 NMS">
              <el-switch v-model="form.nms" />
              <span style="margin-left:8px;font-size:12px;color:#909399">将 NMS 嵌入导出模型</span>
            </el-form-item>
            <el-form-item v-if="hasParam('end2end')" label="端到端模式">
              <el-select v-model="form.end2end" placeholder="使用模型默认" clearable style="width:100%">
                <el-option label="使用模型默认" value="" />
                <el-option label="启用" :value="true" />
                <el-option label="禁用" :value="false" />
              </el-select>
            </el-form-item>
          </el-form>
          <div v-if="hasParam('quantize') && form.quantize === 8" style="margin-top:12px;padding:8px 12px;background:#fef0f0;border-radius:4px;color:#f56c6c;font-size:12px">
            INT8 量化需要校准数据集。确保训练时使用的数据集 YAML 在容器中可访问。
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <template v-else-if="exporting">
      <div style="text-align:center;padding:40px 0">
        <el-progress type="circle" :percentage="100" :stroke-width="8" status="warning" />
        <p style="margin-top:16px;color:#909399;font-size:14px">正在导出模型...<br><span style="font-size:12px">{{ statusText }}</span></p>
      </div>
    </template>

    <template v-else-if="result">
      <div style="text-align:center;padding:20px 0">
        <el-icon :size="48" color="#67c23a"><CircleCheckFilled /></el-icon>
        <p style="margin:12px 0 8px;font-size:16px;font-weight:600">导出完成</p>
        <p style="color:#909399;font-size:13px">格式: {{ result.format }} | 大小: {{ formatSize(result.file_size) }}</p>
        <el-button type="primary" style="margin-top:16px" @click="handleDownload">下载文件</el-button>
      </div>
    </template>

    <template #footer v-if="!exporting && !result">
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleExport" :loading="exporting">开始导出</el-button>
    </template>
    <template #footer v-if="result">
      <el-button type="primary" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { CircleCheckFilled } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const props = defineProps<{ modelId: number; modelName?: string }>();
const emit = defineEmits<{ (e: "done"): void }>();

const visible = defineModel<boolean>("visible", { default: false });
const activeTab = ref("basic");
const exporting = ref(false);
const result = ref<any>(null);

const formats = [
  { label: "ONNX（通用）⭐", value: "onnx" },
  { label: "TorchScript（LibTorch）", value: "torchscript" },
  { label: "TensorRT（NVIDIA GPU）", value: "engine" },
  { label: "OpenVINO（Intel CPU）", value: "openvino" },
  { label: "CoreML（Apple）", value: "coreml" },
  { label: "PaddlePaddle", value: "paddle" },
  { label: "NCNN（移动端）", value: "ncnn" },
  { label: "TFLite（移动端/边缘）", value: "tflite" },
  { label: "TF SavedModel", value: "saved_model" },
  { label: "TF.js（浏览器）", value: "tfjs" },
];

const form = reactive<any>({
  format: "onnx",
  imgsz: 640,
  batch: 1,
  device: "cpu",
  quantize: "",
  simplify: true,
  opset: "",
  workspace: "",
  nms: false,
  end2end: "",
  dynamic: false,
  optimize: false,
  keras: false,
  data: "",
  fraction: 1.0,
});

const wsVal = computed({
  get: () => form.workspace || 4,
  set: (v) => { form.workspace = v; },
});

// Per-format supported parameters (simplified)
const formatParams: Record<string, string[]> = {
  onnx: ["quantize", "dynamic", "simplify", "opset", "nms"],
  torchscript: ["quantize", "dynamic", "optimize", "nms"],
  engine: ["quantize", "dynamic", "simplify", "workspace", "nms"],
  openvino: ["quantize", "dynamic", "nms"],
  coreml: ["quantize", "dynamic", "nms"],
  saved_model: ["quantize", "nms", "keras"],
  paddle: [],
  ncnn: ["quantize"],
  tflite: ["quantize"],
  tfjs: [],
};

function hasParam(name: string): boolean {
  return formatParams[form.format]?.includes(name) ?? false;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

let statusText = ref("准备中...");

async function handleExport() {
  exporting.value = true;
  statusText.value = "正在初始化...";
  try {
    const payload: Record<string, any> = {};
    for (const [k, v] of Object.entries(form)) {
      if (v !== null && v !== undefined) payload[k] = v;
    }

    statusText.value = "容器启动中...";
    const r = await TrainAPI.exportModel(props.modelId, payload);
    result.value = r.data?.data;
    ElMessage.success("模型导出完成");
    emit("done");
  } catch (e: any) {
    ElMessage.error(e?.msg || "导出失败");
    exporting.value = false;
  }
}

function handleDownload() {
  if (result.value?.download_url) window.open(result.value.download_url, "_blank");
}

watch(() => visible.value, (v) => {
  if (!v) { result.value = null; exporting.value = false; }
});
</script>
