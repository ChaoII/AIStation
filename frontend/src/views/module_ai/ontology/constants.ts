/**
 * 本体枚举常量（与后端 service.py 的 ONT_* 保持一致，取值对齐 Palantir 官方）
 */

export const ONT_STATUS = [
  { value: "active", label: "Active（正式）" },
  { value: "experimental", label: "Experimental（实验）" },
  { value: "deprecated", label: "Deprecated（已弃用）" },
];

export const ONT_VISIBILITY = [
  { value: "normal", label: "Normal（常规）" },
  { value: "prominent", label: "Prominent（优先展示）" },
  { value: "hidden", label: "Hidden（对用户隐藏）" },
];

export const ONT_INDEX_STATUS = [
  { value: "success", label: "Success（成功）" },
  { value: "failed", label: "Failed（失败）" },
  { value: "not_started", label: "Not started（未开始）" },
];

export const ONT_JOIN_METHOD = [
  { value: "foreign_key", label: "外键 Foreign key" },
  { value: "dataset", label: "连接表 Dataset" },
  { value: "object_type", label: "中间对象 Object type" },
];

export const ONT_CARDINALITY = [
  { value: "one_to_one", label: "一对一 one-to-one" },
  { value: "one_to_many", label: "一对多 one-to-many" },
  { value: "many_to_one", label: "多对一 many-to-one" },
  { value: "many_to_many", label: "多对多 many-to-many（必须用连接表）" },
];

/** 官方 base type（属性基类型）常用集合 */
export const ONT_BASE_TYPE = [
  { value: "string", label: "string（字符串）" },
  { value: "boolean", label: "boolean（布尔）" },
  { value: "byte", label: "byte" },
  { value: "short", label: "short" },
  { value: "integer", label: "integer（整数）" },
  { value: "long", label: "long（长整数）" },
  { value: "float", label: "float（单精度）" },
  { value: "double", label: "double（双精度）" },
  { value: "decimal", label: "decimal（定点小数）" },
  { value: "date", label: "date（日期）" },
  { value: "timestamp", label: "timestamp（时间戳）" },
  { value: "time", label: "time（时间）" },
  { value: "geohash", label: "geohash（地理哈希）" },
  { value: "geoshape", label: "geoshape（地理形状）" },
  { value: "attachment", label: "attachment（附件）" },
  { value: "media_reference", label: "media_reference（媒体引用）" },
];

export const ONT_RENDER_HINT = [
  { value: "", label: "无" },
  { value: "long-text", label: "长文本" },
  { value: "user", label: "用户" },
  { value: "group", label: "用户组" },
  { value: "resource", label: "资源" },
  { value: "color", label: "颜色" },
  { value: "date", label: "日期" },
  { value: "timestamp", label: "时间戳" },
];

/** 合法 base type 集合，供派生与校验使用 */
export const BASE_TYPE_VALUES = ONT_BASE_TYPE.map((x) => x.value);

/** P5：派生属性的 9 种聚合（与后端 ONT_AGGREGATIONS 一致） */
export const ONT_AGGREGATION = [
  { value: "count", label: "计数 count" },
  { value: "sum", label: "求和 sum" },
  { value: "avg", label: "平均 avg" },
  { value: "min", label: "最小 min" },
  { value: "max", label: "最大 max" },
  { value: "first", label: "第一条 first" },
  { value: "last", label: "最后一条 last" },
  { value: "collect_list", label: "收集为列表 collect_list" },
  { value: "collect_set", label: "收集去重集合 collect_set" },
];

/** P5：属性类型类别 */
export const ONT_TYPE_CLASS = [
  { value: "", label: "基础属性" },
  { value: "shared", label: "共享属性" },
  { value: "derived", label: "派生属性" },
  { value: "struct", label: "Struct" },
];

/** 由编码推导官方风格 API name（PascalCase），与后端 derive_api_name 同规则 */
export function deriveApiName(code: string): string {
  if (!code) return "";
  const parts = code.split(/[^0-9A-Za-z]+/).filter(Boolean);
  if (!parts.length) return "";
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("")
    .slice(0, 100);
}

/** 中文名不做复数变化，英文名追加 s */
export function derivePluralName(name: string): string {
  const n = (name || "").trim();
  if (!n) return "";
  if (/[\u4e00-\u9fff]/.test(n)) return n;
  return n.endsWith("s") ? n : `${n}s`;
}

/** 由 prop_type 推导 base type（与后端 derive_base_type 同规则） */
export function deriveBaseType(propType: string, code = ""): string {
  switch ((propType || "string").toLowerCase()) {
    case "number":
      return code.endsWith("_id") || code.endsWith("_count") || code === "id" ? "long" : "double";
    case "boolean":
      return "boolean";
    case "date":
    case "datetime":
    case "timestamp":
      return "timestamp";
    case "time":
      return "time";
    default:
      return "string";
  }
}

/** 标签查询 */
export function labelOf(list: { value: string; label: string }[], v: string) {
  return list.find((x) => x.value === v)?.label || v || "—";
}

/** 状态标签颜色 */
export function statusTagType(v: string) {
  return v === "active" ? "success" : v === "deprecated" ? "info" : "warning";
}

/** 可见性标签颜色（hidden 用 info，其余用默认色 → undefined） */
export function visibilityTagType(v: string) {
  return v === "hidden" ? ("info" as const) : undefined;
}

/** 索引状态标签颜色 */
export function indexTagType(v: string) {
  return v === "success"
    ? ("success" as const)
    : v === "failed"
      ? ("danger" as const)
      : ("info" as const);
}
