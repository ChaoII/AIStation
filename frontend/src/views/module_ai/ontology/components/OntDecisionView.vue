<!--
  决策（P3）——决策数据与决策谱系

  对齐官方 why-ontology：
  · 决策数据 = 上下文（依据）+ 评估过的不同选项 + 承诺选择的下游影响
  · 决策谱系 = 何时 / 基于哪个版本的企业数据 / 经由哪个应用
  · 智能体提出决策 → 人工拍板 → 执行 → 记录结果（下游决策再引用，形成谱系）
-->
<template>
  <div class="ont-dec">
    <!-- 统计 -->
    <el-row :gutter="12" class="ont-dec__stats">
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never"><el-statistic title="决策总数" :value="stats.total" /></el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never"><el-statistic title="待决" :value="stats.pending" /></el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never">
          <el-statistic title="已拍板率" :value="stats.decided_rate" suffix="%" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never">
          <el-statistic title="已执行率" :value="stats.executed_rate" suffix="%" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never">
          <el-statistic title="智能体提出" :value="stats.by_channel?.['智能体'] || 0" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="never">
          <el-statistic title="人工提出" :value="stats.by_channel?.['本体控制台'] || 0" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <div class="ont-sec__head">
        <span class="ont-sec__title">决策记录</span>
        <el-button class="ont-sec__op" type="primary" size="small" :icon="Plus" @click="openForm()">
          提出决策
        </el-button>
        <el-button size="small" :icon="Share" @click="openGraph">谱系图</el-button>
        <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      </div>

      <div class="ont-dec__filters">
        <el-select v-model="filter.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select
          v-model="filter.object_code"
          placeholder="对象类型"
          clearable
          filterable
          style="width: 180px"
        >
          <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
        </el-select>
        <el-select v-model="filter.channel" placeholder="来源" clearable style="width: 130px">
          <el-option
            v-for="(label, value) in CHANNEL_OPTIONS"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="标题 / 理由关键词"
          clearable
          style="width: 220px"
          @keyup.enter="load"
        />
        <el-button type="primary" size="small" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small" border max-height="560">
        <template #empty>
          <el-empty :image-size="60" description="还没有决策记录" />
        </template>
        <el-table-column label="决策" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.title }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="针对对象" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.object_code" class="ont-mono">
              {{ objectLabel(row.object_code) }}#{{ row.object_key }}
            </span>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="执行动作" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'ont-none': !row.action_code }">{{ row.action_code || "—" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="决策数据" width="180">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" class="ont-tag-gap">
              依据 {{ row.evidence_count }}
            </el-tag>
            <el-tag size="small" effect="plain" class="ont-tag-gap">
              选项 {{ row.option_count }}
            </el-tag>
            <el-tag size="small" effect="plain" class="ont-tag-gap">
              影响 {{ row.impact_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              :type="row.channel === 'agent' ? 'warning' : 'info'"
            >
              {{ row.channel_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="made_by" label="提出人" width="110" show-overflow-tooltip />
        <el-table-column label="数据版本" width="90" align="center">
          <template #default="{ row }">
            <span class="ont-mono">v{{ row.data_version }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="made_at" label="提出时间" width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'proposed'"
              link
              type="primary"
              size="small"
              @click="openDecide(row)"
            >
              拍板
            </el-button>
            <el-button
              v-if="row.status === 'approved'"
              link
              type="success"
              size="small"
              @click="doExecute(row)"
            >
              执行
            </el-button>
            <el-button link type="primary" size="small" @click="openLineage(row)">谱系</el-button>
            <el-button link type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="doRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" :title="detail?.title || '决策详情'" size="60%">
      <template v-if="detail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="编码">
            <span class="ont-mono">{{ detail.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusTagType(detail.status)" effect="plain">
              {{ detail.status_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="针对对象">
            <span v-if="detail.object_code" class="ont-mono">
              {{ objectLabel(detail.object_code) }}#{{ detail.object_key }}
            </span>
            <span v-else class="ont-none">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="执行动作">
            <span class="ont-mono">{{ detail.action_code || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="提出人 / 时间">
            {{ detail.made_by || "—" }} · {{ detail.made_at }}
          </el-descriptions-item>
          <el-descriptions-item label="拍板人 / 时间">
            <span v-if="detail.decided_by">{{ detail.decided_by }} · {{ detail.decided_at }}</span>
            <span v-else class="ont-none">尚未拍板</span>
          </el-descriptions-item>
          <el-descriptions-item label="基于数据版本">
            <el-tag size="small" effect="plain">v{{ detail.data_version }}</el-tag>
            <span class="ont-hint">决策作出时该对象类型已发布的版本</span>
          </el-descriptions-item>
          <el-descriptions-item label="来源应用">
            <el-tag size="small" effect="plain">{{ detail.channel_label }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="执行时间">
            <span v-if="detail.executed_at">{{ detail.executed_at }}</span>
            <span v-else class="ont-none">尚未执行</span>
          </el-descriptions-item>
          <el-descriptions-item label="执行留痕 ID">
            <span v-if="detail.execution_id" class="ont-mono">#{{ detail.execution_id }}</span>
            <span v-else class="ont-none">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="决策理由" :span="2">
            <div class="ont-dec__text">{{ detail.rationale || "—" }}</div>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.decision_note" label="拍板意见" :span="2">
            <div class="ont-dec__text">{{ detail.decision_note }}</div>
          </el-descriptions-item>
          <el-descriptions-item v-if="hasKeys(detail.expected_impact)" label="事前预期" :span="2">
            <pre class="ont-dec__json">{{ pretty(detail.expected_impact) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item v-if="hasKeys(detail.outcome)" label="事后结果" :span="2">
            <pre class="ont-dec__json">{{ pretty(detail.outcome) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item v-if="hasKeys(detail.params)" label="执行参数" :span="2">
            <pre class="ont-dec__json">{{ pretty(detail.params) }}</pre>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 评估过的选项 -->
        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">评估过的选项</span>
          <el-tag size="small" effect="plain">{{ detail.options.length }}</el-tag>
        </div>
        <el-table :data="detail.options" size="small" border>
          <template #empty>
            <el-empty :image-size="50" description="未记录备选方案" />
          </template>
          <el-table-column label="选项" min-width="170">
            <template #default="{ row }">
              <el-tag v-if="row.chosen" size="small" type="success" effect="dark">已采纳</el-tag>
              <span v-else>{{ row.label }}</span>
              <span v-if="row.chosen" class="ont-dec__chosen">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="评分" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.score !== null">{{ row.score }}</span>
              <span v-else class="ont-none">—</span>
            </template>
          </el-table-column>
          <el-table-column label="预计影响" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="hasKeys(row.projected_impact)" class="ont-mono">
                {{ compact(row.projected_impact) }}
              </span>
              <span v-else class="ont-none">—</span>
            </template>
          </el-table-column>
          <el-table-column label="落选原因" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span :class="{ 'ont-none': !row.reject_reason }">
                {{ row.reject_reason || "—" }}
              </span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 上下文依据 -->
        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">决策上下文（依据）</span>
          <el-tag size="small" effect="plain">{{ detail.evidence.length }}</el-tag>
        </div>
        <el-table :data="detail.evidence" size="small" border>
          <template #empty>
            <el-empty :image-size="50" description="未记录依据" />
          </template>
          <el-table-column prop="kind_label" label="种类" width="110" />
          <el-table-column prop="label" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="引用" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <el-button
                v-if="row.kind === 'decision' && row.ref"
                link
                type="primary"
                size="small"
                @click="openLineageByCode(row.ref)"
              >
                {{ row.ref }}
              </el-button>
              <span v-else class="ont-mono">{{ row.ref || "—" }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当时取值" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="hasKeys(row.value)" class="ont-mono">{{ compact(row.value) }}</span>
              <span v-else class="ont-none">—</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 下游影响 -->
        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">下游影响</span>
          <el-tag size="small" effect="plain">{{ detail.impacts.length }}</el-tag>
          <span class="ont-hint">执行后自动对比对象前后快照得出</span>
        </div>
        <el-table :data="detail.impacts" size="small" border>
          <template #empty>
            <el-empty :image-size="50" description="尚未执行或没有字段变化" />
          </template>
          <el-table-column prop="kind_label" label="种类" width="110" />
          <el-table-column prop="label" label="说明" min-width="200" show-overflow-tooltip />
          <el-table-column label="变化" min-width="280">
            <template #default="{ row }">
              <div class="ont-dec__diff">
                <span v-for="(v, k) in diffPairs(row)" :key="k" class="ont-mono">
                  {{ k }}: {{ v }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="自动" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.auto" size="small" type="info" effect="plain">自动</el-tag>
              <span v-else class="ont-none">手工</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="ont-dec__actions">
          <el-button v-if="detail.status === 'proposed'" type="primary" @click="openDecide(detail)">
            拍板
          </el-button>
          <el-button v-if="detail.status === 'approved'" type="success" @click="doExecute(detail)">
            执行决策
          </el-button>
          <el-button v-if="detail.status === 'executed'" @click="openOutcome(detail)">
            记录事后结果
          </el-button>
          <el-button @click="openLineage(detail)">查看谱系</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 提出/编辑决策 -->
    <el-dialog v-model="formVisible" title="提出决策" width="720px" append-to-body>
      <el-form :model="form" label-width="130px">
        <el-form-item label="决策标题" required>
          <el-input v-model="form.title" placeholder="一句话说清要决定什么" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="针对对象类型">
          <el-select v-model="form.object_code" filterable clearable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="对象主键">
          <el-input v-model="form.object_key" placeholder="目标实例的 key" />
        </el-form-item>
        <el-form-item label="执行动作">
          <el-select v-model="form.action_code" filterable clearable style="width: 100%">
            <el-option
              v-for="a in actions"
              :key="a.code"
              :label="`${a.name}（${a.code}）`"
              :value="a.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="执行参数（JSON）">
          <el-input v-model="form.paramsText" type="textarea" :rows="2" placeholder="{}" />
        </el-form-item>
        <el-form-item label="决策理由">
          <el-input
            v-model="form.rationale"
            type="textarea"
            :rows="3"
            placeholder="为什么这么决定？依据是什么？"
          />
        </el-form-item>
        <el-form-item label="评估过的选项">
          <el-input
            v-model="form.optionsText"
            type="textarea"
            :rows="6"
            placeholder='[{"code":"opt1","label":"方案A","chosen":true,"score":85},{"code":"opt2","label":"方案B","chosen":false,"reject_reason":"成本高"}]'
          />
          <div class="ont-hint">被否决的方案也要记录，这才是「评估过的不同选项」</div>
        </el-form-item>
        <el-form-item label="上下文依据">
          <el-input
            v-model="form.evidenceText"
            type="textarea"
            :rows="6"
            placeholder='[{"kind":"object","ref":"video_cameras:1","label":"摄像机实例"},{"kind":"decision","ref":"dec_xxx","label":"上次处置决策"}]'
          />
          <div class="ont-hint">
            kind 可为 object / property / link / function / metric / version / decision / external /
            manual。填
            <code>decision</code>
            并引用另一条决策编码即可形成决策谱系
          </div>
        </el-form-item>
        <el-form-item label="事前预期（JSON）">
          <el-input v-model="form.expectedText" type="textarea" :rows="2" placeholder="{}" />
        </el-form-item>
        <el-form-item label="来源应用">
          <el-radio-group v-model="form.channel">
            <el-radio-button v-for="(label, value) in CHANNEL_OPTIONS" :key="value" :value="value">
              {{ label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 拍板 -->
    <el-dialog v-model="decideVisible" title="拍板" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="`决策：${decideTarget?.title || ''}`"
      />
      <el-form label-width="90px">
        <el-form-item label="结论">
          <el-radio-group v-model="decideApprove">
            <el-radio-button :value="true">批准</el-radio-button>
            <el-radio-button :value="false">否决</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="意见">
          <el-input v-model="decideNote" type="textarea" :rows="3" placeholder="拍板理由（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decideVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doDecide">提交</el-button>
      </template>
    </el-dialog>

    <!-- 事后结果 -->
    <el-dialog v-model="outcomeVisible" title="记录事后结果" width="560px" append-to-body>
      <el-form label-width="110px">
        <el-form-item label="指标名">
          <el-input v-model="outcomeForm.metric" placeholder="如 downtime_minutes" />
        </el-form-item>
        <el-form-item label="事前预期">
          <el-input v-model="outcomeForm.expected" />
        </el-form-item>
        <el-form-item label="实际结果">
          <el-input v-model="outcomeForm.actual" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="outcomeForm.note" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="outcomeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doOutcome">保存</el-button>
      </template>
    </el-dialog>

    <!-- 谱系 -->
    <el-dialog v-model="lineageVisible" title="决策谱系" width="860px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="上游 = 这条决策依据了什么；下游 = 这条决策影响了什么、又引发了哪些后续决策"
      />
      <div v-if="lineage" class="ont-dec__lin-sum">
        <el-tag size="small" effect="plain">依据 {{ lineage.summary.evidence }}</el-tag>
        <el-tag size="small" effect="plain">影响 {{ lineage.summary.impacts }}</el-tag>
        <el-tag size="small" effect="plain">
          上游决策 {{ lineage.summary.upstream_decisions }}
        </el-tag>
        <el-tag size="small" effect="plain">
          下游决策 {{ lineage.summary.downstream_decisions }}
        </el-tag>
      </div>
      <div v-if="lineage" class="ont-dec__tree">
        <div
          v-for="(n, i) in flattenLineage(lineage.lineage)"
          :key="i"
          :style="{ paddingLeft: `${n.depth * 20}px` }"
          class="ont-dec__node"
        >
          <span class="ont-dec__arrow">
            {{ n.dir === "down" ? "↳" : n.dir === "up" ? "↰" : "●" }}
          </span>
          <el-tag size="small" :type="statusTagType(n.status)" effect="plain">
            {{ n.status_label }}
          </el-tag>
          <span class="ont-dec__node-title" @click="openLineageByCode(n.code)">{{ n.title }}</span>
          <span class="ont-none">{{ n.made_by }} · {{ n.made_at }} · v{{ n.data_version }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="lineageVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 谱系图 -->
    <el-dialog v-model="graphVisible" title="决策谱系图" width="900px" append-to-body>
      <GraphCanvas
        v-if="graphVisible && graph.nodes.length"
        :nodes="graph.nodes"
        :edges="graph.edges"
        height="520px"
        layout-name="force"
        @node-tap="onGraphNode"
      />
      <el-empty v-else :image-size="60" description="暂无可绘制的决策" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Share } from "@element-plus/icons-vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import {
  decideOntDecision,
  executeOntDecision,
  getOntDecision,
  getOntDecisionGraph,
  getOntDecisionLineage,
  getOntDecisionStats,
  getOntDecisions,
  recordOntDecisionOutcome,
  removeOntDecision,
  saveOntDecision,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const emit = defineEmits<{ (e: "refresh"): void }>();

const { objects, actions, objectLabel } = useOntologyData();

const STATUS_OPTIONS = [
  { value: "proposed", label: "待决" },
  { value: "approved", label: "已批准" },
  { value: "rejected", label: "已否决" },
  { value: "executed", label: "已执行" },
  { value: "superseded", label: "已被取代" },
  { value: "expired", label: "已过期" },
  { value: "withdrawn", label: "已撤回" },
];
const CHANNEL_OPTIONS: Record<string, string> = {
  ontology: "本体控制台",
  agent: "智能体",
  api: "外部接口",
  automation: "自动化",
  import: "导入",
};

function statusTagType(s: string) {
  return ({ proposed: "warning", approved: "primary", rejected: "danger", executed: "success" }[
    s
  ] || "info") as any;
}
function hasKeys(o: any) {
  return o && typeof o === "object" && Object.keys(o).length > 0;
}
function pretty(o: any) {
  return JSON.stringify(o, null, 2);
}
function compact(o: any) {
  const s = JSON.stringify(o);
  return s.length > 120 ? s.slice(0, 117) + "…" : s;
}
/** 影响行的前后对比（只展示真正变化的字段） */
function diffPairs(row: any): Record<string, string> {
  const out: Record<string, string> = {};
  const keys = new Set([...Object.keys(row.before || {}), ...Object.keys(row.after || {})]);
  keys.forEach((k) => {
    const b = row.before?.[k];
    const a = row.after?.[k];
    if (JSON.stringify(b) !== JSON.stringify(a)) out[k] = `${fmt(b)} → ${fmt(a)}`;
  });
  if (!Object.keys(out).length && row.note) out["说明"] = row.note;
  return out;
}
function fmt(v: any) {
  if (v === null || v === undefined) return "空";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return s.length > 40 ? s.slice(0, 37) + "…" : s;
}

/* ---------------- 列表与统计 ---------------- */
const loading = ref(false);
const rows = ref<any[]>([]);
const stats = ref<any>({ total: 0, pending: 0, decided_rate: 0, executed_rate: 0, by_channel: {} });
const filter = reactive({ status: "", object_code: "", channel: "", keyword: "" });

async function load() {
  loading.value = true;
  try {
    const [r, s] = await Promise.all([
      getOntDecisions({
        status: filter.status || "",
        object_code: filter.object_code || "",
        keyword: filter.keyword || "",
        limit: 300,
      }),
      getOntDecisionStats(),
    ]);
    let list: any[] = r.data?.data || [];
    // channel 过滤在前端做（后端列表接口没有这个参数）
    if (filter.channel) list = list.filter((d) => d.channel === filter.channel);
    rows.value = list;
    stats.value = s.data?.data || stats.value;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载决策失败");
  } finally {
    loading.value = false;
  }
}

/* ---------------- 详情 ---------------- */
const detailVisible = ref(false);
const detail = ref<any>(null);
async function openDetail(row: any) {
  const r = await getOntDecision(row.code);
  detail.value = r.data?.data || null;
  detailVisible.value = true;
}

/* ---------------- 表单 ---------------- */
const formVisible = ref(false);
const saving = ref(false);
const form = reactive<any>({
  id: null,
  code: "",
  title: "",
  description: "",
  object_code: "",
  object_key: "",
  action_code: "",
  paramsText: "",
  rationale: "",
  optionsText: "",
  evidenceText: "",
  expectedText: "",
  channel: "ontology",
  status: "proposed",
});

function parseJson(text: string, what: string, fallback: any) {
  const raw = (text || "").trim();
  if (!raw) return fallback;
  const v = JSON.parse(raw);
  return v;
}

function openForm(row?: any) {
  Object.assign(form, {
    id: null,
    code: "",
    title: "",
    description: "",
    object_code: "",
    object_key: "",
    action_code: "",
    paramsText: "",
    rationale: "",
    optionsText: "",
    evidenceText: "",
    expectedText: "",
    channel: "ontology",
    status: "proposed",
  });
  if (row) {
    Object.assign(form, {
      id: row.id,
      code: row.code,
      title: row.title,
      description: row.description,
      object_code: row.object_code,
      object_key: row.object_key,
      action_code: row.action_code,
      paramsText: hasKeys(row.params) ? pretty(row.params) : "",
      rationale: row.rationale,
      expectedText: hasKeys(row.expected_impact) ? pretty(row.expected_impact) : "",
      channel: row.channel,
      status: row.status,
    });
    // 选项与依据要单独取（列表里没有）
    getOntDecision(row.code).then((r) => {
      const d = r.data?.data;
      if (!d) return;
      form.optionsText = d.options?.length ? pretty(d.options) : "";
      form.evidenceText = d.evidence?.length
        ? pretty(
            d.evidence.map((e: any) => ({
              kind: e.kind,
              ref: e.ref,
              label: e.label,
              value: e.value,
            }))
          )
        : "";
    });
  }
  formVisible.value = true;
}

async function doSave() {
  if (!form.title?.trim()) return ElMessage.warning("请填决策标题");
  let params: any = {};
  let options: any[] = [];
  let evidence: any[] = [];
  let expected: any = {};
  try {
    params = parseJson(form.paramsText, "执行参数", {});
    options = parseJson(form.optionsText, "选项", []);
    evidence = parseJson(form.evidenceText, "依据", []);
    expected = parseJson(form.expectedText, "事前预期", {});
  } catch (e: any) {
    return ElMessage.error(`JSON 解析失败：${e.message}`);
  }
  saving.value = true;
  try {
    const r = await saveOntDecision({
      id: form.id,
      code: form.code,
      title: form.title,
      description: form.description,
      object_code: form.object_code,
      object_key: form.object_key,
      action_code: form.action_code,
      params,
      rationale: form.rationale,
      options,
      evidence,
      expected_impact: expected,
      channel: form.channel,
      status: form.status,
    });
    ElMessage.success(r.data?.msg || "已保存");
    formVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

/* ---------------- 拍板 / 执行 / 结果 / 删除 ---------------- */
const decideVisible = ref(false);
const decideTarget = ref<any>(null);
const decideApprove = ref(true);
const decideNote = ref("");
function openDecide(row: any) {
  decideTarget.value = row;
  decideApprove.value = true;
  decideNote.value = "";
  decideVisible.value = true;
}
async function doDecide() {
  if (!decideTarget.value) return;
  saving.value = true;
  try {
    const r = await decideOntDecision(
      decideTarget.value.code,
      decideApprove.value,
      decideNote.value
    );
    ElMessage.success(r.data?.msg || "已处理");
    decideVisible.value = false;
    detailVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  } finally {
    saving.value = false;
  }
}

async function doExecute(row: any) {
  await ElMessageBox.confirm(
    `将执行决策「${row.title}」${row.action_code ? `（动作 ${row.action_code}）` : ""}，` +
      "会真实写入目标对象的真实数据表，且不可自动撤销。确认执行？",
    "执行决策",
    { type: "warning", confirmButtonText: "执行", cancelButtonText: "取消" }
  );
  try {
    const r = await executeOntDecision(row.code, false);
    const d = r.data?.data || {};
    ElMessage.success(r.data?.msg || "已执行");
    if (d.changed && Object.keys(d.changed).length) {
      ElMessageBox.alert(
        Object.entries(d.changed)
          .map(([k, v]: any) => `${k}: ${fmt(v.before)} → ${fmt(v.after)}`)
          .join("<br/>"),
        "捕获到的下游影响",
        { dangerouslyUseHTMLString: true }
      );
    }
    detailVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "执行失败");
  }
}

const outcomeVisible = ref(false);
const outcomeForm = reactive({ metric: "", expected: "", actual: "", note: "" });
function openOutcome(row: any) {
  outcomeForm.metric = row.outcome?.metric || "";
  outcomeForm.expected = row.outcome?.expected ?? "";
  outcomeForm.actual = row.outcome?.actual ?? "";
  outcomeForm.note = row.outcome?.note || "";
  outcomeVisible.value = true;
}
async function doOutcome() {
  if (!detail.value) return;
  saving.value = true;
  try {
    await recordOntDecisionOutcome(detail.value.code, { ...outcomeForm });
    ElMessage.success("已记录事后结果");
    outcomeVisible.value = false;
    await openDetail(detail.value);
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    `将删除决策「${row.title}」及其 ${row.option_count} 个选项、${row.evidence_count} 条依据、` +
      `${row.impact_count} 条影响记录，且不可恢复。确认删除？`,
    "删除决策",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  try {
    const r = await removeOntDecision(row.code);
    ElMessage.success(r.data?.msg || "已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

/* ---------------- 谱系 ---------------- */
const lineageVisible = ref(false);
const lineage = ref<any>(null);
function flattenLineage(node: any, depth = 0, dir = "self", out: any[] = []) {
  if (!node) return out;
  out.push({ ...node, depth, dir });
  (node.upstream || []).forEach((u: any) => flattenLineage(u, depth + 1, "up", out));
  (node.downstream || []).forEach((d: any) => flattenLineage(d, depth + 1, "down", out));
  return out;
}
async function openLineage(row: any) {
  await openLineageByCode(row.code);
}
async function openLineageByCode(code: string) {
  try {
    const r = await getOntDecisionLineage(code, 4);
    lineage.value = r.data?.data || null;
    lineageVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "查询谱系失败");
  }
}

/* ---------------- 谱系图 ---------------- */
const graphVisible = ref(false);
const graph = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
async function openGraph() {
  try {
    const r = await getOntDecisionGraph({ limit: 80 });
    const d = r.data?.data || {};
    graph.value = { nodes: d.nodes || [], edges: d.edges || [] };
    graphVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载谱系图失败");
  }
}
function onGraphNode(name: string) {
  if (name?.startsWith("dec_")) openLineageByCode(name);
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-dec__stats {
  margin-bottom: 12px;
}

.ont-dec__stats :deep(.el-card__body) {
  padding: 12px;
}

.ont-dec__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.ont-dec__text {
  white-space: pre-wrap;
}

.ont-dec__json {
  padding: 8px;
  margin: 0;
  overflow: auto;
  font-size: var(--el-font-size-extra-small);
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.ont-dec__chosen {
  margin-left: 6px;
}

.ont-dec__diff {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ont-dec__actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.ont-dec__lin-sum {
  display: flex;
  gap: 8px;
  margin: 10px 0;
}

.ont-dec__tree {
  max-height: 420px;
  overflow: auto;
}

.ont-dec__node {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
}

.ont-dec__arrow {
  color: var(--el-text-color-secondary);
}

.ont-dec__node-title {
  color: var(--el-color-primary);
  cursor: pointer;
}
</style>
