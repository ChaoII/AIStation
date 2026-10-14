/**
 * 本体页共享数据层
 *
 * 采用「模块级单例」写法：所有 ref 定义在模块作用域，useOntologyData() 每次返回同一份状态。
 * 这样左导航、对象类型视图、关系类型视图等多个组件共享同一份数据，避免各自重复拉取。
 */
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  discardOntWip,
  getOntActions,
  getOntChangelog,
  getOntDomains,
  getOntFunctions,
  getOntLinks,
  getOntObjects,
  getOntVersions,
  getOntWip,
  stageOntChange,
} from "@/api/module_ai/ontology";

/* ---------------- 原始数据（模块级单例） ---------------- */
const domains = ref<any[]>([]);
const objects = ref<any[]>([]);
const links = ref<any[]>([]);
const actions = ref<any[]>([]);
const functions = ref<any[]>([]);
const versions = ref<any[]>([]);
const changelog = ref<any[]>([]);
const pendingVersions = ref<any[]>([]);
const ready = ref(false);
const loading = ref(false);

/** 当前作用域：undefined = 全部本体；字符串 = 指定本体编码 */
const currentDomain = ref<string | undefined>(undefined);

/* ---------------- 工作副本（模块级单例） ----------------
 * 放在这里的原因：任何子组件都可能暂存改动，若各自维护状态，
 * 父页面的「未保存」角标就不会刷新——用户改了东西却看不到提示。
 */
const wip = ref<{
  count: number;
  changes: any[];
  errors: string[];
  warnings: string[];
  destructive: any[];
}>({ count: 0, changes: [], errors: [], warnings: [], destructive: [] });

async function refreshWip() {
  try {
    const r = await getOntWip();
    const d = r.data?.data || {};
    wip.value = {
      count: d.count || 0,
      changes: d.changes || [],
      errors: d.errors || [],
      warnings: d.warnings || [],
      destructive: d.destructive || [],
    };
  } catch {
    wip.value = { count: 0, changes: [], errors: [], warnings: [], destructive: [] };
  }
}

/** 暂存一条改动（所有类型都走这里，保证角标与列表同步刷新） */
async function stage(
  kind: string,
  action: "create" | "update" | "delete" | "restore",
  data: Record<string, any>,
  msg = "已暂存（点右上角「保存」才生效）"
): Promise<boolean> {
  try {
    await stageOntChange({ kind, action, data });
    await reloadAll();
    await refreshWip();
    ElMessage.success(msg);
    return true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "暂存失败");
    return false;
  }
}

/** 丢弃全部改动 */
async function discardAllWip(): Promise<number> {
  const r = await discardOntWip();
  await reloadAll();
  await refreshWip();
  return r.data?.data?.discarded ?? 0;
}

/* ---------------- 加载 ---------------- */
async function reloadAll() {
  loading.value = true;
  try {
    const [dr, or_, lr, ar, fr, vr] = await Promise.all([
      getOntDomains(),
      getOntObjects(),
      getOntLinks(),
      getOntActions(),
      getOntFunctions(),
      getOntVersions(),
    ]);
    domains.value = dr.data?.data || [];
    objects.value = or_.data?.data || [];
    links.value = lr.data?.data || [];
    actions.value = ar.data?.data || [];
    functions.value = fr.data?.data || [];
    versions.value = vr.data?.data || [];
    const cr = await getOntChangelog("", 300);
    changelog.value = cr.data?.data || [];
    ready.value = true;
  } finally {
    loading.value = false;
  }
}

/* ---------------- 作用域过滤 ---------------- */
const currentDomainObj = computed(() =>
  currentDomain.value === undefined
    ? null
    : domains.value.find((d: any) => d.code === currentDomain.value) || null
);
const currentDomainName = computed(() =>
  currentDomain.value === undefined
    ? "全部本体"
    : currentDomainObj.value?.name || currentDomain.value
);

const scopedObjects = computed(() =>
  currentDomain.value === undefined
    ? objects.value
    : objects.value.filter((o: any) => (o.domain_code || "") === currentDomain.value)
);
const scopedCodes = computed(() => new Set(scopedObjects.value.map((o: any) => o.code)));
const scopedLinks = computed(() =>
  links.value.filter(
    (l: any) => scopedCodes.value.has(l.source_object) && scopedCodes.value.has(l.target_object)
  )
);
const scopedActions = computed(() =>
  actions.value.filter((a: any) => scopedCodes.value.has(a.object_code))
);
const scopedFunctions = computed(() =>
  functions.value.filter((f: any) => scopedCodes.value.has(f.object_code))
);
const scopedProperties = computed(() => {
  // 属性总量：按对象类型的 property_count 汇总（对象列表接口已带该字段）
  return scopedObjects.value.reduce((n: number, o: any) => n + (o.property_count || 0), 0);
});
const scopedVersions = computed(() =>
  versions.value.filter((v: any) => scopedCodes.value.has(v.object_code))
);

/* ---------------- 辅助查询 ---------------- */
function objectLabel(code: string) {
  return objects.value.find((o: any) => o.code === code)?.name || code;
}
function objectByCode(code: string) {
  return objects.value.find((o: any) => o.code === code) || null;
}
function functionCountOf(code: string) {
  return functions.value.filter((f: any) => f.object_code === code).length;
}
/** 某对象类型参与的关系（双向） */
function linksOf(code: string) {
  return links.value.filter((l: any) => l.source_object === code || l.target_object === code);
}
function actionsOf(code: string) {
  return actions.value.filter((a: any) => a.object_code === code);
}
function functionsOf(code: string) {
  return functions.value.filter((f: any) => f.object_code === code);
}

/* ---------------- 健康检查（P0：由既有字段派生，不做假数据） ---------------- */
const healthIssues = computed(() => {
  const out: any[] = [];
  scopedObjects.value.forEach((o: any) => {
    if (!o.key_prop) {
      out.push({ object_code: o.code, object_name: o.name, level: "error", msg: "缺少主键属性" });
    }
    if (!o.description) {
      out.push({
        object_code: o.code,
        object_name: o.name,
        level: "warning",
        msg: "对象类型缺少描述",
      });
    }
    if ((o.property_count || 0) === 0) {
      out.push({ object_code: o.code, object_name: o.name, level: "error", msg: "没有任何属性" });
    }
    if ((o.link_count || 0) === 0) {
      out.push({ object_code: o.code, object_name: o.name, level: "info", msg: "未参与任何关系" });
    }
    if (o.dq_score != null && o.dq_score < 60) {
      out.push({
        object_code: o.code,
        object_name: o.name,
        level: "warning",
        msg: `数据质量分偏低（${o.dq_score}）`,
      });
    }
  });
  return out;
});

export function useOntologyData() {
  return {
    // 原始数据
    domains,
    objects,
    links,
    actions,
    functions,
    versions,
    changelog,
    pendingVersions,
    ready,
    loading,
    // 作用域
    currentDomain,
    currentDomainObj,
    currentDomainName,
    scopedObjects,
    scopedLinks,
    scopedActions,
    scopedFunctions,
    scopedProperties,
    scopedVersions,
    wip,
    refreshWip,
    stage,
    discardAllWip,
    // 派生
    healthIssues,
    // 方法
    reloadAll,
    objectLabel,
    objectByCode,
    functionCountOf,
    linksOf,
    actionsOf,
    functionsOf,
  };
}
