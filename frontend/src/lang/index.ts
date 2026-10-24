import type { App } from "vue";
import { createI18n } from "vue-i18n";
import { useAppStoreHook } from "@/store/modules/app.store";
// 本地语言包
import enLocale from "./package/en";
import zhCnLocale from "./package/zh-cn";
import zhHantLocale from "./package/zh-hant";
import jaLocale from "./package/ja";
import koLocale from "./package/ko";
import frLocale from "./package/fr";
import esLocale from "./package/es";
import deLocale from "./package/de";
import ruLocale from "./package/ru";
import viLocale from "./package/vi";
import thLocale from "./package/th";
import arLocale from "./package/ar";

const appStore = useAppStoreHook();

const messages = {
  "zh-cn": {
    ...zhCnLocale,
  },
  en: {
    ...enLocale,
  },
  "zh-hant": {
    ...zhHantLocale,
  },
  ja: {
    ...jaLocale,
  },
  ko: {
    ...koLocale,
  },
  fr: {
    ...frLocale,
  },
  es: {
    ...esLocale,
  },
  de: {
    ...deLocale,
  },
  ru: {
    ...ruLocale,
  },
  vi: {
    ...viLocale,
  },
  th: {
    ...thLocale,
  },
  ar: {
    ...arLocale,
  },
};

const i18n = createI18n({
  legacy: false,
  locale: appStore.language,
  fallbackLocale: "en",
  messages,
  globalInjection: true,
});

// 全局注册 i18n
export function setupI18n(app: App<Element>) {
  app.use(i18n);
}

export default i18n;
