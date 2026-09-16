import { Aim, Search, StarFilled, TrophyBase } from "@element-plus/icons-vue";
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
