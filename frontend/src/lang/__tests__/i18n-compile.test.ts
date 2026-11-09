/**
 * i18n 消息编译守卫：用 vue-i18n **真实的编译器**逐条编译所有语言的所有消息。
 *
 * 为什么需要（2026-11-09 连续踩了三次，且都是「点开某个弹窗才炸」）：
 * - 文案里裸写 `{{变量}}` → `Not allowed nest placeholder`（提示词新建弹窗打不开）；
 * - 文案里 `abc@example.com` 的 `@` → `Invalid linked format`（本体「试校验」输入框消失）；
 * - 文案里 JSON 示例 `{"timeout": 15}` → `Invalid token in placeholder`（集成页页签报错）。
 *
 * 规则：要显示字面量花括号/竖线/@，写成 `{'{'}`、`{'}'}`、`{'|'}`、`{'@'}`。
 * 这条测试比正则扫描靠谱：编译不过的写法，这里一定会红。
 */
import { createI18n } from "vue-i18n";
import { describe, expect, it } from "vitest";

import ar from "@/lang/package/ar";
import de from "@/lang/package/de";
import en from "@/lang/package/en";
import es from "@/lang/package/es";
import fr from "@/lang/package/fr";
import ja from "@/lang/package/ja";
import ko from "@/lang/package/ko";
import ru from "@/lang/package/ru";
import th from "@/lang/package/th";
import vi from "@/lang/package/vi";
import zhCn from "@/lang/package/zh-cn";
import zhHant from "@/lang/package/zh-hant";

const LOCALES: Record<string, unknown> = {
  "zh-cn": zhCn,
  en,
  "zh-hant": zhHant,
  ja,
  ko,
  fr,
  es,
  de,
  ru,
  vi,
  th,
  ar,
};

function walk(obj: unknown, prefix = ""): [string, string][] {
  const out: [string, string][] = [];
  for (const [k, v] of Object.entries((obj || {}) as Record<string, unknown>)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out.push([key, v]);
    else if (v && typeof v === "object") out.push(...walk(v, key));
  }
  return out;
}

describe("i18n 消息编译", () => {
  it("所有语言的所有消息都能被 vue-i18n 编译", () => {
    const bad: string[] = [];
    for (const [locale, messages] of Object.entries(LOCALES)) {
      const i18n = createI18n({
        legacy: false,
        locale,
        messages: { [locale]: messages as Record<string, unknown> },
        missingWarn: false,
        fallbackWarn: false,
      });
      for (const [key, text] of walk(messages)) {
        try {
          i18n.global.t(key);
        } catch (e) {
          bad.push(`${locale} ${key} :: ${String((e as Error)?.message || e).slice(0, 90)} :: ${text.slice(0, 60)}`);
        }
      }
    }
    expect(bad, bad.slice(0, 20).join("\n")).toEqual([]);
  });
});
