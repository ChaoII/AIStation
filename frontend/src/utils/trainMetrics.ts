import {
  Aim,
  Collection,
  DataBoard,
  Search,
  StarFilled,
  TrendCharts,
  TrophyBase,
} from "@element-plus/icons-vue";
import type { Component } from "vue";

// 主指标卡片定义（训练详情与评估详情共用，避免两处 spec 漂移）
export interface MetricSpecItem {
  key: string;
  label: string;
  color: string;
  icon: Component;
}

// 0-1 比例指标 → 百分比；空值/非法值 → "—"
export function fmtRatio(v: any): string {
  return v != null && !isNaN(Number(v)) ? (Number(v) * 100).toFixed(1) + "%" : "—";
}

/* ============================================================================
 * 全量指标枚举（训练详情 / 评估详情共用）
 *
 * 起因：旧版指标清单是**按框架硬编码**的（resolveMainMetricSpec 返回固定的
 * map50/map5095/precision/recall），TorchKiln 分支更只返回 1 个主指标 ——
 * 于是页面上永远只有那几个，模型实际算出来的指标一律不显示。
 *
 * 指标本身是**随模型而变**的（YOLO 给 map50/recall/precision，TorchKiln 给
 * mAP50/mAP75/mAP50-95，回归给 RMSE），所以清单必须**从数据/模型接口枚举**。
 * ========================================================================== */

/** 簿记字段：存在于指标行里但**不是指标**，枚举时排除 */
const NON_METRIC_KEYS = new Set([
  "_kind",
  "seq",
  "epoch",
  "total_epochs",
  "global_step",
  "best",
  "main_indicator",
  "main_indicator_mode",
  "main_value",
  "exit_reason",
  "duration_sec",
  "timestamp",
  "date",
  "classes", // per-class 是嵌套 dict，单独用表格/柱状图展示，不进标量列表
]);

/** 指标名友好映射（没命中就原样用 key） */
const METRIC_LABEL: Record<string, string> = {
  map50: "mAP@50",
  map5095: "mAP@50:95",
  map50_95: "mAP@50:95",
  mAP50: "mAP@50",
  mAP75: "mAP@75",
  "mAP50-95": "mAP@50:95",
  precision: "Precision",
  recall: "Recall",
  hmean: "HMean",
  acc: "Acc",
  accuracy: "Acc",
  top1: "Top1",
  top5: "Top5",
  f1: "F1",
  iou: "IoU",
  loss: "Loss",
  lr: "LR",
  ips: "IPS",
  fps: "FPS",
  box_loss: "Box Loss",
  cls_loss: "Cls Loss",
  dfl_loss: "DFL Loss",
};

/** 数值缩放（键 → 换算），避免大整数直接铺满卡片 */
const METRIC_SCALE: Record<string, { div: number; label: string }> = {
  mem_reserved: { div: 1024 ** 3, label: "显存 (GB)" },
  mem: { div: 1024 ** 3, label: "显存 (GB)" },
};

/** 调色板：8 色，取色按 key 稳定散列 —— 同一指标在不同图/不同页颜色一致 */
const METRIC_COLORS = [
  "#409eff",
  "#67c23a",
  "#e6a23c",
  "#f56c6c",
  "#909399",
  "#9b59b6",
  "#13c2c2",
  "#fa8c16",
];

const ICON_POOL: Component[] = [
  TrendCharts,
  DataBoard,
  Aim,
  StarFilled,
  Collection,
  TrophyBase,
  Search,
];

/** 比例类指标名（0~1 → 百分比）；loss/lr/ips/fps/mem 之类不命中 */
const RATIO_KEY_RE = /^(map|ap|top|precision|recall|hmean|acc|iou|f1|auc)/i;

export function metricColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return METRIC_COLORS[h % METRIC_COLORS.length];
}

function metricIcon(key: string): Component {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 17 + key.charCodeAt(i)) >>> 0;
  return ICON_POOL[h % ICON_POOL.length];
}

export function metricLabel(key: string): string {
  return METRIC_LABEL[key] ?? key;
}

/**
 * 该指标的**显示值**（含换算，如 `mem_reserved` 字节 → GB）。
 *
 * ⚠️ 卡片和小图**必须用同一个换算**，否则曲线 y 轴是 3.4e9、卡片写着 3.17GB，
 *    同一张图两个量纲。
 */
export function metricDisplayValue(key: string, v: any): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (isNaN(n)) return null;
  const sc = METRIC_SCALE[key];
  return sc ? n / sc.div : n;
}

/**
 * 该指标的**换算除数**（无换算返回 1）。
 *
 * 图表内循环每格都要用它：5000 行 × 10 指标 = 5 万次，若在那里调
 * `metricDisplayValue` 就是 5 万次函数调用 + 5 万次 `METRIC_SCALE` 对象查表。
 * 调用方在循环**外**把这个除数取出来存进数组，循环内只做一次除法。
 */
export function metricScaleDiv(key: string): number {
  return METRIC_SCALE[key]?.div ?? 1;
}

/**
 * 指标值格式化。
 *
 * ⚠️ 不能一律用 `fmtRatio`：fps=85 会被显示成 "8500.0%"，loss=3.5 会成 "350%"。
 * 这里按**键名 + 数值区间**双条件判定：
 *   - 键名是比例类（map50/precision/…）且值在 [-0.5, 1.5] → 按 0~1 转百分比
 *   - 键名是比例类但值已 >1.5 且 ≤100 → 本来就是百分数，直接加 %
 *   - 其余 → 按量级给小数位（整数原样、大数少给位、小数给 4 位保真）
 */
export function fmtMetricValue(key: string, v: any): string {
  const n = metricDisplayValue(key, v);
  if (n == null) return v == null || v === "" ? "—" : String(v);
  // 做过换算的（字节→GB）不再套比例/大数规则
  if (METRIC_SCALE[key]) return n.toFixed(2);
  if (RATIO_KEY_RE.test(key)) {
    if (n >= -0.5 && n <= 1.5) return (n * 100).toFixed(1) + "%";
    if (n > 1.5 && n <= 100) return n.toFixed(1) + "%";
  }
  if (Number.isInteger(n)) return String(n);
  const abs = Math.abs(n);
  // 给足 4 位再**去掉尾零**：loss 要 3.3849 的精度，ips=20.5 却不该显示成 20.5000
  if (abs >= 1e6) return n.toExponential(3);
  if (abs >= 1000) return String(Number(n.toFixed(1)));
  return n.toFixed(4).replace(/\.?0+$/, "");
}

/**
 * 从一个 `metrics` JSONB 里提取**可展示的标量指标键**。
 *
 * 必须跳过嵌套结构：`classes` 是 `{类别: {precision, recall, ...}}`，
 * 直接当标量画会得到 NaN，卡片会显示 "NaN%"。
 */
export function scalarMetricKeys(metrics: any): string[] {
  if (!metrics || typeof metrics !== "object") return [];
  const out: string[] = [];
  for (const k of Object.keys(metrics)) {
    if (NON_METRIC_KEYS.has(k)) continue;
    const v = metrics[k];
    if (v == null) continue;
    if (typeof v === "number") out.push(k);
    else if (typeof v === "boolean") continue;
    else if (typeof v === "string" && v !== "" && !isNaN(Number(v))) out.push(k);
    // dict/list → 跳过（per-class 单独处理）
  }
  return out;
}

/**
 * 按「指标键清单」生成全量 spec（指标名来自模型/任务实际产出，不硬编码）。
 */
export function buildMetricSpecFromKeys(keys: string[]): MetricSpecItem[] {
  const seen = new Set<string>();
  const out: MetricSpecItem[] = [];
  for (const k of keys) {
    if (!k || seen.has(k)) continue;
    seen.add(k);
    out.push({
      key: k,
      label: metricLabel(k),
      color: metricColor(k),
      icon: metricIcon(k),
    });
  }
  return out;
}

/**
 * 从 `metrics_log` 枚举「训练指标 / 评估指标」两组键。
 *
 * ⚠️ 性能：全量扫 5000 行 × Object.keys ≈ 6 万次属性枚举，且都发生在
 *    Vue 的 reactive proxy 上（比普通对象慢一个量级）。
 *    指标名集合在**一个训练任务内是稳定的**，所以只扫头部窗口 + 尾部窗口，
 *    不扫中间（同一个任务的行结构不会中途改变）。
 */
export function enumerateMetricsFromLog(log: any[]): { train: string[]; eval: string[] } {
  const train = new Set<string>();
  const ev = new Set<string>();
  const push = (m: any, target: Set<string>) => {
    if (m == null || typeof m !== "object") return;
    const kind = m._kind;
    for (const key in m) {
      if (NON_METRIC_KEYS.has(key)) continue;
      const v = m[key];
      if (typeof v !== "number") continue;
      // `_kind` 决定归属：step 行 → 训练指标；eval/best 行 → 评估指标。
      // 没有 `_kind` 的（YOLO/PaddleX 合并行）按键名判断。
      const isEval =
        kind === "eval" || kind === "best"
          ? true
          : kind === "step"
            ? false
            : RATIO_KEY_RE.test(key);
      (isEval ? ev : target).add(key);
    }
  };
  const HEAD = 200;
  const TAIL = 60;
  const from = Math.min(log.length, HEAD);
  for (let i = 0; i < from; i++) push(log[i], train);
  if (log.length > HEAD + TAIL) {
    for (let i = log.length - TAIL; i < log.length; i++) push(log[i], train);
  }
  return { train: [...train].sort(), eval: [...ev].sort() };
}

// 按 framework / mode 解析主指标：
// PaddleX det→HMean/Precision/Recall；PaddleX rec→Acc；
// YOLO 分类→Top1/Top5；其余（YOLO det/seg/obb/pose）→mAP@50/mAP@50:95/Precision/Recall
export function resolveMainMetricSpec(opts: {
  framework?: string | null;
  mode?: string | null;
  classify?: boolean;
}): MetricSpecItem[] {
  const framework = String(opts.framework || "").toLowerCase();
  const mode = String(opts.mode || "det").toLowerCase();
  if (framework === "paddlex") {
    return mode === "rec"
      ? [{ key: "acc", label: "Acc", color: "#409eff", icon: Aim }]
      : [
          { key: "hmean", label: "HMean", color: "#52c41a", icon: StarFilled },
          { key: "precision", label: "Precision", color: "#409eff", icon: Aim },
          { key: "recall", label: "Recall", color: "#fa8c16", icon: Search },
        ];
  }
  if (opts.classify) {
    return [
      { key: "top1", label: "Top1", color: "#52c41a", icon: Aim },
      { key: "top5", label: "Top5", color: "#409eff", icon: StarFilled },
    ];
  }
  return [
    { key: "map50", label: "mAP@50", color: "#fa8c16", icon: StarFilled },
    { key: "map5095", label: "mAP@50:95", color: "#9b59b6", icon: TrophyBase },
    { key: "precision", label: "Precision", color: "#52c41a", icon: Aim },
    { key: "recall", label: "Recall", color: "#409eff", icon: Search },
  ];
}
