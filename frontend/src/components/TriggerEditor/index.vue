<!-- 统一触发配置组件（全平台唯一入口）：选择触发类型 + 编辑该类型的参数 + 实时预览 -->
<!--
  预览的「人话描述」与「下次运行时间」一律来自后端统一层（`POST .../trigger/preview` → TriggerUtil），
  组件内**不自算**，否则会与调度器形成第二套口径。
-->
<template>
  <div class="trigger-editor">
    <el-radio-group :model-value="trigger" @change="handleTriggerChange">
      <el-radio-button v-for="item in TRIGGER_TYPES" :key="item.value" :value="item.value">
        {{ item.label }}
      </el-radio-button>
    </el-radio-group>

    <!--
      定时：标准 5 段 crontab（无秒、无 ?、无 L/W），选择器由 @vue-js-cron/element-plus 提供。
      format 传字符串 `crontab` 而不是 { inherit: "crontab" }：两者语义完全等价，但库的运行时
      props 把 format 声明成了 String，传对象会触发 Vue 的 prop 类型告警。
    -->
    <div v-if="trigger === 'cron'" class="trigger-editor__body">
      <CronElementPlus
        :model-value="cronExpr"
        format="crontab"
        locale="zh"
        @update:model-value="handleCronChange"
        @error="handleCronError"
      />
    </div>

    <!-- 间隔：周/天/时/分/秒；全 0 由后端判非法并给出可读原因（见下方预览区） -->
    <div v-else-if="trigger === 'interval'" class="trigger-editor__body">
      <el-row :gutter="12">
        <el-col v-for="field in INTERVAL_FIELDS" :key="field.key" :span="8">
          <div class="trigger-editor__interval-item">
            <span class="trigger-editor__interval-label">{{ field.label }}</span>
            <el-input-number
              :model-value="intervalArgs[field.key]"
              :min="0"
              :precision="0"
              step-strictly
              controls-position="right"
              @change="handleIntervalChange(field.key, $event)"
            />
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 单次：未来某一时刻执行一次（过去时间由后端判非法，并提示改用「立即」） -->
    <div v-else-if="trigger === 'date'" class="trigger-editor__body">
      <el-date-picker
        :model-value="dateValue"
        type="datetime"
        value-format="YYYY-MM-DD HH:mm:ss"
        placeholder="请选择执行时间"
        @update:model-value="handleDateChange"
      />
    </div>

    <!-- 立即：无参数，保存后由中心调度器触发一次 -->
    <div v-else-if="trigger === 'now'" class="trigger-editor__body">
      <el-text type="info">保存后立即执行一次</el-text>
    </div>

    <!--
      兜底：未知/遗留的 trigger（历史脏数据）不冒充「立即」外观——否则与预览区
      后端返回的「非法」原因自相矛盾；此处只如实说明，不显示误导文案。
    -->
    <div v-else class="trigger-editor__body">
      <el-text type="warning">未知触发类型：{{ trigger }}</el-text>
    </div>

    <!--
      预览区：固定两行（描述 / 下次运行）。非法时描述行替换为红色原因；
      非法输入的 describe 是「尽力而为」可能非空，故作为次要信息保留，不做「非法 ⇒ 描述为空」的假设。
    -->
    <div class="trigger-editor__preview">
      <div class="trigger-editor__preview-row">
        <span class="trigger-editor__preview-label">描述：</span>
        <el-text v-if="previewFailed" type="warning">预览暂不可用（网络或权限问题）</el-text>
        <template v-else-if="preview && !preview.valid">
          <el-text type="danger">{{ preview.reason }}</el-text>
          <el-text
            v-if="preview.describe"
            type="info"
            size="small"
            class="trigger-editor__preview-hint"
          >
            （{{ preview.describe }}）
          </el-text>
        </template>
        <el-text v-else>{{ preview?.describe || "—" }}</el-text>
      </div>
      <div class="trigger-editor__preview-row">
        <span class="trigger-editor__preview-label">下次运行：</span>
        <el-text>{{ preview?.next_run || "—" }}</el-text>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CronElementPlus } from "@vue-js-cron/element-plus";
import "@vue-js-cron/element-plus/dist/element-plus.css";
import { previewTrigger, type TriggerPreview } from "@/api/module_ai/workspace";

/** 触发类型选项：与后端 TriggerUtil.TRIGGERS（cron / interval / date / now）一一对应 */
const TRIGGER_TYPES = [
  { value: "cron", label: "定时" },
  { value: "interval", label: "间隔" },
  { value: "date", label: "单次" },
  { value: "now", label: "立即" },
] as const;

/** cron 空值规范化默认值：每天 09:00（与既有存量数据一致，不用「每分钟」） */
const DEFAULT_CRON = "0 9 * * *";

/** 间隔参数字段：顺序与后端 TriggerUtil._INTERVAL_FIELDS 一致 */
const INTERVAL_FIELDS = [
  { key: "weeks", label: "周" },
  { key: "days", label: "天" },
  { key: "hours", label: "时" },
  { key: "minutes", label: "分" },
  { key: "seconds", label: "秒" },
] as const;

type IntervalKey = (typeof INTERVAL_FIELDS)[number]["key"];

/** 间隔参数的「规范空值」：五项全 0（后端会判非法并给出可读原因，比静默塞个「每 1 小时」更诚实） */
const EMPTY_INTERVAL: Record<IntervalKey, number> = {
  weeks: 0,
  days: 0,
  hours: 0,
  minutes: 0,
  seconds: 0,
};

/** 预览防抖：输入停止 300ms 后再请求，避免每次按键都打后端 */
const PREVIEW_DEBOUNCE_MS = 300;

/**
 * 预览接口缺省地址：AI 工作台路由（四个入口的预览契约完全一致，均为 `POST .../trigger/preview`）。
 * 各业务页按自己模块的权限传 `previewUrl`，避免只有本模块权限的用户看到「预览暂不可用」。
 */
const DEFAULT_PREVIEW_URL = "/ai/workspace/trigger/preview";

/** 后端 date 参数允许省略秒（`YYYY-MM-DD HH:mm`），补齐秒后才能被日期选择器正确回显 */
const DATE_MINUTE_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/;

const props = withDefaults(
  defineProps<{
    /** 触发类型：cron / interval / date / now */
    trigger: string;
    /** 触发参数：cron 为 5 段表达式字符串，interval 为 JSON，date 为时间字符串，now 为 null */
    triggerArgs: unknown;
    /**
     * 预览接口地址：缺省为 AI 工作台路由（保持既有调用方零改动）。
     * 四个业务页应各传本模块的预览路由，使预览受本模块权限管辖：
     * - 工作台 `/ai/workspace/trigger/preview`（默认）
     * - 工作流 `/ai/workflows/trigger/preview`
     * - 训练 `/train/trigger/preview`
     * - 节点 `/task/cronjob/node/trigger/preview`
     */
    previewUrl?: string;
  }>(),
  { previewUrl: DEFAULT_PREVIEW_URL }
);

const emit = defineEmits<{
  (e: "update:trigger", value: string): void;
  (e: "update:triggerArgs", value: unknown): void;
  (e: "error", message: string): void;
}>();

/**
 * 交给 cron 选择器的表达式：非字符串或空串一律落到默认值，并去掉首尾空格。
 * 这样「选择器显示什么，父组件的 triggerArgs 就是什么」，不会出现显示与取值不一致。
 */
const cronExpr = computed<string>(() => {
  const args = props.triggerArgs;
  if (typeof args !== "string") return DEFAULT_CRON;
  return args.trim() || DEFAULT_CRON;
});

/** 把任意形态的间隔参数（对象 / JSON 字符串 / 脏数据）收敛为「五项皆非负整数」的视图模型 */
const parseInterval = (args: unknown): Record<IntervalKey, number> => {
  let source: Record<string, unknown> = {};
  if (typeof args === "string") {
    try {
      const parsed: unknown = JSON.parse(args);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        source = parsed as Record<string, unknown>;
      }
    } catch {
      // 非 JSON 字符串（如切换类型时误留的 cron 表达式）按全 0 处理，由后端给出可读原因
      source = {};
    }
  } else if (args && typeof args === "object" && !Array.isArray(args)) {
    source = args as Record<string, unknown>;
  }

  const result = { ...EMPTY_INTERVAL };
  for (const field of INTERVAL_FIELDS) {
    const raw = Number(source[field.key]);
    result[field.key] = Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 0;
  }
  return result;
};

const intervalArgs = computed<Record<IntervalKey, number>>(() => parseInterval(props.triggerArgs));

/** 交给日期选择器的时间字符串：补齐秒，保证后端允许的 `YYYY-MM-DD HH:mm` 也能正确回显 */
const dateValue = computed<string>(() => {
  const args = props.triggerArgs;
  if (typeof args !== "string") return "";
  const text = args.trim();
  return DATE_MINUTE_RE.test(text) ? `${text}:00` : text;
});

// ---------- 预览（描述与下次运行时间一律来自后端统一层，组件不自算） ----------

/** 预览结果：null 表示尚未取得（首屏 300ms 防抖窗口内） */
const preview = ref<TriggerPreview | null>(null);
/** 预览请求本身失败（网络 / 权限 / 服务异常）：与「配置非法」区分，不误报为非法 */
const previewFailed = ref(false);
/** 请求序号：只采纳最后一次请求的结果，避免慢响应覆盖新输入 */
let previewSeq = 0;
let previewTimer: ReturnType<typeof setTimeout> | undefined;

/** 预览请求体：cron 用规范化后的表达式，其余直接透传参数（与保存时提交的口径一致） */
const previewPayload = (): unknown => {
  return props.trigger === "cron" ? cronExpr.value : props.triggerArgs;
};

const runPreview = async () => {
  const seq = ++previewSeq;
  try {
    // 统一预览契约（valid/reason/describe/next_run）四个入口完全一致，故按 prop 的路由调用：
    // 缺省为 AI 工作台路由，各业务页传本模块路由，使预览受调用方模块的权限管辖。
    const res = await previewTrigger(
      {
        trigger: props.trigger,
        trigger_args: previewPayload(),
      },
      props.previewUrl
    );
    if (seq !== previewSeq) return;
    const data = res.data.data;
    preview.value = data;
    previewFailed.value = false;
    emit("error", data.valid ? "" : data.reason || "触发配置无效");
  } catch {
    if (seq !== previewSeq) return;
    // 预览不可用：不谎报「非法」（网络抖动不应挡住保存），保存时后端仍会再校验一次
    preview.value = null;
    previewFailed.value = true;
    emit("error", "");
  }
};

const schedulePreview = () => {
  // 输入一变就作废在途响应：否则「cron 非法 → 切到间隔（error 已清空）→ 旧响应回来」
  // 会把上一个类型的原因回灌到已切换的新类型上。
  previewSeq += 1;
  if (previewTimer !== undefined) clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    previewTimer = undefined;
    void runPreview();
  }, PREVIEW_DEBOUNCE_MS);
};

// 触发类型或参数变化都重新预览；deep 兼容父组件就地修改对象
watch([() => props.trigger, () => props.triggerArgs], schedulePreview, {
  deep: true,
  immediate: true,
});

onBeforeUnmount(() => {
  if (previewTimer !== undefined) clearTimeout(previewTimer);
  previewSeq += 1; // 卸载后不再采纳在途响应
});

// ---------- 各分支的参数编辑 ----------

/** 各触发类型的「规范空值」：切类型时用它重置参数，避免把上一类型的参数带过去 */
const defaultArgsOf = (trigger: string): unknown => {
  if (trigger === "cron") return DEFAULT_CRON;
  if (trigger === "interval") return { ...EMPTY_INTERVAL };
  if (trigger === "date") return "";
  return null;
};

/**
 * 切换触发类型：重置参数 + 立即清空错误提示。
 * cron 分支会被 `v-if` 卸载、不再有 `@error` 事件，不在这里清空会残留「非法表达式」提示。
 */
const handleTriggerChange = (value: string | number | boolean | undefined) => {
  if (typeof value !== "string" || value === props.trigger) return;
  // 立即作废在途预览响应：切换类型时旧类型的 reason 不得回灌到新类型
  previewSeq += 1;
  emit("update:trigger", value);
  emit("update:triggerArgs", defaultArgsOf(value));
  emit("error", "");
};

const handleCronChange = (value: string) => {
  emit("update:triggerArgs", value);
};

/** 上抛 cron 选择器的校验原因；空串表示已恢复正常，不作为错误上报 */
const handleCronError = (message: string) => {
  if (message) emit("error", message);
};

const handleIntervalChange = (key: IntervalKey, value: number | undefined) => {
  const next = { ...intervalArgs.value };
  next[key] =
    typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
  emit("update:triggerArgs", next);
};

const handleDateChange = (value: unknown) => {
  emit("update:triggerArgs", typeof value === "string" ? value : "");
};

// 把规范化后的 cron 表达式回写父组件；只在 cron 分支生效，避免覆盖其它类型的参数
watch(
  [() => props.trigger, cronExpr],
  () => {
    if (props.trigger !== "cron") return;
    if (cronExpr.value !== props.triggerArgs) emit("update:triggerArgs", cronExpr.value);
  },
  { immediate: true }
);
</script>

<style scoped lang="scss">
.trigger-editor {
  font-size: var(--el-font-size-base);
}

.trigger-editor__body {
  margin-top: 12px;
}

.trigger-editor__interval-item {
  display: flex;
  align-items: center;
}

.trigger-editor__interval-label {
  width: 24px;
  color: var(--el-text-color-regular);
}

.trigger-editor__preview {
  padding: 8px 12px;
  margin-top: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
}

.trigger-editor__preview-label {
  color: var(--el-text-color-secondary);
}

.trigger-editor__preview-hint {
  margin-left: 4px;
}
</style>
