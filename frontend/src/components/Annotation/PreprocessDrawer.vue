<template>
  <el-drawer
    v-model="visible"
    title="数据落地（视频抽帧 / 图片清洗）"
    size="720px"
    destroy-on-close
  >
    <el-form v-if="!job" label-width="96px" size="default">
      <el-form-item label="处理方式">
        <el-radio-group v-model="form.source">
          <el-radio value="video">视频抽帧</el-radio>
          <el-radio value="images">批量图片清洗</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="form.source === 'video' ? '视频文件' : '图片文件'">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :multiple="form.source === 'images'"
          :limit="form.source === 'video' ? 1 : undefined"
          :accept="form.source === 'video' ? 'video/*' : 'image/jpeg,image/png,image/bmp'"
          drag
          :file-list="fileList"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
        >
          <el-icon size="32"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            拖拽{{ form.source === "video" ? "视频" : "图片" }}到此处，或
            <em>点击选择</em>
          </div>
        </el-upload>
      </el-form-item>

      <el-form-item v-if="form.source === 'video'" label="抽帧设置">
        <div class="cfg-grid">
          <div class="cfg-item">
            <span class="cfg-label">间隔(秒)</span>
            <el-input-number v-model="form.interval" :min="0.05" :step="0.5" :controls="false" />
          </div>
          <div class="cfg-item">
            <span class="cfg-label">最多帧数</span>
            <el-input-number v-model="form.maxFrames" :min="0" :step="10" :controls="false" />
          </div>
          <div class="cfg-item">
            <span class="cfg-label">场景变化</span>
            <el-switch v-model="form.sceneChange" />
          </div>
          <div v-if="form.sceneChange" class="cfg-item">
            <span class="cfg-label">场景阈值</span>
            <el-input-number v-model="form.sceneThreshold" :min="0" :step="1" :controls="false" />
          </div>
        </div>
        <div class="cfg-hint">0 表示不限；场景变化模式会在画面突变处额外取帧</div>
      </el-form-item>

      <el-form-item label="清洗设置">
        <div class="cfg-grid">
          <div class="cfg-item">
            <span class="cfg-label">短边下限</span>
            <el-input-number v-model="form.minSide" :min="0" :step="32" :controls="false" />
          </div>
          <div class="cfg-item">
            <span class="cfg-label">模糊阈值</span>
            <el-input-number v-model="form.blur" :min="0" :step="10" :controls="false" />
          </div>
          <div class="cfg-item">
            <span class="cfg-label">近重复阈值</span>
            <el-input-number v-model="form.phash" :min="0" :max="64" :step="1" :controls="false" />
          </div>
        </div>
        <div class="cfg-hint">填 0 表示不启用该项；亮度区间默认剔除过暗/过曝帧</div>
        <div class="cfg-grid cfg-grid--bright">
          <div class="cfg-item">
            <span class="cfg-label">过暗(亮度)</span>
            <el-input-number
              v-model="form.brightnessMin"
              :min="0"
              :max="255"
              :step="5"
              :controls="false"
            />
          </div>
          <div class="cfg-item">
            <span class="cfg-label">过曝(亮度)</span>
            <el-input-number
              v-model="form.brightnessMax"
              :min="0"
              :max="255"
              :step="5"
              :controls="false"
            />
          </div>
        </div>
        <div class="cfg-hint">平均灰度低于过暗阈值、高于过曝阈值的帧会被剔除（填 0 关闭）</div>
      </el-form-item>
    </el-form>

    <!-- 进度 / 报表 -->
    <div v-else class="report">
      <el-steps :active="stepActive" align-center class="steps">
        <el-step title="处理" />
        <el-step title="写入" />
        <el-step title="完成" />
      </el-steps>

      <el-progress
        :percentage="percent"
        :status="progressStatus"
        :indeterminate="indeterminate"
        :stroke-width="14"
      />
      <div class="report-line report-line--primary">{{ phaseText }}</div>
      <div v-if="processedText" class="report-line">{{ processedText }}</div>
      <div v-if="job.elapsed_sec != null" class="report-line report-line--muted">
        已用 {{ fmtDuration(job.elapsed_sec) }}
      </div>

      <el-alert
        v-if="job.error"
        :title="job.error"
        type="error"
        :closable="false"
        show-icon
        class="report-alert"
      />
      <el-alert
        v-else-if="job.status === 'done'"
        type="success"
        :closable="false"
        show-icon
        class="report-alert"
      >
        <template #title>
          完成：共处理 {{ job.total }}，入库 {{ job.ingested }}，剔除 {{ droppedTotal }}
        </template>
      </el-alert>

      <el-descriptions
        v-if="job.status === 'done'"
        :column="2"
        border
        size="small"
        class="report-desc"
      >
        <el-descriptions-item label="入库图片">{{ job.ingested ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="分辨率过低">{{ job.dropped_small ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="画面模糊">{{ job.dropped_blur ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="近重复">{{ job.dropped_duplicate ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="过暗/黑帧">{{ job.dropped_dark ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="过曝/白帧">{{ job.dropped_bright ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="无法解码">
          {{ job.dropped_unreadable ?? 0 }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <template #footer>
      <template v-if="!job">
        <el-button @click="close">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">开始处理</el-button>
      </template>
      <template v-else>
        <el-button @click="close">关闭</el-button>
        <el-button v-if="job.status === 'done'" type="primary" @click="emitDone">
          查看数据集图片
        </el-button>
      </template>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";
import { ElMessage } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";

const visible = ref(false);
const submitting = ref(false);
const fileList = ref<any[]>([]);
const uploadRef = ref<any>();
const datasetId = ref<number | null>(null);
const job = ref<any>(null);
let pollTimer: number | null = null;

const form = reactive({
  source: "video" as "video" | "images",
  interval: 1,
  maxFrames: 0,
  sceneChange: false,
  sceneThreshold: 25,
  minSide: 320,
  blur: 30,
  brightnessMin: 20,
  brightnessMax: 240,
  phash: 6,
});

function onFileChange(_f: any, files: any[]) {
  fileList.value = files;
}
function onFileRemove(_f: any, files: any[]) {
  fileList.value = files;
}

function close() {
  stopPoll();
  visible.value = false;
  form.source = "video";
  fileList.value = [];
  job.value = null;
  uploadRef.value?.clearFiles?.();
}

function emitDone() {
  close();
}

function buildParams() {
  const clean = {
    min_side: form.minSide,
    blur: form.blur,
    brightness_min: form.brightnessMin,
    brightness_max: form.brightnessMax,
    phash: form.phash,
  };
  if (form.source === "video") {
    return {
      ...clean,
      interval: form.interval,
      max_frames: form.maxFrames,
      scene_change: form.sceneChange,
      scene_threshold: form.sceneThreshold,
    };
  }
  return clean;
}

async function submit() {
  if (!datasetId.value) {
    ElMessage.warning("缺少目标数据集");
    return;
  }
  if (fileList.value.length === 0) {
    ElMessage.warning("请先选择文件");
    return;
  }
  submitting.value = true;
  try {
    const files = fileList.value.map((f: any) => f.raw).filter(Boolean);
    const params = buildParams();
    let r: any;
    if (form.source === "video") {
      r = await AnnotationAPI.preprocessVideo(datasetId.value, files[0], params);
    } else {
      r = await AnnotationAPI.preprocessImages(datasetId.value, files, params);
    }
    const jobId = r.data?.data?.job_id;
    if (!jobId) throw new Error("未获取到任务ID");
    job.value = { job_id: jobId, status: "pending", phase: "", started_at: Date.now() / 1000 };
    startPoll();
  } catch (e: any) {
    ElMessage.error(e?.message || "提交失败");
  } finally {
    submitting.value = false;
  }
}

function startPoll() {
  stopPoll();
  pollTimer = window.setInterval(poll, 900);
  poll();
}
function stopPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}
async function poll() {
  const id = job.value?.job_id;
  if (!id) return;
  try {
    const r = await AnnotationAPI.getPreprocessJob(id);
    const d = r.data?.data;
    if (d) job.value = d;
    if (d && ["done", "failed"].includes(d.status)) stopPoll();
  } catch {
    /* 单次失败忽略 */
  }
}

function open(dsId: number, name: string) {
  datasetId.value = dsId;
  fileList.value = [];
  job.value = null;
  form.source = "video";
  visible.value = true;
  uploadRef.value?.clearFiles?.();
  void name;
}

defineExpose({ open });

const stepActive = computed(() => {
  const s = job.value?.status;
  if (s === "done") return 3;
  if (s === "running") return 2;
  if (s === "pending") return 1;
  return 1;
});
const percent = computed(() => {
  const j = job.value;
  if (!j) return 0;
  if (j.status === "done") return 100;
  if (j.status === "failed") return j.total ? Math.round((j.processed / j.total) * 100) : 0;
  return j.total ? Math.round((j.processed / j.total) * 100) : 0;
});
const indeterminate = computed(() => job.value?.status === "running" && !job.value?.total);
const progressStatus = computed<any>(() => {
  const s = job.value?.status;
  if (s === "done") return "success";
  if (s === "failed") return "exception";
  return "";
});
const phaseText = computed(() => {
  const j = job.value;
  if (!j) return "";
  if (j.status === "failed") return "处理失败";
  if (j.status === "done") return j.source === "video" ? "抽帧入库完成" : "清洗入库完成";
  if (j.phase === "extract") return "正在抽帧…";
  if (j.phase === "clean") return "正在清洗并入库…";
  return "处理中…";
});
const processedText = computed(() => {
  const j = job.value;
  if (!j) return "";
  if (j.status === "done") return `共处理 ${j.total ?? 0} 项，入库 ${j.ingested ?? 0} 张`;
  return `已处理 ${j.processed ?? 0} / ${j.total ?? 0}`;
});
const droppedTotal = computed(() => {
  const j = job.value;
  if (!j) return 0;
  return (
    (j.dropped_blur ?? 0) +
    (j.dropped_dark ?? 0) +
    (j.dropped_bright ?? 0) +
    (j.dropped_small ?? 0) +
    (j.dropped_duplicate ?? 0) +
    (j.dropped_unreadable ?? 0)
  );
});
function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
</script>

<style scoped>
.cfg-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
}
.cfg-grid--bright {
  margin-top: 8px;
}
.cfg-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.cfg-label {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
.cfg-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.steps {
  margin-bottom: 16px;
}
.report-line {
  margin-top: 10px;
  font-size: var(--el-font-size-base);
}
.report-line--primary {
  font-weight: 600;
}
.report-line--muted {
  color: var(--el-text-color-secondary);
}
.report-alert {
  margin-top: 12px;
}
.report-desc {
  margin-top: 16px;
}
</style>
