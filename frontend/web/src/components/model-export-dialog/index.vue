<template>
  <ElDialog
    :model-value="visible"
    title="导出模型"
    width="600px"
    :close-on-click-modal="false"
    :closeable="!exporting"
    @update:model-value="(v: boolean) => (visible = v)"
  >
    <template v-if="!exporting && !result">
      <div style="margin-bottom:12px">
        <ElButton size="small" type="info" plain @click="showCmdPreview = !showCmdPreview">
          {{ showCmdPreview ? "隐藏" : "查看" }} Docker 命令
        </ElButton>
      </div>
      <div v-if="showCmdPreview" style="margin-bottom:16px">
        <pre class="export-cmd-pre">{{ dockerCmd }}</pre>
      </div>
      <ElTabs v-model="activeTab">
        <ElTabPane label="基本" name="basic">
          <ElForm label-width="120px" size="small">
            <ElFormItem label="导出格式">
              <ElSelect v-model="form.format" style="width:100%">
                <ElOption v-for="fmt in formats" :key="fmt.value" :label="fmt.label" :value="fmt.value" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="输入尺寸">
              <ElInputNumber v-model="form.imgsz" :min="32" :step="32" style="width:100%" />
            </ElFormItem>
            <ElFormItem label="批量大小">
              <ElInputNumber v-model="form.batch" :min="1" :max="32" style="width:100%" />
            </ElFormItem>
            <ElFormItem label="导出设备">
              <ElSelect v-model="form.device" style="width:100%">
                <ElOption label="CPU" value="cpu" />
                <ElOption label="GPU 0" value="0" />
                <ElOption label="GPU 1" value="1" />
              </ElSelect>
            </ElFormItem>
          </ElForm>
        </ElTabPane>
        <ElTabPane label="优化" name="optimize">
          <ElForm label-width="140px" size="small">
            <ElFormItem v-if="hasParam('quantize')" label="量化精度">
              <ElSelect v-model="form.quantize" placeholder="无（FP32）" clearable style="width:100%">
                <ElOption label="FP32（无量化）" value="" />
                <ElOption label="FP16（半精度）" value="16" />
                <ElOption label="INT8（整数量化）" value="8" />
                <ElOption label="W8A16（权重INT8+激活FP16）" value="w8a16" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem v-if="hasParam('dynamic')" label="动态输入尺寸">
              <ElSwitch v-model="form.dynamic" />
              <span class="export-tip">允许输入不同尺寸的图片</span>
            </ElFormItem>
            <ElFormItem v-if="hasParam('simplify')" label="ONNX 图简化">
              <ElSwitch v-model="form.simplify" />
            </ElFormItem>
            <ElFormItem v-if="hasParam('opset')" label="ONNX Opset 版本">
              <ElSelect v-model="form.opset" placeholder="自动" clearable style="width:100%">
                <ElOption label="自动（推荐）" value="" />
                <ElOption v-for="v in [15,16,17,18,19]" :key="v" :label="String(v)" :value="String(v)" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem v-if="hasParam('workspace')" label="TensorRT 工作空间">
              <ElInputNumber v-model="wsVal" :min="1" :max="32" style="width:100%" /> GiB
            </ElFormItem>
            <ElFormItem v-if="hasParam('optimize')" label="移动端优化">
              <ElSwitch v-model="form.optimize" />
              <span class="export-tip">TorchScript 移动端优化</span>
            </ElFormItem>
            <ElFormItem v-if="hasParam('keras')" label="Keras 格式">
              <ElSwitch v-model="form.keras" />
            </ElFormItem>
          </ElForm>
        </ElTabPane>
        <ElTabPane label="后处理" name="postproc">
          <ElForm label-width="140px" size="small">
            <ElFormItem v-if="hasParam('nms')" label="内置 NMS">
              <ElSwitch v-model="form.nms" />
              <span class="export-tip">将 NMS 嵌入导出模型</span>
            </ElFormItem>
            <ElFormItem v-if="hasParam('end2end')" label="端到端模式">
              <ElSelect v-model="form.end2end" placeholder="使用模型默认" clearable style="width:100%">
                <ElOption label="使用模型默认" value="" />
                <ElOption label="启用" :value="true" />
                <ElOption label="禁用" :value="false" />
              </ElSelect>
            </ElFormItem>
          </ElForm>
          <div v-if="hasParam('quantize') && form.quantize === 8" class="export-warn">
            INT8 量化需要校准数据集。确保训练时使用的数据集 YAML 在容器中可访问。
          </div>
        </ElTabPane>
      </ElTabs>
    </template>

    <template v-else-if="exporting">
      <div class="export-progress">
        <ElProgress type="circle" :percentage="100" :stroke-width="8" status="warning" />
        <p class="export-progress-text">正在导出模型...<br /><span class="export-tip">{{ statusText }}</span></p>
      </div>
    </template>

    <template v-else-if="exportError">
      <div class="export-error">
        <div class="export-error-head">
          <ElIcon :size="48" color="#f56c6c"><CircleCloseFilled /></ElIcon>
          <p class="export-error-title">导出失败</p>
        </div>
        <ElDivider>Docker 日志（最后 200 行）</ElDivider>
        <pre class="export-log-pre">{{ exportLog }}</pre>
        <div style="text-align:center">
          <ElButton type="primary" @click="handleRetry">重新导出</ElButton>
        </div>
      </div>
    </template>

    <template v-else-if="result">
      <div class="export-result">
        <ElIcon :size="48" color="#67c23a"><CircleCheckFilled /></ElIcon>
        <p class="export-result-title">导出完成</p>
        <p class="export-tip">格式: {{ result.format }} | 大小: {{ formatSize(result.file_size) }}</p>
        <div class="export-result-actions">
          <ElButton type="primary" @click="handleDownload"><ElIcon><Download /></ElIcon> 下载文件</ElButton>
          <ElButton @click="visible = false">关闭</ElButton>
        </div>
      </div>
    </template>

    <template v-if="!exporting && !result" #footer>
      <ElButton @click="visible = false">取消</ElButton>
      <ElButton type="primary" @click="handleExport" :loading="exporting">开始导出</ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { CircleCheckFilled, CircleCloseFilled, Download } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const props = defineProps<{ modelId: number; modelName?: string }>();
const emit = defineEmits<{ (e: "done"): void }>();

const visible = ref(false);
const showCmdPreview = ref(false);
const tempDir = ref("/tmp");

TrainAPI.getTempDir()
  .then(res => { if (res?.data?.data?.tempdir) tempDir.value = res.data.data.tempdir; })
  .catch(() => {});
const activeTab = ref("basic");
const exporting = ref(false);
const exportError = ref("");
const exportLog = ref("");
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
  set: (v: number) => { form.workspace = v; },
});

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

const workDir = computed(() => `${tempDir.value}/model_export/${props.modelId}`);
const dockerCmd = computed(() => {
  const cmdArgs: string[] = [];
  for (const [k, v] of Object.entries(form)) {
    if (v === null || v === undefined || v === "") continue;
    if (k === "format") { cmdArgs.push(`format=${v}`); continue; }
    if (!hasParam(k)) continue;
    if (v === true) cmdArgs.push(`${k}=true`);
    else if (v === false) continue;
    else cmdArgs.push(`${k}=${v}`);
  }
  const yoloCmd = ["yolo", "export", "model=/weights/best.pt", ...cmdArgs].join(" \\\n  ");
  return [
    "# 导出流程（后端自动执行，无需手动运行）：",
    "#",
    "# 1. 从 RustFS 下载原始模型 (.pt)：",
    `#    ${workDir.value}/weights/best.pt`,
    "#",
    "# 2. 运行 Docker 容器进行格式转换：",
    `docker run \\`,
    `  -v ${workDir.value}/weights:/weights:rw \\`,
    `  -v ${workDir.value}/output:/output:rw \\`,
    `  ultralytics/ultralytics:latest \\`,
    `  ${yoloCmd}`,
    "#",
    "# 3. 转换完成后将结果上传回 RustFS，并返回下载链接",
  ].join("\n");
});

function formatSize(bytes: number) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

const statusText = ref("准备中...");

async function handleExport() {
  exporting.value = true;
  statusText.value = "正在初始化...";
  try {
    const payload: Record<string, any> = {};
    for (const [k, v] of Object.entries(form)) {
      if (v !== null && v !== undefined && v !== "") payload[k] = v;
    }
    statusText.value = "容器启动中...";
    const r = await TrainAPI.exportModel(props.modelId, payload);
    exportError.value = "";
    exporting.value = false;
    result.value = r.data?.data;
    emit("done");
  } catch (e: any) {
    const msg = e?.response?.data?.msg || e?.msg || "导出失败，未知错误";
    exportError.value = msg.split("\n最后日志:")[0].trim();
    exportLog.value = (msg.split("\n最后日志:")[1] || "").trim();
    if (!exportLog.value) exportLog.value = msg;
    exporting.value = false;
  }
}

function handleDownload() {
  if (result.value?.download_url) window.open(result.value?.download_url, "_blank");
}

function handleRetry() {
  exportError.value = "";
  handleExport();
}

function open() {
  visible.value = true;
}
function close() {
  visible.value = false;
}
defineExpose({ open, close });
</script>

<style scoped>
.export-cmd-pre,
.export-log-pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  font-family: "Cascadia Code", "Fira Code", monospace;
  white-space: pre-wrap;
  word-break: break-all;
}
.export-tip {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
.export-warn {
  margin-top: 12px;
  padding: 8px 12px;
  background: #fef0f0;
  border-radius: 4px;
  color: #f56c6c;
  font-size: 12px;
}
.export-progress {
  text-align: center;
  padding: 40px 0;
}
.export-progress-text {
  margin-top: 16px;
  color: #909399;
  font-size: 14px;
}
.export-error {
  padding: 20px 0;
}
.export-error-head {
  text-align: center;
  margin-bottom: 16px;
}
.export-error-title {
  margin: 12px 0 8px;
  font-size: 16px;
  font-weight: 600;
}
.export-log-pre {
  max-height: 300px;
  overflow-y: auto;
  margin: 0 20px 16px;
}
.export-result {
  text-align: center;
  padding: 24px 0 16px;
}
.export-result-title {
  margin: 12px 0 4px;
  font-size: 16px;
  font-weight: 600;
}
.export-result-actions {
  margin-top: 16px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
