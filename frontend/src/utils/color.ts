/**
 * 图谱分类上色工具：给任意分组键（本体/关系名等）一个**稳定**的颜色。
 *
 * 同 key 永远同色、不同 key 大概率不同色，供本体图谱按所属本体 / 关系类型上色，
 * 以及知识库图谱按实体类型上色时复用。
 */

/** 内置 12 色柔和调色板（与 Element Plus 色系协调） */
export const PALETTE = [
  "#4a86f7",
  "#5ac66b",
  "#f7a733",
  "#c86a8a",
  "#3f9ad6",
  "#e6b455",
  "#8a6ef5",
  "#f56c6c",
  "#2f9e8f",
  "#6bb8e8",
  "#d95f6e",
  "#7f8fa6",
];

/** 未分组 / 空 key 的中性色 */
export const NEUTRAL = "#a8abb3";

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h * 31 + str.charCodeAt(i)) >>> 0;
  }
  return h;
}

/** 让某类保留一个稳定的中性色（如「未分组」对象、未知关系） */
const NEUTRAL_KEYS = new Set(["", "未分组", "未分类", "unknown", "related"]);

/**
 * 返回 key 对应的稳定颜色。
 * @param key 分组键（所属本体编码、关系名等）
 * @param palette 可选调色板，默认 [[PALETTE]]
 */
export function stableColor(key: string, palette: string[] = PALETTE): string {
  const k = (key || "").trim();
  if (NEUTRAL_KEYS.has(k)) return NEUTRAL;
  return palette[hash(k) % palette.length];
}
