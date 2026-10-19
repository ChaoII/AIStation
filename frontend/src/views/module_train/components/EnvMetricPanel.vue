<template>
  <!-- 单根 div：本组件经 router-view 的 <Transition mode="out-in"> 渲染，
       多根节点会让过渡卡死（整页白屏），见 AGENTS.md 的 Transition 陷阱 -->
  <div>
    <el-card v-if="rows.length" shadow="never" class="section-card">
      <template #header>
        <span class="card-title">环境指标</span>
      </template>

      <!-- 当前值：最新一条 env 行（GPU 每卡 / CPU / 内存 / 磁盘 / 网络） -->
      <el-row :gutter="12">
        <el-col v-for="item in currentItems" :key="item.key" :xs="12" :sm="8" :md="6">
          <div class="metric-item">
            <el-icon :size="22" :style="{ color: item.color, marginBottom: '4px' }">
              <component :is="item.icon" />
            </el-icon>
            <span class="metric-val" :style="{ color: item.color }">{{ item.value }}</span>
            <span class="metric-lbl">{{ item.label }}</span>
            <span v-if="item.sub" class="sub-epoch">{{ item.sub }}</span>
          </div>
        </el-col>
      </el-row>

      <!-- 趋势：每指标一张小图（与上方训练/评估指标同款 mini-chart-card 布局） -->
      <el-row :gutter="12" style="margin-top: 12px">
        <el-col v-for="s in seriesList" :key="s.key" :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="never" class="mini-chart-card">
            <div class="mini-head">
              <span class="mini-name" :style="{ color: s.color }">{{ s.label }}</span>
              <span class="mini-val">{{ s.latest }}</span>
            </div>
            <MetricMiniChart :points="s.points" :color="s.color" :height="132" x-label="秒" />
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Box, Connection, Cpu, DataLine, Odometer } from "@element-plus/icons-vue";
import { metricColor } from "@/utils/trainMetrics";
import MetricMiniChart from "./MetricMiniChart.vue";

/**
 * 简单模式环境指标面板（GPU / CPU / 内存 / 磁盘 / 网络）。
 *
 * 数据**由父组件（任务详情页）持有**，本组件是纯渲染：
 *   - 初载/重载走 `GET /train/task/{id}/env-metrics`（每行带 ts，epoch 秒）；
 *   - 实时追加走 SSE 的 env 行（父组件按 seq 去重、5000 行裁剪）；
 *   - x 轴 = `ts - 首行 ts`（相对秒），缺值点不画（MetricMiniChart 的
 *     connectNulls 会把相邻有效点连起来）。
 *
 * 样式全部复用 train-detail.css 全局类（section-card / metric-item /
 * mini-chart-card …）与 Element Plus 组件，不新增自定义字号/主题色。
 */
const props = defineProps<{
  /** env 行：`{_kind:"env", seq, ts(epoch秒), gpu:[{id,util,mem_allocated_mb,mem_total_mb,temp_c,power_w}], cpu, mem:{used_mb,total_mb}, disk:{read_mb_s,write_mb_s}, net:{rx_mb_s,tx_mb_s}}` */
  rows: any[];
}>();

/** 数值守卫：非 number / NaN → null */
function num(v: any): number | null {
  return typeof v === "number" && v === v ? v : null;
}

const latest = computed<any>(() => {
  const rows = props.rows;
  return rows.length ? rows[rows.length - 1] : null;
});

/* ---------------- 当前值（最新一条 env 行） ---------------- */

function fmtPct(v: any): string {
  const n = num(v);
  return n == null ? "—" : `${n.toFixed(0)}%`;
}
function fmtInt(v: any): string {
  const n = num(v);
  return n == null ? "—" : `${n.toFixed(0)}`;
}
function fmtRate(v: any): string {
  const n = num(v);
  return n == null ? "—" : n.toFixed(1);
}

interface CurrentItem {
  key: string;
  label: string;
  value: string;
  sub?: string;
  icon: any;
  color: string;
}

const currentItems = computed<CurrentItem[]>(() => {
  const r = latest.value;
  const items: CurrentItem[] = [];
  const gpus = Array.isArray(r?.gpu) ? r.gpu : [];
  if (gpus.length) {
    gpus.forEach((g: any, idx: number) => {
      const key = `gpu_${g?.id ?? idx}`;
      const alloc = num(g?.mem_allocated_mb);
      const total = num(g?.mem_total_mb);
      const mem =
        alloc != null
          ? `${(alloc / 1024).toFixed(1)} / ${total != null ? (total / 1024).toFixed(1) : "?"} GB`
          : "—";
      items.push({
        key,
        label: `GPU ${g?.id ?? idx}`,
        value: fmtPct(g?.util),
        sub: `${fmtInt(g?.temp_c)}°C · ${mem} · ${fmtInt(g?.power_w)} W`,
        icon: Cpu,
        color: metricColor(key),
      });
    });
  } else {
    items.push({
      key: "gpu_none",
      label: "GPU",
      value: "未检测到 GPU",
      icon: Cpu,
      color: metricColor("gpu_none"),
    });
  }
  items.push({
    key: "cpu",
    label: "CPU",
    value: fmtPct(r?.cpu),
    icon: Odometer,
    color: metricColor("env_cpu"),
  });
  const memUsed = num(r?.mem?.used_mb);
  const memTotal = num(r?.mem?.total_mb);
  items.push({
    key: "mem",
    label: "内存",
    value: memUsed != null && memTotal ? fmtPct((memUsed / memTotal) * 100) : "—",
    sub:
      memUsed != null && memTotal
        ? `${(memUsed / 1024).toFixed(1)} / ${(memTotal / 1024).toFixed(1)} GB`
        : undefined,
    icon: Box,
    color: metricColor("env_mem"),
  });
  items.push({
    key: "disk",
    label: "磁盘读 / 写",
    value: `${fmtRate(r?.disk?.read_mb_s)} / ${fmtRate(r?.disk?.write_mb_s)}`,
    sub: "MB/s",
    icon: DataLine,
    color: metricColor("env_disk_read"),
  });
  items.push({
    key: "net",
    label: "网络收 / 发",
    value: `${fmtRate(r?.net?.rx_mb_s)} / ${fmtRate(r?.net?.tx_mb_s)}`,
    sub: "MB/s",
    icon: Connection,
    color: metricColor("env_net_rx"),
  });
  return items;
});

/* ---------------- 趋势（每指标一张小图） ---------------- */

/** 小图只画最近 1500 点（env 约 5s 一条 ≈ 2h，图宽 256px 已远超像素列数）；
 *  x 仍以**首行** ts 为基准，窗口滑动不改变量纲 */
const CHART_TAIL = 1500;

interface SeriesDef {
  key: string;
  /** GPU 系列标签随卡号生成，其余固定 */
  label: (gpuId: number | string) => string;
  unit: string;
  div: number;
  pick: (r: any) => number | null;
}

const SERIES_DEFS: SeriesDef[] = [
  {
    key: "env_gpu_util",
    label: (i) => `GPU ${i} 利用率`,
    unit: "%",
    div: 1,
    pick: (r) => num(r?.gpu?.[0]?.util),
  },
  {
    key: "env_gpu_mem",
    label: (i) => `GPU ${i} 显存`,
    unit: " GB",
    div: 1024,
    pick: (r) => num(r?.gpu?.[0]?.mem_allocated_mb),
  },
  {
    key: "env_gpu_temp",
    label: (i) => `GPU ${i} 温度`,
    unit: "°C",
    div: 1,
    pick: (r) => num(r?.gpu?.[0]?.temp_c),
  },
  {
    key: "env_gpu_power",
    label: (i) => `GPU ${i} 功耗`,
    unit: " W",
    div: 1,
    pick: (r) => num(r?.gpu?.[0]?.power_w),
  },
  { key: "env_cpu", label: () => "CPU", unit: "%", div: 1, pick: (r) => num(r?.cpu) },
  {
    key: "env_mem",
    label: () => "内存",
    unit: " GB",
    div: 1024,
    pick: (r) => num(r?.mem?.used_mb),
  },
  {
    key: "env_disk_read",
    label: () => "磁盘读",
    unit: " MB/s",
    div: 1,
    pick: (r) => num(r?.disk?.read_mb_s),
  },
  {
    key: "env_disk_write",
    label: () => "磁盘写",
    unit: " MB/s",
    div: 1,
    pick: (r) => num(r?.disk?.write_mb_s),
  },
  {
    key: "env_net_rx",
    label: () => "网络收",
    unit: " MB/s",
    div: 1,
    pick: (r) => num(r?.net?.rx_mb_s),
  },
  {
    key: "env_net_tx",
    label: () => "网络发",
    unit: " MB/s",
    div: 1,
    pick: (r) => num(r?.net?.tx_mb_s),
  },
];

const seriesList = computed(() => {
  const rows = props.rows;
  const t0 = num(rows[0]?.ts) ?? 0;
  const from = Math.max(0, rows.length - CHART_TAIL);
  const gpuId = latest.value?.gpu?.[0]?.id ?? 0;
  return SERIES_DEFS.map((d) => {
    const pts: [number | null, number][] = [];
    let lastVal: number | null = null;
    for (let i = from; i < rows.length; i++) {
      const r = rows[i];
      const v = d.pick(r);
      if (v == null) continue; // 缺值不画点（connectNulls 会把前后点连起来）
      const x = num(r?.ts);
      const y = d.div === 1 ? v : v / d.div;
      pts.push([x == null ? null : x - t0, y]);
      lastVal = y;
    }
    return {
      key: d.key,
      label: d.label(gpuId),
      color: metricColor(d.key),
      points: pts,
      latest: lastVal == null ? "—" : `${lastVal.toFixed(1)}${d.unit}`,
    };
  });
});
</script>
