<!-- 统一触发配置组件（全平台唯一入口）：选择触发类型 + 编辑该类型的参数 -->
<!-- 本文件当前只实现「定时（cron）」分支；间隔 / 单次 / 立即 三个分支由后续任务在本文件补齐 -->
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
  </div>
</template>

<script setup lang="ts">
import { CronElementPlus } from "@vue-js-cron/element-plus";
import "@vue-js-cron/element-plus/dist/element-plus.css";

/** 触发类型选项：与后端 TriggerUtil.TRIGGERS（cron / interval / date / now）一一对应 */
const TRIGGER_TYPES = [
  { value: "cron", label: "定时" },
  { value: "interval", label: "间隔" },
  { value: "date", label: "单次" },
  { value: "now", label: "立即" },
] as const;

/** cron 表达式的默认值：每分钟（与迁移前节点页 Quartz `* * * * ? *` 的语义一致） */
const DEFAULT_CRON = "* * * * *";

const props = defineProps<{
  /** 触发类型：cron / interval / date / now */
  trigger: string;
  /** 触发参数：cron 为 5 段表达式字符串，interval 为 JSON，date 为时间字符串，now 为 null */
  triggerArgs: unknown;
}>();

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

// 把规范化后的表达式回写父组件；只在 cron 分支生效，避免覆盖其它类型的参数
watch(
  [() => props.trigger, cronExpr],
  () => {
    if (props.trigger !== "cron") return;
    if (cronExpr.value !== props.triggerArgs) emit("update:triggerArgs", cronExpr.value);
  },
  { immediate: true }
);

/** 切换触发类型：只上抛类型本身，各类型参数的默认值由后续分支逻辑负责 */
const handleTriggerChange = (value: string | number | boolean | undefined) => {
  if (typeof value === "string" && value !== props.trigger) {
    emit("update:trigger", value);
  }
};

const handleCronChange = (value: string) => {
  emit("update:triggerArgs", value);
};

/** 上抛 cron 选择器的校验原因；空串表示已恢复正常，不作为错误上报 */
const handleCronError = (message: string) => {
  if (message) emit("error", message);
};
</script>

<style scoped lang="scss">
.trigger-editor__body {
  margin-top: 12px;
}
</style>
