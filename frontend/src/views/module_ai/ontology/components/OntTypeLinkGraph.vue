<!--
  对象类型的「关系类型」分区图（对齐 Palantir 对象类型 Overview 第 4 分区）
  当前对象类型居中，周围是与之关联的对象类型，连线是关系类型。
-->
<template>
  <div class="ont-linkgraph">
    <div class="ont-linkgraph__bar">
      <el-button-group size="small">
        <el-button
          :icon="ZoomIn"
          :title="i18nT('ai_ontology.zoomIn')"
          @click="graphRef?.zoom(1.25)"
        />
        <el-button
          :icon="ZoomOut"
          :title="i18nT('ai_ontology.zoomOut')"
          @click="graphRef?.zoom(0.8)"
        />
        <el-button
          :icon="FullScreen"
          :title="i18nT('ai_ontology.fitCanvas')"
          @click="graphRef?.fit()"
        />
      </el-button-group>
      <el-select v-model="layout" size="small" class="ont-linkgraph__layout">
        <el-option :label="i18nT('ai_ontology.concentricLayout')" value="concentric" />
        <el-option :label="i18nT('ai_ontology.forceDirected')" value="cose" />
        <el-option :label="i18nT('ai_ontology.ringLayout')" value="circle" />
        <el-option :label="i18nT('ai_ontology.treeLayout')" value="breadthfirst" />
        <el-option :label="i18nT('ai_ontology.gridLayout')" value="grid" />
      </el-select>
      <el-tag size="small" type="info" effect="plain">
        {{
          i18nT("ai_ontology.typeRelationCount", {
            typeCount: graph.nodes.length,
            relationCount: graph.edges.length,
          })
        }}
      </el-tag>
      <el-button size="small" type="primary" plain @click="emit('create')">
        {{ i18nT("ai_ontology.newRelationType") }}
      </el-button>
    </div>
    <GraphCanvas
      v-if="graph.edges.length || graph.nodes.length > 1"
      :key="layout"
      ref="graphRef"
      :nodes="graph.nodes"
      :edges="graph.edges"
      height="440px"
      :layout-name="layout"
      :max-zoom="1.7"
      :node-style="{
        sizeMode: 'fixed',
        fixedSize: 22,
        labelSize: 10,
        colorMode: 'category',
        shapeMode: 'uniform',
        uniformShape: 'round-rectangle',
      }"
      :edge-style="{ label: 'show', colorMode: 'category', arrow: 'triangle', opacity: 0.75 }"
      @node-tap="onNodeTap"
    />
    <el-empty
      v-else
      :image-size="60"
      :description="
        i18nT('ai_ontology.thisObjectTypeIsNotInAnyRelationRelationsComeFromDBForeignKeys')
      "
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { FullScreen, ZoomIn, ZoomOut } from "@element-plus/icons-vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string }>();
const emit = defineEmits<{
  (e: "node-tap", code: string): void;
  (e: "create"): void;
}>();

const { objects, linksOf, objectByCode } = useOntologyData();
const graphRef = ref<any>(null);
const layout = ref("cose");

const graph = computed(() => {
  const center = objectByCode(props.code);
  const rel = linksOf(props.code);
  const used = new Set<string>();
  const nameOf: Record<string, string> = {};

  const centerLabel = center?.name || props.code;
  used.add(centerLabel);
  nameOf[props.code] = centerLabel;

  // 邻居：所有与本类型有关系的另一端对象类型
  const neighborCodes = new Set<string>();
  rel.forEach((l: any) => {
    if (l.source_object !== props.code) neighborCodes.add(l.source_object);
    if (l.target_object !== props.code) neighborCodes.add(l.target_object);
  });

  const nodes = [
    {
      id: 0,
      name: centerLabel,
      etype: "center",
      weight: 3,
      category: (center?.domain_code || "")?.trim() || i18nT("ai_ontology.uncategorized"),
    },
    ...Array.from(neighborCodes).map((c: string) => {
      let label = objectByCode(c)?.name || c;
      if (used.has(label)) label = `${label}（${c}）`;
      used.add(label);
      nameOf[c] = label;
      const o = objectByCode(c);
      return {
        id: 0,
        name: label,
        etype: "neighbor",
        weight: 1,
        category: (o?.domain_code || "")?.trim() || i18nT("ai_ontology.uncategorized"),
      };
    }),
  ];

  const edges = rel
    .filter((l: any) => nameOf[l.source_object] && nameOf[l.target_object])
    .map((l: any) => ({
      source: nameOf[l.source_object],
      target: nameOf[l.target_object],
      rtype: l.name || "relation",
      weight: 1,
    }));

  return { nodes, edges };
});

function onNodeTap(name: string) {
  const label = String(name);
  const hit =
    objects.value.find((o: any) => (o.name || o.code) === label) ||
    objects.value.find((o: any) => label.startsWith(o.name || o.code));
  if (hit && hit.code !== props.code) emit("node-tap", hit.code);
}
</script>

<style scoped lang="scss">
.ont-linkgraph__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.ont-linkgraph__layout {
  width: 130px;
}
</style>
