<template>
  <div class="cuboid-panel">
    <div class="hint">
      选中 3D 框后：拖四角改底面平行四边形、拖蓝点调高度、拖弧线手柄改航向角、拖底面内部移动整体。
    </div>

    <el-form v-if="!cuboid" label-width="76px" size="small">
      <el-form-item label="提示">
        <span class="text-secondary">先在画布上画一个 3D 框</span>
      </el-form-item>
    </el-form>

    <template v-else>
      <!-- 画布侧（2D 投影）：只读，因为它是「投影」而非真值 -->
      <el-form label-width="76px" size="small" class="proj-form">
        <div class="section-title">画布投影（只读）</div>
        <el-form-item label="投影高度">
          <span class="text-regular">{{ heightText }}</span>
        </el-form-item>
        <el-form-item label="底面朝向">
          <span class="text-regular">{{ formatAngle(angle1) }} / {{ formatAngle(angle2) }}</span>
        </el-form-item>      </el-form>

      <el-divider />

      <!-- 米制 3D 框：训练真值，可编辑 -->
      <el-form label-width="76px" size="small" class="box3d-form">
        <div class="section-title">
          3D 参数（米 · 相机系）
          <el-tag v-if="!has3d" size="small" type="info">缺省值</el-tag>
        </div>
        <div class="coord-hint">
          相机系：x 右 / y 下 / z 前。z 是底面中心的**前向距离（深度）**。
        </div>

        <el-form-item label="深度 z">
          <el-input-number
            v-model="box.z"
            :min="0.1"
            :max="500"
            :step="0.5"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('z')"
          />
        </el-form-item>
        <el-form-item label="横向 x">
          <el-input-number
            v-model="box.x"
            :step="0.1"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('x')"
          />
        </el-form-item>
        <el-form-item label="纵向 y">
          <el-input-number
            v-model="box.y"
            :step="0.1"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('y')"
          />
        </el-form-item>
        <el-form-item label="长 l">
          <el-input-number
            v-model="box.l"
            :min="0.05"
            :step="0.1"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('l')"
          />
        </el-form-item>
        <el-form-item label="宽 w">
          <el-input-number
            v-model="box.w"
            :min="0.05"
            :step="0.1"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('w')"
          />
        </el-form-item>
        <el-form-item label="高 h">
          <el-input-number
            v-model="box.h"
            :min="0.05"
            :step="0.1"
            :precision="2"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('h')"
          />
        </el-form-item>
        <el-form-item label="航向角 ry">
          <el-input-number
            v-model="box.ry"
            :min="-Math.PI"
            :max="Math.PI"
            :step="0.05"
            :precision="3"
            controls-position="right"
            style="width: 100%"
            @change="onFieldChange('ry')"
          />
        </el-form-item>

        <div class="actions">
          <el-button size="small" @click="syncFromQuad">按画布底面推算 x / y</el-button>
          <el-button size="small" @click="alignRyWithQuad">用底面朝向对齐 ry</el-button>
          <el-button size="small" type="primary" plain @click="applyToCanvas">写回画布投影</el-button>
        </div>
        <div class="coord-hint">「写回画布投影」会用 3D 参数重新投影底面四边形，让画布与数值保持一致。</div>

        <el-collapse :model-value="['out']">
          <el-collapse-item name="out" title="导出给 TorchKiln 时（LiDAR 系 · 米）">
            <div class="export-row">
              <code>{{ exportText }}</code>
            </div>
            <div class="coord-hint">
              相机系 x右/y下/z前 → LiDAR 系 x前/y左/z上，并把底面**抬升半个身高**成中心
              （TorchKiln 要的是框中心）。航向角随换轴改为 ry − π/2。
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { Annotation, Box3DMeters, PluginPanelContext } from "../../core/types";
import {
  box3dToLidar,
  defaultBox3D,
  deriveXYFromQuad,
  getBox3D,
  hasBox3D,
  projectBottomCorners,
  validateBox3D,
  wrapAngle,
} from "./box3d";

const props = defineProps<{ ctx: PluginPanelContext }>();

const heightText = ref("0%");
const cuboid = ref<Annotation | null>(null);
const has3d = ref(false);
/** 面板的可编辑副本；改动经 onFieldChange 提交回标注 */
const box = reactive<Box3DMeters>({ ...defaultBox3D() });

function selectedCuboid(): Annotation | null {
  const cands = (props.ctx.annotations ?? []).filter((a) => a.type === "Cuboid");
  if (cands.length === 0) return null;
  const selId = props.ctx.selectedAnnotationId;
  if (selId) {
    const hit = cands.find((a) => a.id === selId);
    if (hit) return hit;
  }
  const sel = props.ctx.selectedClassId;
  const cls = cands.filter((a) => a.class_id === sel);
  return cls[cls.length - 1] ?? cands[cands.length - 1];
}

function classNameOf(a: Annotation): string {
  const list = props.ctx.classes ?? [];
  const hit = list.find((c: any) => c.id === a.class_id);
  return String(hit?.name ?? "");
}

function formatAngle(rad: number): string {
  const deg = (rad * 180) / Math.PI;
  return `${deg.toFixed(1)}°`;
}

/** 底面两条边的方向角（弧度）。它们是 CuboidShape 上的可选字段，不在 Annotation 联合类型里。 */
const angle1 = computed(() => {
  const c = cuboid.value as any;
  return Number(c?.angle1 ?? c?.yaw ?? 0);
});
const angle2 = computed(() => {
  const c = cuboid.value as any;
  const a1 = Number(c?.angle1 ?? c?.yaw ?? 0);
  return Number(c?.angle2 ?? a1 + Math.PI / 2);
});

/** 导出给 TorchKiln 的实际数值（核对用；类 id 由后端按 names 顺序填，这里占位） */
const exportText = computed(() => {
  const v = box3dToLidar(box);
  return `x=${v[0].toFixed(2)}  y=${v[1].toFixed(2)}  z=${v[2].toFixed(2)}  ` +
    `l=${v[3].toFixed(2)}  w=${v[4].toFixed(2)}  h=${v[5].toFixed(2)}  yaw=${v[6].toFixed(3)}`;
});

function refresh() {
  const cub = selectedCuboid();
  cuboid.value = cub;
  if (!cub) return;
  heightText.value = `${Math.round((cub.depth ?? 0) * 100)}%`;
  has3d.value = hasBox3D(cub);
  const b = getBox3D(cub);
  Object.assign(box, b);
}

/** 提交：整体替换 box3d 字段，走 ctx.update（自带 shallowEqual 守卫 + 撤销历史） */
function commitBox3D() {
  const cub = cuboid.value;
  if (!cub || !props.ctx.update) return;
  const errs = validateBox3D(box);
  if (errs.length) {
    ElMessage.warning(errs[0]);
    refresh(); // 回滚到合法值，避免面板停在一个非法状态
    return;
  }
  props.ctx.update({ ...cub, box3d: { ...box, ry: wrapAngle(box.ry) } } as Annotation);
  has3d.value = true;
}

function onFieldChange(_k: keyof Box3DMeters) {
  commitBox3D();
}

/** 由画布底面（归一化）与已知深度反推相机系 x/y */
function syncFromQuad() {
  const cub = cuboid.value;
  if (!cub) return;
  const iw = props.ctx.imageWidth;
  if (!iw) {
    ElMessage.warning("拿不到图像尺寸，无法推算");
    return;
  }
  const { x, y } = deriveXYFromQuad(cub, iw, props.ctx.imageHeight ?? iw, box.z);
  box.x = x;
  box.y = y;
  commitBox3D();
}

/** 用底面第一条边的方向角作为航向角（相机系下 ry 是绕 y 轴，需换算） */
function alignRyWithQuad() {
  const cub = cuboid.value;
  if (!cub) return;
  const a1 = (cub as any).angle1 ?? (cub as any).yaw ?? 0;
  // 底面第一条边的图像方向角 → 相机系航向角：图像 y 向下、相机 y 向下，
  // 而相机航向角绕 y 轴、车头为 +z 前方，故取 atan2(dy, dx) 后减 π/2
  box.ry = wrapAngle(Math.atan2(Math.sin(a1), Math.cos(a1)) - Math.PI / 2);
  commitBox3D();
}

/** 用 3D 参数重新投影底面，把画布拉回与数值一致 */
function applyToCanvas() {
  const cub = cuboid.value;
  if (!cub || !props.ctx.update) return;
  const iw = props.ctx.imageWidth;
  if (!iw) {
    ElMessage.warning("拿不到图像尺寸，无法投影");
    return;
  }
  const ih = props.ctx.imageHeight ?? iw;
  const pts = projectBottomCorners(box, iw, ih);
  // 投影回 (cx, cy, w, h, angle1, angle2)：长边沿 angle1、短边沿 angle2+π/2
  const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
  const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
  const dx = pts[1].x - pts[0].x;
  const dy = pts[1].y - pts[0].y;
  const angle1 = Math.atan2(dy * ih, dx * iw); // 像素空间求角，避免各向异性
  const ex = pts[3].x - pts[0].x;
  const ey = pts[3].y - pts[0].y;
  const angle2 = Math.atan2(ey * ih, ex * iw);
  const lenPx = Math.hypot(dx * iw, dy * ih);
  const widPx = Math.hypot(ex * iw, ey * ih);
  // 顶面高度随 3D 高变化：按焦距把米制高度换算成画布上的竖直偏移
  const f = 0.9 * iw;
  const topCy = Math.min(1, (box.h * f) / (Math.max(box.z, 0.1) * ih));
  // ⚠️ 只调一次 update：调两次会推两条撤销历史，用户按一次撤销回不去
  props.ctx.update({
    ...cub,
    cx,
    cy,
    w: lenPx / iw,
    h: widPx / ih,
    angle1,
    angle2,
    yaw: angle1,
    top_cy: topCy,
    depth: topCy,
  } as Annotation);
  ElMessage.success("已按 3D 参数重投影底面");
}

watch(
  () => [props.ctx.annotations, props.ctx.selectedAnnotationId],
  () => refresh(),
  { deep: true }
);

onMounted(() => refresh());
</script>

<style scoped>
.cuboid-panel .hint {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.cuboid-panel .section-title {
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 600;
}
.cuboid-panel .coord-hint {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.cuboid-panel .text-regular {
  color: var(--el-text-color-regular);
}
.cuboid-panel .text-secondary {
  color: var(--el-text-color-secondary);
}
.cuboid-panel .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.cuboid-panel :deep(.el-divider) {
  margin: 8px 0;
}
</style>
