/**
 * cuboid 的米制 3D 参数：坐标系约定、缺省值、投影、导出格式转换。
 *
 * ## 坐标系（两套，别搞混）
 *
 * **相机系**（KITTI `label_2` 惯例，本平台**标注与存储**用这套）
 *   x 右 / y 下 / z 前（沿光轴）。`ry` 是 KITTI 的 `rotation_y`：车长轴在相机
 *   (x, z) 平面内的方向为 `(cos ry, 0, -sin ry)`——即 `ry = 0` 时车头朝**画面右方**，
 *   `ry = π/2` 时朝**正前方**。
 *
 * **LiDAR / ego 系**（TorchKiln `det3d` / `mono3d` 用这套）
 *   x 前 / y 左 / z 上；`yaw` 是绕 **z 轴**的航向角（`rbox2poly_np` 里 `l` 沿
 *   `(cos yaw, sin yaw)`）；`z` 是**框中心**而非底面。
 *
 * ## 航向角的换算：直接沿用 TorchKiln 的公式
 *
 * ```
 *   x_lidar =  z_cam            （前）
 *   y_lidar = -x_cam            （左）
 *   z_lidar = -y_cam + h/2      （上；且相机系存的是**底面**，要抬 h/2 成中心）
 *   yaw      =  ry_cam + π/2
 * ```
 *
 * ⚠️ 最后一条**照抄** `torchkiln/tools/convert/kitti_to_det3d.py:59`
 * （`yaw = ry + np.pi / 2.0`）。这里刻意**不做"几何修正"**：该文件注释里那套
 * 角度推导与 KITTI devkit `compute_box_3d` 的实际约定并不自洽，若在这里自作聪明
 * 改成 `-ry - π/2`，就会与 TorchKiln 自己的 KITTI 转换器产生固定的朝向偏差——
 * 而 TorchKiln 的评估/后处理都按它那套写。**双方共用一个约定**比"各自正确"更重要。
 * 回归验证见 `torchkiln/service/_yaw_convention_probe.py`。
 *
 * ## z 是中心还是底面
 *
 * 相机系（KITTI）存的是**底面中心**；TorchKiln 要的是**框中心**，所以必须抬 `h/2`。
 * 这一步极容易漏——漏了框会整体下沉半个身高，训练照跑但指标上不去。
 */
import type { Annotation, Box3DMeters } from "@/annotation/core/types";

/** 缺省 3D 框：底面中心在相机前 8m、略偏左，车级尺寸。 */
export const DEFAULT_BOX3D: Box3DMeters = {
  x: 0,
  y: -1.5,
  z: 8,
  l: 4.5,
  w: 1.8,
  h: 1.6,
  ry: 0,
};

/** 各类别的缺省尺寸（米）。按常见类别给，未命中用 `DEFAULT_BOX3D`。 */
const CLASS_SIZE_HINTS: Record<string, { l: number; w: number; h: number }> = {
  car: { l: 4.5, w: 1.8, h: 1.6 },
  van: { l: 5.4, w: 2.0, h: 2.2 },
  truck: { l: 9.0, w: 2.6, h: 3.2 },
  bus: { l: 11.0, w: 2.6, h: 3.2 },
  ped: { l: 0.7, w: 0.7, h: 1.75 },
  pedestrian: { l: 0.7, w: 0.7, h: 1.75 },
  cyc: { l: 1.7, w: 0.7, h: 1.6 },
  cyclist: { l: 1.7, w: 0.7, h: 1.6 },
};

export function defaultBox3D(className?: string): Box3DMeters {
  const key = (className || "").trim().toLowerCase();
  const hint = CLASS_SIZE_HINTS[key];
  return hint ? { ...DEFAULT_BOX3D, ...hint } : { ...DEFAULT_BOX3D };
}

/** 取标注上的 box3d；缺失时按 `nullOnMissing=false` 返回一份缺省值。 */
export function getBox3D(ann: Annotation): Box3DMeters {
  const b = (ann as { box3d?: Partial<Box3DMeters> }).box3d;
  if (!b) return { ...DEFAULT_BOX3D };
  return {
    x: num(b.x, DEFAULT_BOX3D.x),
    y: num(b.y, DEFAULT_BOX3D.y),
    z: num(b.z, DEFAULT_BOX3D.z),
    l: num(b.l, DEFAULT_BOX3D.l),
    w: num(b.w, DEFAULT_BOX3D.w),
    h: num(b.h, DEFAULT_BOX3D.h),
    ry: num(b.ry, DEFAULT_BOX3D.ry),
  };
}

export function hasBox3D(ann: Annotation): boolean {
  return !!(ann as { box3d?: unknown }).box3d;
}

function num(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

/**
 * 相机系 → LiDAR/ego 系，返回 TorchKiln 的 `[x, y, z, l, w, h, yaw]`（7 元素）。
 *
 * 已把「底面 → 中心」的抬升做掉，导出侧不需要再处理。
 */
export function box3dToLidar(b: Box3DMeters): number[] {
  const x = b.z; // 前
  const y = -b.x; // 左
  // 相机系 y 向下为正，LiDAR z 向上为正；且相机系存的是底面，要抬 h/2 才是中心
  const z = -b.y + b.h / 2;
  // 照抄 TorchKiln 的 KITTI 转换公式（见文件头注释，不要改成"几何修正版"）
  const yaw = b.ry + Math.PI / 2;
  return [x, y, z, b.l, b.w, b.h, yaw];
}

/**
 * LiDAR/ego 系 7 元素 → 相机系（`box3dToLidar` 的逆，供调试与校验用）。
 *
 * ⚠️ 两个易错点：
 *  - y 的逆变换：由 `z_lidar = -y_cam + h/2` 解出的是 `y_cam = h/2 - z_lidar`，
 *    **不是** `-(z_lidar + h/2)`——后者会把高度算重。
 *  - yaw 的逆变换：由 `yaw = ry + π/2` 解出 `ry = yaw - π/2`。
 */
export function lidarToBox3D(v: number[]): Box3DMeters {
  const [x, y, z, l, w, h, yaw] = v;
  return {
    x: -y,
    y: h / 2 - z, // 中心 → 底面
    z: x,
    l,
    w,
    h,
    ry: yaw - Math.PI / 2,
  };
}

/** 把角度规整到 (-π, π]，避免 ry 累加后跑出大数值。 */
export function wrapAngle(a: number): number {
  let r = a % (2 * Math.PI);
  if (r <= -Math.PI) r += 2 * Math.PI;
  if (r > Math.PI) r -= 2 * Math.PI;
  return r;
}

/**
 * 由 3D 框（相机系）投影出底面四边形的**归一化图像坐标**。
 *
 * 需要相机内参；本项目**没有内参管理**，所以用「焦距 ≈ 0.9×图宽」的针孔近似，
 * 光轴过图心。用途仅限画布上把 3D 框的投影与 2D 底面对齐（给人看），
 * **不参与训练真值**——真值永远是 `box3d` 本身。
 *
 * @param b 相机系 3D 框
 * @param imgW 图像宽（像素）
 * @param imgH 图像高（像素）
 * @param f 焦距（像素），默认 0.9×imgW
 */
export function projectBottomCorners(
  b: Box3DMeters,
  imgW: number,
  imgH: number,
  f?: number
): { x: number; y: number }[] {
  const fx = f ?? 0.9 * imgW;
  const cx = imgW / 2;
  const cy = imgH / 2;
  const hl = b.l / 2;
  const hw = b.w / 2;
  // 相机系：航向角绕 y 轴。车长轴在 x-z 平面内，与图像 x 轴的夹角为 ry。
  const c = Math.cos(b.ry);
  const s = Math.sin(b.ry);
  // 车长方向单位向量（在 x-z 平面）与车宽方向（沿 y）
  const fx1 = c;
  const fz1 = -s; // ry 增大时车头朝更远处
  const local: [number, number, number][] = [
    [-hl, -hw, 0],
    [hl, -hw, 0],
    [hl, hw, 0],
    [-hl, hw, 0],
  ];
  return local.map(([lx, ly]) => {
    const X = b.x + lx * fx1;
    const Y = b.y + ly;
    const Z = b.z + lx * fz1;
    const zc = Math.max(Z, 1e-3); // 深度为负/零时钳住，避免除零
    return { x: (cx + (fx * X) / zc) / imgW, y: (cy + (fx * Y) / zc) / imgH };
  });
}

/**
 * 由 2D 底面 + 已知的 3D 深度，反推相机系的 x/y（米）。
 *
 * 用途：标注者在画布上拖出底面后，只要填一个深度 z，横纵向位置就能自动算出来，
 * 不用手敲 x/y。仍属**辅助**——最终真值仍以面板里确认的 `box3d` 为准。
 *
 * @param ann 标注（提供归一化的 cx/cy 与画布像素尺寸）
 * @param z 深度（米）
 */
export function deriveXYFromQuad(
  ann: Annotation,
  imgW: number,
  imgH: number,
  z: number
): { x: number; y: number } {
  const f = 0.9 * imgW;
  const zc = Math.max(z, 1e-3);
  return {
    x: (((ann.cx * imgW - imgW / 2) * zc) / f),
    y: (((ann.cy * imgH - imgH / 2) * zc) / f),
  };
}

/** 合理性校验；返回错误文案数组，空数组表示通过。 */
export function validateBox3D(b: Box3DMeters): string[] {
  const errs: string[] = [];
  if (!(b.z > 0)) errs.push("深度 z 必须为正数（相机前方）");
  for (const k of ["l", "w", "h"] as const) {
    if (!(b[k] > 0)) errs.push(`尺寸 ${k} 必须为正数`);
  }
  if (Math.abs(b.l) < 1e-6 || Math.abs(b.w) < 1e-6) errs.push("长宽不能为 0");
  if (!Number.isFinite(b.ry)) errs.push("航向角 ry 非法");
  return errs;
}
