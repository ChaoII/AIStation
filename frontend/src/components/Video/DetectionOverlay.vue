<template>
  <canvas
    ref="canvasRef"
    class="detection-overlay"
    :width="width"
    :height="height"
    :style="{ width: width + 'px', height: height + 'px' }"
  />
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUnmount } from "vue";

interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Detection {
  label: string;
  confidence: number;
  bbox: BBox;
}

const props = withDefaults(
  defineProps<{
    detections: Detection[];
    width: number;
    height: number;
    detectRegion?: number[][];
  }>(),
  {
    detections: () => [],
    width: 640,
    height: 480,
  }
);

const canvasRef = ref<HTMLCanvasElement | null>(null);

const LABEL_COLORS: Record<string, string> = {
  person: "#F56C6C",
  car: "#409EFF",
  bicycle: "#67C23A",
  motorcycle: "#E6A23C",
  bus: "#909399",
  truck: "#B37FEB",
  fire: "#F56C6C",
  smoke: "#909399",
};

function getColor(label: string): string {
  return LABEL_COLORS[label] || "#409EFF";
}

function draw() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const w = props.width;
  const h = props.height;

  ctx.clearRect(0, 0, w, h);

  // Draw detect region
  if (props.detectRegion && props.detectRegion.length > 2) {
    ctx.beginPath();
    ctx.moveTo(props.detectRegion[0][0] * w, props.detectRegion[0][1] * h);
    for (let i = 1; i < props.detectRegion.length; i++) {
      ctx.lineTo(props.detectRegion[i][0] * w, props.detectRegion[i][1] * h);
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(64, 158, 255, 0.08)";
    ctx.fill();
    ctx.strokeStyle = "rgba(64, 158, 255, 0.4)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Draw detections
  for (const d of props.detections) {
    const { x, y, width: bw, height: bh } = d.bbox;
    const x1 = x * w;
    const y1 = y * h;
    const x2 = (x + bw) * w;
    const y2 = (y + bh) * h;
    const color = getColor(d.label);
    const confPct = Math.round(d.confidence * 100);

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

    const label = `${d.label} ${confPct}%`;
    ctx.font = "12px sans-serif";
    const tw = ctx.measureText(label).width;

    ctx.fillStyle = color;
    ctx.fillRect(x1, y1 - 18, tw + 6, 18);

    ctx.fillStyle = "#fff";
    ctx.fillText(label, x1 + 3, y1 - 4);
  }
}

watch(
  () => props.detections,
  () => {
    nextTick(draw);
  },
  { deep: true }
);

watch(
  () => [props.width, props.height],
  () => {
    nextTick(draw);
  }
);

onBeforeUnmount(() => {
  const canvas = canvasRef.value;
  if (canvas) {
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, props.width, props.height);
  }
});

defineExpose({ draw });
</script>

<style scoped>
.detection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 10;
  pointer-events: none;
}
</style>
