import request from "@/utils/request";

/** 场景参数 schema 项（对齐后端 SceneDef.param_schema，spec §4.6） */
export interface SceneParamSchema {
  /** 参数键，对应 PARAM_TO_LEAF 的 pkey */
  key: string;
  /** polygon | polyline | point | int | float | str | list | bool */
  type: string;
  /** 中文显示名 */
  label?: string;
  /** 默认值 */
  default?: unknown;
}

/** 场景（任务类型）定义，对齐后端 SceneDef */
export interface SceneDefinition {
  code: string;
  name: string;
  category: string;
  scene_type: string;
  model_families: string[];
  pipeline: Array<{ role: string; type: string }>;
  param_schema: SceneParamSchema[];
  default_rule: Record<string, unknown>;
  needs_tracking: boolean;
  description: string;
}

/** 叶子参数 schema 项（对齐后端 LEAF_CAPABILITIES.params） */
export interface LeafParamSchema {
  key: string;
  type: string;
  label?: string;
  default?: unknown;
}

/** 单个条件树叶子的能力描述 */
export interface LeafCapability {
  /** 叶子 subject，如 object_present */
  subject: string;
  /** 中文显示名 */
  label: string;
  /** 求值器是否已实现（false 时前端置灰、不可选） */
  implemented: boolean;
  params: LeafParamSchema[];
  ops: string[];
}

/** 规则能力接口载荷 */
export interface RuleCapabilities {
  logic: string[];
  leaves: LeafCapability[];
}

/** 查询场景（任务类型）目录 */
export function getSceneCatalog(params?: { category?: string }) {
  return request({ url: "/video/scene/catalog", method: "get", params });
}

/** 按场景码查询场景详情（含 param_schema / default_rule） */
export function getSceneDetail(code: string) {
  return request({ url: `/video/scene/catalog/${code}`, method: "get" });
}

/** 查询规则叶子能力（条件树据此渲染） */
export function getRuleCapabilities() {
  return request({ url: "/video/scene/rule-capabilities", method: "get" });
}
