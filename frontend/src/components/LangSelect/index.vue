<!-- 语言切换 -->
<template>
  <el-dropdown trigger="click" @command="handleLanguageChange">
    <div class="i-svg:language" :class="size" />
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in langOptions"
          :key="item.value"
          :disabled="appStore.language === item.value"
          :command="item.value"
        >
          {{ item.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { watch } from "vue";
import { useAppStore } from "@/store/modules/app.store";
import { LanguageEnum } from "@/enums/settings/locale.enum";

defineProps({
  size: {
    type: String,
    required: false,
  },
});

const RTL_LANGUAGES = ["ar"];

function applyDirection(lang: string) {
  document.documentElement.dir = RTL_LANGUAGES.includes(lang) ? "rtl" : "ltr";
}

const langOptions = [
  { label: "中文", value: LanguageEnum.ZH_CN },
  { label: "English", value: LanguageEnum.EN },
  { label: "繁體中文", value: LanguageEnum.ZH_HANT },
  { label: "日本語", value: LanguageEnum.JA },
  { label: "한국어", value: LanguageEnum.KO },
  { label: "Français", value: LanguageEnum.FR },
  { label: "Español", value: LanguageEnum.ES },
  { label: "Deutsch", value: LanguageEnum.DE },
  { label: "Русский", value: LanguageEnum.RU },
  { label: "Tiếng Việt", value: LanguageEnum.VI },
  { label: "ไทย", value: LanguageEnum.TH },
  { label: "العربية", value: LanguageEnum.AR },
];

const appStore = useAppStore();
const { locale, t } = useI18n();

/**
 * 处理语言切换
 *
 * @param lang  语言（zh-cn、en）
 */
function handleLanguageChange(lang: string) {
  locale.value = lang;
  appStore.changeLanguage(lang);
  applyDirection(lang);

  ElMessage.success(t("langSelect.message.success"));
}

// 初始化与切换时同步页面方向（阿拉伯语 RTL，其余 LTR）
watch(
  () => appStore.language,
  (val) => applyDirection(val),
  { immediate: true }
);
</script>
