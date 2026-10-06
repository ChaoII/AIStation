<!-- AI 工作台：Palantir Foundry 式支柱入口（数据资产 / 本体 / 数据与集成 / 无代码应用 / 治理 / 智能体） -->
<template>
  <div class="app-container ai-workspace-page">
    <PageHeader
      title="AI 工作台"
      subtitle="本体驱动 + AI Grounding + 治理的数据 / 决策平台 · 按 Foundry 支柱组织"
    />
    <el-row :gutter="16">
      <el-col v-if="loading" :span="24">
        <el-skeleton :rows="5" animated />
      </el-col>
      <el-col v-for="p in pillars" :key="p.route" :xs="24" :sm="12" :md="8">
        <el-card
          shadow="hover"
          class="pillar-card"
          :body-style="{ padding: '20px' }"
          @click="go(p.route)"
        >
          <div class="pillar-card__head">
            <div class="pillar-card__icon" :style="{ background: p.color }">
              <el-icon :size="22"><component :is="p.icon" /></el-icon>
            </div>
            <div>
              <div class="pillar-card__name">{{ p.name }}</div>
              <div class="pillar-card__tag">{{ p.en }}</div>
            </div>
          </div>
          <div class="pillar-card__desc">{{ p.desc }}</div>
          <div class="pillar-card__metrics">
            <el-tag
              v-for="m in p.metrics"
              :key="m"
              size="small"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ m }}
            </el-tag>
            <span v-if="!p.metrics.length" class="pillar-card__empty">—</span>
          </div>
          <el-button class="pillar-card__enter" type="primary" plain size="small" :icon="Right">
            进入
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  DataBoard,
  Files,
  Connection,
  Monitor,
  Odometer,
  User,
  Right,
} from "@element-plus/icons-vue";
import { getGovernanceOverview } from "@/api/module_ai/query";

const router = useRouter();
const g = ref<any>({ overview: {} });
const loading = ref(true);
const pillars = ref<any[]>([]);

async function load() {
  loading.value = true;
  try {
    const r = await getGovernanceOverview();
    g.value = { overview: r.data?.data || {} };
  } catch {
    g.value = { overview: {} };
  } finally {
    loading.value = false;
  }
  const o = g.value.overview || {};
  pillars.value = [
    {
      name: "数据资产",
      en: "Data Assets",
      icon: DataBoard,
      color: "var(--el-color-primary)",
      route: "/ai/asset",
      desc: "平台数据准备底座：资产目录 / 指标 / 术语 / 概念 / 图谱 / 语义抽取",
      metrics: [`${o.metrics ?? "-"} 指标`, `${o.terms ?? "-"} 术语`, `${o.concepts ?? "-"} 概念`],
    },
    {
      name: "本体",
      en: "Ontology",
      icon: Files,
      color: "var(--el-color-success)",
      route: "/ai/ontology",
      desc: "强类型本体：对象 / 属性 / Link / Action，创建对象不必先有表",
      metrics: [`${o.objects ?? "-"} 业务对象`],
    },
    {
      name: "数据与集成",
      en: "Data & Integration",
      icon: Connection,
      color: "var(--el-color-info)",
      route: "/ai/integration",
      desc: "数据连接 + 数据管道：从外部系统抽取、加工并接入本体",
      metrics: [`${o.datasources ?? "-"} 连接`, `${o.pipelines ?? "-"} 管道`],
    },
    {
      name: "无代码应用",
      en: "Workshop",
      icon: Monitor,
      color: "var(--el-color-warning)",
      route: "/ai/workshop",
      desc: "在业务对象上无代码构建看板 / 表单应用",
      metrics: [`${o.workshop_apps ?? "-"} 应用`],
    },
    {
      name: "治理",
      en: "Governance",
      icon: Odometer,
      color: "var(--el-color-danger)",
      route: "/ai/governance",
      desc: "治理驾驶舱 / ABAC 权限 / 数据质量 / 数据域隔离",
      metrics: [
        `健康分 ${o.dq?.avg_score ?? "-"}`,
        `${o.domains ?? "-"} 数据域`,
        `${o.access_rules ?? "-"} 策略`,
      ],
    },
    {
      name: "智能体",
      en: "AIP · Agent",
      icon: User,
      color: "var(--el-color-primary)",
      route: "/ai/agent",
      desc: "AIP Agent Studio：能力装配（问数 / 接地 / RAG / 工具 / 技能）",
      metrics: [`${o.agents ?? "-"} Agent`],
    },
  ];
}
function go(route: string) {
  router.push(route);
}
onMounted(load);
</script>

<style scoped lang="scss">
.ai-workspace-page {
  padding: 12px;
}
.pillar-card {
  margin-bottom: 16px;
  cursor: pointer;
  transition:
    transform 0.2s,
    box-shadow 0.2s;
}
.pillar-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(31, 45, 61, 0.1);
}
.pillar-card__head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pillar-card__icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.pillar-card__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.pillar-card__tag {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pillar-card__desc {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-top: 12px;
  min-height: 40px;
  line-height: 1.6;
}
.pillar-card__metrics {
  margin-top: 10px;
  min-height: 24px;
}
.pillar-card__enter {
  margin-top: 12px;
  width: 100%;
}
</style>
