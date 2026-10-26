/**
 * 办公室「任务播报」的纯数据层。
 *
 * 为什么单独抽出来：播报条要记「谁派给谁 / 谁回话 / 定时任务开始结束 / 断线」，
 * 这些逻辑全是数组操作，放在 4000 行的页面里没法测。这里只做纯函数，
 * 页面负责把事件喂进来、把列表渲染出去。
 */

/** 播报类型：派活 / 回话 / 工具 / 汇总 / 定时任务 / 连接 / 普通提示 */
export type CastKind = "delegate" | "reply" | "tool" | "summary" | "cron" | "conn" | "info";

export interface CastItem {
  /** 自增序号（列表 key，不参与业务） */
  id: number;
  /** HH:MM:SS */
  t: string;
  kind: CastKind;
  text: string;
  /** 失败/断线一类，需要红点提示 */
  bad?: boolean;
}

/** 只保留最近 30 条：页面常开几天也不会一直长 */
export const CAST_LIMIT = 30;

let seq = 0;

/** 造一条播报（时间取本地时区，和面板里的步骤时间一致） */
export function makeCast(
  kind: CastKind,
  text: string,
  opts: { bad?: boolean; at?: Date; max?: number } = {}
): CastItem {
  const at = opts.at || new Date();
  const max = opts.max || 120;
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  return {
    id: ++seq,
    t: at.toTimeString().slice(0, 8),
    kind,
    text: clean.length > max ? `${clean.slice(0, max)}…` : clean,
    ...(opts.bad ? { bad: true } : {}),
  };
}

/** 追加一条并按上限截断（返回新数组，方便 Vue 直接赋值触发渲染） */
export function pushCast(list: CastItem[], item: CastItem, limit = CAST_LIMIT): CastItem[] {
  const next = [...list, item];
  return next.length > limit ? next.slice(next.length - limit) : next;
}

/** 每种播报前面的小符号（纯文本，避免再引一套图标） */
export function castGlyph(kind: CastKind): string {
  switch (kind) {
    case "delegate":
      return "→";
    case "reply":
      return "←";
    case "tool":
      return "⚙";
    case "summary":
      return "✓";
    case "cron":
      return "⏰";
    case "conn":
      return "!";
    default:
      return "·";
  }
}

/** 有没有需要提醒的条目（断线 / 失败）：播报条折叠时靠它点红点 */
export function hasBad(list: CastItem[]): boolean {
  return list.some((x) => x.bad);
}

/** 派活/回话这种「A → B」的统一写法，省得各处拼字符串不一致 */
export function castHandoff(from: string, to: string, task?: string): string {
  const head = `${from || "组长"} 派给 ${to || "成员"}`;
  return task ? `${head}：${task}` : head;
}
