<template>
  <div
    ref="rootRef"
    class="snapshot-overlay"
    data-testid="snapshot-overlay"
    :data-box-count="String(objects.length)"
    :data-image-loaded="imageLoaded ? 'true' : 'false'"
  >
    <div class="snapshot-overlay__toolbar">
      <span class="snapshot-overlay__title">快照叠加</span>
      <div class="snapshot-overlay__actions">
        <el-button size="small" :disabled="!imageLoaded" @click="resetView">重置</el-button>
        <el-dropdown trigger="click" @command="handleDownload">
          <el-button size="small" :disabled="!imageLoaded">
            下载
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="original">下载原图</el-dropdown-item>
              <el-dropdown-item command="overlay">下载叠加图（PNG）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div
      ref="stageWrapRef"
      class="snapshot-overlay__stage"
      :style="{ height }"
      @mouseleave="hoveredIndex = -1"
    >
      <Stage
        ref="stageRef"
        :config="stageConfig"
        @wheel="onWheel"
        @dragmove="onDragMove"
        @dragend="onDragMove"
      >
        <!-- 底层：占位 + 等比 contain（letterbox）的底图，不响应指针事件 -->
        <Layer :listening="false">
          <Rect :config="placeholderConfig" />
          <KonvaImage v-if="bgImage" :config="imageConfig" />
        </Layer>
        <!-- 叠加层：与底图共用同一缩放/平移变换 -->
        <Layer>
          <template v-for="box in boxes" :key="box.key">
            <Rect
              :config="box.rect"
              @mouseenter="hoveredIndex = box.index"
              @mouseleave="hoveredIndex = -1"
            />
          </template>
          <template v-for="box in boxes" :key="`meta-${box.key}`">
            <Rect v-if="box.labelBg" :config="box.labelBg" :listening="false" />
            <Text :config="box.labelText" :listening="false" />
            <Rect v-if="box.trackBg" :config="box.trackBg" :listening="false" />
            <Text v-if="box.trackText" :config="box.trackText" :listening="false" />
            <template v-for="(line, li) in box.attrLines" :key="li">
              <Rect :config="line.bg" :listening="false" />
              <Text :config="line.text" :listening="false" />
            </template>
          </template>
        </Layer>
      </Stage>

      <!-- 加载中 / 失败占位与错误文案（HTML 层，便于无障碍与断言） -->
      <div v-if="!imageLoaded" class="snapshot-overlay__placeholder">
        {{ errorText || "快照加载中…" }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Image as KonvaImage, Layer, Rect, Stage, Text } from "vue-konva";
import { ArrowDown } from "@element-plus/icons-vue";
import type { KonvaEventObject } from "konva/lib/Node";
import request from "@/utils/request";

/** 归一化检测框（0~1） */
export interface SnapshotOverlayBBox {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  [key: string]: unknown;
}

/** 单个叠加对象（对齐后端 v2 `objects`，兼容旧 `detections`） */
export interface SnapshotOverlayObject {
  label?: string;
  confidence?: number;
  bbox?: SnapshotOverlayBBox;
  attributes?: Record<string, unknown>;
  text?: string;
  track_id?: number | string | null;
  [key: string]: unknown;
}

const props = withDefaults(
  defineProps<{
    /** 快照 URL（相对路径或 http(s) 绝对地址），可空 */
    src?: string | null;
    /** 叠加对象（归一化坐标） */
    objects?: SnapshotOverlayObject[];
    /** label → 颜色映射；缺省按 label 哈希取色 */
    labelColors?: Record<string, string>;
    /** 舞台容器高度（CSS 值），默认 480px */
    height?: string;
  }>(),
  {
    src: null,
    objects: () => [],
    labelColors: () => ({}),
    height: "480px",
  }
);

/** 画布单位字号：随 Konva 缩放自动放大，不随 CSS 像素变化 */
const LABEL_FONT_RATIO = 0.035;
const ATTR_FONT_RATIO = 0.028;
const ATTR_LINE_GAP = 2;
/** 属性小字最多渲染行数（避免长属性列表淹没画面） */
const MAX_ATTR_LINES = 10;
/** 超过该框数时降级：只画框与标签，跳过属性小字 */
const PERF_BOX_LIMIT = 200;
const FONT_FAMILY = "Microsoft YaHei, Arial, sans-serif";

const rootRef = ref<HTMLElement | null>(null);
const stageWrapRef = ref<HTMLElement | null>(null);
const stageRef = ref<any>(null);

const stageW = ref(640);
const stageH = ref(360);
const scale = ref(1);
const posX = ref(0);
const posY = ref(0);
const hoveredIndex = ref(-1);

const bgImage = ref<HTMLImageElement | null>(null);
const imageLoaded = ref(false);
const errorText = ref("");

let objectUrl: string | null = null;
let resizeObserver: ResizeObserver | null = null;
let loadSeq = 0;
let disposed = false;

const num = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

/** 解析 height 属性为像素值（非法值回退 360） */
function parseHeight(): number {
  const parsed = Number.parseFloat(props.height);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 360;
}

/** 容器尺寸自适应：观测外层包裹容器（Konva 撑大的元素不能观测，否则自反馈锁定） */
function applySize() {
  const el = stageWrapRef.value ?? rootRef.value;
  const width = el?.clientWidth || 640;
  const height = el?.clientHeight || parseHeight();
  stageW.value = Math.max(240, Math.floor(width));
  stageH.value = Math.max(180, Math.floor(height));
}

/**
 * 归一化快照 URL → 交给 request 的相对路径。
 * 后端返回的 `snapshot_url` 自带 `/api/v1` 前缀，而 request 的 baseURL 也含该前缀，需剥离避免重复。
 */
function toRequestUrl(src: string): string {
  if (/^https?:\/\//i.test(src)) return src;
  const base = import.meta.env.VITE_APP_BASE_API || "";
  if (base && src.startsWith(`${base}/`)) return src.slice(base.length);
  return src;
}

/** 解析 bbox：支持 `{x,y,width,height}` 与 `[x,y,width,height]` 两种形态 */
function readBBox(bbox: unknown) {
  if (!bbox) return null;
  if (Array.isArray(bbox) && bbox.length >= 4) {
    return {
      x: num(bbox[0]),
      y: num(bbox[1]),
      width: num(bbox[2]),
      height: num(bbox[3]),
    };
  }
  if (typeof bbox === "object") {
    const box = bbox as SnapshotOverlayBBox;
    return { x: num(box.x), y: num(box.y), width: num(box.width), height: num(box.height) };
  }
  return null;
}

/** label 哈希取色（同 label 恒定），hue 落在 0~359 */
function hashColor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i += 1) {
    hash = (hash * 31 + label.charCodeAt(i)) % 360;
  }
  return `hsl(${hash}, 68%, 52%)`;
}

function resolveColor(label: string, index: number): string {
  const mapped = props.labelColors?.[label];
  if (mapped) return mapped;
  if (!label) return `hsl(${(index * 67) % 360}, 68%, 52%)`;
  return hashColor(label);
}

/** 颜色转半透明（hex / hsl 支持，其余回退中性白） */
function toTranslucent(color: string, alpha: number): string {
  const value = color.trim();
  const short = /^#([0-9a-f]{3})$/i.exec(value);
  if (short) {
    const [r, g, b] = short[1].split("").map((c) => Number.parseInt(c + c, 16));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const full = /^#([0-9a-f]{6})$/i.exec(value);
  if (full) {
    const int = Number.parseInt(full[1], 16);
    const r = (int >> 16) & 255;
    const g = (int >> 8) & 255;
    const b = int & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  if (value.startsWith("hsl(")) return `hsla(${value.slice(4, -1)}, ${alpha})`;
  return "rgba(255, 255, 255, 0.16)";
}

/** 估算文字宽度（CJK 记 1 字宽，其余记 0.58），用于标签/属性背景框 */
function estimateTextWidth(text: string, fontSize: number): number {
  let units = 0;
  for (const char of text) {
    units += /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/.test(char) ? 1 : 0.58;
  }
  return Math.max(fontSize * 0.6, units * fontSize);
}

function truncate(text: string, max = 40): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 属性值格式化：数字保留两位（整数原样），对象 JSON 化并截断 */
function formatAttrValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") {
    try {
      return truncate(JSON.stringify(value));
    } catch {
      return String(value);
    }
  }
  return truncate(String(value));
}

/** 底图 letterbox 显示区域（与 RoiCanvas 同一套 contain 公式） */
const frame = computed(() => {
  const img = bgImage.value;
  if (!img || !img.naturalWidth || !img.naturalHeight) {
    return { x: 0, y: 0, width: stageW.value, height: stageH.value };
  }
  const ratio = Math.min(stageW.value / img.naturalWidth, stageH.value / img.naturalHeight);
  const width = img.naturalWidth * ratio;
  const height = img.naturalHeight * ratio;
  return { x: (stageW.value - width) / 2, y: (stageH.value - height) / 2, width, height };
});

const labelFontSize = computed(() => Math.max(12, Math.round(stageH.value * LABEL_FONT_RATIO)));
const attrFontSize = computed(() => Math.max(10, Math.round(stageH.value * ATTR_FONT_RATIO)));
const attrLineHeight = computed(() => attrFontSize.value + 4);

const stageConfig = computed(() => ({
  width: stageW.value,
  height: stageH.value,
  scaleX: scale.value,
  scaleY: scale.value,
  x: posX.value,
  y: posY.value,
  draggable: true,
}));

const placeholderConfig = computed(() => ({
  x: 0,
  y: 0,
  width: stageW.value,
  height: stageH.value,
  fill: "#f5f7fa",
  listening: false,
}));

const imageConfig = computed(() => ({
  image: bgImage.value,
  x: frame.value.x,
  y: frame.value.y,
  width: frame.value.width,
  height: frame.value.height,
  listening: false,
}));

interface AttrLine {
  bg: Record<string, unknown>;
  text: Record<string, unknown>;
}

interface BoxLayout {
  key: string;
  index: number;
  rect: Record<string, unknown>;
  labelBg: Record<string, unknown> | null;
  labelText: Record<string, unknown>;
  trackBg: Record<string, unknown> | null;
  trackText: Record<string, unknown> | null;
  attrLines: AttrLine[];
}

/** 叠加元素布局：框、标签、属性小字、track_id 徽标 */
const boxes = computed<BoxLayout[]>(() => {
  const f = frame.value;
  const labelFont = labelFontSize.value;
  const attrFont = attrFontSize.value;
  const lineHeight = attrLineHeight.value;
  const showAttrs = props.objects.length <= PERF_BOX_LIMIT;
  const layouts: BoxLayout[] = [];

  props.objects.forEach((obj, index) => {
    const bbox = readBBox(obj?.bbox);
    if (!bbox) return;
    const color = resolveColor(String(obj?.label ?? ""), index);
    const hovering = hoveredIndex.value === index;

    const left = f.x + bbox.x * f.width;
    const top = f.y + bbox.y * f.height;
    const width = Math.max(1, bbox.width * f.width);
    const height = Math.max(1, bbox.height * f.height);

    const boxHeight = labelFont + 4;
    const labelTop = top - boxHeight - 2 >= 0 ? top - boxHeight - 2 : top + 2;
    const labelTextValue = `${obj?.label ?? ""} ${num(obj?.confidence).toFixed(2)}`;
    const labelWidth = estimateTextWidth(labelTextValue, labelFont) + 6;

    const attrSource = obj?.attributes && typeof obj.attributes === "object" ? obj.attributes : {};
    const attrEntries = Object.entries(attrSource);
    const attrLines: AttrLine[] = [];
    if (showAttrs) {
      const lines: string[] = [];
      if (obj?.text !== undefined && obj?.text !== null && String(obj.text).trim()) {
        lines.push(`text=${truncate(String(obj.text))}`);
      }
      attrEntries.forEach(([key, value]) => {
        lines.push(`${key}=${formatAttrValue(value)}`);
      });
      lines.slice(0, MAX_ATTR_LINES).forEach((line, lineIndex) => {
        const lineWidth = estimateTextWidth(line, attrFont) + 6;
        const lineTop = top + height + 4 + lineIndex * (lineHeight + ATTR_LINE_GAP);
        attrLines.push({
          bg: {
            x: left,
            y: lineTop,
            width: lineWidth,
            height: lineHeight,
            fill: "rgba(0, 0, 0, 0.55)",
            cornerRadius: 2,
            listening: false,
          },
          text: {
            x: left + 3,
            y: lineTop,
            width: Math.max(lineWidth - 4, 0),
            height: lineHeight,
            text: line,
            fontSize: attrFont,
            fontFamily: FONT_FAMILY,
            fill: "#ffffff",
            verticalAlign: "middle",
            wrap: "none",
            listening: false,
          },
        });
      });
    }

    const trackId = obj?.track_id;
    const hasTrack = trackId !== undefined && trackId !== null && trackId !== "";
    const trackValue = hasTrack ? `#${trackId}` : "";
    const trackWidth = hasTrack ? estimateTextWidth(trackValue, labelFont) + 6 : 0;
    const trackLeft = Math.max(left, left + width - trackWidth);

    layouts.push({
      key: `${index}-${obj?.label ?? ""}-${trackValue}`,
      index,
      rect: {
        x: left,
        y: top,
        width,
        height,
        stroke: color,
        strokeWidth: hovering ? 4 : 2,
        fill: hovering ? toTranslucent(color, 0.18) : undefined,
        cornerRadius: 2,
      },
      labelBg: {
        x: left,
        y: labelTop,
        width: labelWidth,
        height: boxHeight,
        fill: color,
        cornerRadius: 2,
        listening: false,
      },
      labelText: {
        x: left + 3,
        y: labelTop,
        width: labelWidth,
        height: boxHeight,
        text: labelTextValue,
        fontSize: labelFont,
        fontFamily: FONT_FAMILY,
        fill: "#ffffff",
        verticalAlign: "middle",
        wrap: "none",
        listening: false,
      },
      trackBg: hasTrack
        ? {
            x: trackLeft,
            y: labelTop,
            width: trackWidth,
            height: boxHeight,
            fill: "rgba(0, 0, 0, 0.65)",
            cornerRadius: 2,
            listening: false,
          }
        : null,
      trackText: hasTrack
        ? {
            x: trackLeft + 3,
            y: labelTop,
            width: trackWidth,
            height: boxHeight,
            text: trackValue,
            fontSize: labelFont,
            fontFamily: FONT_FAMILY,
            fill: "#ffffff",
            verticalAlign: "middle",
            wrap: "none",
            listening: false,
          }
        : null,
      attrLines,
    });
  });

  return layouts;
});

function resetView() {
  scale.value = 1;
  posX.value = 0;
  posY.value = 0;
}

/** 同步拖拽后的位移（Konva 内部直接改 node，需要回写响应式值） */
function onDragMove(e: KonvaEventObject<DragEvent>) {
  posX.value = e.target.x();
  posY.value = e.target.y();
}

/** 滚轮缩放：以指针所在画布点为锚，重算 stage 位移 */
function onWheel(e: KonvaEventObject<WheelEvent>) {
  e.evt.preventDefault();
  const stage = stageRef.value?.getNode?.();
  const pointer = stage?.getPointerPosition?.();
  if (!pointer) return;
  const oldScale = scale.value;
  const factor = e.evt.deltaY > 0 ? 1 / 1.15 : 1.15;
  const nextScale = Math.min(8, Math.max(0.2, oldScale * factor));
  const anchor = {
    x: (pointer.x - posX.value) / oldScale,
    y: (pointer.y - posY.value) / oldScale,
  };
  scale.value = nextScale;
  posX.value = pointer.x - anchor.x * nextScale;
  posY.value = pointer.y - anchor.y * nextScale;
}

function releaseObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

function decodeImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new window.Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片解码失败"));
    img.src = url;
  });
}

/** 鉴权取图：request blob → objectURL → Image 解码 */
async function loadSnapshot(rawSrc: string | null | undefined) {
  const seq = (loadSeq += 1);
  releaseObjectUrl();
  bgImage.value = null;
  imageLoaded.value = false;
  errorText.value = "";
  resetView();

  const src = (rawSrc ?? "").trim();
  if (!src) {
    errorText.value = "暂无快照";
    return;
  }

  try {
    const res = await request<Blob>({
      url: toRequestUrl(src),
      method: "get",
      responseType: "blob",
    });
    if (seq !== loadSeq || disposed) return;
    const blob = res.data;
    if (!(blob instanceof Blob) || blob.size === 0) throw new Error("空快照");
    const localUrl = URL.createObjectURL(blob);
    const img = await decodeImage(localUrl);
    if (seq !== loadSeq || disposed) {
      URL.revokeObjectURL(localUrl);
      return;
    }
    objectUrl = localUrl;
    bgImage.value = img;
    imageLoaded.value = true;
    await nextTick();
    applySize();
  } catch {
    if (seq === loadSeq && !disposed) {
      errorText.value = "快照加载失败";
      imageLoaded.value = false;
    }
  }
}

function triggerDownload(url: string, filename: string, revoke: boolean) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  if (revoke) window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** 下载：① 原图（重新鉴权取 blob）② 含叠加 PNG（stage.toDataURL） */
async function handleDownload(command: string | number | object) {
  if (!imageLoaded.value || !props.src) return;
  if (command === "overlay") {
    const stage = stageRef.value?.getNode?.();
    if (!stage) return;
    triggerDownload(stage.toDataURL({ pixelRatio: 2 }), "snapshot-overlay.png", false);
    return;
  }
  try {
    const res = await request<Blob>({
      url: toRequestUrl(props.src),
      method: "get",
      responseType: "blob",
    });
    const blob = res.data;
    if (!(blob instanceof Blob)) throw new Error("空快照");
    const ext = (blob.type.split("/")[1] || "jpg").replace("jpeg", "jpg");
    triggerDownload(URL.createObjectURL(blob), `snapshot.${ext}`, true);
  } catch {
    ElMessage.error("原图下载失败");
  }
}

watch(
  () => props.src,
  (value) => {
    void loadSnapshot(value);
  },
  { immediate: true }
);

watch(
  () => props.height,
  () => applySize()
);

onMounted(() => {
  applySize();
  const el = rootRef.value;
  if (!el) return;
  resizeObserver = new ResizeObserver(() => applySize());
  resizeObserver.observe(el);
});

onBeforeUnmount(() => {
  disposed = true;
  resizeObserver?.disconnect();
  resizeObserver = null;
  releaseObjectUrl();
});
</script>

<style scoped>
.snapshot-overlay {
  /* 允许在 flex 容器中收缩，避免被 Konva 舞台撑宽 */
  min-width: 0;
}

.snapshot-overlay__toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.snapshot-overlay__title {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.snapshot-overlay__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.snapshot-overlay__stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  cursor: grab;
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
}

.snapshot-overlay__placeholder {
  position: absolute;
  top: 50%;
  left: 50%;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  pointer-events: none;
  transform: translate(-50%, -50%);
}
</style>
