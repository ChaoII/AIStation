import { ref, type Ref } from "vue";

/**
 * 下拉选项的统一加载策略：
 * - `cachedOptions`：模块级短 TTL 缓存 + 并发去重，避免同一资源在多页/多次导航重复请求。
 * - `useLazyOptions`：把选项绑定到"首次真正需要时"再加载（打开弹窗、展开下拉）。
 */

const TTL = 30_000;
const cache = new Map<string, { data: any[]; at: number }>();
const inflight = new Map<string, Promise<any[]>>();

/** 带缓存与并发去重的选项加载。 */
export function cachedOptions<T = any>(key: string, loader: () => Promise<T[]>): Promise<T[]> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return Promise.resolve(hit.data as T[]);
  const pending = inflight.get(key);
  if (pending) return pending as Promise<T[]>;
  const p = loader()
    .then((data) => {
      cache.set(key, { data: data || [], at: Date.now() });
      inflight.delete(key);
      return data || [];
    })
    .catch((e) => {
      inflight.delete(key);
      throw e;
    });
  inflight.set(key, p);
  return p;
}

/** 清除指定缓存（数据变更后调用，例如新增/编辑下拉来源）。 */
export function invalidateOptions(key?: string) {
  if (key) cache.delete(key);
  else cache.clear();
}

export interface UseLazyOptions {
  options: Ref<any[]>;
  loading: Ref<boolean>;
  /** 首次调用才真正加载；重复调用为 no-op。 */
  ensure: () => Promise<void>;
  /** 直接赋初始值（例如来自父组件）。 */
  setOptions: (v: any[]) => void;
}

/**
 * 懒加载选项：`ensure()` 在打开弹窗/展开下拉时才触发，且只加载一次。
 * `loader` 通常为 `() => cachedOptions(key, fetchFn)`。
 */
export function useLazyOptions(loader: () => Promise<any[]> | any[]): UseLazyOptions {
  const options = ref<any[]>([]);
  const loading = ref(false);
  let loaded = false;

  async function ensure() {
    if (loaded || loading.value) return;
    loading.value = true;
    try {
      options.value = (await loader()) || [];
      loaded = true;
    } finally {
      loading.value = false;
    }
  }

  function setOptions(v: any[]) {
    options.value = v || [];
    loaded = true;
  }

  return { options, loading, ensure, setOptions };
}
